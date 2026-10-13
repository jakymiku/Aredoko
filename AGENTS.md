# Aredoko — Codex / coding agent instructions

## Product vision — mandatory first read

**Before planning, coding, changing retrieval/ranking, selecting AI models, or changing a GUI flow, read [docs/product-vision.md](docs/product-vision.md).** It is the canonical long-term definition of what Aredoko is for: a local-first Windows media library for finding books/doujinshi **and** images, videos, audio, and creative assets through vague Japanese queries, using hybrid text/tag/semantic/visual indexing. **Do not narrow the product into an adult-book-only tagger or an EmbeddingGemma-specific app.** The model and technique are replaceable; the user-facing retrieval goal and existing non-AI features are not.

The vision defines product intent, not implementation status. The latest source, tests, [docs/codex-handoff.md](docs/codex-handoff.md), [docs/chat-handoff.md](docs/chat-handoff.md), and PR state define what actually works. If a proposed change contradicts the vision, flag it explicitly instead of silently redefining scope.

**Read [docs/codex-handoff.md](docs/codex-handoff.md) and [Issue #4](https://github.com/jakymiku/Aredoko/issues/4) before implementation.** They are the current project state and next-action checklist (2026-10-11). Some legacy READMEs/status files describe the earlier stage where the GUI framework was undecided; **the user now chose WinUI 3 for the production MVP**.

## Safe workflow
- Work on `feat/winui3-production-mvp-20261011` (or an explicitly approved successor feature branch). Confirm `git status`, HEAD, diffs, and PR dependencies before edits. Do not merge into `main`, squash the draft PR history or force-push without the user's direction.
- PR #1 is the compact Web UX prototype; PR #2 is the **separate, unmerged** read-only library index; PR #3 contains the **comparison-only** WinUI/Tauri apps and Windows benchmarks. Do not confuse the benchmarking app with the production app. Do not merge PR #2 blindly; inspect and carry over only needed safe changes.
- Create a separate production WinUI 3 + C# project. Preserve the Python stdlib + SQLite API and all existing tests and demos. **Never re-scaffold or delete** `experiments/gui-compare/winui3/generated`. Treat it as user-local state even if absent in this checkout.
- Implement the smallest working vertical slice first: launch app → local API connection → register consented **test** folder → read-only index → browse/search → edit tags/favorites → save/restart persistence. Build/verify incrementally, commit and update the handoff when you stop.
- The UI should be modern Fluent 2 and rich but lean: compact nav/search, big list, right edit pane, narrow-width drawer, accessibility, keyboard navigation, DPI, sensible loading/error/empty states.
- **No real media mutation.** Do not rename, delete, move or re-encode source files. Do not scan private media folders before explicit user selection. Do not commit personal data, absolute user paths, DBs, caches, models or credentials. Bind APIs to loopback only. Do not silently install system dependencies, change Windows settings, or download AI models.
- Observe past WinUI Release problems documented in `docs/codex-handoff.md`: .NET reflection JSON serialization may be disabled; certain managed `ListView.ItemsSource` bindings caused WinRT/ComWrappers crash; false dirty-state and async selection races. Avoid repeating them without tests.
- Run relevant tests + Windows Release build whenever possible. **If Windows native GUI cannot actually be operated in your environment, state that explicitly.** Never report screenshot/device tests as passed without running them.
- Keep PR #1/#2/#3 intact. Open a new **Draft PR** with exact results for the production MVP; do not merge it on your own.

## Where to report work
Update `docs/codex-handoff.md` with the current HEAD, implementation progress, test commands/results, blockers, next 3 actionable steps. Keep the GitHub PR description current. Mark skipped/unverified work as such rather than presenting a planned item as completed.
