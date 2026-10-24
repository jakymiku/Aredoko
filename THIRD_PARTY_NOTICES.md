# Aredoko — Third-Party Notices and Open Source Licenses

This document contains licensing notices and acknowledgements for third-party software, libraries, and AI model weights utilized by or compatible with Aredoko.

---

## 1. Privacy, Offline Operation & Weight Distribution Policy

1. **Zero Telemetry & Offline Integrity**:
   - Aredoko operates strictly on your local machine (`127.0.0.1` loopback).
   - No analytics, user file metadata, search queries, or diagnostics are ever transmitted to external servers.
   - Core library functions—including folder registration, metadata editing, shelves, tags, full-text literal search, book/image/video/audio browsing, and reading progress—operate 100% offline without any AI models installed.

2. **No Automatic Model Downloads**:
   - AI models are never downloaded silently or bundled unauthorized into the distribution.
   - Users explicitly configure local AI environments and acquire authorized model weights according to their respective licenses.

---

## 2. Machine Learning Models & Weights

### EmbeddingGemma 2 (2B)
- **Author**: Google LLC
- **Repository**: `google/embeddinggemma-2-2b`
- **License**: Gemma Terms of Use
- **Notice**:
  Gemma is provided by Google under the Gemma Terms of Use. Use of Gemma is subject to the Gemma Prohibited Use Policy.
  See: https://ai.google.dev/gemma/terms

### SmilingWolf WD Tagger (SwinV2 v3)
- **Author**: SmilingWolf
- **Repository**: `SmilingWolf/wd-swinv2-tagger-v3`
- **License**: Apache License, Version 2.0
- **Notice**:
  The [fixed upstream model card](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/blob/627aef95638667ddcaa3ac8ae625e88ea5b02f51/README.md) declares Apache-2.0. Aredoko's optional acquisition pack downloads the unmodified ONNX model and selected tag list from that revision, only after explicit consent.
  The complete [Apache 2.0 license](config/acquisition/notices/wd-swinv2-v3-LICENSE.txt), [model attribution](config/acquisition/notices/wd-swinv2-v3-NOTICE.txt), and [unmodified model card](config/acquisition/notices/wd-swinv2-v3-NOTICE-upstream-model-card.txt) are included as bounded, hash-verified metadata in the pack.
  Python and AI runtimes are separate; this model pack does not contain their dependencies or authorize their redistribution by itself.

---

## 3. Python Runtime & Open-Source Libraries

### PyTorch
- **License**: BSD 3-Clause License
- **Copyright**: (c) 2016-present, Meta Platforms, Inc. and affiliates.
- **URL**: https://pytorch.org/

### Hugging Face Transformers & Accelerate & Tokenizers & Safetensors
- **License**: Apache License, Version 2.0
- **Copyright**: (c) Hugging Face Inc.
- **URL**: https://github.com/huggingface/transformers

### Microsoft ONNX Runtime
- **License**: MIT License
- **Copyright**: (c) Microsoft Corporation. All rights reserved.
- **URL**: https://github.com/microsoft/onnxruntime

### NumPy
- **License**: BSD 3-Clause License
- **Copyright**: (c) 2005-2024, NumPy Developers.
- **URL**: https://numpy.org/

### Pillow (PIL Fork)
- **License**: Historical Permission Notice and Disclaimer (HPND)
- **Copyright**: (c) 2010-2024 by Jeffrey A. Clark (Alex) and contributors.
- **URL**: https://python-pillow.org/

---

## 4. Microsoft .NET & Windows App SDK Dependencies

### .NET Runtime & Libraries (CoreCLR, BCL)
- **License**: MIT License
- **Copyright**: (c) .NET Foundation and Contributors.
- **URL**: https://github.com/dotnet/runtime

### Microsoft Windows App SDK (`Microsoft.WindowsAppSDK`)
- **License**: MIT License / Microsoft Software License
- **Copyright**: (c) Microsoft Corporation. All rights reserved.
- **URL**: https://github.com/microsoft/WindowsAppSDK

### Microsoft Windows SDK Build Tools
- **License**: Microsoft Software License
- **Copyright**: (c) Microsoft Corporation. All rights reserved.

---

## 5. SQLite
- **License**: Public Domain
- **Notice**: SQLite is in the Public Domain. All of the code and documentation in SQLite has been dedicated to the public domain by the authors.
- **URL**: https://www.sqlite.org/copyright.html
