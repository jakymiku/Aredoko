# P3 bidirectional incremental browsing (2026-10-23)

## 2026-10-26 現行追記
snapshotの原本guardを最大4件で並行化し、生成5万metadata/実80PNGの全payload一致と限定native15 checksを確認（`7aa2162`、[正本・測定範囲](result-sessions.md)）。初回/手動range移動時も「ページ番号/総ページ」から「保持中の先頭–末尾 / 総件数」へ表示を統一。追加読込/端移動/取消の既存表記と揃え、空結果は0件とする。後者はPortable build/コードレビュー済みで、変更後のGUIは未実施。

このPCのSDKは10.0.403へ変わり、キャッシュはruntime/Crossgen2 10.0.13。既定publishは未取得10.0.14で失敗。一律`RuntimeFrameworkVersion`はWindows SDK参照まで誤上書きするため使わない。ローカルの`data/ai-ui/snapshot-review-20261026/cached-frameworks.targets`でFrameworkReference/NET10 KnownCrossgen2Packだけ13へ指定し、`-p:CustomAfterMicrosoftCommonTargets=<当該絶対path>`・`--no-restore`でfrontend06の通常Portable/ReadyToRun publish成功。MSIXが使うBefore hookを上書きしない。追加取得/製品設定変更/警告抑制なし。失敗build01–05も保持する。この一時指定は製品依存を旧版へ恒久固定する方針ではない。

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


## 2026-10-25 先頭・末尾移動と5万件metadata
Ctrl+Home/Endで、現在の結果セッションの先頭/末尾120件へ直接移動する。ファイル名検索・棚/登録フォルダ等の条件を作り直さず、既存range契約を使う。タグeditor内の同キーは通常のカーソル移動を優先し、draftを勝手に保存/破棄しない。サイズ変更中のanchor復元と範囲取得を競合させない。

native `data/ai-ui/p3-global-edge-20261025/run04/report.json`、frontend05で14 checks PASS、4 PNG全目視、所有app exit0/残存なし。生成metadata50,000件・実PNG80枚（残りは未接続相当）で、1→50,000→1、editor Ctrl+Home無干渉、10件に検索後の末尾と範囲維持を確認。全5万実メディアの走査/thumbnail負荷ではない。UIA card 12/11/11、frontend WorkingSet 190,132,224→196,595,712→201,859,072 bytes、private 144,150,528→149,917,696→150,151,168 bytes。backendを含む専用host WorkingSet 52,887,552→54,272,000 bytes。少数のwarm-up点でありメモリ漏れ不存在の証明ではない。80原本SHA/mtime不変。

途中失敗は保存：run01は初回検索準備中の10秒待機切れ、run02は試験CLIのargs変数shadowing（対象appを後から通常WM_CLOSE、exit0のsupplement）、run03はIsEnabledが初期値trueのため準備終了を誤判定。いずれもキー操作前。run04は実測と一致する有限60秒の最初のcard待機へ修正した。failure03 PNGも目視。無変更反復や既存原本の利用はしていない。

結果の生成処理で見つけたCOUNT/OFFSET反復と検証接続の改善は[result-sessions](result-sessions.md)へ記録。初回全件snapshotの待ち時間自体は残り、瞬時表示の達成とはしない。


2026-10-25 UI-2追加：検索準備中は初回登録案内を隠し、「検索結果を準備しています…」を表示。空状態で中断したら再検索を案内し、前の結果がある場合は保持する。空棚/履歴/お気に入り/絞り込みを未登録ライブラリと区別。専用GUIの新規一連と証拠は[棚UI](shelf-ui-20261023.md)の最新節を参照。既知警告のみでfrontend06 publish成功。


## UI-2：検索ツールバーの省スペース化とfit境界（2026-10-27）

source6209c6aで重複headerを除き、共通余白8へ。種類/検索方法のaccessible name・tooltipを維持し、Filter/View両groupのDesiredSizeから折返しを決める。通常幅で右詳細を開いても実際に収まる場合は同一行に保ち、特定のwindow幅840で一律に折り返さない。音声の種別表示も「音声・音楽」へ統一。Portable publish PASS（既存picker3/SDK IL2104）。

個別許可後のDark初回はComboBoxのUIA枠がButtonより4px上下へ広いことをharnessが重なりと誤判定。矩形の垂直交差で同一行を認識する修正後、Light01/Dark02は操作非重複・詳細・grid・未保存draft保持・保存の機能確認PASS、正常exit0。query高さ32、query下からlistまで60px、詳細ありでも操作同列、list高さ560px（この生成fixture/通常window）。機能を減らさず一覧領域を広げた。

ただしPNG目視で、fitしているlistをgridへ変えると先頭thumbnailが42px（他144px）に欠ける旧reflow不具合を発見。両報告のvisual_reviewはPARTIALへ訂正。ScrollableHeight=0/offset=0を「末尾」と解釈し、新gridの末尾へ移動していた。末尾保持は元のscrollable heightが2px超の場合だけに限定する修正を追加し、frontend03へpublish済み。専用fixtureで先頭が欠けないことを追加確認する。旧試行/ログは残す。


修正source21d60e8/frontend03は個別許可後 `toolbar-reflow03` でDarkの先頭全表示・操作列・詳細・grid・draft・保存を確認。23checks/4PNG目視、元生成SHA/mtime不変、正常exit0。旧42pxだった先頭画像が他rowと同じ144px全表示へ戻った。Light/Darkのtoolbar機能確認と、この境界修正のDark実機確認を区別する。通常DB/Alpha/GPU/再生変更0。新しい全面UIの完了ではなく、主画面の一単位の改善である。


## UI-2：詳細のファイル名重複・長名を整理（2026-10-29）

source31f32dcで、タイトルと完全一致する裸の相対ファイル名だけ詳細の位置欄から省き、階層付き位置・別の表示名は保持する。詳細タイトル/位置は最大3行と省略表示、全文のアクセシブル名/tooltip・選択を維持。「元の検索に戻る」の説明をtooltipへ移し、動作は変えていない。Core表示5件/関連worker11項目・WinUI API照合/build PASS。

ZIP14/source29114e6を、専用2PNG/DB・UIAだけでLight追加1試行とDark1試行、各9checks/3PNG/正常exit0で確認。計6PNGを目視。重複位置の解消、長名の3行上限/全文到達、階層付き位置、list/grid切替の未保存タグ保持と未自動保存を確認した。初回Lightは試験側の期待件数145対fixture2で起動前停止し、そのままFAIL記録を保持。追加許可後の修正は期待件数だけ。証拠 `data/ai-ui/continuation-20261029/detail-polish-{light02,dark01}/` と別のvisual review。

この受入は詳細パネルの限定改善。小さいgridのファイル名表現や全カードの長名問題を解決済みとはせず、HC/物理DPI/実clipboard・hoverは未確認。専用以外のデータ、前面化要求、物理入力、再生、GPUを使わない。ZIP14の通常EXE起動経路の新規受入とも区別する。


## 2026-10-29 継続：小カードと棚の省略記号を枠内へ

`2f01d50`で、カード幅から固定32pxを引いていた文字幅を、Gridの実際の内容幅/星列の幅へ変更。テーマのListViewItem padding/選択borderを二重に使い潰さず、ファイル名の省略記号がclipされない。ライブラリと棚の共通helperで、サイズ/詳細開閉/選択による幅変化を追従する。棚も1行ellipsis・全文tooltip/accessibilityを揃え、モデルや検索処理は変更しない。新しい列APIはproject referencesで存在確認し、Portable build/publish成功（既存picker3/SDK trim警告は維持）。

frontend01/source2f01d50、生成2PNG/専用DB・UIAだけでLight/Dark各25checks/各7PNG目視/正常exit0。60/180%のgrid、list、棚の両layoutでtitle全名とカード内bounds・1行、棚所属、未保存タグ保持を確認。表示サイズの倍率は物理DPIの受入とはしない。captionサイズ調整に伴う全5万件性能は未計測。

上記画像では表示サイズflyoutがUIAによるnavigation後も旧位置に残ることを観測した。`cbc1c9e`でナビ/表示切替時に明示Hideし、frontend02の未確認部分だけを `card-menu-dark01` で7checks/2PNG目視/exit0確認。全25項目を無変更で繰り返さず、旧画像/報告も保持した。証拠 `continuation-20261029b/card-captions-{light01,dark01}`、`card-menu-dark01`、`caption-visual-review.json`。通常DB/Alpha/媒体原本は変更していない。
