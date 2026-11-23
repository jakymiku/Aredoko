use rayon::prelude::*;

use crate::{ffi_guard, ERR_INVALID_ARG, OK};

#[inline(always)]
fn neumaier_step(s: &mut f64, c: &mut f64, x: f64) {
    let t = *s + x;
    if s.abs() >= x.abs() {
        *c += (*s - t) + x;
    } else {
        *c += (x - t) + *s;
    }
    *s = t;
}

#[inline(always)]
fn neumaier_finish(s: f64, c: f64) -> f64 {
    if c.is_finite() {
        s + c
    } else {
        s
    }
}

/// Evaluates `n_vectors` float32 embeddings against `n_queries` float64 queries
/// using Neumaier compensated f64 summation matching CPython 3.13 `sum(map(operator.mul, ...))`.
///
/// Output arrays:
/// - `out_valid`: length `n_vectors` (`1` valid, `0` invalid/corrupt norm)
/// - `out_scores`: length `n_vectors` (best dot product across `0..n_queries`)
/// - `out_best_q`: length `n_vectors` (0-based query index of best score)
#[no_mangle]
pub unsafe extern "C" fn aredoko_score_f32_batch(
    queries_f64: *const f64,
    n_queries: usize,
    vectors_f32_bytes: *const u8,
    n_vectors: usize,
    dim: usize,
    normalize_vec: u8,
    out_scores: *mut f64,
    out_best_q: *mut u32,
    out_valid: *mut u8,
) -> i32 {
    ffi_guard(|| {
        if n_queries == 0 || dim == 0 {
            return ERR_INVALID_ARG;
        }
        if n_vectors == 0 {
            return OK;
        }
        if queries_f64.is_null()
            || vectors_f32_bytes.is_null()
            || out_scores.is_null()
            || out_best_q.is_null()
            || out_valid.is_null()
        {
            return ERR_INVALID_ARG;
        }
        let queries_len = match n_queries.checked_mul(dim) {
            Some(v) => v,
            None => return ERR_INVALID_ARG,
        };
        let stride_bytes = match dim.checked_mul(4) {
            Some(v) => v,
            None => return ERR_INVALID_ARG,
        };
        let total_vec_bytes = match n_vectors.checked_mul(stride_bytes) {
            Some(v) => v,
            None => return ERR_INVALID_ARG,
        };
        let queries = std::slice::from_raw_parts(queries_f64, queries_len);
        let vec_bytes = std::slice::from_raw_parts(vectors_f32_bytes, total_vec_bytes);
        let scores_out = std::slice::from_raw_parts_mut(out_scores, n_vectors);
        let best_q_out = std::slice::from_raw_parts_mut(out_best_q, n_vectors);
        let valid_out = std::slice::from_raw_parts_mut(out_valid, n_vectors);
        let do_norm = normalize_vec != 0;

        let score_one = |i: usize| -> (u8, f64, u32) {
            let chunk = &vec_bytes[i * stride_bytes..(i + 1) * stride_bytes];
            let mut sq_s = 0.0f64;
            let mut sq_c = 0.0f64;
            for c in chunk.chunks_exact(4) {
                let v = f32::from_le_bytes([c[0], c[1], c[2], c[3]]) as f64;
                neumaier_step(&mut sq_s, &mut sq_c, v * v);
            }
            let sq = neumaier_finish(sq_s, sq_c);
            if !sq.is_finite() || (sq - 1.0).abs() > 1e-4 {
                return (0, 0.0, 0);
            }
            let inv_or_div = if do_norm { Some(sq.sqrt()) } else { None };
            let mut best_score = f64::NEG_INFINITY;
            let mut best_idx = 0u32;
            let mut has_best = false;
            for q in 0..n_queries {
                let q_slice = &queries[q * dim..(q + 1) * dim];
                let mut d_s = 0.0f64;
                let mut d_c = 0.0f64;
                match inv_or_div {
                    None => {
                        for (j, c) in chunk.chunks_exact(4).enumerate() {
                            let v = f32::from_le_bytes([c[0], c[1], c[2], c[3]]) as f64;
                            neumaier_step(&mut d_s, &mut d_c, q_slice[j] * v);
                        }
                    }
                    Some(norm) => {
                        for (j, c) in chunk.chunks_exact(4).enumerate() {
                            let v = (f32::from_le_bytes([c[0], c[1], c[2], c[3]]) as f64) / norm;
                            neumaier_step(&mut d_s, &mut d_c, q_slice[j] * v);
                        }
                    }
                }
                let dot = neumaier_finish(d_s, d_c);
                if !has_best || dot > best_score {
                    best_score = dot;
                    best_idx = q as u32;
                    has_best = true;
                }
            }
            (1, best_score, best_idx)
        };

        if n_vectors >= 512 {
            scores_out
                .par_iter_mut()
                .zip(best_q_out.par_iter_mut())
                .zip(valid_out.par_iter_mut())
                .enumerate()
                .for_each(|(i, ((s, bq), v))| {
                    let (valid, score, best) = score_one(i);
                    *v = valid;
                    *s = score;
                    *bq = best;
                });
        } else {
            for i in 0..n_vectors {
                let (valid, score, best) = score_one(i);
                valid_out[i] = valid;
                scores_out[i] = score;
                best_q_out[i] = best;
            }
        }
        OK
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn batch_scoring_and_validation() {
        let q = [1.0f64, 0.0, 0.0, 1.0];
        let mut vecs = Vec::new();
        // v0: [1.0, 0.0] -> valid, q0=1.0
        for f in [1.0f32, 0.0f32] {
            vecs.extend_from_slice(&f.to_le_bytes());
        }
        // v1: [0.0, 0.5] -> bad norm (0.25) -> invalid
        for f in [0.0f32, 0.5f32] {
            vecs.extend_from_slice(&f.to_le_bytes());
        }
        // v2: [0.0, 1.00001] -> valid within 1e-4, q1 higher
        for f in [0.0f32, 1.00001f32] {
            vecs.extend_from_slice(&f.to_le_bytes());
        }
        let mut scores = [0.0f64; 3];
        let mut best_q = [0u32; 3];
        let mut valid = [0u8; 3];
        let rc = unsafe {
            aredoko_score_f32_batch(
                q.as_ptr(),
                2,
                vecs.as_ptr(),
                3,
                2,
                1,
                scores.as_mut_ptr(),
                best_q.as_mut_ptr(),
                valid.as_mut_ptr(),
            )
        };
        assert_eq!(rc, OK);
        assert_eq!(valid, [1, 0, 1]);
        assert_eq!(best_q[0], 0);
        assert!((scores[0] - 1.0).abs() < 1e-12);
        assert_eq!(best_q[2], 1);
        assert!((scores[2] - 1.0).abs() < 1e-12);
    }
}
