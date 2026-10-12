# WinUI 3 production MVP — developer preview

Latest validation (2026-10-12): Python117 tests, C#15 checks and x64 SelfContained Release pass (two existing IL2104 warnings). Generated 17-item native AI/editor/appearance flow was previously verified at 105 checks / 17 screenshots. Resource-native-06 passes 155 functional assertions with 23 screenshots reviewed and eight graceful closes. Light/Dark saved/restarted values are visible, but release feedback is a clipped 1px UIA peer and absent from its screenshots. Visual sign-off remains pending; the final minimum-height guard has CPU regression coverage but has not been rerun natively. GitHub CI jobs on e3caae4 never started due account billing/spending limits (see current handoff). Offline EG2 text+cover scaling passes through 10,000 generated works with 768px covers and long Japanese tags, including cancellation, restart and inference-free cached rebuild. Production HTTP paging/kind/favorites also pass at 10,000; see [index-scaling.md](index-scaling.md). This is still a developer preview; native-GUI 10,000 load, real-library/1TB, high-DPI/Contrast/screen-reader, AOT and installer remain unverified.

AI索引 also offers manual model release, opt-in idle release and cancellable index pacing (defaults disabled). Saved vectors survive release; the next AI search reloads the same model. Settings apply immediately without reindexing. Actual owned-worker exit/reload passes 30 CUDA checks; see [ai-resource-policy.md](ai-resource-policy.md).

Run from the repository with `pwsh -File tools/start-winui.ps1`. Requires the already installed Python, .NET 10, Windows App SDK/WinApp CLI development prerequisites. The launcher builds and registers a development package; it is not an end-user installer. No dependency or model installation is performed by this script.

The launcher starts the production-only API on `127.0.0.1:8769`, refuses an occupied port, and stops only its own backend when the window exits. Persistent catalog: `%LOCALAPPDATA%/Aredoko/catalog.sqlite`; logs: `%LOCALAPPDATA%/Aredoko/logs`. A custom `-Database` may be supplied. Do not put the database under a library root. The Web demo on port 8765 remains separate.

Use フォルダ管理 to select a **test folder**, explicitly consent, register and scan. Registration alone does not scan. The default search matches filenames/tags. AI意味検索 and AI画像・表紙 are now optional modes, prepared from AI索引; see the AI section below. Sixty records are loaded per page. Select a record to edit tags, shelf, favorite and reviewed status, then save. Ctrl+F focuses search, Ctrl+S saves. Narrow windows use a details drawer.

Scanning reads directory entries and filesystem metadata only, skips links/reparse points and preserves missing locations. A failed or cancelled scan rolls back the partial index. Resume currently means a fresh atomic traversal, not a checkpoint resume. A process crash is marked interrupted on the next start. Metadata publication is repaired on startup if interrupted after the index commits. Paths identify records; moved files are not automatically matched. Folder contents are indexed as individual files, not grouped books yet. ZIP/CBZ first-image previews are read in memory; nothing is extracted to disk.

Excluded records retain annotations but disappear from search after a rescan. Offline roots are shown in folder management and failed scans preserve previous records. Large scans use one SQLite write transaction; metadata edits, root registration and exclusion changes return HTTP 409 promptly while a scan is active (the editor retains changes for retry after the scan). This first slice has not been benchmarked against 1 TB of real media.

Batch updates remain available in the original API; the new native editor edits one record. Readers, Komga, OCR, folder-to-book grouping, move tracking, advanced shelves and installer distribution remain outside this slice. The initial optional EmbeddingGemma 2 slice is described in [ai-search-plan.md](ai-search-plan.md).

Validation:
```
python -m unittest discover -s tests -v
dotnet run --project tests/Aredoko.Core.Tests -c Release
dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64
```

Native GUI regression: launch with a **fresh dedicated test database**, then run `pwsh -File tools/test-winui-local.ps1 -AppPid <actual PID>`. The script operates a local window and creates 75 fictional fixtures under ignored `data/mvp-ui/<run-id>`. It requires a fresh catalog and never targets private roots. The launcher was also tested through close/restart; saved tags were read back in WinUI. Screen capture was visually reviewed at 100% DPI/dark theme. The preview test also operated the details drawer at 700px width. Later Light/Dark coverage is recorded above and in ui-polish.md; other DPI/Contrast/screen-reader checks remain pending. WinUI analyzer is not installed; no analyzer result is claimed. SDK trim warnings IL2104 remain and Native AOT has not been tested.

Image and book previews:
- Registered present images and the first supported image in CBZ/ZIP appear in lists, tiles and details. Archive entries sort naturally (page 2 before page 10). PDF, video, audio, unsupported, changed, oversized and corrupt sources show a fallback label.
- PNG/JPEG/WebP/GIF/BMP encoded source limit: 8 MiB; decoder validates at most 16 million pixels. Size/mtime changes require a rescan. Current exclusions, presence and path boundaries are checked again before reading.
- Archive limits: 512 MiB archive, 4 MiB central directory, 10,000 entries, 8 MiB selected image, compression ratio at most 200. Encrypted, split and unsupported ZIP64 boundary cases fall back. No archive member is written to disk.
- Two workers derive at most 256px PNGs in a 64-entry memory LRU keyed by root/id/mtime/size. Visible rows load asynchronously, unload cancels and clears images; stale selections cannot replace the current detail image. No persistent thumbnail cache or new codec package.
- Fixture creation: python tools/create_preview_fixture.py --output <new test directory>. Launch with a fresh dedicated DB, then pwsh -File tools/test-preview-ui-local.ps1 -AppPid <PID> -FixtureDirectory <fixture directory> -ArtifactDirectory <ignored artifact directory>.
- Earlier preview-specific verification: 40 Python tests, 13 pure-C# checks, Windows Release build, native preview test and original metadata regression passed. Generated fixture hashes remained unchanged. Sandbox executable is absent; native tests ran on local Windows. No private media was scanned.

Production API additions (same existing catalog routes):
- `GET /api/session`: production mode and per-process token.
- `GET /api/library/roots`, `GET /api/library/scan`: require session token.
- `POST /api/library/roots`: absolute path, `consent:true`, optional excludes; registers only.
- `POST /api/library/excludes`: root_id and patterns replace custom exclusions (built-in exclusions remain).
- `POST /api/library/scan`: root_id, starts one background scan.
- `POST /api/library/cancel`: requests rollback of the running scan.
All writes require the token and matching loopback Origin. Catalog search adds relative_path, availability, root_id, mtime_ns and size_bytes to records. Missing records are retained; excluded records are hidden from search.

Preview route: GET /api/library/preview/<id> requires the session token and accepts only an indexed ID. It returns bounded encoded source bytes, 404 for fallback and 503 when both reader workers are busy.

AI search developer preview:
- Explicit project setup: pwsh -File tools/setup-ai.ps1 -InstallAndDownload. It uses existing Python3.11 in .venv-ai and a pinned local model under models, with a shared 6 MB/s download cap. No system driver/SDK changes. Setup has been performed on this machine with user approval.
- In WinUI: consent/register/scan a test folder, click AI索引 then 索引を作成・更新. Choose AI意味検索 or AI画像・表紙 and enter a description. Normal 名前・タグ remains available. Current cap: earliest 2,000 eligible records; inspect progress and cancel in AI索引.
- Text/cover input only. PDF/video/audio names and tags can be searched, but their contents and book interiors are not analyzed. Actual user-library accuracy is unverified. Broad combined scoring is experimental; choose visual mode for visual queries.
- The sibling <catalog>.ai.sqlite contains vectors/checkpoints; keep catalog/cache outside library roots. Updates to title/tags/source revision require AI index update; stale revisions are not ranked. Current exclusions and metadata filters apply when searching.
- AI failures preserve normal search. Runtime never downloads weights. The owned worker is stopped when its backend parent exits. Laya is pending.
- Manual actual-model smoke: python -X utf8 tools/test_ai_model.py --output <new ignored output directory>. Native actual-model flow: tools/test-ai-ui-local.ps1 with a fresh DB/PID and generated fixture/artifact directories. These operate generated test files only.

- Native actual-model verification (2026-10-12): full generated-17-item flow **PASS**, plus close/restart tag and AI-vector persistence **PASS** without reindexing. Use pwsh -File tools/test-ai-ui-local.ps1 -AppPid <PID> -FixtureDirectory <generated-17-item fixture> -ArtifactDirectory <new ignored evidence directory> for the fresh DB, then close/relaunch with the **same dedicated test DB** and add -RestartOnly with a new artifact directory. The fixture is produced by test_ai_model.py. UIA popup selection is HWND-scoped; startup waits handle the CLI's string-valued IsEnabled. Screenshots are manually reviewed; no private sources or models are committed.

Model selection: use -AIProfile <local JSON> with start-winui.ps1; omit it for the original EmbeddingGemma 2. Model-specific vectors/checkpoints stay separate and changing weights requires index creation for that profile. See [model profiles](model-profiles.md) for adapters, prompt/precision settings and rollback. Switching never downloads weights.


Developer appearance checks: `tools/start-winui.ps1 -UITheme System|Light|Dark` affects only the launched app root; System is the default and follows Windows. No theme preference is persisted and no OS setting is changed. The latest native appearance/error-recovery results and pending dialog visual rerun are tracked in [ui-polish.md](ui-polish.md).
