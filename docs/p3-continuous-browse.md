# P3 bidirectional incremental browsing (2026-10-23)

Source implementation follows the integrated roadmap; **native acceptance remains pending**. This is not a full-list scrollbar backed by all metadata: the standard ListView continuously extends near either edge and evicts distant metadata. At most600 rows/keys in its UI buffer; ResultWindow separately retains at most5×120 backend-derived rows. These are two bounded stores, not a combined600-object/RSS guarantee. No all-result UI or metadata array.

ResultBuffer accepts only adjacent, same-total, unique-ID ordered ranges; invalid ranges leave its state unchanged. Forward overflow evicts the head; backward overflow evicts the tail. Native source connects the internal ListView ScrollViewer, fetches up to120 through the existing authenticated ResultWindow, updates observable native-string keys without replacing all containers, and compensates a retained visual anchor when trimming/prepending. It does not rank/filter on the frontend. Cancellation, session identity, buffer identity and source guards are retained. Fetch failure stops automatic retries and keeps the error visible. Dirty editor fields are not saved/discarded by scrolling; existing transitions own search/navigation.

Viewer initial ordinal and return-selection now use the buffer's global start, independent of the old60/20-page boundary. Manual previous/next remain as range-jump compatibility. Layout toggles keep current keys; source loading subscriptions are attached before an image joins its live template. List/grid panel CacheLength is1 viewport to reduce offscreen thumbnail competition; this is not a measured latency win.

## Evidence

Core Release873 PASS assertions, including6 new cases: exact60/61 and120/121 order, full50k forward/backward traversal with600 retention, gap/duplicate/changed-total rejection without partial publication. Existing result window/session tests retained. Portable x64 build0 errors/3 known WUI1001 warnings11.49s. Final guard/compatibility/anchor refinements use supported existing APIs; next native publish compiles them. No backend changes, no repeated broad Python suite, no dependency/model/CI/private data changes. No new native run yet; prior card-only flow3/3 is preserved separately.

## Next acceptance / open work

A newly justified **continuous-browse** flow (not another card-only replay) should use145+ generated items, cross60/120 without pressing Next, reverse-scroll, verify viewer return/ordinal and retained dirty selection. A larger generated metadata scroll should exercise head eviction/prepend and report realized/retained counts. Limit to3 attempts and preserve every failure. Current card-only screenshots show blank/late thumbnails; do not claim thumbnail completeness/speed. High Contrast/DPI/Light, whole-process RAM, full UI polish, multiple shelves, online backup, AI download/distribution and real audio remain in the roadmap.
