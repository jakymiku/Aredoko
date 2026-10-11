# AI search — proposed next milestone (2026-10-11)

Status (2026-10-12): first EmbeddingGemma 2 retrieval slice implemented and verified with actual offline CUDA inference on generated fixtures. The user explicitly authorized project-local packages/model download with a shared 6 MB/s cap. Laya remains planned. Filename/tag search stays available independently.

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

## Implemented first slice

- Run the existing launcher, register/scan a user-selected test folder, open **AI索引**, then **索引を作成・更新**. Select **AI意味検索** for filename/tag + image/cover candidates, or **AI画像・表紙** to rank only image/cover vectors. Empty queries browse the existing literal library rather than pretending to perform semantic retrieval.
- Prototype limit: earliest 2,000 present eligible records by item ID; this is not coverage of the full personal library. Image and CBZ/ZIP first-page sources use the existing bounded read-only preview reader. PDF/video/audio are filename/tag inputs only. No interior-page OCR or actual audio/video encoding.
- Separate text and cover vectors, 768 dimensions, normalized float32 blobs in a sibling AI SQLite DB. Fingerprints include source location/size/mtime and current title/tags. Metadata changes hide stale vectors until index update; favorite/reviewed/shelf filters apply at search time. Current exclusions apply without waiting for rescan. Cancelling preserves completed items, and rerun reuses matching revisions.
- The stdlib catalog controls an owned Python 3.11 subprocess in .venv-ai. Runtime loads only local model files, disables HF network/telemetry and remote code. Only text or bounded in-memory image bytes cross the subprocess protocol; no source is sent to a network inference endpoint. On Windows the worker watches parent termination so launcher exit/crash releases it. Optional AI cache corruption does not prevent literal catalog startup.
- Setup is explicit: pwsh -File tools/setup-ai.ps1 -InstallAndDownload. All setup HTTPS downloads use one temporary loopback CONNECT proxy capped at 6,000,000 bytes/s; Xet/transfer fast paths disabled. Pin torch2.9.1+CUDA12.8 / torchvision0.24.1 / sentence-transformers6.1.0 / transformers5.19.0 and model revision914f7f89142e33e77833254d9c9b90c3cef7303b. Model/environment/cache are ignored, not committed. Other platforms and CPU retrieval performance are not verified.
- Deterministic tests verify the protocol and lifecycle with known vectors; they are not retrieval-accuracy evidence. Separate actual-model tests used 17 generated records, including deliberately corrupt sources. Japanese filename paraphrase, blue image and red CBZ cover each returned the expected top hit in their respective text/cover modes. Warm query end-to-end time was roughly 104–106ms on this small fixture; PyTorch peak allocated GPU memory was 931.8MiB (not total OS/app GPU memory). Full-library speed/accuracy is still unknown.
- Mixing raw text and cover cosine scores (current combined mode uses their maximum) biased color rankings toward filenames in the first test. Visual mode fixes this by explicitly selecting cover vectors. Combined-mode calibration and intent routing need evaluation before relying on general mixed queries.

Next: evaluate Laya multilingual intent choices locally, then calibrate mixed-mode ranking and scale incremental/checkpoint indexing beyond this deliberately small prototype. Laya setup has not been performed.

Native verification status: the original metadata regression passed, and the new native AI flow created 17 records with actual CUDA inference via the GUI. The new full AI flow is **not passed**: after two fix/rerun cycles it stopped on ambiguous text selection of the mode ComboBox. Dedicated mode AutomationIds have been added and built, but their native rerun is pending. Screenshots/results were saved and visually inspected. Owned model workers stopped after launcher exit. Resolve this pending GUI flow before claiming end-to-end completion.
