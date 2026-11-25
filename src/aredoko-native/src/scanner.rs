use std::ffi::c_void;
use std::path::Path;

use windows_sys::Win32::Foundation::{
    GetLastError, ERROR_ACCESS_DENIED, ERROR_NO_MORE_FILES, INVALID_HANDLE_VALUE,
};
use windows_sys::Win32::Storage::FileSystem::{
    FindClose, FindFirstFileExW, FindNextFileW, FindExInfoBasic, FindExSearchNameMatch,
    FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_REPARSE_POINT, FIND_FIRST_EX_LARGE_FETCH,
    WIN32_FIND_DATAW,
};

use crate::plain_path::{
    check_plain_dir, check_plain_dir_node, child_wide, filetime_to_mtime_ns,
    get_full_path_wide, normalize_case_path_utf16, to_extended_wide_nul, wide_slice_to_string,
};
use crate::{
    clear_out, ffi_guard, vec_to_raw, write_err, ERR_ACCESS_DENIED, ERR_CANCELLED, ERR_CHANGED,
    ERR_INVALID_ARG, ERR_IO, ERR_LINK_REJECTED, ERR_NOT_PLAIN, ERR_PATH_MISSING, OK,
};

pub type CancelCb = Option<unsafe extern "C" fn(*mut c_void) -> i32>;

struct FindGuard(windows_sys::Win32::Foundation::HANDLE);
impl Drop for FindGuard {
    fn drop(&mut self) {
        unsafe {
            if !self.0.is_null() && self.0 != INVALID_HANDLE_VALUE {
                FindClose(self.0);
            }
        }
    }
}

fn casefold_chars(s: &str) -> Vec<char> {
    let mut out = Vec::with_capacity(s.len());
    for c in s.chars() {
        if c == 'ß' {
            out.push('s');
            out.push('s');
        } else {
            for lc in c.to_lowercase() {
                out.push(lc);
            }
        }
    }
    out
}

/// Exact match for Python `fnmatch.fnmatchcase` over already-casefolded char slices.
pub fn fnmatch_chars(name: &[char], pat: &[char]) -> bool {
    let (mut ni, mut pi) = (0usize, 0usize);
    let n = name.len();
    let m = pat.len();
    let mut star_pi: Option<usize> = None;
    let mut star_ni = 0usize;

    while ni < n {
        if pi < m {
            match pat[pi] {
                '*' => {
                    star_pi = Some(pi);
                    star_ni = ni;
                    pi += 1;
                    continue;
                }
                '?' => {
                    ni += 1;
                    pi += 1;
                    continue;
                }
                '[' => {
                    if let Some((matched, next_pi)) = match_bracket(name[ni], pat, pi) {
                        if matched {
                            ni += 1;
                            pi = next_pi;
                            continue;
                        }
                    } else if pat[pi] == name[ni] {
                        ni += 1;
                        pi += 1;
                        continue;
                    }
                }
                c if c == name[ni] => {
                    ni += 1;
                    pi += 1;
                    continue;
                }
                _ => {}
            }
        }
        if let Some(sp) = star_pi {
            pi = sp + 1;
            star_ni += 1;
            ni = star_ni;
        } else {
            return false;
        }
    }
    while pi < m && pat[pi] == '*' {
        pi += 1;
    }
    pi == m
}

fn match_bracket(ch: char, pat: &[char], start: usize) -> Option<(bool, usize)> {
    let m = pat.len();
    let mut j = start + 1;
    if j >= m {
        return None;
    }
    let negate = pat[j] == '!';
    if negate {
        j += 1;
    }
    if j < m && pat[j] == ']' {
        j += 1;
    }
    while j < m && pat[j] != ']' {
        j += 1;
    }
    if j >= m {
        return None;
    }
    let close_idx = j;
    let mut stuff = start + 1;
    if negate {
        stuff += 1;
    }
    let mut inside = false;
    let mut k = stuff;
    while k < close_idx {
        if k + 2 < close_idx && pat[k + 1] == '-' {
            let lo = pat[k];
            let hi = pat[k + 2];
            if lo <= ch && ch <= hi {
                inside = true;
            }
            k += 3;
        } else {
            if pat[k] == ch {
                inside = true;
            }
            k += 1;
        }
    }
    let ok = if negate { !inside } else { inside };
    Some((ok, close_idx + 1))
}

#[inline]
fn ext_kind(filename: &str) -> Option<u8> {
    let dot = filename.rfind('.')?;
    let ext = &filename[dot..];
    if ext.len() > 16 || !ext.is_ascii() {
        return None;
    }
    let mut lower = [0u8; 16];
    for (i, b) in ext.bytes().enumerate() {
        lower[i] = b.to_ascii_lowercase();
    }
    match &lower[..ext.len()] {
        b".cbz" | b".pdf" | b".epub" => Some(0), // book
        b".zip" => Some(1),                     // archive
        b".jpg" | b".jpeg" | b".png" | b".apng" | b".webp" | b".gif" | b".bmp" | b".tif"
        | b".tiff" | b".avif" | b".heic" | b".heif" => Some(2), // image
        b".mp4" | b".mkv" | b".webm" | b".avi" | b".mov" | b".wmv" | b".m4v" | b".ts" => Some(3), // video
        b".mp3" | b".flac" | b".wav" | b".ogg" | b".opus" | b".m4a" | b".aac" | b".wma" => Some(4), // audio
        b".psd" | b".clip" | b".kra" | b".ora" | b".blend" | b".svg" | b".ase" | b".aseprite" => {
            Some(5) // material
        }
        _ => None,
    }
}

fn parse_patterns(raw: &[u8]) -> Result<Vec<Vec<char>>, i32> {
    let mut pos = 0usize;
    let mut out = Vec::new();
    while pos < raw.len() {
        if raw.len() - pos < 4 {
            return Err(ERR_INVALID_ARG);
        }
        let len = u32::from_le_bytes(raw[pos..pos + 4].try_into().unwrap()) as usize;
        pos += 4;
        if raw.len() - pos < len {
            return Err(ERR_INVALID_ARG);
        }
        let s = std::str::from_utf8(&raw[pos..pos + len]).map_err(|_| ERR_INVALID_ARG)?;
        pos += len;
        out.push(casefold_chars(s));
    }
    Ok(out)
}

/// Binary pattern list: repeated `<len:u32_le><utf8>`.
/// Output format:
///   `<ignored_files:u32_le><skipped_links:u32_le>` followed by records:
///   type `1`: `<1u8><size:u64_le><mtime_ns:i64_le><kind:u8><rel_len:u32_le><rel_utf8>`
///   type `2`: `<2u8><dir_rel_len:u32_le><dir_rel_utf8><page_count:u32_le>`
///             followed by `page_count` x `<size:u64_le><mtime_ns:i64_le><name_len:u32_le><name_utf8>`
///   type `3`: `<3u8><is_dir:u8><rel_len:u32_le><rel_utf8>`
fn push_access_denied(buf: &mut Vec<u8>, is_dir: bool, rel: &str) {
    buf.push(3u8);
    buf.push(if is_dir { 1u8 } else { 0u8 });
    let rb = rel.as_bytes();
    buf.extend_from_slice(&(rb.len() as u32).to_le_bytes());
    buf.extend_from_slice(rb);
}
#[no_mangle]
pub unsafe extern "C" fn aredoko_scan_tree(
    root_ptr: *const u8,
    root_len: usize,
    db_ptr: *const u8,
    db_len: usize,
    patterns_ptr: *const u8,
    patterns_len: usize,
    recursive: u8,
    folder_books: u8,
    ctx: *mut c_void,
    cancel_cb: CancelCb,
    out_ptr: *mut *mut u8,
    out_len: *mut usize,
    out_err_ptr: *mut *mut u8,
    out_err_len: *mut usize,
) -> i32 {
    ffi_guard(|| {
        clear_out(out_ptr, out_len);
        clear_out(out_err_ptr, out_err_len);
        if root_ptr.is_null() || root_len == 0 || out_ptr.is_null() || out_len.is_null() {
            return ERR_INVALID_ARG;
        }
        if let Some(cb) = cancel_cb {
            if cb(ctx) != 0 {
                return ERR_CANCELLED;
            }
        }
        let root_str = match std::str::from_utf8(std::slice::from_raw_parts(root_ptr, root_len)) {
            Ok(s) => s,
            Err(_) => return ERR_INVALID_ARG,
        };
        let root_w = match check_plain_dir(root_str) {
            Ok(w) => w,
            Err(code) => {
                write_err(out_err_ptr, out_err_len, root_str);
                return code;
            }
        };

        let db_norm = if !db_ptr.is_null() && db_len > 0 {
            let db_str = match std::str::from_utf8(std::slice::from_raw_parts(db_ptr, db_len)) {
                Ok(s) => s,
                Err(_) => return ERR_INVALID_ARG,
            };
            match get_full_path_wide(db_str) {
                Ok(w) => Some(normalize_case_path_utf16(&w)),
                Err(_) => Some(Path::new(db_str).to_string_lossy().to_lowercase()),
            }
        } else {
            None
        };

        let pat_slice = if patterns_len > 0 {
            if patterns_ptr.is_null() {
                return ERR_INVALID_ARG;
            }
            std::slice::from_raw_parts(patterns_ptr, patterns_len)
        } else {
            &[]
        };
        let patterns = match parse_patterns(pat_slice) {
            Ok(p) => p,
            Err(code) => return code,
        };

        let is_excluded = |component: &str, partial: &str| -> bool {
            if patterns.is_empty() {
                return false;
            }
            let comp_cf = casefold_chars(component);
            let part_cf = casefold_chars(partial);
            patterns
                .iter()
                .any(|p| fnmatch_chars(&comp_cf, p) || fnmatch_chars(&part_cf, p))
        };

        let mut stack: Vec<(Vec<u16>, String)> = vec![(root_w, String::new())];
        let mut records_buf: Vec<u8> = Vec::with_capacity(128 * 1024);
        records_buf.extend_from_slice(&0u32.to_le_bytes()); // placeholder ignored_files
        records_buf.extend_from_slice(&0u32.to_le_bytes()); // placeholder skipped_links

        let mut ignored_files: u32 = 0;
        let mut skipped_links: u32 = 0;
        let mut cancel_tick: u32 = 0;

        while let Some((dir_w, rel_prefix)) = stack.pop() {
            if let Some(cb) = cancel_cb {
                if cb(ctx) != 0 {
                    return ERR_CANCELLED;
                }
            }
            if let Err(code) = check_plain_dir_node(&dir_w) {
                if code == ERR_ACCESS_DENIED && !rel_prefix.is_empty() {
                    push_access_denied(&mut records_buf, true, &rel_prefix);
                    continue;
                }
                let msg = String::from_utf16_lossy(&dir_w);
                write_err(out_err_ptr, out_err_len, &msg);
                return if code == ERR_LINK_REJECTED || code == ERR_NOT_PLAIN || code == ERR_PATH_MISSING {
                    ERR_CHANGED
                } else if code == ERR_ACCESS_DENIED {
                    ERR_IO
                } else {
                    code
                };
            }

            let pattern = to_extended_wide_nul(&child_wide(&dir_w, &[b'*' as u16]));
            let mut fd: WIN32_FIND_DATAW = std::mem::zeroed();
            let handle = FindFirstFileExW(
                pattern.as_ptr(),
                FindExInfoBasic,
                &mut fd as *mut WIN32_FIND_DATAW as *mut c_void,
                FindExSearchNameMatch,
                std::ptr::null(),
                FIND_FIRST_EX_LARGE_FETCH,
            );
            if handle == INVALID_HANDLE_VALUE || handle.is_null() {
                let err = GetLastError();
                if err == ERROR_NO_MORE_FILES {
                    continue;
                }
                if err == ERROR_ACCESS_DENIED && !rel_prefix.is_empty() {
                    push_access_denied(&mut records_buf, true, &rel_prefix);
                    continue;
                }
                let msg = String::from_utf16_lossy(&dir_w);
                write_err(out_err_ptr, out_err_len, &msg);
                return ERR_IO;
            }
            let _guard = FindGuard(handle);

            let mut pages: Vec<(String, u64, i64)> = Vec::new();
            loop {
                cancel_tick = cancel_tick.wrapping_add(1);
                if cancel_tick & 63 == 0 {
                    if let Some(cb) = cancel_cb {
                        if cb(ctx) != 0 {
                            return ERR_CANCELLED;
                        }
                    }
                }
                let name_end = fd
                    .cFileName
                    .iter()
                    .position(|&c| c == 0)
                    .unwrap_or(fd.cFileName.len());
                let name_w = &fd.cFileName[..name_end];
                let is_dot = name_w == [b'.' as u16] || name_w == [b'.' as u16, b'.' as u16];
                if !is_dot {
                    if (fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0 {
                        skipped_links = skipped_links.saturating_add(1);
                    } else {
                        let name = match wide_slice_to_string(name_w) {
                            Ok(s) => s,
                            Err(code) => return code,
                        };
                        let rel = if rel_prefix.is_empty() {
                            name.clone()
                        } else {
                            format!("{}/{}", rel_prefix, name)
                        };
                        if !is_excluded(&name, &rel) {
                            let abs_w = child_wide(&dir_w, name_w);
                            if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0 {
                                if recursive != 0 {
                                    stack.push((abs_w, rel));
                                }
                            } else {
                                let skip_db = match &db_norm {
                                    Some(dbn) => normalize_case_path_utf16(&abs_w) == *dbn,
                                    None => false,
                                };
                                if !skip_db {
                                    match ext_kind(&name) {
                                        None => {
                                            ignored_files = ignored_files.saturating_add(1);
                                        }
                                        Some(kind_id) => {
                                            let size = ((fd.nFileSizeHigh as u64) << 32)
                                                | (fd.nFileSizeLow as u64);
                                            let mtime_ns =
                                                filetime_to_mtime_ns(&fd.ftLastWriteTime);
                                            if folder_books != 0 && kind_id == 2 {
                                                pages.push((name, size, mtime_ns));
                                            } else {
                                                records_buf.push(1u8);
                                                records_buf.extend_from_slice(&size.to_le_bytes());
                                                records_buf
                                                    .extend_from_slice(&mtime_ns.to_le_bytes());
                                                records_buf.push(kind_id);
                                                let rb = rel.as_bytes();
                                                records_buf.extend_from_slice(
                                                    &(rb.len() as u32).to_le_bytes(),
                                                );
                                                records_buf.extend_from_slice(rb);
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                if FindNextFileW(handle, &mut fd) == 0 {
                    let err = GetLastError();
                    if err == ERROR_NO_MORE_FILES {
                        break;
                    }
                    if err == ERROR_ACCESS_DENIED && !rel_prefix.is_empty() {
                        push_access_denied(&mut records_buf, true, &rel_prefix);
                        break;
                    }
                    let msg = String::from_utf16_lossy(&dir_w);
                    write_err(out_err_ptr, out_err_len, &msg);
                    return ERR_IO;
                }
            }

            if !pages.is_empty() {
                if let Some(cb) = cancel_cb {
                    if cb(ctx) != 0 {
                        return ERR_CANCELLED;
                    }
                }
                let dir_rel = if rel_prefix.is_empty() {
                    "./".to_string()
                } else {
                    format!("{}/", rel_prefix)
                };
                records_buf.push(2u8);
                let db_b = dir_rel.as_bytes();
                records_buf.extend_from_slice(&(db_b.len() as u32).to_le_bytes());
                records_buf.extend_from_slice(db_b);
                records_buf.extend_from_slice(&(pages.len() as u32).to_le_bytes());
                for (name, size, mtime_ns) in &pages {
                    records_buf.extend_from_slice(&size.to_le_bytes());
                    records_buf.extend_from_slice(&mtime_ns.to_le_bytes());
                    let nb = name.as_bytes();
                    records_buf.extend_from_slice(&(nb.len() as u32).to_le_bytes());
                    records_buf.extend_from_slice(nb);
                }
            }
        }

        records_buf[0..4].copy_from_slice(&ignored_files.to_le_bytes());
        records_buf[4..8].copy_from_slice(&skipped_links.to_le_bytes());
        let (ptr, len) = vec_to_raw(records_buf);
        *out_ptr = ptr;
        *out_len = len;
        OK
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fnmatch_parity_cases() {
        let m = |n: &str, p: &str| fnmatch_chars(&casefold_chars(n), &casefold_chars(p));
        assert!(m(".git", ".git"));
        assert!(m("ThumbS.DB", "thumbs.db"));
        assert!(m("nested/unwanted.tmp", "*.tmp"));
        assert!(m("a/b/c.png", "a/*/c.png"));
        assert!(!m("a/b/c.jpg", "*.png"));
        assert!(m("page_01.png", "page_[0-9][0-9].png"));
        assert!(!m("page_a1.png", "page_[0-9][0-9].png"));
        assert!(m("page_a1.png", "page_[!0-9]?.png"));
    }

    #[test]
    fn extended_wide_nul_handles_short_long_unc_and_prefixed() {
        let to_u16 = |s: &str| s.encode_utf16().collect::<Vec<u16>>();
        let from_nul = |w: Vec<u16>| {
            assert_eq!(w.last().copied(), Some(0));
            String::from_utf16_lossy(&w[..w.len() - 1])
        };

        assert_eq!(from_nul(to_extended_wide_nul(&to_u16(r"D:\short\path"))), r"D:\short\path");

        let long_drive = format!(r"D:\{}", "a".repeat(250));
        assert_eq!(
            from_nul(to_extended_wide_nul(&to_u16(&long_drive))),
            format!(r"\\?\{}", long_drive)
        );

        let long_unc = format!(r"\\server\share\{}", "b".repeat(240));
        assert_eq!(
            from_nul(to_extended_wide_nul(&to_u16(&long_unc))),
            format!(r"\\?\UNC\server\share\{}", "b".repeat(240))
        );

        let already = format!(r"\\?\D:\{}", "c".repeat(250));
        assert_eq!(from_nul(to_extended_wide_nul(&to_u16(&already))), already);
    }
}
