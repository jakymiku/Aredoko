# P3 bidirectional incremental browsing (2026-10-23)

Source implementation follows the integrated roadmap; **native acceptance remains pending**. This is not a full-list scrollbar backed by all metadata: the standard ListView continuously extends near either edge and evicts distant metadata. At most600 rows/keys in its UI buffer; ResultWindow separately retains at most5×120 backend-derived rows. These are two bounded stores, not a combined600-object/RSS guarantee. No all-result UI or metadata array.

ResultBuffer accepts only adjacent, same-total, unique-ID ordered ranges; invalid ranges leave its state unchanged. Forward overflow evicts the head; backward overflow evicts the tail. Native source connects the internal ListView ScrollViewer, fetches up to120 through the existing authenticated ResultWindow, updates observable native-string keys without replacing all containers, and compensates a retained visual anchor when trimming/prepending. It does not rank/filter on the frontend. Cancellation, session identity, buffer identity and source guards are retained. Fetch failure stops automatic retries and keeps the error visible. Dirty editor fields are not saved/discarded by scrolling; existing transitions own search/navigation.

Viewer initial ordinal and return-selection now use the buffer's global start, independent of the old60/20-page boundary. Manual previous/next remain as range-jump compatibility. Layout toggles keep current keys; source loading subscriptions are attached before an image joins its live template. List/grid panel CacheLength is1 viewport to reduce offscreen thumbnail competition; this is not a measured latency win.

## Evidence

Core Release873 PASS assertions, including6 new cases: exact60/61 and120/121 order, full50k forward/backward traversal with600 retention, gap/duplicate/changed-total rejection without partial publication. Existing result window/session tests retained. Portable x64 build0 errors/3 known WUI1001 warnings11.49s. Final guard/compatibility/anchor refinements use supported existing APIs; next native publish compiles them. No backend changes, no repeated broad Python suite, no dependency/model/CI/private data changes. No new native run yet; prior card-only flow3/3 is preserved separately.

## Next acceptance / open work

A newly justified **continuous-browse** flow (not another card-only replay) should use145+ generated items, cross60/120 without pressing Next, reverse-scroll, verify viewer return/ordinal and retained dirty selection. A larger generated metadata scroll should exercise head eviction/prepend and report realized/retained counts. Limit to3 attempts and preserve every failure. Current card-only screenshots show blank/late thumbnails; do not claim thumbnail completeness/speed. High Contrast/DPI/Light, whole-process RAM, full UI polish, multiple shelves, online backup, AI download/distribution and real audio remain in the roadmap.

## Native boundary follow-up (`6c29048`, current)

Continuous flow **3/3 consumed**, no fourth run or renamed replay. All test processes exited0 normally, no remaining Aredoko.WinUI process after03. New isolated Portable frontend candidates only; installed Alpha/basic03/shortcuts untouched.

- `data/ai-ui/p3-continuous-20261023-01/run01`: FAIL before first item. Actual trimmed ItemsSource marshalling NullReferenceException in WinRT.GetAbiToProjectionVftblPtr. No screenshot delivered in this early runner; original commands/report retained.
- `.../p3-continuous-20261023-02/run02`: FAIL at same point after external-type attribute alone. Failure PNG reviewed. It was not fixed until unsafe source generation was enabled.
- `.../p3-continuous-20261023-03/run03`: generated745 catalog/native initial viewport/realized card bound PASS; 1–180/745 extension PASS; actual viewer60→61→60→61 position checks PASS. It then failed the right-detail return assertion (still059). The harness waited for changed sequence identity, not final image decoding/content-open completion, before closing. Product records the last actually decoded ContentOpened, so close-before-ready is consistent with that result; this is not proof of either correct or broken return after a fully displayed61st image. A source-only wait for ImageFit enabled has been added; **UNRUN**, no success claim. Tail/head eviction/reverse/draft/source invariance were not reached. Initial/failure03 PNGs reviewed (three PNGs total across all runs).

Fix: explicit `[assembly: GeneratedWinRTExposedExternalType(typeof(ObservableCollection<string>))]` and AllowUnsafeBlocks=true enable existing CsWinRT generator; no dependency/optimizer-disable/trim suppression. Generated CPU output `data/ai-ui/p3-abi-generated-20261023` contains actual ObservableCollection<string> IList_string/IEnumerable_string vtable lookup and VideoRandomAccessStream vtables; build0 errors/known3 warnings11.67s. All3 Portable publishes succeeded (known SDK trim warnings). This is generated ABI code, not arbitrary runtime code generation. Official rationale: https://github.com/microsoft/CsWinRT/blob/master/docs/aot-trimming.md (external generic types and AllowUnsafeBlocks).

Harness now captures failure tree/PNG, hashes actual app DLL plus worktree diff for provenance, closes owned child/parent windows normally and disposes backend result/animation/thumbnail/setup owners. Final runner AST2 PASS; no extra GUI. Current source remains P3 PARTIAL, thumbnail latency/HC/DPI/memory/main-UI and fully loaded viewer return unaccepted. Do not spend another same-flow attempt under a new name. Continue independent P4 backend while preserving the native gate for renewed scope/permission.


## 2026-10-24 実修正後の継続確認（最新）
現在の[テスト方針](local-test-policy.md)に従い、旧3回の失敗を保持して、既知のContentOpened待ち修正と独立LOCALAPPDATA/DBを使った関連確認を行った。旧成功の再演や無変更でのcap復活ではない。
- `data/ai-ui/p3-content-ready-20261024/run01`：完全に画像表示を待った60→61→60→61とdetailへの61番復帰はPASS。未保存editorの×を閉じるだけで破棄dialogを出す製品バグに到達、全体FAIL。cleanupも既存dialog中のcloseで失敗したためrawを保持。専用生成draftを明示破棄→通常WM_CLOSEで所有PID47472終了を確認（元runnerのexit codeは欠測）。
- 修正：メディア/登録フォルダの詳細を隠すだけなら選択/編集baseline/draftを保持する。別アイテム選択・画面移動・終了時の破棄確認は維持。仮想化で同じ論理IDが再選択されてもdraftを再読込しない。
- run02：追加取得/隠したdraftは進んだが、600件超でheadを外す際の遅延native scroll補正が逆方向読込を呼び、61–660から1–600へ戻った。修正はanchorのScrollIntoViewとChangeViewを低優先queueで順にsettleし、extending/transition所有を完了まで維持する。画面履歴の同じanchor呼出しもawaitへ更新。
- 初回publishは旧呼出し1箇所の更新漏れCS0103→WMC cascadeでFAIL、修正後publish成功。run03/04はUIA peerの一時不在と初回legacy page labelに対するハーネスの早すぎる厳密lookupでFAIL。PNGにfooterが存在する証拠を保存し、25回のbounded predicate内で有効なrangeを待つよう修正。範囲を架空60へ置換するfallbackを撤去。cleanupはwindow消滅とprocess exitの時間差も扱い、強制終了しない。
- **run05 / frontend02 PASS**。source `28d5e7b`＋reportのsource一覧/差分SHA、app DLL SHA。range1–180→1–540→61–660→146–745（保持600以内）→26–625→1–600。元61番のhidden draftを保持し、明示Saveだけで専用DBへ反映、元745 PNGのSHA/mtime不変。3 PNG全目視、app正常終了0、所有process残存なし。Coreは変更しておらず直前1019を反復せず、Portable関連publishだけを行った。
- ここでの末尾到達は「末尾を含むrangeの取得」。実画面の最終745番row表示、120↔121のnative操作、全検索方式/条件、grid/HC/DPI、RSS、全thumbnail速度は引き続き未受入。先頭/失敗PNGの遅いthumbnailを速度合格とはしない。


## 2026-10-25 物理末尾行・サイズ変更の限定確認

745生成画像/独立DB・Light・専用Portableで、range取得だけでなく745番の実カード表示を確認する新しい残件caseを実施。run01は読込完了で非表示になるPreviewStatusをカード数と数えたハーネス誤りでFAIL。実カード `Item<id>` のUIA keyを数える修正後、run02で末尾list→grid切替がrange146–745から26–625へ逆方向fetchし、157番付近へ戻る**製品バグ**を再現。どちらも元log/PNGを保持、所有app通常exit0。

修正はlayout/size変更中を `browseReflowing` で追加読込から隔離し、変更前のanchor・末尾位置・session/buffer範囲を保持する。変更後のlayoutをawaitして、同一session/範囲の場合だけanchorを復元する。末尾にいた場合は末尾へ合わせ、再帰したsize通知は同じreflowへまとめる。別検索へ古い位置を適用しない。選択/未保存draft/既存原本guardは維持。

`data/ai-ui/p3-tail-20261025/run03` / `continuation-20261025/frontend02` PASS。物理745番list→grid→180/60/100%で表示を保持、draft未保存を保全し自動保存0、逆方向1番を物理表示、range保持600以内、生成745原本SHA/mtime不変、app exit0/残存なし。4 PNGを目視。最初のthumbnail未完了PNGは速度合格に使わない。倍率180/60はUIA座標・draft確認で、各倍率ごとのPNG目視は未実施。

所有WinUIの単回WorkingSet bytesは初期178,749,440、list末尾202,395,648、grid倍率変更後237,703,168、先頭復帰246,673,408（Private bytesはreport参照）。UIA keyを持つカード12/12/10/18。これはwarmingとlayout変更を含む4点で、実現全オブジェクト数やリークなしの証明ではない。5万件・長時間RSS・HC/実モニターDPIの受入は残る。関連Portable publish成功/既知warnings、Coreは無変更なので全Core反復なし。
