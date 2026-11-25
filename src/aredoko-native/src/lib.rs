use std::panic::{catch_unwind, AssertUnwindSafe};

pub const OK: i32 = 0;
pub const ERR_INVALID_ARG: i32 = -1;
pub const ERR_PATH_MISSING: i32 = -2;
pub const ERR_LINK_REJECTED: i32 = -3;
pub const ERR_HARDLINK_REJECTED: i32 = -4;
pub const ERR_NOT_PLAIN: i32 = -5;
pub const ERR_CHANGED: i32 = -6;
pub const ERR_CANCELLED: i32 = -7;
pub const ERR_OBSERVER: i32 = -8;
pub const ERR_TOO_LARGE: i32 = -9;
pub const ERR_OUTPUT_TOO_LARGE: i32 = -10;
pub const ERR_UNSUPPORTED: i32 = -11;
pub const ERR_IO: i32 = -12;
pub const ERR_ACCESS_DENIED: i32 = -13;
pub const ERR_PANIC: i32 = -99;

mod plain_path;
mod scanner;
mod thumbnail;
mod vectors;
mod verify;

pub(crate) fn vec_to_raw(mut v: Vec<u8>) -> (*mut u8, usize) {
    if v.is_empty() {
        return (std::ptr::null_mut(), 0);
    }
    v.shrink_to_fit();
    let boxed = v.into_boxed_slice();
    let len = boxed.len();
    let ptr = Box::into_raw(boxed) as *mut u8;
    (ptr, len)
}

pub(crate) unsafe fn write_err(out_ptr: *mut *mut u8, out_len: *mut usize, msg: &str) {
    if out_ptr.is_null() || out_len.is_null() {
        return;
    }
    let (ptr, len) = vec_to_raw(msg.as_bytes().to_vec());
    *out_ptr = ptr;
    *out_len = len;
}

pub(crate) unsafe fn clear_out(out_ptr: *mut *mut u8, out_len: *mut usize) {
    if !out_ptr.is_null() {
        *out_ptr = std::ptr::null_mut();
    }
    if !out_len.is_null() {
        *out_len = 0;
    }
}

pub(crate) fn ffi_guard<F: FnOnce() -> i32>(f: F) -> i32 {
    match catch_unwind(AssertUnwindSafe(f)) {
        Ok(code) => code,
        Err(_) => ERR_PANIC,
    }
}

#[no_mangle]
pub extern "C" fn aredoko_native_version() -> u32 {
    1
}

#[no_mangle]
pub unsafe extern "C" fn aredoko_free_buffer(ptr: *mut u8, len: usize) {
    if ptr.is_null() || len == 0 {
        return;
    }
    let slice_ptr = std::ptr::slice_from_raw_parts_mut(ptr, len);
    drop(Box::from_raw(slice_ptr));
}
