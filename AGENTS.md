# Aredoko — Codex / coding agent instructions

## Start here — all development agents

The entrypoint is the repository-root **AGENTS.md** (plural, uppercase). Read linked documents before acting; this applies to Codex, Antigravity, ChatGPT and other agents.

1. [docs/product-vision.md](docs/product-vision.md): canonical product purpose and principles.
2. [docs/agent-start.md](docs/agent-start.md): current development branch, document roles and resume procedure.
3. The latest sections of [docs/codex-handoff.md](docs/codex-handoff.md) and [docs/chat-handoff.md](docs/chat-handoff.md), then [Issue #4](https://github.com/jakymiku/Aredoko/issues/4) and [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5): actual progress, tests, blockers and next work.
4. [docs/spec.md](docs/spec.md) and task-specific design documents as needed.

Product intent comes from the vision. Implementation claims come from current code, test evidence and the latest handoffs/PR. Old proposal documents and historical handoff sections do not override those. Confirm the checked-out branch; an old main checkout is not the current production worktree.

## Product vision — mandatory first read

**Before planning, coding, changing retrieval/ranking, selecting AI models, or changing a GUI flow, read [docs/product-vision.md](docs/product-vision.md).** It is the canonical long-term definition of what Aredoko is for: a local-first Windows media library for finding books/doujinshi **and** images, videos, audio, and creative assets through vague Japanese queries, using hybrid text/tag/semantic/visual indexing. **Do not narrow the product into an adult-book-only tagger or an EmbeddingGemma-specific app.** The model and technique are replaceable; the user-facing retrieval goal and existing non-AI features are not.

For video/audio content indexing and item-origin similarity search, also read [docs/media-content-plan.md](docs/media-content-plan.md), which records the user-confirmed final goal and the current implementation boundaries.

The vision defines product intent, not implementation status. The latest source, tests, [docs/codex-handoff.md](docs/codex-handoff.md), [docs/chat-handoff.md](docs/chat-handoff.md), and PR state define what actually works. If a proposed change contradicts the vision, flag it explicitly instead of silently redefining scope.

**Read [docs/codex-handoff.md](docs/codex-handoff.md) and [Issue #4](https://github.com/jakymiku/Aredoko/issues/4) before implementation.** They are the current project state and next-action checklist (2026-10-11). Some legacy READMEs/status files describe the earlier stage where the GUI framework was undecided; **the user now chose WinUI 3 for the production MVP**.

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
Update `docs/codex-handoff.md` with the current HEAD, implementation progress, test commands/results, blockers, next 3 actionable steps. Keep the GitHub PR description current. Mark skipped/unverified work as such rather than presenting a planned item as completed.
