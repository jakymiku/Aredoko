# Aredoko — License & Third-Party Notices

This document describes the license of Aredoko itself and provides licensing notices, provenance notes, and acknowledgements for all bundled third-party components, optional user-consented runtimes, and AI model weights used with Aredoko.

---

## 0. Aredoko Software License & Distribution Notice

- **License**: **MIT License** (see [LICENSE](LICENSE))
- **Copyright**: Copyright (c) 2026 JAKYMIKU
- **Scope**: The MIT License applies to Aredoko's own source code and Aredoko-authored binaries (`Aredoko.exe`, `Aredoko.WinUI.exe`, `Aredoko.WinUI.dll`, `Aredoko.Core.dll`, `PythonSetup.exe`, `app/*.py`, `tools/*.py`, `tools/*.ps1`, `config/*` definitions).
- **Third-Party Components**: Bundled third-party runtimes/binaries (`runtime/media/`, Microsoft `.NET` / `WindowsAppSDK` / `WebView2` / `WinML` in `bin/`) and optional user-downloaded Python/AI packages and model weights remain governed by their own respective licenses listed below.
- **Unsigned Distribution Notice (`未署名配布`)**: Release executables in the portable ZIP are distributed **without Authenticode code signing**. On Windows systems where Smart App Control is enforced (`VerifiedAndReputablePolicyState = 1`), Windows may block unsigned executables from running.

---

## 1. Privacy, Offline Operation & Weight Distribution Policy

1. **Zero Telemetry & Offline Integrity**:
   - Aredoko operates strictly on your local machine (`127.0.0.1` loopback).
   - No analytics, user file metadata, search queries, or diagnostics are ever transmitted to external servers.
   - Core library functions—including folder registration, metadata editing, shelves, tags, full-text literal search, book/image/video/audio browsing, and reading progress—operate 100% offline without any AI models installed.

2. **No Automatic Model or Runtime Downloads**:
   - AI models and Python/AI dependencies are never downloaded silently or bundled unauthorized into the distribution.
   - Users explicitly review sources/licenses and consent before downloading the Basic Python runtime or optional AI runtimes and model weights.

---

## 2. Bundled Media Tools (`runtime/media/`) — GNU GPL v3

### FFmpeg & ffprobe (`n8.1.3-34-ga35157abb9-20261109`)
- **Files Bundled**: `runtime/media/ffmpeg.exe`, `runtime/media/ffprobe.exe`, `runtime/media/LICENSE.txt`
- **Build Provenance**: Built by [BtbN/FFmpeg-Builds](https://github.com/FFmpeg-Builds/FFmpeg-Builds) (`ffmpeg-n8.1-latest-win64-gpl-8.1`, `--enable-gpl --enable-version3`, archive SHA-256 `e54b2fdb1af658faf60ebc805886f73d9c9903c6183c929ebb0aae6065d860a4`).
- **License**: **GNU General Public License Version 3 (`GPL-3.0`)** — full verbatim license text is bundled in `runtime/media/LICENSE.txt`.
- **Integration Boundary**: Aredoko invokes `ffmpeg.exe` and `ffprobe.exe` strictly as separate child processes over standard I/O / pipes (`app/video_*.py`, `app/audio_*.py`) and does not link against `libav*` libraries.
- **Corresponding Source (GPLv3 Section 6)**: When redistributing `runtime/media/ffmpeg.exe` and `ffprobe.exe` in public binary releases, the distributor must satisfy GPLv3 §6 Corresponding Source obligations for FFmpeg revision `n8.1.3-34-ga35157abb9-20261109` and the enabled GPL/LGPL codec libraries built into that BtbN release (e.g., hosting the exact matching source archive or providing a valid written offer, or replacing `runtime/media/` with an LGPL FFmpeg build).

---

## 3. Bundled Windows Desktop & .NET Dependencies (`bin/` & `THIRD_PARTY_LICENSES/`)

Self-contained binaries in `bin/` include the following Microsoft runtime and SDK payloads, whose verbatim `LICENSE*`, `NOTICE.txt`, and `THIRD-PARTY-NOTICES.txt` files are included in `THIRD_PARTY_LICENSES/` (tracked in [config/desktop-notices/](config/desktop-notices/manifest.json)):

### .NET 10 Runtime & Windows Desktop (`10.0.14`)
- **Packages**: `Microsoft.NETCore.App.Runtime.win-x64` (`10.0.14`), `Microsoft.WindowsDesktop.App.Runtime.win-x64` (`10.0.14`)
- **License**: **MIT License** — `(c) .NET Foundation and Contributors`
- **Verbatim Files**: `dotnet-10.0.14-LICENSE.txt`, `dotnet-10.0.14-THIRD-PARTY-NOTICES.txt`, `windowsdesktop-10.0.14-LICENSE.txt`

### Microsoft Windows App SDK (`2.5.1`)
- **Packages**: `Microsoft.WindowsAppSDK` (`2.5.1`), `WinUI` (`2.3.9`), `Foundation` (`2.3.12`), `InteractiveExperiences` (`2.1.9`), `ML` (`2.1.94`), `Base`, `DWrite`, `AI`, `Search`, `Widgets`
- **License**: **Microsoft Software License Terms** (Section 3 permits redistribution of binplaced files in self-contained deployments; Section 4(c) requires preserving notices)
- **Verbatim Files**: `windowsappsdk-2.5.1-license.txt`, `windowsappsdk-2.5.1-NOTICE.txt`

### Microsoft Windows AI / Machine Learning Runtime (`2.1.74`)
- **Packages**: `Microsoft.Windows.AI.MachineLearning` (`2.1.74`, includes `onnxruntime.dll`, `DirectML.dll`, `Microsoft.Windows.AI.*.dll`)
- **License**: **Microsoft Software License Terms** + Open-Source Notices (`Intel MKL`, `ONNX Runtime`, etc.)
- **Verbatim Files**: `winml-2.1.74-license.txt`, `winml-2.1.74-ThirdPartyNotices.txt`

### Microsoft Edge WebView2 (`1.0.3719.77`)
- **Packages**: `Microsoft.Web.WebView2` (`1.0.3719.77`, includes `WebView2Loader.dll` and `Microsoft.Web.WebView2.Core.dll`)
- **License**: **BSD 3-Clause License** — `Copyright (C) Microsoft Corporation. All rights reserved.`
- **Verbatim Files**: `webview2-1.0.3719.77-LICENSE.txt`, `webview2-1.0.3719.77-NOTICE.txt` (reproduced verbatim in `THIRD_PARTY_LICENSES/` as required by the BSD-3-Clause binary distribution terms)

---

## 4. Basic Python Runtime (Optional On-Demand Download, NOT in ZIP)

With explicit first-run user consent, `PythonSetup.exe` and `tools/prepare_basic_runtime.py` download and verify the official CPython and Pillow packages (`cpython-3.13.17-pillow-12.3.0-win-x64-v1`) directly into `%LOCALAPPDATA%\Aredoko\`:

- **CPython `3.13.17`** (`python.3.13.17.nupkg`, PSF License + embedded OpenSSL, bzip2, libffi, Expat, mpdecimal, SQLite, xz/lzma, zlib, and `pip 26.2.2` notices) — installed verbatim as `tools/LICENSE.txt` and archived for audit in [config/runtime-notices/basic-cp313-20261116/](config/runtime-notices/basic-cp313-20261116/sources.json).
- **Pillow `12.3.0`** (`pillow-12.3.0-cp313-cp313-win_amd64.whl`) — **MIT-CMU License** (`Copyright (c) 1997-2011 Secret Labs AB, 1995-2011 Fredrik Lundh, 2010-2025 Jeffrey A. Clark and contributors`), including full notices for statically linked codecs (`libjpeg`, `zlib-ng 2.3.3`, `libtiff`, `xz`) inside `pillow-12.3.0.dist-info/licenses/LICENSE` and [pillow-12.3.0-LICENSE.txt](config/runtime-notices/basic-cp313-20261116/pillow-12.3.0-LICENSE.txt).
- **Legacy CPython 3.11.9 Notice Snapshot**: Commit-pinned native notice references for the earlier local CPython 3.11.9 candidate are preserved in [config/runtime-notices/cpython311-20261029/](config/runtime-notices/cpython311-20261029/sources.json) and [docs/runtime-notice-inventory.md](docs/runtime-notice-inventory.md) (`redistribution_approved: false`).

---

## 5. Optional AI Runtime (`cp313-cu128`, NOT Bundled & NOT Redistributed)

The optional GPU AI environment (`config/ai-runtime-recipes/cp313-cu128-draft.json`, 44 pinned wheels) is downloaded directly from upstream PyPI / PyTorch URLs by user consent and is **not** bundled or redistributed with Aredoko (`redistribution_approved: false`, notice inventory audited in [config/runtime-notices/cp313-cu128-20261116/](config/runtime-notices/cp313-cu128-20261116/inventory-manifest.json) with 44/44 distributions covered including commit-pinned `tokenizers==0.23.3` supplement):

- **PyTorch (`2.9.1+cu128`) & TorchVision (`0.24.1+cu128`)**: **BSD-3-Clause / BSD** (`torch`, `torchvision`), bundled with proprietary NVIDIA CUDA 12 / cuDNN 9 / NVRTC / NCCL and Intel OpenMP (`libiomp5md.dll`) runtime DLLs inside `torch/lib/` governed by NVIDIA CUDA EULA and upstream redistributable notices in `torch-2.9.1+cu128.dist-info/{LICENSE,NOTICE}`.
- **Transformers (`5.19.0`), Sentence-Transformers (`6.1.0`), HuggingFace Hub (`1.33.0`), Tokenizers (`0.23.3`), Safetensors (`0.8.0`), hf-xet (`1.8.0`)**: **Apache-2.0**.
- **NumPy (`2.5.4`), SciPy (`1.18.1`), scikit-learn (`1.9.1`), Click, fsspec, httpx, httpcore, idna, Jinja2, MarkupSafe, NetworkX, Pygments, SymPy, cloudpickle, joblib, colorama, threadpoolctl**: **BSD-3-Clause / BSD-2-Clause / 0BSD / Zlib / CC0-1.0**.
- **Certifi (`2026.10.23`) & tqdm (`4.70.1`)**: **MPL-2.0** (`tqdm` is `MPL-2.0 AND MIT`). Source modifications to MPL-2.0 files would require sharing per MPL-2.0 §3.
- **Regex (`2026.11.9`)**: `Apache-2.0 AND CNRI-Python`.
- **AnyIO, annotated-doc, filelock, h11, markdown-it-py, mdurl, narwhals, PyYAML, rich, setuptools, typer**: **MIT**; **shellingham**: **ISC**; **typing_extensions**: **PSF-2.0**; **packaging**: `Apache-2.0 OR BSD-2-Clause`.
- **Standalone ONNX Runtime** (legacy `cp311` / WD Tagger): **MIT License** (`https://github.com/microsoft/onnxruntime`).

---

## 6. Machine Learning Models & Weights (Optional User Download, NOT Bundled)

### EmbeddingGemma 2 (Application-Pinned Revision)
- **Author**: Google
- **Repository**: `google/embeddinggemma-2`
- **Revision**: `914f7f89142e33e77833254d9c9b90c3cef7303b`
- **License**: **Apache License, Version 2.0**, as declared by the [fixed upstream model card](https://huggingface.co/google/embeddinggemma-2/blob/914f7f89142e33e77833254d9c9b90c3cef7303b/README.md).
- **Notice**: Downloaded only after explicit consent. Complete [license](config/acquisition/notices/embeddinggemma-2-LICENSE.txt), [attribution](config/acquisition/notices/embeddinggemma-2-NOTICE.txt), and [unmodified model card](config/acquisition/notices/embeddinggemma-2-NOTICE-upstream-model-card.txt) are included in the pack.

### SmilingWolf WD Tagger (SwinV2 v3)
- **Author**: SmilingWolf
- **Repository**: `SmilingWolf/wd-swinv2-tagger-v3`
- **Revision**: `627aef95638667ddcaa3ac8ae625e88ea5b02f51`
- **License**: **Apache License, Version 2.0**, as declared by the [fixed upstream model card](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/blob/627aef95638667ddcaa3ac8ae625e88ea5b02f51/README.md).
- **Notice**: Complete [Apache 2.0 license](config/acquisition/notices/wd-swinv2-v3-LICENSE.txt), [model attribution](config/acquisition/notices/wd-swinv2-v3-NOTICE.txt), and [unmodified model card](config/acquisition/notices/wd-swinv2-v3-NOTICE-upstream-model-card.txt) are included in the pack.

---

## 7. SQLite
- **License**: Public Domain
- **Notice**: SQLite is in the Public Domain. All of the code and documentation in SQLite has been dedicated to the public domain by the authors.
- **URL**: https://www.sqlite.org/copyright.html
