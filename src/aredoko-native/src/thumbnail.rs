use std::io::Cursor;

use fast_image_resize as fr;
use image::ImageReader;

use crate::{
    clear_out, ffi_guard, vec_to_raw, ERR_INVALID_ARG, ERR_OUTPUT_TOO_LARGE, ERR_TOO_LARGE,
    ERR_UNSUPPORTED, OK,
};

/// Mirrors `app/image_animations.py::detect_animation_header`.
fn is_animated_header(data: &[u8]) -> bool {
    if data.len() < 16 {
        return false;
    }
    if data.starts_with(b"GIF87a") || data.starts_with(b"GIF89a") {
        return true;
    }
    if &data[0..4] == b"RIFF" && &data[8..12] == b"WEBP" {
        if data.len() >= 21 && &data[12..16] == b"VP8X" && (data[20] & 0x02) != 0 {
            return true;
        }
        let head = &data[..data.len().min(128)];
        if head.windows(4).any(|w| w == b"ANIM" || w == b"ANMF") {
            return true;
        }
    }
    if data.starts_with(b"\x89PNG\r\n\x1a\n") {
        let mut offset = 8usize;
        let limit = data.len().min(32768);
        while offset + 8 <= limit {
            let length = u32::from_be_bytes(data[offset..offset + 4].try_into().unwrap()) as usize;
            let kind = &data[offset + 4..offset + 8];
            if kind == b"acTL" {
                return true;
            }
            if kind == b"IDAT" || kind == b"IEND" {
                return false;
            }
            if length > limit || offset.saturating_add(12).saturating_add(length) > limit {
                break;
            }
            offset += 12 + length;
        }
    }
    false
}

fn parse_tiff_orientation(tiff: &[u8]) -> u16 {
    if tiff.len() < 8 {
        return 1;
    }
    let little = match &tiff[0..2] {
        b"II" => true,
        b"MM" => false,
        _ => return 1,
    };
    let u16_at = |off: usize| -> Option<u16> {
        let b: [u8; 2] = tiff.get(off..off + 2)?.try_into().ok()?;
        Some(if little {
            u16::from_le_bytes(b)
        } else {
            u16::from_be_bytes(b)
        })
    };
    let u32_at = |off: usize| -> Option<u32> {
        let b: [u8; 4] = tiff.get(off..off + 4)?.try_into().ok()?;
        Some(if little {
            u32::from_le_bytes(b)
        } else {
            u32::from_be_bytes(b)
        })
    };
    if u16_at(2) != Some(42) {
        return 1;
    }
    let ifd_off = match u32_at(4) {
        Some(v) => v as usize,
        None => return 1,
    };
    let count = match u16_at(ifd_off) {
        Some(v) => (v as usize).min(512),
        None => return 1,
    };
    for i in 0..count {
        let entry = ifd_off + 2 + i * 12;
        if entry + 12 > tiff.len() {
            break;
        }
        if u16_at(entry) == Some(0x0112)
            && u16_at(entry + 2) == Some(3)
            && u32_at(entry + 4) == Some(1)
        {
            if let Some(val) = u16_at(entry + 8) {
                if (1..=8).contains(&val) {
                    return val;
                }
            }
        }
    }
    1
}

fn extract_exif_orientation(data: &[u8]) -> u16 {
    // JPEG SOI
    if data.starts_with(b"\xFF\xD8") {
        let mut pos = 2usize;
        while pos + 4 <= data.len() {
            if data[pos] != 0xFF {
                pos += 1;
                continue;
            }
            while pos < data.len() && data[pos] == 0xFF {
                pos += 1;
            }
            if pos >= data.len() {
                break;
            }
            let marker = data[pos];
            pos += 1;
            if marker == 0xD9 || marker == 0xDA {
                break;
            }
            if marker == 0x00 || marker == 0x01 || (0xD0..=0xD8).contains(&marker) {
                continue;
            }
            if pos + 2 > data.len() {
                break;
            }
            let seg_len = u16::from_be_bytes([data[pos], data[pos + 1]]) as usize;
            if seg_len < 2 || pos + seg_len > data.len() {
                break;
            }
            let payload = &data[pos + 2..pos + seg_len];
            if marker == 0xE1 && payload.starts_with(b"Exif\0\0") {
                return parse_tiff_orientation(&payload[6..]);
            }
            pos += seg_len;
        }
        return 1;
    }
    // PNG eXIf chunk
    if data.starts_with(b"\x89PNG\r\n\x1a\n") {
        let mut pos = 8usize;
        while pos + 12 <= data.len() {
            let length = u32::from_be_bytes(data[pos..pos + 4].try_into().unwrap()) as usize;
            let kind = &data[pos + 4..pos + 8];
            if kind == b"IDAT" || kind == b"IEND" {
                break;
            }
            if pos + 12 + length > data.len() {
                break;
            }
            if kind == b"eXIf" {
                return parse_tiff_orientation(&data[pos + 8..pos + 8 + length]);
            }
            pos += 12 + length;
        }
        return 1;
    }
    // WebP EXIF RIFF chunk
    if data.len() >= 12 && &data[0..4] == b"RIFF" && &data[8..12] == b"WEBP" {
        let mut pos = 12usize;
        while pos + 8 <= data.len() {
            let chunk_id = &data[pos..pos + 4];
            let chunk_size = u32::from_le_bytes(data[pos + 4..pos + 8].try_into().unwrap()) as usize;
            let payload_start = pos + 8;
            let payload_end = payload_start.saturating_add(chunk_size);
            if payload_end > data.len() {
                break;
            }
            if chunk_id == b"EXIF" {
                let payload = &data[payload_start..payload_end];
                let tiff = if payload.starts_with(b"Exif\0\0") {
                    &payload[6..]
                } else {
                    payload
                };
                return parse_tiff_orientation(tiff);
            }
            let padded = chunk_size + (chunk_size & 1);
            pos = payload_start.saturating_add(padded);
        }
    }
    1
}

fn apply_orientation(img: image::DynamicImage, orientation: u16) -> image::DynamicImage {
    match orientation {
        2 => img.fliph(),
        3 => img.rotate180(),
        4 => img.flipv(),
        5 => img.rotate90().fliph(),
        6 => img.rotate90(),
        7 => img.rotate270().fliph(),
        8 => img.rotate270(),
        _ => img,
    }
}

/// Exact Pillow `Image.thumbnail((edge, edge))` sizing math.
fn thumbnail_dimensions(w: u32, h: u32, edge: u32) -> (u32, u32) {
    if w <= edge && h <= edge {
        return (w.max(1), h.max(1));
    }
    let wf = w as f64;
    let hf = h as f64;
    let ef = edge as f64;
    let aspect = wf / hf;
    let round_aspect = |number: f64, err: &dyn Fn(u32) -> f64| -> u32 {
        let lo = number.floor().max(0.0) as u32;
        let hi = number.ceil().max(0.0) as u32;
        let best = if err(lo) <= err(hi) { lo } else { hi };
        best.max(1)
    };
    if 1.0 >= aspect {
        let x = round_aspect(ef * aspect, &|n| (aspect - (n as f64) / ef).abs());
        (x.min(edge), edge)
    } else {
        let y = round_aspect(ef / aspect, &|n| {
            if n == 0 {
                0.0
            } else {
                (aspect - ef / (n as f64)).abs()
            }
        });
        (edge, y.min(edge))
    }
}

#[no_mangle]
pub unsafe extern "C" fn aredoko_image_probe(
    data_ptr: *const u8,
    data_len: usize,
    out_w: *mut u32,
    out_h: *mut u32,
) -> i32 {
    ffi_guard(|| {
        if data_ptr.is_null() || data_len == 0 || out_w.is_null() || out_h.is_null() {
            return ERR_INVALID_ARG;
        }
        let data = std::slice::from_raw_parts(data_ptr, data_len);
        if is_animated_header(data) {
            return ERR_UNSUPPORTED;
        }
        let reader = match ImageReader::new(Cursor::new(data)).with_guessed_format() {
            Ok(r) => r,
            Err(_) => return ERR_UNSUPPORTED,
        };
        match reader.into_dimensions() {
            Ok((w, h)) if w >= 1 && h >= 1 => {
                *out_w = w;
                *out_h = h;
                OK
            }
            _ => ERR_UNSUPPORTED,
        }
    })
}

#[no_mangle]
pub unsafe extern "C" fn aredoko_render_thumbnail(
    data_ptr: *const u8,
    data_len: usize,
    max_edge: u32,
    max_pixels: u64,
    max_png_bytes: usize,
    out_ptr: *mut *mut u8,
    out_len: *mut usize,
) -> i32 {
    ffi_guard(|| {
        clear_out(out_ptr, out_len);
        if data_ptr.is_null()
            || data_len == 0
            || max_edge == 0
            || out_ptr.is_null()
            || out_len.is_null()
        {
            return ERR_INVALID_ARG;
        }
        let data = std::slice::from_raw_parts(data_ptr, data_len);
        if is_animated_header(data) {
            return ERR_UNSUPPORTED;
        }
        let reader = match ImageReader::new(Cursor::new(data)).with_guessed_format() {
            Ok(r) => r,
            Err(_) => return ERR_UNSUPPORTED,
        };
        let format = match reader.format() {
            Some(f)
                if matches!(
                    f,
                    image::ImageFormat::Jpeg
                        | image::ImageFormat::Png
                        | image::ImageFormat::WebP
                        | image::ImageFormat::Bmp
                ) =>
            {
                f
            }
            _ => return ERR_UNSUPPORTED,
        };
        let reader_with_fmt = ImageReader::with_format(Cursor::new(data), format);
        let (w, h) = match reader_with_fmt.into_dimensions() {
            Ok(d) => d,
            Err(_) => return ERR_UNSUPPORTED,
        };
        if w == 0 || h == 0 || (w as u64).saturating_mul(h as u64) > max_pixels {
            return ERR_TOO_LARGE;
        }

        let orientation = extract_exif_orientation(data);
        let mut decoder = ImageReader::with_format(Cursor::new(data), format);
        let mut limits = image::Limits::default();
        limits.max_image_width = Some(16_384);
        limits.max_image_height = Some(16_384);
        decoder.limits(limits);
        let decoded = match decoder.decode() {
            Ok(img) => img,
            Err(_) => return ERR_UNSUPPORTED,
        };
        let oriented = apply_orientation(decoded, orientation);
        let rgba = oriented.into_rgba8();
        let src_w = rgba.width();
        let src_h = rgba.height();
        if src_w == 0 || src_h == 0 || (src_w as u64).saturating_mul(src_h as u64) > max_pixels {
            return ERR_TOO_LARGE;
        }

        let (dst_w, dst_h) = thumbnail_dimensions(src_w, src_h, max_edge);
        let (out_w, out_h, final_rgba): (u32, u32, Vec<u8>) = if dst_w == src_w && dst_h == src_h {
            (src_w, src_h, rgba.into_raw())
        } else {
            let src_img = match fr::images::Image::from_vec_u8(
                src_w,
                src_h,
                rgba.into_raw(),
                fr::PixelType::U8x4,
            ) {
                Ok(im) => im,
                Err(_) => return ERR_UNSUPPORTED,
            };
            let mut dst_img = fr::images::Image::new(dst_w, dst_h, fr::PixelType::U8x4);
            let options = fr::ResizeOptions::new()
                .resize_alg(fr::ResizeAlg::Convolution(fr::FilterType::Lanczos3));
            let mut resizer = fr::Resizer::new();
            if resizer.resize(&src_img, &mut dst_img, &options).is_err() {
                return ERR_UNSUPPORTED;
            }
            (dst_w, dst_h, dst_img.into_vec())
        };

        let mut png_bytes = Vec::with_capacity((out_w as usize) * (out_h as usize) * 2);
        {
            let mut encoder = png::Encoder::new(&mut png_bytes, out_w, out_h);
            encoder.set_color(png::ColorType::Rgba);
            encoder.set_depth(png::BitDepth::Eight);
            encoder.set_compression(png::Compression::Fast);
            encoder.set_filter(png::FilterType::Sub);
            let mut writer = match encoder.write_header() {
                Ok(w) => w,
                Err(_) => return ERR_UNSUPPORTED,
            };
            if writer.write_image_data(&final_rgba).is_err() {
                return ERR_UNSUPPORTED;
            }
        }
        if png_bytes.len() > max_png_bytes {
            return ERR_OUTPUT_TOO_LARGE;
        }
        let (ptr, len) = vec_to_raw(png_bytes);
        *out_ptr = ptr;
        *out_len = len;
        OK
    })
}
