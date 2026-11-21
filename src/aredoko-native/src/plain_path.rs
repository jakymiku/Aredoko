use std::path::Path;
use windows_sys::Win32::Foundation::{
    CloseHandle, GetLastError, ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND, FILETIME, HANDLE,
    INVALID_HANDLE_VALUE,
};
use windows_sys::Win32::Storage::FileSystem::{
    CreateFileW, GetFileAttributesW, GetFileInformationByHandle, GetFullPathNameW,
    BY_HANDLE_FILE_INFORMATION, FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_REPARSE_POINT,
    FILE_FLAG_OPEN_REPARSE_POINT, FILE_FLAG_SEQUENTIAL_SCAN, FILE_GENERIC_READ,
    FILE_READ_ATTRIBUTES, FILE_SHARE_DELETE, FILE_SHARE_READ, FILE_SHARE_WRITE,
    INVALID_FILE_ATTRIBUTES, OPEN_EXISTING,
};

use crate::{
    ERR_HARDLINK_REJECTED, ERR_INVALID_ARG, ERR_IO, ERR_LINK_REJECTED, ERR_NOT_PLAIN,
    ERR_PATH_MISSING,
};

pub struct WinHandle(pub HANDLE);

impl Drop for WinHandle {
    fn drop(&mut self) {
        unsafe {
            if !self.0.is_null() && self.0 != INVALID_HANDLE_VALUE {
                CloseHandle(self.0);
            }
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct FileIdentity {
    pub vol: u32,
    pub idx_hi: u32,
    pub idx_lo: u32,
    pub size_hi: u32,
    pub size_lo: u32,
    pub mtime_lo: u32,
    pub mtime_hi: u32,
    pub ctime_lo: u32,
    pub ctime_hi: u32,
    pub nlink: u32,
}

impl FileIdentity {
    pub fn from_info(info: &BY_HANDLE_FILE_INFORMATION) -> Self {
        Self {
            vol: info.dwVolumeSerialNumber,
            idx_hi: info.nFileIndexHigh,
            idx_lo: info.nFileIndexLow,
            size_hi: info.nFileSizeHigh,
            size_lo: info.nFileSizeLow,
            mtime_lo: info.ftLastWriteTime.dwLowDateTime,
            mtime_hi: info.ftLastWriteTime.dwHighDateTime,
            ctime_lo: info.ftCreationTime.dwLowDateTime,
            ctime_hi: info.ftCreationTime.dwHighDateTime,
            nlink: info.nNumberOfLinks,
        }
    }

    pub fn size_bytes(&self) -> u64 {
        ((self.size_hi as u64) << 32) | (self.size_lo as u64)
    }
}

#[inline]
pub fn filetime_to_mtime_ns(ft: &FILETIME) -> i64 {
    let ticks = ((ft.dwHighDateTime as u64) << 32) | (ft.dwLowDateTime as u64);
    let unix_ns = (ticks as i128 - 116_444_736_000_000_000i128) * 100i128;
    unix_ns as i64
}

pub fn to_wide_no_nul(s: &str) -> Result<Vec<u16>, i32> {
    if s.is_empty() || s.contains('\0') {
        return Err(ERR_INVALID_ARG);
    }
    Ok(s.encode_utf16().collect())
}

pub fn with_nul(w: &[u16]) -> Vec<u16> {
    let mut out = Vec::with_capacity(w.len() + 1);
    out.extend_from_slice(w);
    out.push(0);
    out
}

pub fn get_full_path_wide(raw: &str) -> Result<Vec<u16>, i32> {
    let mut input = to_wide_no_nul(raw)?;
    input.push(0);
    let needed = unsafe { GetFullPathNameW(input.as_ptr(), 0, std::ptr::null_mut(), std::ptr::null_mut()) };
    if needed == 0 {
        return Err(ERR_IO);
    }
    let mut buf = vec![0u16; needed as usize];
    let len = unsafe {
        GetFullPathNameW(
            input.as_ptr(),
            buf.len() as u32,
            buf.as_mut_ptr(),
            std::ptr::null_mut(),
        )
    };
    if len == 0 || (len as usize) >= buf.len() {
        return Err(ERR_IO);
    }
    buf.truncate(len as usize);
    let min_root = root_prefix_len(&buf);
    while buf.len() > min_root
        && (buf.last() == Some(&(b'\\' as u16)) || buf.last() == Some(&(b'/' as u16)))
    {
        buf.pop();
    }
    Ok(buf)
}

pub fn root_prefix_len(full_w: &[u16]) -> usize {
    // \\?\C:\ or \\?\UNC\server\share\
    if full_w.len() >= 7
        && full_w[0] == b'\\' as u16
        && full_w[1] == b'\\' as u16
        && full_w[2] == b'?' as u16
        && full_w[3] == b'\\' as u16
    {
        if full_w.len() >= 8 && full_w[5] == b':' as u16 && full_w[6] == b'\\' as u16 {
            return 7;
        }
        if full_w.len() >= 8
            && (full_w[4] == b'U' as u16 || full_w[4] == b'u' as u16)
            && (full_w[5] == b'N' as u16 || full_w[5] == b'n' as u16)
            && (full_w[6] == b'C' as u16 || full_w[6] == b'c' as u16)
            && full_w[7] == b'\\' as u16
        {
            return unc_root_len(full_w, 8);
        }
    }
    // C:\
    if full_w.len() >= 3 && full_w[1] == b':' as u16 && full_w[2] == b'\\' as u16 {
        return 3;
    }
    // \\server\share\
    if full_w.len() >= 2 && full_w[0] == b'\\' as u16 && full_w[1] == b'\\' as u16 {
        return unc_root_len(full_w, 2);
    }
    0
}

fn unc_root_len(full_w: &[u16], start: usize) -> usize {
    let mut seps = 0usize;
    for (idx, &ch) in full_w[start..].iter().enumerate() {
        if ch == b'\\' as u16 {
            seps += 1;
            if seps == 2 {
                return start + idx + 1;
            }
        }
    }
    full_w.len()
}

/// Validates every lexical ancestor (and optional file nlink==1) mirroring `storage_lease.plain_path`.
pub fn check_plain_full_wide(full_w: &[u16], expect_dir: bool) -> Result<(), i32> {
    if full_w.is_empty() {
        return Err(ERR_INVALID_ARG);
    }
    let min_root = root_prefix_len(full_w);
    let mut split_points: Vec<usize> = Vec::new();
    if min_root > 0 && min_root <= full_w.len() {
        split_points.push(min_root);
    }
    for idx in min_root..full_w.len() {
        if full_w[idx] == b'\\' as u16 {
            if split_points.last().copied() != Some(idx) {
                split_points.push(idx);
            }
        }
    }
    if split_points.last().copied() != Some(full_w.len()) {
        split_points.push(full_w.len());
    }

    let count = split_points.len();
    for (i, &end) in split_points.iter().enumerate() {
        let is_target = i + 1 == count;
        let is_folder = !is_target || expect_dir;
        let prefix = with_nul(&full_w[..end]);
        let attrs = unsafe { GetFileAttributesW(prefix.as_ptr()) };
        if attrs == INVALID_FILE_ATTRIBUTES {
            let err = unsafe { GetLastError() };
            if err == ERROR_FILE_NOT_FOUND || err == ERROR_PATH_NOT_FOUND {
                return Err(ERR_PATH_MISSING);
            }
            return Err(ERR_NOT_PLAIN);
        }
        if (attrs & FILE_ATTRIBUTE_REPARSE_POINT) != 0 {
            return Err(ERR_LINK_REJECTED);
        }
        let attr_is_dir = (attrs & FILE_ATTRIBUTE_DIRECTORY) != 0;
        if is_folder != attr_is_dir {
            return Err(ERR_NOT_PLAIN);
        }
        if !is_folder {
            let _ = check_file_handle_nlink(&prefix)?;
        }
    }
    Ok(())
}

pub fn check_plain_dir(raw: &str) -> Result<Vec<u16>, i32> {
    let full = get_full_path_wide(raw)?;
    check_plain_full_wide(&full, true)?;
    Ok(full)
}

pub fn open_for_meta(wide_nul: &[u16]) -> Result<FileIdentity, i32> {
    check_file_handle_nlink(wide_nul)
}

pub fn check_file_handle_nlink(wide_nul: &[u16]) -> Result<FileIdentity, i32> {
    let attrs = unsafe { GetFileAttributesW(wide_nul.as_ptr()) };
    if attrs == INVALID_FILE_ATTRIBUTES {
        let err = unsafe { GetLastError() };
        if err == ERROR_FILE_NOT_FOUND || err == ERROR_PATH_NOT_FOUND {
            return Err(ERR_PATH_MISSING);
        }
        return Err(ERR_NOT_PLAIN);
    }
    if (attrs & FILE_ATTRIBUTE_REPARSE_POINT) != 0 {
        return Err(ERR_LINK_REJECTED);
    }
    if (attrs & FILE_ATTRIBUTE_DIRECTORY) != 0 {
        return Err(ERR_NOT_PLAIN);
    }
    let handle = unsafe {
        CreateFileW(
            wide_nul.as_ptr(),
            FILE_READ_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            std::ptr::null(),
            OPEN_EXISTING,
            FILE_FLAG_OPEN_REPARSE_POINT,
            std::ptr::null_mut(),
        )
    };
    if handle == INVALID_HANDLE_VALUE || handle.is_null() {
        return Err(ERR_IO);
    }
    let _guard = WinHandle(handle);
    let mut info: BY_HANDLE_FILE_INFORMATION = unsafe { std::mem::zeroed() };
    let ok = unsafe { GetFileInformationByHandle(handle, &mut info) };
    if ok == 0 {
        return Err(ERR_IO);
    }
    if (info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0 {
        return Err(ERR_LINK_REJECTED);
    }
    if (info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0 {
        return Err(ERR_NOT_PLAIN);
    }
    if info.nNumberOfLinks != 1 {
        return Err(ERR_HARDLINK_REJECTED);
    }
    Ok(FileIdentity::from_info(&info))
}

pub fn open_plain_file_for_read(wide_nul: &[u16]) -> Result<(WinHandle, FileIdentity), i32> {
    let handle = unsafe {
        CreateFileW(
            wide_nul.as_ptr(),
            FILE_GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            std::ptr::null(),
            OPEN_EXISTING,
            FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_SEQUENTIAL_SCAN,
            std::ptr::null_mut(),
        )
    };
    if handle == INVALID_HANDLE_VALUE || handle.is_null() {
        let err = unsafe { GetLastError() };
        if err == ERROR_FILE_NOT_FOUND || err == ERROR_PATH_NOT_FOUND {
            return Err(ERR_PATH_MISSING);
        }
        return Err(ERR_IO);
    }
    let guard = WinHandle(handle);
    let mut info: BY_HANDLE_FILE_INFORMATION = unsafe { std::mem::zeroed() };
    let ok = unsafe { GetFileInformationByHandle(handle, &mut info) };
    if ok == 0 {
        return Err(ERR_IO);
    }
    if (info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0 {
        return Err(ERR_LINK_REJECTED);
    }
    if (info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0 {
        return Err(ERR_NOT_PLAIN);
    }
    if info.nNumberOfLinks != 1 {
        return Err(ERR_HARDLINK_REJECTED);
    }
    Ok((guard, FileIdentity::from_info(&info)))
}

/// Checks relative components from an already-validated directory `root_w` down to `rel_posix`.
pub fn check_rel_path_components(root_w: &[u16], rel_posix: &str) -> Result<Vec<u16>, i32> {
    if rel_posix.is_empty() || rel_posix.contains('\\') || rel_posix.contains('\0') {
        return Err(ERR_INVALID_ARG);
    }
    let mut buf = Vec::with_capacity(root_w.len() + rel_posix.len() + 4);
    buf.extend_from_slice(root_w);
    let parts: Vec<&str> = rel_posix.split('/').collect();
    for (idx, part) in parts.iter().enumerate() {
        if part.is_empty() || *part == "." || *part == ".." {
            return Err(ERR_INVALID_ARG);
        }
        if !buf.ends_with(&[b'\\' as u16]) {
            buf.push(b'\\' as u16);
        }
        buf.extend(part.encode_utf16());
        let is_file = idx + 1 == parts.len();
        buf.push(0);
        let attrs = unsafe { GetFileAttributesW(buf.as_ptr()) };
        buf.pop();
        if attrs == INVALID_FILE_ATTRIBUTES {
            let err = unsafe { GetLastError() };
            if err == ERROR_FILE_NOT_FOUND || err == ERROR_PATH_NOT_FOUND {
                return Err(ERR_PATH_MISSING);
            }
            return Err(ERR_NOT_PLAIN);
        }
        if (attrs & FILE_ATTRIBUTE_REPARSE_POINT) != 0 {
            return Err(ERR_LINK_REJECTED);
        }
        let attr_is_dir = (attrs & FILE_ATTRIBUTE_DIRECTORY) != 0;
        if is_file && attr_is_dir {
            return Err(ERR_NOT_PLAIN);
        }
        if !is_file && !attr_is_dir {
            return Err(ERR_NOT_PLAIN);
        }
    }
    buf.push(0);
    Ok(buf)
}

pub fn check_plain_dir_node(dir_w_no_nul: &[u16]) -> Result<(), i32> {
    let nul = with_nul(dir_w_no_nul);
    let attrs = unsafe { GetFileAttributesW(nul.as_ptr()) };
    if attrs == INVALID_FILE_ATTRIBUTES {
        let err = unsafe { GetLastError() };
        if err == ERROR_FILE_NOT_FOUND || err == ERROR_PATH_NOT_FOUND {
            return Err(ERR_PATH_MISSING);
        }
        return Err(ERR_IO);
    }
    if (attrs & FILE_ATTRIBUTE_REPARSE_POINT) != 0 {
        return Err(ERR_LINK_REJECTED);
    }
    if (attrs & FILE_ATTRIBUTE_DIRECTORY) == 0 {
        return Err(ERR_NOT_PLAIN);
    }
    Ok(())
}

pub fn normalize_case_path_utf16(w: &[u16]) -> String {
    // Match Windows case-insensitive path identity comparison cleanly.
    String::from_utf16_lossy(w).replace('/', "\\").to_lowercase()
}

pub fn wide_slice_to_string(slice: &[u16]) -> Result<String, i32> {
    let end = slice.iter().position(|&c| c == 0).unwrap_or(slice.len());
    String::from_utf16(&slice[..end]).map_err(|_| ERR_INVALID_ARG)
}

pub fn child_wide(dir_w: &[u16], child_w_no_nul: &[u16]) -> Vec<u16> {
    let mut out = Vec::with_capacity(dir_w.len() + 1 + child_w_no_nul.len());
    out.extend_from_slice(dir_w);
    if !out.ends_with(&[b'\\' as u16]) {
        out.push(b'\\' as u16);
    }
    out.extend_from_slice(child_w_no_nul);
    out
}

pub fn _unused_path_ref(_p: &Path) {}
