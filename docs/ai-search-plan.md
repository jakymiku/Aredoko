# AI search — proposed next milestone (2026-10-11)

Status: researched and planned; no AI packages or model weights installed, no AI search result claimed. Filename/tag search stays available. Model downloads and dependency setup need explicit authorization under AGENTS.md. Prepare a concrete isolated environment/package/model list before requesting it.

## First usable slice

1. Verify an isolated Python inference worker on Windows with RTX 4070 Ti 12 GB. Measure GPU compatibility, peak memory and batch throughput before estimating full-library indexing time. Keep the stdlib catalog/API independently runnable.
2. Use EmbeddingGemma 2 text+vision mode for filename/tag text and selected image/CBZ/ZIP cover inputs. Store normalized vectors separately from sources with item ID, source revision, model revision, modality and dimension. Start with hundreds to thousands of explicitly selected test items. Expose semantic search in WinUI alongside literal search, and evaluate Japanese ambiguous queries against expected hits.
3. Try upstream Laya multilingual for bounded choices of query intent / suggested media filter. Respect explicit user filters, display inferred choices and fall back when uncertain. Compare its benefit with EmbeddingGemma-only retrieval. It is an optional typed decision layer, not an image encoder or open-ended text generator.

Planning target: first usable EmbeddingGemma prototype in the next one or two development sessions after authorized runtime/model setup succeeds. This is an estimate, not a measured delivery date. Laya follows working retrieval. Robust tens-of-thousands indexing is a separate stage: incremental changes, cancellation/checkpoint recovery, exclusion/deletion propagation, resource limits and ranking/latency measurement. Audio/video and book interior OCR/pages follow later.

Cover-only indexing cannot establish unseen interior content. Anime/doujin accuracy and Japanese nuance need user-selected sample evaluation. No private source is sent to an external inference service.

## Primary sources

- [Google model card](https://huggingface.co/google/embeddinggemma-2): unified text/image/audio/video vectors and selectively loadable encoders. Use task prefixes and bfloat16 where supported or float32; avoid float16 as explicitly warned. Start with fixed normalized 768-dimensional vectors; evaluate smaller supported dimensions later without mixing index dimensions.
- [Google developer guide](https://developers.googleblog.com/en/embeddinggemma-2-the-developer-guide/): selective loading and multimodal integration.
- [laya-mlx](https://github.com/mizorewww/laya-mlx): requires Apple Silicon/macOS; unsuitable for this Windows PC.
- [Upstream Laya](https://github.com/NandhaKishorM/laya): PyTorch implementation documents Windows setup and typed choice/score/yes-no decisions. Validate a multilingual checkpoint locally; documentation is not proof that the current Python/GPU stack has been tested.

GPU latency, VRAM use, full-library initial indexing duration and personal-library ranking accuracy are not yet measured.
