# Aredoko — Codex / coding agent instructions

## Latest direct book-page search checkpoint (2026-10-17)

The first bounded internal-page image embedding slice is now implemented: per-book context action, explicit range (maximum 16 pages/request), profile/source revision/page provenance, reuse/atomic cancellation, book aggregation in existing visual/combined search and revision-safe reader jump. Normal AI builds still use covers; they do not silently index internal pages. Read [docs/page-image-search.md](docs/page-image-search.md) and the latest handoffs for evidence/remaining limits. Do not recreate this slice or resume OCR by default. Next: per-book indexed-page coverage/next-range UX, measured bounded multi-book jobs and representative quality. English WD labels, pending-tag semantics, simple GUI/no feature removal and P0 cumulative 1/2 remain unchanged.

## User-confirmed Japanese search over original WD tags (2026-10-17)

Keep raw English/Danbooru-style tags; do not require per-item Japanese translation. Use the replaceable embedding model for Japanese meaning search and evaluate any dictionary fallback only from actual misses. Approved tags already use normal AI text indexing; the new **separate pending-tag semantic index/search** is documented in [docs/tag-semantic-search.md](docs/tag-semantic-search.md). Pending proposals must remain unconfirmed, revision/profile bound and separate from normal tag search. Prepare their vectors only on explicit scoped AI builds, never from startup/generation/query. Preserve the literal candidate mode, review/history, source media and existing scopes. OCR deferral below stays in effect.


## User-confirmed OCR deferral (2026-10-17)

**Do not continue dedicated OCR development as the default next task.** The user explicitly decided to consider OCR only if **many content-search misses remain after EmbeddingGemma 2 direct image/page indexing is used and evaluated**. Prioritize the existing model's image/page search coverage and reviewable WD tagging. EmbeddingGemma 2 produces embeddings, not transcribed text or automatic tags; direct semantic retrieval does not prove verbatim text search. Books currently use their cover for ordinary AI image indexing: advance bounded internal-page embeddings with page/revision/model provenance before treating missing inner content as a model failure. Keep existing page-text APIs/search, fixed OCR evaluation assets and all non-AI features available. This supersedes older handoff/priority lines saying to connect an OCR adapter next. The uncommitted Windows OCR experiment was parked outside product source; it is **not** an installed/enabled/completed product feature. See [current priorities](docs/development-priorities.md).


## Start here — all development agents

The entrypoint is the repository-root **AGENTS.md** (plural, uppercase). Read linked documents before acting; this applies to Codex, Antigravity, ChatGPT and other agents.

1. [docs/product-vision.md](docs/product-vision.md): canonical product purpose and principles.
2. [docs/agent-start.md](docs/agent-start.md): current development branch, document roles and resume procedure.
3. [docs/development-priorities.md](docs/development-priorities.md): **current implementation priorities, sequencing, measurable acceptance gates and the next three coding tasks**.
4. The latest sections of [docs/codex-handoff.md](docs/codex-handoff.md) and [docs/chat-handoff.md](docs/chat-handoff.md), then [Issue #4](https://github.com/jakymiku/Aredoko/issues/4) and [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5): actual progress, tests, blockers and next work.
5. [docs/spec.md](docs/spec.md) and task-specific design documents as needed.

Product intent comes from the vision. Implementation claims come from current code, test evidence and the latest handoffs/PR. Old proposal documents and historical handoff sections do not override those. Confirm the checked-out branch; an old main checkout is not the current production worktree.

## Product vision — mandatory first read

**Before planning, coding, changing retrieval/ranking, selecting AI models, or changing a GUI flow, read [docs/product-vision.md](docs/product-vision.md).** It is the canonical long-term definition of what Aredoko is for: a local-first Windows media library for finding books/doujinshi **and** images, videos, audio, and creative assets through vague Japanese queries, using hybrid text/tag/semantic/visual indexing. **Do not narrow the product into an adult-book-only tagger or an EmbeddingGemma-specific app.** The model and technique are replaceable; the user-facing retrieval goal and existing non-AI features are not.

For video/audio content indexing and item-origin similarity search, also read [docs/media-content-plan.md](docs/media-content-plan.md), which records the user-confirmed final goal and the current implementation boundaries.

The vision defines product intent, not implementation status. The latest source, tests, [docs/codex-handoff.md](docs/codex-handoff.md), [docs/chat-handoff.md](docs/chat-handoff.md), and PR state define what actually works. If a proposed change contradicts the vision, flag it explicitly instead of silently redefining scope.

**Read [docs/codex-handoff.md](docs/codex-handoff.md) and [Issue #4](https://github.com/jakymiku/Aredoko/issues/4) before implementation.** They are the current project state and next-action checklist (2026-10-11). Some legacy READMEs/status files describe the earlier stage where the GUI framework was undecided; **the user now chose WinUI 3 for the production MVP**.

## UIを複雑にしない・機能を減らさない（ユーザー指示、2026-10-16）

**本番のGUIは日常の検索・閲覧・整理に集中できる簡潔な構成にする。機能削減によって簡潔に見せてはならない。** AIエージェントのテスト都合で、検証用の長文・内部ID・実装説明・注意書きを通常画面へ追加し続けない。テスト手順/検証注記は文書・ログ、操作識別はAutomationIdに置く。

- 普段使う操作を前に出し、管理操作は名前付きツール、詳細条件やモデル版・前処理は説明/折りたたみへ整理する。既存機能・情報は到達可能なまま保持し、消去・恒久無効化・API撤去で代用しない。
- エラー、未保存、取消/進捗、元ファイル変更、未承認タグ、現在の検索範囲など、判断に必要な状態は常時分かる形にする。安全や検索範囲の警告を詳細の中へ隠さない。
- 長い技術説明より短い自然な日本語を使い、同じ説明やボタンを重複させない。必要な説明・根拠・モデル由来は任意に確認できる。新機能も既存の導線へ統合し、画面/設定を無制限に増やさない。
- 整理した操作へのマウス/キーボード導線、Light/Dark、狭幅、未保存編集、既存の検索/登録/読書/承認を検証する。AI用テストの古い見た目の期待に合わせて製品GUIを再び散らかさず、テストを新導線へ更新する。

## Latest integration checkpoint (2026-10-17)

Open Code through `8e90a02` is integrated; do not recreate its animation/video/page-text/purge features. Subsequent review reproduced and fixed legacy text-only freshness skipping new image/video preprocessing, purge missing the real profile sidecar DBs/video frames, large purge SQL variable overflow, and revision-unbound text-to-reader jumps. Read the latest handoffs. Python412 PASS/3 SKIP (415 total), Core370, Release0 warnings/errors and native current/stale page-jump37 checks/8 inspected PNGs pass. Per-item `ai_source_contracts` updates visual inputs on an **explicit scoped AI rebuild**, reusing text vectors and preserving model namespaces/ranking; no automatic private reindex. Profile DB purge is per-file atomic; failure retains manual catalog records for retry, not a global all-DB atomic guarantee. Frozen Japanese OCR evaluation8 pages/10 queries and CER/retrieval scoring now exist ([docs/ocr-evaluation.md](docs/ocr-evaluation.md)); **real OCR is still unconnected/unmeasured**, and scoring controls are not OCR accuracy. Next: consented bounded OCR adapter and real evaluation, then representative tag quality and multi-page provenance. No new downloads/private scan/CI; P0 trials1/2.

## Latest user-feedback checkpoint (2026-10-16 All 22 feedback items implemented & Windows-validated)

Read the latest handoff before continuing. All 22 items in [docs/user-feedback-20261016.md](docs/user-feedback-20261016.md) are now implemented and validated: viewing history (`view=history`), unreviewed in search options, footer Settings, wheel/X viewer navigation (images and reader), recursive registration, common shell/properties actions, video control improvements (double-click entry, canvas click, right volume slider, common context menu), **safe inactive-root DB purge (F21: `POST /api/library/roots/purge`, `PurgeFolder<id>`, monotonic root IDs via `library_root_seq`)**, **bounded GIF/WebP/APNG animation playback & 54,802KB large APNG handling & representative-frame AI indexing (F07/F08/F11)**, **WinUI page-text search & direct matched-page reader opening (`ModePageText`, `PageTextEvidence<id>`, `PageEvidenceClient`)**, and **time-coded video content AI indexing & matched-timestamp playback (F12: `ai_video_frames`, `video_match_ms`, `VideoPlayerView` initial timestamp seek)**. Python **397 run (394 PASS / 3 Windows platform SKIP)**, Core **361 PASS**, and x64 Release **0 warnings / 0 errors** pass. Native GUI batches pass: folder/reader/settings/purge **`feedback-antigravity-20261016-13` (98 checks PASS / 19 PNGs)**, video seek/double-click/context/time-coded AI **`feedback-video-ai-20261016-02` (106 checks PASS / 56 keys / 24 PNGs)**, animation/54.8MB APNG **`feedback-animation-20261016-01` (16 checks PASS / 4 PNGs)**, and candidate + page-text search **`page-text-search-20261016-01` (29 checks PASS / 5 PNGs)**. Real OCR adapter connection, multi-page situation-tag provenance, and audio/music content indexing remain future slices. Preserve P0 trials 1/2, local-only tests and all features.

## Current user-feedback work (2026-10-16)

The user reported22 concrete runtime/UX issues. Read [docs/user-feedback-20261016.md](docs/user-feedback-20261016.md) before choosing the next slice; this current direction precedes the older resume list. Confirmed: mouse X buttons navigate images/pages inside viewers; left-nav Unreviewed becomes Viewing history, while the unreviewed filter remains in search options. Put app settings at the left-nav bottom, clarify search names, preserve all features and source files. Animation/large-image/video content indexing and inactive-root DB purge require their own bounded data-safe implementation/tests; do not claim them fixed through UI labels alone.

## Current product-development emphasis (2026-10-15)

**Read [docs/development-priorities.md](docs/development-priorities.md) before choosing the next feature or continuing implementation.** The user wants development effort redirected from generic viewer/player polish toward **finding the right local item**: (P0) search quality evaluation and evidence-led ranking improvements, (P1) image/item-origin right-click similarity search, (P2) OCR, reviewable AI tag suggestions and multi-page situation-tag understanding. After that, advance logical folder-book grouping and time-coded video/audio content indexing in small independently tested slices. These are priorities, **not completed features or an instruction to discard existing functions**.

A future agent should inspect the latest code/PR/handoff first; then select the highest-priority unfinished vertical slice, implement it and run targeted local tests rather than stopping at planning. Preserve text search, manual metadata, scopes, native viewer, privacy rules and WinUI-only GUI direction. Measure retrieval success (Top1/Recall@5/MRR, no-answer behavior and time to find) and explicitly separate synthetic benchmarks from real-life quality. No private library scanning or model/dependency downloads without explicit permission. Major regressions and data-safety blockers override feature ordering.

## Current checkpoint (2026-10-16 P2 foundation & explicit candidate search)

P1 similarity and registered-folder hub are implemented and Windows-validated. The new P0 v7 baseline was frozen before inference and measured once on generated sources with the existing CUDA model. P0 closes with **1/2 cumulative improvement trials**, one adopted empty-cover-pool inference optimization, and no ranking/threshold/routing tuning. Read [docs/search-phase-v7-results.md](docs/search-phase-v7-results.md). P2 now has a backend provenance/review/cancel API foundation, native review UI (`TagSuggestionsView`), and an explicitly separate unapproved candidate search mode (`POST /api/library/tag-suggestions/search`, `ModeTagCandidates`); read [docs/tag-suggestions.md](docs/tag-suggestions.md). The user explicitly approved WD model/runtime installation and generated-only CPU validation. Capped setup completed with all 46 existing package versions unchanged, and the actual WD CPU/API smoke passed 35 checks with all four owned workers stopped. Read [docs/wd-tagger.md](docs/wd-tagger.md). This is runtime validation, not real-library tagging quality. Native review supports generation/provenance/edit approval/rejection/history/cancel (`59 checks PASS / 15 PNGs`), and explicit candidate search (`ModeTagCandidates`, `ProposalEvidence<id>`) passed **337 Python tests / 305 Core tests / Release 0 warnings 0 errors / 24 native GUI checks (4 Light/Dark wide & narrow PNGs visually reviewed)** on generated media without mixing unapproved proposals into confirmed tag search. Representative asset tagging quality evaluation, OCR, and multi-page situation-tag provenance remain unfinished. New downloads outside this specific consent still require permission. Do not consume the remaining P0 trial budget or reopen P0 without new evidence/user direction.

## Latest Windows integration checkpoint (2026-10-16)

The backend through `ad850aa` is integrated, not unfinished work to recreate. Windows Core320 and final x64 Release pass. The later user-directed UI cleanup retains all features: Tools contains AI preparation/related terms, search explanations and tag model details are available on demand, while warnings/dirty/scope/evidence remain visible. Native generated-only cleanup/folder-book checks64 and search-mode checks63 pass; all20 Light/Dark normal/narrow PNGs were visually reviewed. The previous reader bottom strip, old-token GUI rescan and restart gates are now validated. Read the latest handoffs for exact evidence and the UI simplicity rule above before adding controls or test-oriented copy. Production Python did not change in this UI slice (previous381 passed/3 skips). Real OCR and dedicated page-text WinUI remain unconnected; default extraction503, P0 trials1/2, no CI/download/private scan.

## Latest folder-book checkpoint (2026-10-16, no Windows device)

P3's opt-in folder-book backend has deterministic natural-name ties, bounded preview/tag inputs, before/after source checks and per-directory scan aggregation. Read [docs/folder-books.md](docs/folder-books.md) and the latest handoffs. **Existing folder-book roots need one rescan for the `folder-book-v2` token; item IDs and manual metadata stay intact.** Python 353 tests pass on Linux; this does not validate Windows Release/XAML/native GUI. No P0 trial, real-model download or CI run was added. The previous P2/P1 Windows evidence remains historical evidence for those revisions.

## Latest page-evidence checkpoint (2026-10-16, continued without Windows)

P2/P3 now have opaque page IDs, revision-bound page snapshots/evidence retrieval, optional atomic/cancellable page-text extraction storage and **explicit page-text search**, separate from normal/AI/tag-candidate search. Read [docs/page-evidence.md](docs/page-evidence.md). Images, ZIP/CBZ and opted-in folder books share the contract. **The real OCR adapter and dedicated WinUI flow remain unconnected; default extraction is 503.** Generated-only Python validation is **383 PASS / 87.094 seconds / skip 0**. This is persistence/provenance/HTTP validation, not OCR accuracy or Windows validation. C# changes are error translations only; no .NET SDK is available here. Preserve P0's 1/2 cumulative trials and cover-only tag review. Next: fixed OCR evaluation fixtures/scoring, a consented bounded local OCR adapter, then native evidence review and multi-page proposal integration; retain the pending P3 Windows gate.

## Registered-folder management — user-approved next UX slice (2026-10-15)

Read [docs/folder-library-management.md](docs/folder-library-management.md) before folder navigation, search-root selection or folder settings work. The user approved one left-nav entry opening a main-view list/grid, multiple-root search shared by text/AI/similarity, and editing existing **initial shelf** / exclusions / scan / unregister settings there. Initial shelf is not a new tag feature. Preserve individual metadata; batch edits save only changed fields, and empty/stale selections must not broaden to all roots. Saved scope shortcuts/pins are later work.

**OpenCode is actively developing in the user's local worktree. This update is documentation only.** Finish or safely checkpoint the current task before adopting this UX slice; inspect local uncommitted changes and current remote first. Never reset/rebase/overwrite another agent's live work or assume the document writer saw local progress. Use the latest implemented state, not the old handoff snapshot. This is a focused usability change, not authorization for a full visual redesign.

## Long-term Windows visual direction (not a current PoC requirement)

The **current WinUI 3 GUI is intentionally a plain, mostly monochrome proof of concept**, not the final intended look. Once core search, indexing, reader, tagging, performance and stability are established, evolve the **native WinUI 3 frontend** toward a **polished dark creator-oriented UI combined with a cover/artwork-first visual library**. Keep the compact search and navigation, spacious grid/list area and right-side details/tag editor; use restrained violet/blue accents, coherent Fluent 2 design tokens, typography, icons and subtle transitions, without sacrificing image visibility or accessibility. **Read [docs/design-vision-winui.md](docs/design-vision-winui.md) before future UI design work.** The direction is a future milestone, **not permission to redesign the current PoC now**; no WebView/Electron/Tauri migration for aesthetics. Preserve fast scrolling, low UI overhead, keyboard/focus behavior and Windows-native operation. Continue to treat Linux/backend development as valid; Windows Release/native visual validation remains required for GUI claims.

## Safe workflow
- Work on `feat/winui3-production-mvp-20261011` (or an explicitly approved successor feature branch). Confirm `git status`, HEAD, diffs, and PR dependencies before edits. Do not merge into `main`, squash the draft PR history or force-push without the user's direction.
- PR #1 is the compact Web UX prototype; PR #2 is the **separate, unmerged** read-only library index; PR #3 contains the **comparison-only** WinUI/Tauri apps and Windows benchmarks. Do not confuse the benchmarking app with the production app. Do not merge PR #2 blindly; inspect and carry over only needed safe changes.
- Create a separate production WinUI 3 + C# project. Preserve the Python stdlib + SQLite API and all existing tests and demos. **Never re-scaffold or delete** `experiments/gui-compare/winui3/generated`. Treat it as user-local state even if absent in this checkout.
- Implement the smallest working vertical slice first: launch app → local API connection → register consented **test** folder → read-only index → browse/search → edit tags/favorites → save/restart persistence. Build/verify incrementally, commit and update the handoff when you stop.
- The UI should be modern Fluent 2 and rich but lean: compact nav/search, big list, right edit pane, narrow-width drawer, accessibility, keyboard navigation, DPI, sensible loading/error/empty states.
- **No real media mutation.** Do not rename, delete, move or re-encode source files. Do not scan private media folders before explicit user selection. Do not commit personal data, absolute user paths, DBs, caches, models or credentials. Bind APIs to loopback only. Do not silently install system dependencies, change Windows settings, or download AI models.
- Observe past WinUI Release problems documented in `docs/codex-handoff.md`: .NET reflection JSON serialization may be disabled; certain managed `ListView.ItemsSource` bindings caused WinRT/ComWrappers crash; false dirty-state and async selection races. Avoid repeating them without tests.
- Run relevant tests + Windows Release build whenever possible. **If Windows native GUI cannot actually be operated in your environment, state that explicitly.** Never report screenshot/device tests as passed without running them.
- Keep PR #1/#2/#3 intact. Continue the existing **Draft PR #5**, based on `feat/gui-framework-comparison-20261010`, with exact validation results. Do not create a duplicate production PR or merge it on your own.

## CI usage — agent-discretionary single-run policy

**GitHub Actions CI is a scarce resource. The user reports the monthly ~2,000-unit allowance is already exhausted until next month. Do not waste it.**

- **Default: local tests only.** Use targeted Python/.NET tests, static checks, and real Windows Release/native GUI validation when available; if Windows or another dependency is unavailable, mark the check unverified.
- **No CI for routine commits, documentation, formatting, minor refactors, or repeated confidence checks.** Avoid push/PR events that would unintentionally trigger CI; check workflow triggers before pushing.
- Once the quota is usable, an agent **may start exactly one deliberately scoped GitHub Actions CI run for a specific substantial change or an essential integration/platform check that cannot reasonably be completed locally**. **No separate user approval is required for that single warranted run.** First state internally/record in handoff why it is needed, what will be tested, and the anticipated workflow/cost.
- **Never automatically rerun failed or cancelled CI, retry in a loop, launch multiple workflows, or rerun merely to obtain a green badge.** If the single run fails, investigate locally and report the failure; a *new* run must be independently justified as genuinely necessary, not an automatic retry. Prefer to defer CI and ask for guidance if unsure.
- **While the currently exhausted quota remains unavailable, do not dispatch CI**; preserve work and record pending Windows/CI checks. No agent should change quotas, billing, workflow triggers or spending settings to circumvent the limit.
- The desired workflow trigger policy is **manual `workflow_dispatch` only**: no automatic `push`, `pull_request`, `schedule`, or `workflow_run` triggers for resource-consuming CI. Confirm the real `.github/workflows/*.yml` / `*.yaml` files and update them safely when accessible. Writing this instruction alone does **not** disable existing GitHub Actions triggers.
- Documentation-only changes require content/link validation, not CI. Never claim an unrun check passed.

## Where to report work

For item-origin similarity Windows validation, read [docs/windows-similarity-handoff.md](docs/windows-similarity-handoff.md). `Check-Similarity.cmd` runs existing local Python/Core/Release gates and the generated-media native batch once, without downloads or CI. Native automation code being present is not proof it has passed: inspect its result/logs and every PNG before recording GUI/visual success.

Update `docs/codex-handoff.md` with the current HEAD, implementation progress, test commands/results, blockers, next 3 actionable steps. Keep the GitHub PR description current. Mark skipped/unverified work as such rather than presenting a planned item as completed.
