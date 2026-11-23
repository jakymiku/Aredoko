use std::ffi::c_void;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc};
use std::time::{Duration, Instant};

use rayon::ThreadPoolBuilder;
use rayon::prelude::*;
use sha2::{Digest, Sha256};
use windows_sys::Win32::Foundation::{GetLastError, ERROR_NO_MORE_FILES, INVALID_HANDLE_VALUE};
use windows_sys::Win32::Storage::FileSystem::{
    FindClose, FindFirstFileExW, FindNextFileW, FindExInfoBasic, FindExSearchNameMatch, ReadFile,
    FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_REPARSE_POINT, FIND_FIRST_EX_LARGE_FETCH,
    WIN32_FIND_DATAW,
};

use crate::plain_path::{
    check_file_handle_nlink, check_plain_dir, check_plain_dir_node, check_rel_path_components,
    child_wide, open_for_meta, open_plain_file_for_read, wide_slice_to_string, with_nul,
};
use crate::{
    clear_out, ffi_guard, vec_to_raw, write_err, ERR_CANCELLED, ERR_CHANGED, ERR_INVALID_ARG,
    ERR_IO, ERR_LINK_REJECTED, ERR_OBSERVER, OK,
};

pub type CancelCb = Option<unsafe extern "C" fn(*mut c_void) -> i32>;
pub type ProgressCb = Option<unsafe extern "C" fn(*mut c_void, u64, u64) -> i32>;

struct ManifestEntry<'a> {
    size: u64,
    sha256: [u8; 32],
    rel_path: &'a str,
}

enum VerifyMsg {
    Bytes(u64),
    FileDone,
    Failed(i32, String),
    AllDone,
}

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

fn parse_manifest(raw: &[u8]) -> Result<Vec<ManifestEntry<'_>>, i32> {
    let mut pos = 0usize;
    let mut out = Vec::new();
    while pos < raw.len() {
        if raw.len() - pos < 8 + 32 + 4 {
            return Err(ERR_INVALID_ARG);
        }
        let size = u64::from_le_bytes(raw[pos..pos + 8].try_into().unwrap());
        pos += 8;
        let mut sha = [0u8; 32];
        sha.copy_from_slice(&raw[pos..pos + 32]);
        pos += 32;
        let path_len = u32::from_le_bytes(raw[pos..pos + 4].try_into().unwrap()) as usize;
        pos += 4;
        if path_len == 0 || path_len > 2048 || raw.len() - pos < path_len {
            return Err(ERR_INVALID_ARG);
        }
        let rel = std::str::from_utf8(&raw[pos..pos + path_len]).map_err(|_| ERR_INVALID_ARG)?;
        pos += path_len;
        out.push(ManifestEntry {
            size,
            sha256: sha,
            rel_path: rel,
        });
    }
    Ok(out)
}

fn hash_single_entry(
    root_w: &[u16],
    entry: &ManifestEntry<'_>,
    buf: &mut [u8],
    stop: &AtomicBool,
    tx: &mpsc::Sender<VerifyMsg>,
) -> Result<(), (i32, String)> {
    if stop.load(Ordering::Relaxed) {
        return Err((ERR_CANCELLED, String::new()));
    }
    let path_nul = check_rel_path_components(root_w, entry.rel_path)
        .map_err(|code| (code, entry.rel_path.to_string()))?;
    let (file_handle, before_id) = open_plain_file_for_read(&path_nul)
        .map_err(|code| (code, entry.rel_path.to_string()))?;
    if before_id.size_bytes() != entry.size {
        return Err((ERR_CHANGED, entry.rel_path.to_string()));
    }
    let mut hasher = Sha256::new();
    loop {
        if stop.load(Ordering::Relaxed) {
            return Err((ERR_CANCELLED, String::new()));
        }
        let mut bytes_read: u32 = 0;
        let ok = unsafe {
            ReadFile(
                file_handle.0,
                buf.as_mut_ptr(),
                buf.len() as u32,
                &mut bytes_read,
                std::ptr::null_mut(),
            )
        };
        if ok == 0 {
            return Err((ERR_IO, entry.rel_path.to_string()));
        }
        if bytes_read == 0 {
            break;
        }
        hasher.update(&buf[..bytes_read as usize]);
        let _ = tx.send(VerifyMsg::Bytes(bytes_read as u64));
    }
    drop(file_handle);
    if stop.load(Ordering::Relaxed) {
        return Err((ERR_CANCELLED, String::new()));
    }
    let _ = check_rel_path_components(root_w, entry.rel_path)
        .map_err(|code| (code, entry.rel_path.to_string()))?;
    let after_id = open_for_meta(&path_nul)
        .map_err(|code| (code, entry.rel_path.to_string()))?;
    if before_id != after_id {
        return Err((ERR_CHANGED, entry.rel_path.to_string()));
    }
    let actual: [u8; 32] = hasher.finalize().into();
    if actual != entry.sha256 {
        return Err((ERR_CHANGED, entry.rel_path.to_string()));
    }
    let _ = tx.send(VerifyMsg::FileDone);
    Ok(())
}

/// Manifest binary format: repeated `<size:u64_le><sha256:32bytes><path_len:u32_le><rel_posix_utf8>`.
/// Every `cancel_cb` and `progress_cb` invocation stays strictly on the calling (owner) thread.
#[no_mangle]
pub unsafe extern "C" fn aredoko_verify_manifest(
    root_ptr: *const u8,
    root_len: usize,
    manifest_ptr: *const u8,
    manifest_len: usize,
    workers: u32,
    ctx: *mut c_void,
    cancel_cb: CancelCb,
    progress_cb: ProgressCb,
    out_err_ptr: *mut *mut u8,
    out_err_len: *mut usize,
) -> i32 {
    ffi_guard(|| {
        clear_out(out_err_ptr, out_err_len);
        if root_ptr.is_null() || root_len == 0 || (manifest_len > 0 && manifest_ptr.is_null()) {
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
        let manifest_slice = if manifest_len == 0 {
            &[]
        } else {
            std::slice::from_raw_parts(manifest_ptr, manifest_len)
        };
        let entries = match parse_manifest(manifest_slice) {
            Ok(e) => e,
            Err(code) => return code,
        };
        let root_w = match check_plain_dir(root_str) {
            Ok(w) => w,
            Err(code) => return code,
        };
        if let Some(cb) = progress_cb {
            if cb(ctx, 0, 0) != 0 {
                return ERR_OBSERVER;
            }
        }
        if entries.is_empty() {
            return OK;
        }

        // Convert entries to owned data for 'static thread scope, keeping everything bounded cleanly.
        let owned_entries: Vec<(u64, [u8; 32], String)> = entries
            .into_iter()
            .map(|e| (e.size, e.sha256, e.rel_path.to_string()))
            .collect();
        let num_workers = if workers == 0 {
            std::thread::available_parallelism()
                .map(|n| n.get().clamp(1, 8))
                .unwrap_or(4)
        } else {
            (workers as usize).clamp(1, 8)
        };

        let stop = Arc::new(AtomicBool::new(false));
        let (tx, rx) = mpsc::channel::<VerifyMsg>();
        let coord_stop = Arc::clone(&stop);
        let coord_root = root_w.clone();

        let coord = std::thread::spawn(move || {
            let pool = match ThreadPoolBuilder::new().num_threads(num_workers).build() {
                Ok(p) => p,
                Err(_) => {
                    coord_stop.store(true, Ordering::SeqCst);
                    let _ = tx.send(VerifyMsg::Failed(ERR_IO, String::new()));
                    return;
                }
            };
            pool.install(|| {
                owned_entries
                    .par_iter()
                    .for_each_init(
                        || vec![0u8; 1024 * 1024],
                        |buf, (size, sha, rel)| {
                            if coord_stop.load(Ordering::Relaxed) {
                                return;
                            }
                            let entry = ManifestEntry {
                                size: *size,
                                sha256: *sha,
                                rel_path: rel.as_str(),
                            };
                            if let Err((code, msg)) =
                                hash_single_entry(&coord_root, &entry, buf, &coord_stop, &tx)
                            {
                                coord_stop.store(true, Ordering::SeqCst);
                                if code != ERR_CANCELLED {
                                    let _ = tx.send(VerifyMsg::Failed(code, msg));
                                }
                            }
                        },
                    );
            });
            drop(pool);
            let _ = tx.send(VerifyMsg::AllDone);
        });

        let mut files_done: u64 = 0;
        let mut bytes_done: u64 = 0;
        let mut final_res: Result<(), (i32, String)> = Ok(());
        let mut finished = false;
        let mut last_progress = Instant::now();

        while !finished {
            if let Some(cb) = cancel_cb {
                if cb(ctx) != 0 {
                    stop.store(true, Ordering::SeqCst);
                    final_res = Err((ERR_CANCELLED, String::new()));
                    break;
                }
            }
            let first = rx.recv_timeout(Duration::from_millis(15));
            let mut changed = false;
            let mut handle_msg = |msg: VerifyMsg| -> bool {
                match msg {
                    VerifyMsg::Bytes(n) => {
                        bytes_done += n;
                        changed = true;
                        false
                    }
                    VerifyMsg::FileDone => {
                        files_done += 1;
                        changed = true;
                        false
                    }
                    VerifyMsg::Failed(code, msg_str) => {
                        stop.store(true, Ordering::SeqCst);
                        if final_res.is_ok() {
                            final_res = Err((code, msg_str));
                        }
                        true
                    }
                    VerifyMsg::AllDone => true,
                }
            };
            if let Ok(m) = first {
                if handle_msg(m) {
                    finished = true;
                }
                let mut drained = 0usize;
                while !finished && drained < 512 {
                    match rx.try_recv() {
                        Ok(m2) => {
                            if handle_msg(m2) {
                                finished = true;
                            }
                            drained += 1;
                        }
                        Err(_) => break,
                    }
                }
            }
            if final_res.is_ok()
                && changed
                && (finished || last_progress.elapsed() >= Duration::from_millis(20))
            {
                if let Some(cb) = progress_cb {
                    if cb(ctx, files_done, bytes_done) != 0 {
                        stop.store(true, Ordering::SeqCst);
                        final_res = Err((ERR_OBSERVER, String::new()));
                        break;
                    }
                }
                last_progress = Instant::now();
            }
            if finished {
                break;
            }
        }

        // Guarantee every worker has terminated before returning to caller.
        let _ = coord.join();

        if let Err((code, msg)) = final_res {
            if !msg.is_empty() {
                write_err(out_err_ptr, out_err_len, &msg);
            }
            return code;
        }
        if let Some(cb) = cancel_cb {
            if cb(ctx) != 0 {
                return ERR_CANCELLED;
            }
        }
        if let Some(cb) = progress_cb {
            if cb(ctx, files_done, bytes_done) != 0 {
                return ERR_OBSERVER;
            }
        }
        OK
    })
}

/// Lists all plain regular files under `root` (with ancestor/reparse/hardlink guards).
/// Output buffer format: repeated `<path_len:u32_le><rel_posix_utf8>`.
#[no_mangle]
pub unsafe extern "C" fn aredoko_list_plain_files(
    root_ptr: *const u8,
    root_len: usize,
    include_cache: u8,
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
            Err(code) => return code,
        };

        let mut stack: Vec<(Vec<u16>, String)> = vec![(root_w, String::new())];
        let mut out_buf: Vec<u8> = Vec::with_capacity(64 * 1024);
        let mut check_counter: u32 = 0;

        while let Some((dir_w, rel_prefix)) = stack.pop() {
            if let Some(cb) = cancel_cb {
                if cb(ctx) != 0 {
                    return ERR_CANCELLED;
                }
            }
            if let Err(code) = check_plain_dir_node(&dir_w) {
                write_err(out_err_ptr, out_err_len, &rel_prefix);
                return code;
            }
            let pattern = with_nul(&child_wide(&dir_w, &[b'*' as u16]));
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
                write_err(out_err_ptr, out_err_len, &rel_prefix);
                return ERR_IO;
            }
            let _guard = FindGuard(handle);

            loop {
                check_counter = check_counter.wrapping_add(1);
                if check_counter & 127 == 0 {
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
                    let name = match wide_slice_to_string(name_w) {
                        Ok(s) => s,
                        Err(code) => return code,
                    };
                    let rel = if rel_prefix.is_empty() {
                        name.clone()
                    } else {
                        format!("{}/{}", rel_prefix, name)
                    };
                    if (fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0 {
                        write_err(out_err_ptr, out_err_len, &rel);
                        return ERR_LINK_REJECTED;
                    }
                    let abs_w = child_wide(&dir_w, name_w);
                    if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0 {
                        if include_cache == 0 && name == "__pycache__" {
                            // Allowed to skip only AFTER confirming it's not a link/reparse.
                        } else {
                            stack.push((abs_w, rel));
                        }
                    } else {
                        let abs_nul = with_nul(&abs_w);
                        if let Err(code) = check_file_handle_nlink(&abs_nul) {
                            write_err(out_err_ptr, out_err_len, &rel);
                            return code;
                        }
                        let b = rel.as_bytes();
                        out_buf.extend_from_slice(&(b.len() as u32).to_le_bytes());
                        out_buf.extend_from_slice(b);
                    }
                }
                if FindNextFileW(handle, &mut fd) == 0 {
                    let err = GetLastError();
                    if err == ERROR_NO_MORE_FILES {
                        break;
                    }
                    return ERR_IO;
                }
            }
        }

        let (ptr, len) = vec_to_raw(out_buf);
        *out_ptr = ptr;
        *out_len = len;
        OK
    })
}
