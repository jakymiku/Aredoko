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

### 2026-10-29d：検索・表示操作の2段化と媒体アイコン

cfff134で表示操作を見出しへ、種類/検索方法をquery横へ移し、グループ単位で幅に応じて折り返す。54a08ffで音声等の空白previewにnative/テーマ対応iconを追加、実画像が来たら隠す。Imageを先頭に保ち、仮想化/サイズ変更/取消/未保存編集を保持。frontend02の生成6媒体はLight/Dark各31checks/所有exit0、各list/details/grid PNGを目視。先行frontend01各28の結果は二重合算しない。

幅1600/1100と長い検索方法の試験03は21checks/exit0だが、目視で1100詳細時の見出しclip（自然73px→27px）を発見。257f74cでstar列に制約された親幅から子の自然幅合計へ変更し、frontend03のheader-fit-dark01は23checks/exit0・1600/1100の2PNG目視、両幅73pxを保持した。Search切替で詳細が閉じた後にcloseした01、選択直後のtree walkがstaleだった02は試験側FAILとして保持し、更新待機/明示IDへ変更。実pointer/key/全DPIは確認していない。証拠root `data/ai-ui/continuation-20261029d/`。Source/assembly/test SHAは各reportを参照する。


## 2026-10-29d：検索・詳細・設定の密度改善

- `cfff134` は検索欄と種類/方式を同じ行、表示操作を見出しへ移動。狭い場合は操作群を折り返す。`54a08ff` は音声等の空枠をnative SymbolIconで示し、実画像取得時に隠す。既存Image先頭・セル再利用・取消を維持。frontend02/source54a08ffの生成6媒体Light/Dark各31checks/exit0。先行frontend01各28は別証拠で二重合算しない。
- 1100px詳細時に見出し幅27pxへclipする実不具合を発見し、`257f74c` で子の自然幅から算定。frontend03の1600/1100pxは23checks/exit0、両幅で見出し73px保持/2PNG目視。試験側の古い詳細close・ComboBox変更直後のstaleは別FAILとして保存。
- `2cea680` はタグを最大120pxで折返し、棚名と変更ボタンを一行に整理。frontend04/source2cea680のLight02/Dark01各11checks/exit0、4PNG目視。長いタグのdraft、棚選択取消、grid切替、保存を保持。Light01は収まったフォームへ不要なscrollを送ったharness FAILであり、`df998c8`で試験だけ修正。
- `260e577` はgrid/listの明示切替を既存viewer-settingsのoptional `library_view`へatomic保存。サイズ/theme/閲覧設定と共存し、legacyはlist。バックアップ形式の受入も同時更新。基本Python3.11の関連3method、Core限定79assertions、変更後の全Core1,441assertions PASS。検索順位/DB schema/画面履歴の並びは変更しない。
- `6b0bb56` は設定の6操作を2列3行に整理し、高度な設定を末尾へ。frontend05（build時HEAD260e577＋今回settings変更、reportのsource_filesで固定）はrequested Light/Dark各15checks/exit0、4PNG目視で両色の表示・native footer保存/再表示を確認（保存したsystemテーマはOS表示へ反映）。個別の全遷移/実キー/HC/物理DPIは未検証。
- 証拠は `data/ai-ui/continuation-20261029d/`。専用DB/生成素材/UIA-only。前面化/物理入力/モデル/GPU/通常DB/Alphaの変更なし。monitor-off/locked desktop下のcaptureを実入力受入やclean Windows合格にしない。

- `bc73b09` は使い方ガイドを3手順＋72px装飾に整理し、旧5節の詳細をExpanderへ保持。フォルダ登録への直接ボタンを追加し、任意AI用途選択も維持。frontend06（build時HEAD6b0bb56＋guide差分）はLight/Dark各11checks/exit0、概要2枚/登録2枚/復帰1枚を目視。新規取得/モデル/実scanなし。
- `9fdf07c` は登録フォルダの二重の作品一覧戻るを共通ヘッダー `BtnRoots`へ統一。frontend08のfolder-toolbar-dark01は8checks/exit0/1PNG目視。通常幅で登録フォーム/戻るを確認し、操作自体は保持。診断の重複closeもnative footer一つへ統一する。個別GUI候補はbase HEADに作業差分を含む場合があり、reportのsource_files/assembly SHAを根拠とし、後のcommitだけでProductVersionを言い換えない。

- 診断画面の追加確認で、AcceptsReturnをText代入後に設定していたため実TextBox/UIAが先頭行だけになる製品不具合を発見（diagnostic-footer-dark02 FAIL/exit0）。複数行を有効にしてからTextを代入する順序へ修正。独自close styleも外し標準footerを維持。frontend10のdark03は9checks/exit0/1PNG目視、全行とビルド元/配布種別のUIA保持を確認。copy操作は未実行だが既存の全report文字列をコピーする処理は不変。dark01の可視だけの8checksを全文受入にしない。


## 2026-10-29e：一覧下部と文脈に合う案内、初回AI用途

b81bbc3は読み込み済み範囲/LibrarySelection全体の選択数を固定footerへ配置し、前後範囲と接続・一覧更新をnative MenuFlyoutへ集約した。既存handler/IsEnabled/捨てる確認を再利用。frontend01の生成145PNG・専用DB・UIA-onlyはLight/Dark各14checks/exit0、各3PNGを目視。検索条件、画面外選択、draftと取消を保持。popup撮影はWinAppの合成画像なので位置の実測には使わない。証拠 continuation-20261029e/footer-{light01,dark01}。

ab1d812はliteralの不一致をAI準備の案内から分離し、共通CloseBrowseMenusを検索/直接folder/shelf/navigationで適用。frontend02/empty-guidance01では視覚文言は正しいがUIA Nameが固定案内メッセージであった。94eac96で固定名だけ外し、TxtEmpty ID/LiveSettingを維持。frontend03/guidance-setup02では実文言/検索時popup終了を確認し、次のComboBoxが同じpeerを二重列挙して試験側停止/exit0。残りを成功にしない。既存select_combo_itemを再利用して直す。

e362a32は4用途を説明付き2列のnative CheckBoxへ整理。選択mask/要件確認/保存/AIなし開始・取得同意は維持。restored projectのAPI確認とPortable build/publish0errors（既存picker3/trim2警告）、native用途画面は次の許可付き試行。frontend03 assembly/source fingerprintは各reportが正本。モデル・私物・通常DB・Alphaは使わない。

- 追加許可後guidance-setup03は20checks/exit0。literal/AI案内、検索・folder・shelfへのpopup終了、用途2列、保存mask15とAIなし0/idleを確認し5PNG目視。先行FAILを消さず、生成2PNGのSHA保持。モデル取得/GPU/通常データなし。


### 2026-10-29e：AI未導入からの復帰・棚の絞り込み

3e0ec2bは既存のAI未導入判定に限り、空画面から用途選択/同じ語でファイル名・タグ検索へ直行する操作を追加。通常の接続異常/期限切れ/類似失敗は従来のerror表示と診断を保持。検索開始時に復帰ボタンを隠し、順位/範囲/原本は変えない。frontend04のempty-ai-recovery01は11checks/exit0・2PNG目視、生成2PNG/専用DB/UIA-only。準備画面の往復、文字検索への復帰、取得/owner0を確認した。

68e2718は共通棚選択へ名前filter、表示件数/全選択数/表示外数を追加。HashSetで選択を保持し、絞り込みで消えた所属を適用時に落とさない。既存64棚上限、未知ID保全、取消/明示保存を維持。shelf-filter01は取消/draft保持/適用前DB不変まで成功し、保存の実文言「保存しました」に対し旧期待「保存済み」で停止。failure画像とDBの[1,74,75]/tag保存を確認し、製品保存失敗にはしない。

f7b733aで取得画面をモデル/実行環境と任意タグ付けの短い説明にし、既定無制限の速度設定をExpanderへ。復旧guideの重複closeをnative一つへ統一。frontend06/shelf-acquisition02は成功済み取消を省いて残り保存/再表示・表示外所属・取得画面・速度展開・復旧closeを12checks/exit0、4PNG目視。実download/backup開始は0、棚初期設定/一括routeの個別GUI/64件入力/HC/DPIは未実施。証拠root continuation-20261029e、ui-recovery-shelf-review01.json。


### 2026-10-30：表示サイズpresetとZIP24の通常起動

1e8e7caは共通表示サイズflyoutに小60/中100/大180のnative Buttonを追加し、既存Slider/標準復帰/Ctrl+wheel/保存/仮想化の経路を再利用。新しいサイズ計算や全件生成は追加しない。基本ZIP24の通常入口で生成1PNG、presetの同一行/非重複と値変更、一覧へ戻る操作、終了/再起動を含む16checks/4exit0・3PNG目視。shelf画面のpreset個別GUI/Light preset/物理wheel/HC/DPIは未確認。a52cc0cはNavFavorites完了を待ってNavAllへ戻る試験側だけの待機を追加した。

bf0db36は配置先のembedding役割を「内容検索（文章・画像・動画・音声）」と説明し、お気に入りフォルダはあるが作品は0件のときに「お気に入りはまだありません」と案内しない。既存enabled/favorite条件と表示する作品のscopeを保持する文言修正。Portable build0errors/既存3warnings、GUI/publish/ZIP24への収録は未実施。個別のミラー単体テストや無変更の全回帰は追加しない。


8ee9049はお気に入りフォルダ行にnativeの操作ボタン/右クリックmenuを追加し、既存APIによる解除と登録設定へ直接移る。再利用時に古いContextFlyoutを消し、名前はstar列で制約する。新しい設定入口からアイテム編集を失わないよう、共通SelectFolderForSettingsAsyncでもDirty時に既存破棄確認を通す。生成fixtureは2PNG/2registered roots・favorite boolをCPUで確認、Portable build/publish0errors（既存警告保持）。frontend08/source8ee9049のGUIは具体化して許可待ち。ZIP24/通常DB/Alphaには未反映。


frontend08/favorite-root-actions01（専用2PNG/2root・UIA-only）は設定直行、破棄確認の取消でdraft保持、作品お気に入り解除、folderだけの案内、両folder解除まで成功。最後のfolderが消えても古い空案内が残る実不具合でFAIL/exit0。両root favorite=false/enabled=1、items2、tag未保存をDBでも確認。menu/設定/失敗PNG計3枚を目視。復旧/登録解除/メディア削除の障害ではない。

f2ba198は既存の差分更新がLoadAsyncを通らないことを踏まえ、literal/空query/0作品のお気に入りに限り、フォルダ表示とEmptyScopeGuidanceを同じUI更新で更新する。検索語/AI/類似の案内は保持。Portable build0errors（既存3warnings）。frontend09で残る解除後案内/登録・原本保持だけを追加許可後に確認し、成功済みの設定/取消を反復しない。旧FAILは保持する。

追加許可後frontend09/sourcef2ba198のfavorite-root-removal02は9checks/exit0/残存processなし。最後のfolder解除後の正しい案内、2root登録/enabled・2items・元PNG不変・tag未保存を確認し1PNG目視。先行の設定/取消は反復していない。favorite-root-final-review.jsonも参照。ZIP24/Alphaには未収録、モデル配置役割名/物理右クリック/HC/DPI/多数folderの個別受入は残す。


## 2026-11-01：登録フォルダ設定の階層と個別保存（source34d2802）

- 一覧取得を前面、除外・初期棚・起動時更新・解除をnative Expanderへ。進捗/未保存は固定footerに残し、batchの対象/混在値、同意、既存操作を保全。
- Terraのレビューで、除外保存時のdraft再作成による未保存棚の消失経路を修正。保存成功した除外だけbaselineへ反映し、リクエスト中の編集を止め、POST失敗と更新失敗を区別。同じfolder設定への再入でdraftを保持、棚保存後も展開を保持する。
- Core関連10checks PASS。最初の旧cached-targetが削除されSDK10.0.403既定runtime10.0.14が未取得のbuildはNETSDK1112。ignoredの専用targetsで既存10.0.13 runtime/crossgen/ILLinkへ明示固定し、新規取得/プロジェクト依存変更なしにbuild/publish0errors（従来WUI1001×3/IL2104×2）。
- frontend01で個別保存/相互draft保全をLight02までに確認。Light03の再表示/別folder取消/batch3項目、Dark03は同項目を含む7checks・正常exit0・生成原本保持。関連画像5枚を確認。全手順1runのPASSとは合算せず、`data/ai-ui/continuation-20261101/folder-settings-final-review.json`へ範囲を明記。
- builtin除外を含めない期待値、短命な保存文言、閉じるを破棄確認と誤認した試験、非表示の準備中folder行を読む試験を修正。FAILは全て保持。製品の追加破損とは区別する。初回cleanupの破棄後HWND消滅競合は、window消滅時に所有process終了を待つ方式へ修正。強制終了なし。HC/物理入力/DPI/実folder/スキャン・起動時設定の再受入は今回の対象外。
- [agent-desktop評価](agent-desktop-evaluation.md)は読取/対象特定まで。操作未確認を製品GUIの成功へ混ぜない。


## 2026-11-01：設定保存結果の固定表示（source8cc23fc）

SettingsStatusをscroll内容から外し、native保存/閉じるfooterの直前へ配置。表示・閲覧・高度設定・保存契約を維持し、読み上げはPolite。frontend02の設定保存/上下scroll/再表示4操作は成功、Dark01は原本保持を含む8checks/exit0。Light01は保存時に既定systemテーマへ移るfixture不整合が画像で判明し、厳密なLight受入にはしない。専用設定fileにも指定themeを記録し、実際のComboBox選択を待つようharnessを修正。Lightの未確認分は追加許可を待つ。第三者CLIのstorage errorは別記し、Aredokoの設定失敗と混同しない。


設定feedbackの後続受入：fixtureの保存themeを明示したfrontend02/settings-feedback-light02は8checks/exit0/原本保持。実Lightの保存結果画像を確認し、Dark01/8checks/exit0と区別して両テーマを受入。CLIの再試行はせず、tool失敗を成功へ書換えていない。最新登録変更d727876は別のbuild/publish済み単位で、上記settings GUIの対象へ混ぜない。


## 2026-11-02：登録・filterの限定受入（a0ac6cb）

許可付きregistration-filter02は10checks/exit0/残存processなし。生成PNG/専用DB、有効root2/無効path1で、二つ目も登録できること、部分失敗のpath保持・警告、一覧だけの取得、検索DB反映、filterの0件案内/resetと非表示選択保持、原本hash保持を確認。partial-result/resetの2PNGを確認。初回01の旧文言FAILを保持し、source a0ac6cbの受入とした。後続d29f88eのパスcopy/clipboard、全DPI等は対象外。証拠data/ai-ui/continuation-20261102/registration-filter02/report.json。新しい同内容試験を反復しない。


## 2026-11-02：一覧footerからの一括整理（85123b4）

FooterBulkActionsは既存SelectionMenuを呼び、複数選択時だけ表示。解除は既存ConfirmDiscard保護付き処理へ接続し、session/選択IDs/保存中guardを維持。許可付きbulk-footer01はUIA-onlyで9checks/exit0/原本保持、残存processなし。2件選択→お気に入り保存→選択保持→棚picker cancel→footer解除を確認。menu/解除後の2PNG確認。physical入力/HC/DPI/大量選択の再受入/clipboardは今回未実施。登録の成功試験は反復していない。証拠data/ai-ui/continuation-20261102/bulk-footer01/report.json。


837c855でファイルのプロパティへ保存場所/パスcopyのnativeボタンを追加。既存OpenInShell/CopyFilePathへ接続し、activeなpresent作品だけ有効。選択/draft/検証経路は維持。Explorer/clipboard実操作は未確認。基本ZIP26/source85123b4には後続の837c855/4b51901を含まない。


## 2026-11-02：最新source4b51901の追加UI受入

user許可のfolder-selection01は9checks/exit0/残存processなし・原本/source保持。present作品の保存場所/パスボタンの表示・有効状態、登録中/解除済みの混在filterに対する一括選択・表示外選択保持・表示分解除・全解除と未保存の除外draft保持を確認した。解除済みrootはdisabledで対象にならず、2PNGを確認。Explorer/clipboardボタンは押していない。Light UIAのみ、physical入力/HC/DPI/選択上限境界の実機確認は未実施。既存経路/SDK/NuGetは変更なし。基本ZIP26はsource85123b4までであり、後続のproperty/フォルダ選択menuを含まない。証拠data/ai-ui/continuation-20261102/folder-selection01/report.jsonとfinal-review.json。


## 2026-11-03 詳細パネルの閲覧位置

source `0d1ccf2`、試験候補 `data/ai-ui/continuation-20261103/frontend01`。別itemへの切替時だけ詳細ScrollViewerを先頭へ戻し、同じitemの再表示では明示resetしない。閉じたpaneと未準備viewportではpendingを保持し、pane/Loaded/SizeChangedで適用。既存の選択・未保存確認・仮想化は維持。

Portable build/publishは成功（既存WUI1001×3、SDK IL2104×2のみ）。生成PNG2枚・専用DBのUIA `--detail-scroll` は7checks、graceful_exit0、残存appなし。同一作品の閉じる→再表示でscroll保持、開いたpane/閉じたpaneの別作品選択でtitleがviewport上端へ戻ることを確認。`detail-scroll01/detail-scroll-reset.png`を目視し、Lightのtitle/preview/編集欄の重なりなし。ComfyUI queueがrunning0/pending0の時に開始。

同一作品の保存/再検索時のscroll保持、物理wheel、HC/DPIは今回未検証。RootPathの修飾なしEnterによる登録は同sourceでbuild確認まで、実キー入力は未検証。既存の登録/部分失敗/scan案内のGUI成功をEnter経路の成功と読み替えない。


## 2026-11-03 検索のEnter確定・IME中の自動検索抑止

source3ff0849。Queryの修飾なしEnterを既存Search_Click→NavigateAsyncへ接続し、範囲・類似解除・未保存確認を再利用。既存の300ms自動検索と検索ボタンは維持。TextCompositionStarted/Endedで変換中を追跡し、その間はtimerとTickからの検索を抑止する。RootPathのEnterにもcomposition guardを追加し、Ctrl/Shift/Alt/Win付きEnterは対象外。restored projectへのwinapp find-apiでTextBox compositionイベントの存在を確認。

Portable build/publish成功（既存warningのみ）、試験版frontend02。keyboard-entry01は通常の前面化をWindowsに拒否され、入力前に停止/所有app exit0。実Enter・実日本語IMEは未検証であり、成功扱いにしない。生成2PNGだけを用い、GPU/モデル/通常DB/Alphaを利用していない。再現と次の一手はdeferred-issues D04。


## 2026-11-03 設定画面を通信待ちより先に表示

source37c2271、frontend03。runtime-verificationのGETをContentDialog.Opened後へ移し、読み込み中は当該checkboxだけ無効・状態説明を表示。表示テーマ/閲覧設定と既存の機能入口はすぐ使える。dialog所有CTSで閉じた時にGETを取消し、taskを回収、遅い応答で閉じたUIへ書かない。保存時に未知のverification値は更新しない。

Portable build/publish成功（既存warningのみ）。settings-load01は生成PNG2枚・専用DB/UIAで8checks、exit0。専用serverの当該GETだけをgateで待たせ、応答前にdialog表示・local保存・closeが可能、gate解放後の再表示で既定verificationオン取得を確認。入力/foreground要求/GPU/通常DBなし。写真では保存結果がnative footer直前に見える。theme未指定fixtureの保存でWindows既定Darkへ反映されたため、Light/Dark両theme確認とは称さない。実切断/実IME/HC/DPIは未確認。

## 2026-11-04 検索結果の開き始める位置を詳細に表示

MainPageの媒体別操作直下へ短い案内を追加。一致ページ番号、動画/音声の開始時刻を表示し、一致情報なしでは非表示。既存readerのrevision照合・読書位置fallback、playerの開始時刻選択/範囲制限は変更しない。Core/backend/保存処理は無変更。

Portable publish成功（初回sandbox内はMSBuild task host接続失敗、通常権限境界を解消した再publishは既存SDK IL2104のみ）。既存WinUI analyzer WUI1001×3は保持。data/ai-ui/continuation-20261103b/frontend01。生成6媒体・独立DB・供給した表示専用match metadata・UIA-onlyのopen-context-light02は11checks/正常exit0/残存なし/原本SHA・mtime不変。4PNG目視。初回light01は詳細を明示的に開く試験操作の欠落で停止、製品bugとせずraw保持。ignored check-open-context.pyで既存harnessを再利用。モデル/推論/再生なし。実検索精度/実一致位置への移動/Dark/HC/DPI/実入力はこの確認に含めない。

## 2026-11-04 詳細の検索根拠を折り畳み表示

一覧では2行へ省略している既存のAI類似/内部ページ/本文/候補タグ/一致語の根拠を、詳細の「検索の根拠」から読めるようにした。文字一致は既存protocolで検証・上限制御済みの語をすべて表示し、入力語・関連語・一致なしを区別。一致情報のない作品では非表示。選択に追従し、タグ編集中に折り畳みを勝手に閉じない。既存MediaMetadataStyle/ThemeResource・標準Expander/選択可能TextBlockを使用。新規API/保存/検索/reader/playerロジック変更なし。

最終frontend03（continuation-20261103b）へ既存依存だけでPortable publish成功、既存WUI1001×3/SDK IL2104×2のみ。frontend02は最終一致語の省略解除前なのでGUI候補と混同しない。関連native GUIは確認待ち。

2026-11-04追記：最終frontend03の検索根拠はdetail-evidence-dark01/light01各14checks/正常exit0/原本不変/残存なし。AIページのmodel説明、5番目の一致語・関連語・未一致語、別作品で旧根拠を非表示、タグdraft保持と明示保存を確認。Darkの4対象画像とLightの根拠2画像を親が目視確認。表示専用metadata fixtureで実AI検索精度や実メディア再生の実証ではない。初回open-context-light01の試験契約FAILも保持。

## 2026-11-04 元ファイルを開けない理由を詳細で表示

元ファイルmissing/unavailableでは、詳細上部に接続・場所・更新の確認先と登録タグ/棚が残ることを表示。presentでも既存媒体policyが開けない形式にはpropertyから保存場所を開く案内を表示。閲覧権限・path/preview guard・metadata保存は無変更。既存のdisabledボタンを隠して機能を削減しない。

frontend04のPortable publish成功（既存warningのみ）。detail-availability-light03は9checks/正常exit0/原本不変/残存なし、2PNG目視。catalog serializer境界でmissing/unavailableを供給し、disabled閲覧の理由、編集欄有効、正常作品で案内非表示を確認。01は誤った保存table列、02はunavailableが永続statusではないというfixture失敗で、どちらもfrontend起動前。既存schemaを確認し、03はDBを改変しないAPI状態fixtureへ修正。実ドライブ切断・未対応形式・Dark/HC/DPIは未検証。ZIP29/source12b6568にはこの後続変更は未収録。

## 2026-11-04 画像を見ながらお気に入りを整理

ImageViewerViewの操作バーに状態付きstarを追加。既存sessionが順位を保ったままfavorite patchできる通常文字検索のview=all（root/棚等の既存scopeは維持）から接続する。AI/類似/お気に入り/履歴は既存一覧の操作を維持し、新しいbar操作は出さない。Core/backend契約を拡張せず、1件rangeで現在画像のfavoriteを確認し、既存EditFavoriteAsyncでflagのみ保存。画像送り中/状態取得中/保存中は対象操作を無効、保存中は画像送りも停止。遅い応答は表示世代/IDで破棄する。

ViewerWindow.BeforeCloseAsyncで開始済み保存を回収し、close/escapeと保存が競合してもDB保存を途中cancelしない。成功後だけ一覧card/詳細/saved.Favoriteを共通ApplyFavoriteValueへ同期、tag/shelf draftは保存も破棄もしない。保持ackがfalseなら保存済みと報告して一覧へ戻り、既存favorite-only refresh/位置復帰経路を再利用する。通信失敗は成功と称さず一覧での状態確認を案内する。

frontend05→表示世代チェックを追加した最終frontend06のPortable publish成功（既存warningのみ）。viewer-favorite-light01は前段、light02は最終sourceで各12checks/exit0/生成原本不変/残存なし。生成2画像を含む6媒体/独立DB/UIA-onlyで、表示中1件の追加、詳細へ同期/未保存tagをDBへ混ぜない、保存POSTをgateで止めた間の画像送り無効とclose待機、解放後の解除完了・tag保持、次画像へ移動後は次のIDだけ保存、最後に見た画像への復帰を確認。画像付きstar/保存結果を目視。実キー/physical/Dark/HC/DPI/実通信断/keep=falseの競合は未検証。全回帰は反復せずCore/backend変更なし。

2026-11-04 viewer favorite追加安全確認：viewer-favorite-failure01は生成API拒否後の非変更/失敗表示、次の保存をkeep_session=falseで成功させた場合の一覧更新/未保存タグ保持、favorite-only scopeで新action非表示を9checks/exit0/原本不変で確認。実通信断ではなく供給したResultUnavailable/非保持ack。保存失敗画像を目視確認。このfixtureはホストWindowsの専用DBであり、下記Sandbox結果と区別する。

基本ZIP30/source138964eは別Sandboxでも通常EXEから全件・空文字検索→blue画像→star登録の成功表示→閉じた一覧star/詳細checkboxの同期→通常終了exit0を確認（user指定6.1 Terra）。guest DB read-only integrity ok、blueのみfavorite=1、CBZのタグ/読書位置2/2保全。evidence/update30-result.json・update30-db-check.json・update30-appdata。詳細な保存競合/失敗fixtureをSandboxでも反復したものではない。

## 2026-11-04 本の閲覧中のお気に入りと保存処理の共通化

ViewerFavoriteActionを画像/本の2箇所で共有し、state読取・対象ID/世代・flag-only保存・保存中無効化・flush/close・失敗表示を一箇所へ集約。新しい汎用frameworkやbackend経路は作らない。本は既存のreader progress flushの前にfavorite saveを回収し、2つの保存を完了してからclose。metadata draftを保存しない。同じ通常文字検索/all条件だけを接続し、filtered/AI等の既存viewerは維持する。

frontend07/Portable publish成功（既存warningのみ）。**ホスト**reader-favorite-host02は9checks/exit0/原本不変：2page CBZのfavorite登録/解除、未保存tag保持、再表示2/2復元、保存中closeとreader progress両方の保全。初回01はOSタイトルへ移された非表示ReaderPageNumber peerを待った試験FAILでraw保持。shared-favorite-image-host01は12checks、shared-favorite-failure-host02は9checks、各exit0/原本不変/残存なし。failure-host01は保存拒否/fallback通過後、nav直後のstale UIA peerで停止。stdout cp932の記録エラーも保全し、一覧準備完了とpeer再取得・UTF8を試験側だけへ追加した。2回の失敗を製品bugにしない。

読書viewer star/成功noticeを親が画像確認。本の新しい通常packaged Sandbox操作はこの時点では未実行。実通信断/Dark/HC/DPI/AI範囲のfavoriteは未検証・未実装のまま。関連安全確認に絞り、全回帰・旧soakを反復していない。

ZIP31/sourcebb59c40の**Sandbox**確認：同じ専用guest DBを通常EXEから再利用し、CBZ2/2復元・book star登録・一覧/詳細同期・既存tag/位置保持・通常終了exit0。guest DB integrity ok、blueとCBZのみfavorite=1。証拠はevidence/update31-{result,db-check}.json・update31-appdata。ホストの保存途中close/拒否fixtureと混同しない。


## 2026-11-11 動画・音声の再生中のお気に入り

画像/本のViewerFavoriteActionをVideoPlayerViewにも接続。通常文字検索/allの有効なresult sessionだけに星ボタンを表示し、再生を止めずにflagだけを保存する。選択行/詳細へ同期し、非保持ackでは既存契約どおり一覧へ戻って再取得する。保存中はbarを表示し、閉じる際にFlushFavoriteAsyncを待つ。タグ/棚の未保存draft、再生位置・音量・消音・seekは変更しない。AI/類似/お気に入り/履歴scopeは従来どおり新actionを非表示とする。

関連Portable build成功（既存WUI1001×3）。この時点では新しい動画/音声GUI操作、保存中close/保存拒否の実機確認は未実施。共有部品の過去画像/本受入を新しい媒体の受入として数えない。Core/backend/保存APIの追加はない。

## 2026-11-13 狭めのウィンドウでの詳細・一覧比較とタグ・棚操作

source `a3f1f7f92d0a6e8d839db44a66014e67687ce589`、Portable frontend `data/development-tools/frontend-product10`（候補12へ同梱）。920×700px 前後の狭めのウィンドウで詳細パネルを開いたまま一覧を見比べ、タグ・棚を操作しやすくするため以下を修正した。

- **詳細を Inline 維持**: `UpdateNavigationLayout` で `Details.DisplayMode` を `720px` 未満のみ `Overlay`（`720px` 以上は `Inline`）とし、`Details.IsPaneOpen` 時は `1080px` 未満で先に左 `Nav` を畳むように変更。幅に応じて `Details.OpenPaneLength` を調整（`>=1080` は `320`、`>=880` は `280`、`720〜879` は `Math.Clamp(width - 600, 240, 280)`）し、`LibraryLayout_SizeChanged` と `Details_PaneStateChanged` からも再レイアウトする。
- **一覧行と詳細の比較・下書き保持**: `FormatRowMetadata` で一覧メタデータ行に `棚:<棚名>` とタグを表示し、`Items_ContainerContentChanging` で `ItemMeta{id}` を付与して `RefreshFavoriteCard` で選択・保存後にその場更新する。`ChooseShelves_Click`・`ChooseRootShelves_Click`・`ConfirmDiscardAsync`・`ChangeLibrarySelectionAsync` で操作開始時の `Details.IsPaneOpen` を保持し、棚選択や未保存確認キャンセル後も詳細を開いたまま下書きを維持する。
- **狭い領域でのボタンとプレビュー収まり**: `MainPage.xaml` の `Favorite`（`ChkFavorite`）・`Reviewed`（`ChkReviewed`）チェックボックスへ `MinWidth="0"` を設定し、`UpdateDetailLayout` で高さ `760px` 未満のとき `DetailPreview.Height` を `112` へ抑えて保存ボタン周りを収めやすくした。

ホスト実機GUI確認 `data/gui-narrow-compare01/run04`（UIA自動化、生成2画像・1CBZ・独立DB、`Aredoko.Core.Tests` / Portable起動19件 / Sandbox設定8件 / 候補12 `--check` は別途PASS）では終了コード 0・原本SHA不変・DB整合維持で以下を確認した：

- `920×700` ウィンドウで一覧右側 (`628`) と詳細左側 (`673`) が重ならず `Inline` 並置表示。
- タグ下書き入力中に棚選択ダイアログで新規棚「比較棚」を適用しても、詳細が開いたまま下書きを維持 (`shelf_picker_keeps_details_and_draft: true`)。
- 別作品選択時の未保存確認でキャンセルしても、詳細が開いたまま下書きを維持 (`discard_continue_keeps_details_and_draft: true`)。
- 明示保存直後に一覧のメタデータ行へ `"画像 · 棚:比較棚 · 比較タグA、夏"` が即時反映。
- `Item2`（`green-image.png`）へ切り替えても light-dismiss されず詳細が開いたまま比較でき、DB保存を維持 (`narrow_item_switch_compares_without_light_dismiss: true`、`db_saved_and_intact: true`)。
- `run01`〜`run03` ではテスト側のウィンドウ列挙順・空 `TextBox` 属性・未所属棚表示 `'棚なし'` の期待値を修正し、`run04` で全項目合格。物理DPI・ハイコントラスト・実日本語IME・ルート棚ダイアログ単体のGUI操作は未確認。

## 2026-11-14 複数選択の一括整理とサマリーパネル保持

source `0e34708d4284f3898033c3fd7660239bdaec09f2`、Portable frontend `data/development-tools/frontend-product11`（候補13へ同梱）。一覧で複数選択した状態から上部ツールと右サマリーをそのまま使って一括整理しやすくするため以下を改善した。

- **上部選択ツールとサマリー詳細**: `MainPage.xaml` / `MainPage.Selection.cs` で、`SelectionTools`（`librarySelection.Count > 1`）に `SelectionBulkActions`（「まとめて整理」）を追加し、`SelectionSummaryPanel` の `SelectionSummaryText` 下に `SelectionSummaryDetails`（先頭最大3件のタイトル、現在の `お気に入り X/Y 件 · 棚: ...`／`棚なし` 要約）を追加。一括お気に入り・一括棚編集後も `RefreshFavoriteCard` とともに即時更新する。
- **リサイズ・キャンセル・一括適用後のパネル保持**: `Page_SizeChanged`（`librarySelection.Count == 0` 条件追加）・`ConfirmDiscardAsync`・`EditLibrarySelectionAsync` で `Details.IsPaneOpen` を保持し、ウィンドウ幅縮小や一括棚選択ダイアログのキャンセル／適用後にサマリーパネルが閉じないよう修正した。

ホスト実機GUI確認 `data/gui-multiselect-organize01/run01/summary.json`（UIA自動化、`frontend-product11`、独立DB・生成PNG 2件、終了コード `0`・`originals_sha_match: true`）で以下を確認した：

- `Item1`/`Item2` の複数選択で `SelectionCountText`（`2 件選択`）と有効な `SelectionBulkActions`（「まとめて整理」）が一覧上部へ表示 (`top_selection_bar_has_bulk_actions: true`)。
- 詳細パネルに `SelectionSummaryDetails`（`"対象: blue-image.png、green-image.png\n現在: お気に入り 0/2 件 · 棚なし"`）が表示され、`900×720` へ縮小しても閉じず一覧と `Inline` 並置を維持 (`list_right: 608 <= details_left: 653`)。
- `SelectionShelfAdd` からの `BulkShelfChoice` ダイアログをキャンセルしても `SelectionSummaryPanel` が開いたまま状態を保持 (`shelf_cancel_keeps_summary_open: true`)。
- 既存棚「一括棚」への追加と `SelectionFavoriteAdd` 適用後、`SelectionSummaryDetails` が `"現在: お気に入り 2/2 件 · 棚: 一括棚"` へ更新され、一覧行 `ItemMeta1`/`ItemMeta2` へ `"画像 · 棚:一括棚"`、SQLite DB（`favorite=1`、`item_shelves` 2件、`integrity_check=ok`）が一致。
- 257件以上の範囲選択準備中や物理DPI/ハイコントラストは別途確認。

## 2026-11-14 検索・絞り込み条件の一括解除と表示中ページ全選択

source `c0682484e8302a197ee6fa76d402f3139c279bb4`、Portable frontend `data/development-tools/frontend-product12`（候補14へ同梱）。検索・絞り込み条件を迷わず解除できる導線と、一覧の表示中ページを1操作で全選択・解除できる導線を追加した。

- **条件の一括解除**: `MainPage.xaml` / `MainPage.xaml.cs` / `MainPage.Shelves.cs` で、検索フィルタツール欄に `BtnClearSearchConditions`（`ClearSearchConditionsButton`）を、0件時の空状態 `StackPanel` に `EmptyResetConditions`（`EmptyResetConditionsButton`）を追加した。`HasActiveSearchConditions()` と `UpdateClearSearchConditionsVisibility()` で検索語・種類・タグ・範囲・棚絞り込み等の有効時のみ表示し、`ClearSearchConditions_Click` は `ConfirmDiscardAsync()` ガードを通ってから全条件を既定状態（「すべて」／「すべての種類」・空検索・棚絞り込み解除）へ戻す。
- **表示中ページの全選択と解除**: `MainPage.xaml` / `MainPage.Selection.cs` で、`BrowseActionsFlyout` に `BtnSelectVisibleItems`（`SelectVisibleItemsMenuItem` → `SelectVisibleItems_Click`、既存 `LibrarySelection.Maximum` 256件枠内）を、`SelectionSummaryPanel` に `SelectionSummaryClear`（`SelectionSummaryClearButton`）を、`SelectionMenu()` に `BulkClearSelection` を追加した。

単体確認（`tools\dev-dotnet.ps1 run --project tests\Aredoko.Core.Tests\Aredoko.Core.Tests.csproj -c Release --no-restore` exit 0、`frontend-product12` Portable publish exit 0）およびホスト実機GUI `data/gui-search-reset-select01/run05/summary.json`（UIA自動化、生成2画像+1CBZ、独立DB）で以下を確認した：

- 初期状態は `3 件`、両解除ボタン非表示（`initial_clean: true`）。`notfound-xyz` 検索で `0 件`・`BtnClearSearchConditions`・`EmptyResetConditions` 表示（`empty_shows_reset_buttons: true`）、`EmptyResetConditions` で `3 件`・空検索へ復元（`empty_reset_restores_all: true`）。
- `CmbKind='画像'` で `2 件` へ絞り込み後に `TxtTags='未保存タグ'` を入力し、`BtnClearSearchConditions` 押下→確認ダイアログで `CloseButton`（`編集を続ける`）を選ぶと下書きと `2 件` を維持（`reset_cancel_preserves_draft: true`）、`PrimaryButton`（`変更を破棄`）で `すべての種類` と `3 件` を復元（`reset_confirm_restores_kind_and_items: true`）。
- `BrowseActions` → `BtnSelectVisibleItems` で `3 件選択`（`select_visible_selects_all`）、`BtnDetails` 後のサマリー表示（`summary_shows_three_items`: `"対象: blue-image.png、green-image.png、two-pages.cbz\n現在: お気に入り 0/3 件 · 棚なし"`）、`SelectionSummaryClear` での選択解除（`summary_clear_clears_selection: true`）および `SelectionBulkActions` → `BulkClearSelection` での選択解除（`bulk_clear_clears_selection: true`）を確認。`db_intact: true`、`exit_code: 0`、`originals_sha_match: true`、残存 `Aredoko*` プロセスなし。
- なお先行試行 `run04` の `0 件 after kind=動画` は、テスト側で `TxtTags` 未保存状態のまま `CmbKind` 変更を行って確認ダイアログを出した試験順の不備（製品仕様通り）。257件超のページ跨ぎ範囲選択、実日本語IME、物理DPI・ハイコントラストは未検証。

## 2026-11-15 選択上限時の先頭256件一括選択・一覧行の多棚要約・サマリースクロール

source `6fefe0ed45350c6429ac91f6966d2ef776a388bb`（`frontend-product13`、`data/gui-search-reset-select01/quick-run01/summary.json`）および `921060675a42c9d9b9aefde94c613c35569d76d5`（Portable frontend `data/development-tools/frontend-product14`、候補15へ同梱）。256件超過時の部分選択誤認の防止と、257件以上読み込み時の明示一括選択、多数の棚所属時の視認性を改善した。

- **選択上限ガードとサマリースクロール**（`6fefe0e`）：`MainPage.Selection.cs` で `rows.Count > LibrarySelection.Maximum`（256件）のとき `BtnSelectVisibleItems` を無効化して「読み込み済みの作品をすべて選択（上限 256 件）」へ切り替え、`MainPage.xaml` の `SelectionSummaryPanel` を `SelectionSummaryScroll`（`ScrollViewer`）で包んで多数棚でも下部整理・解除ボタンへ到達できるようにした。ホスト実機GUI `data/gui-search-reset-select01/quick-run01/summary.json` で3件選択・32棚スクロール解除・363件時上限無効・`db_intact: true`・`exit_code: 0`・`originals_sha_match: true` を確認。
- **先頭256件一括選択・一覧行多棚要約・一覧外表示**（`9210606`）：`MainPage.xaml` / `MainPage.Selection.cs` の `BrowseActionsFlyout` に `BtnSelectFirstMaxItems`（「読み込み済みの先頭 256 件を選択」）を追加し、`rows.Count > LibrarySelection.Maximum` の間だけ表示・有効化して `SelectLoadedRowsAsync(capToMaximum)` で共通処理化。あわせて `FormatSelectionSummaryDetails()` で `librarySelection.Count > selectedRows.Length` 時に `（一覧外 X 件）` を付記し、`MainPage.xaml.cs` の `FormatRowMetadata()` で1行一覧メタデータ上の棚表示を先頭3棚＋`ほかN棚` に要約してタグ表示を残し、`ItemMeta{id}` Tooltip に全棚＋タグ文字列を設定した。

単体確認（`tools\dev-dotnet.ps1 run --project tests\Aredoko.Core.Tests\Aredoko.Core.Tests.csproj -c Release --no-restore` exit 0、`frontend-product14` Portable publish exit 0 + `portable-build.json` 373 entries）およびホスト実機GUI `data/gui-search-reset-select01/quick-run02/summary.json`（UIA自動化、独立DB、生成2画像+1CBZ+複製360件）で以下を確認した：

- 32棚＋`blue-sample-tag` 付与項目で `ItemMeta1` が `"画像 · 棚:テスト用の長い棚の名前を表示するための項目 00、テスト用の長い棚の名前を表示するための項目 01、テスト用の長い棚の名前を表示するための項目 02 ほか29棚 · blue-sample-tag"` となり、棚を3件要約しつつタグ表示を保持。
- 3件選択（`select_visible_selects_all: "3 件選択"`）後、32棚を含む `SelectionSummaryScroll` 末尾スクロールと `SelectionSummaryClear` による解除（`summary_clear_clears_selection: true`）を確認。
- 363件読み込み後、`BtnSelectVisibleItems` 無効化・`"上限 256 件"` 表示（`over_limit_disabled_without_partial_selection: true`）の一方で、`BtnSelectFirstMaxItems` から `256 件選択`（`select_first_max_selects_256`）および `SelectionBulkActions` → `BulkClearSelection` 解除（`first_max_cleared: true`）を確認。`db_intact: true`、`exit_code: 0`、`originals_sha_match: true`、残存 `Aredoko*` プロセスなし。
- なお257件超のページ跨ぎ範囲選択（Shift選択 `RangeAsync`）・実日本語IME・物理DPI・ハイコントラストは引き続き未検証。

## 2026-11-15 ページ跨ぎ・直前起点からの範囲選択・詳細ペイン維持・棚ピッカーその場作成とルート初期棚ダイアログGUI

source `1f573d2b5d63754a1fd973821e46ca103ec6baa6`、Portable frontend `data/development-tools/frontend-product15`（`portable-build.json` `373` entries）。ページを跨いだ範囲選択をキーボード修飾なしでも迷わず実行できる導線と、棚選択ダイアログ上での新規棚作成、ルート初期棚ダイアログの実機GUI確認を実施した。

- **直前起点の範囲選択と一覧外詳細保持**: `LibrarySelection`（`src/Aredoko.Core/LibrarySelection.cs`）に `PreviousAnchor` を追加し、単一選択（`Single`）で異なる項目へ移った際のみ直前項目を保持し、`Commit`（`Clear` / `Bind` / `Visible` / `RangeAsync`）で初期化するようにした。`MainPage.xaml` / `MainPage.Selection.cs` の `BrowseActionsFlyout` に `BtnSelectRangeSpan`（「直前の選択からここまで選択（N 件）」／256件超時は「（N 件・上限 256 件）」で無効化）を追加し、`MainPage.xaml.cs` の `LoadAsync` は同一検索セッション内で `librarySelection.Count > 0` のとき `Details.IsPaneOpen` を閉じずに保持する。また `SimilarityMenu` に `SelectRangeTo{id}`（「選択起点からここまで選択（N 件）」／上限超過時は無効化）を追加した。
- **棚ピッカーのその場作成**: `MainPage.ShelfPicker.cs` の `PickShelfIdsAsync(..., bool allowCreate = true)` へ `{prefix}NewName`（「新しい棚を作成」）・`{prefix}CreateNew`（「作成して選択」）・`{prefix}CreateError` を追加した（`BulkShelfChoice` の棚解除操作時のみ `allowCreate: false`）。重複名（大文字・小文字無視）は既存棚を選択し、新規作成時は `api.Shelves.CreateAsync` 後に `RefreshShelfDescriptorsAsync`・一覧再構築・即時選択を行う。

単体確認（`tools\dev-dotnet.ps1 run --project tests\Aredoko.Core.Tests\Aredoko.Core.Tests.csproj -c Release --no-restore` exit 0、`PreviousAnchor` 検証 8 件を含む全項目 PASS、`frontend-product15` Portable publish exit 0）およびホスト実機GUI `data/gui-range-root-shelf01/run03/summary.json`（UIA自動化、生成PNG 300件、独立DB、終了コード `0`・`db_intact: true`・`originals_sha_match: true`）で以下を確認した：

- **ルート初期棚ダイアログ＋その場作成（Scenario A）**: `BtnRoots` → `ConfigFolder{root}` → `RootShelfSettings` → `BtnChooseRootShelves` から `ChooseRootShelf` を開き、既存棚「既存棚A」選択に加えて `ChooseRootShelfNewName`／`ChooseRootShelfCreateNew` で「初期新規棚B」を作成・自動選択（`2 件を選択`）→ 適用 → `FillUnsetShelf` オンで保存（`TxtFolderEditStatus`: 「初期棚を保存しました。棚未設定の作品 300 件に適用しました。」、`TxtCurrentShelfSummary`: 「現在の初期棚: 既存棚A ほか1棚」、`FolderMeta{root}` へ反映、`item_shelves` `600` 行・`root_shelves` 2件保存）。
- **ページ跨ぎ範囲選択と詳細維持（Scenario B）**: `Item1` 選択＋`BtnDetails` で詳細表示のまま `BrowseActions` → `BtnNext` で `61–120 / 300` へ移動し、詳細が閉じず `SelectionCountText`=`"1 件選択（一覧外 1 件）"`、`SelectionSummaryDetails` に `"現在の表示範囲外で 1 件を選択中"` を維持（`details_kept_across_page_turn: true`）。続けて `Item65` 選択後に `BtnSelectRangeSpan`（「直前の選択からここまで選択（65 件）」）を実行し、`SelectionCountText`=`"65 件選択（一覧外 60 件）"`、`FooterSelection`=`"65 件選択"`、サマリー詳細に `"現在: お気に入り 0/5 件（一覧外 60 件） · 棚: 既存棚A、初期新規棚B"` を確認。
- **256件超ガード（Scenario C）**: 選択解除後に `1–60 / 300` の先頭項目を選択し、`241–300 / 300` へ移動して末尾項目（300件目）を選択すると、`BtnSelectRangeSpan` が無効化（`IsEnabled == False`）されラベルが `"直前の選択からここまで選択（300 件・上限 256 件）"` となることを確認。
- 先行試行 `run01` は `TxtCurrentShelfSummary` 複合表示形式（`既存棚A ほか1棚`）の試験側アサーション不一致、`run02` はロック中セッションで右クリック `winapp ui click --right` が `No interactive desktop is available` となった試験制約。そのため `SelectRangeTo{id}` 右クリック実機操作・実日本語IME・物理DPI・ハイコントラストは引き続き未確認。なお `frontend-product15` 同梱の配布再梱包はまだ実施していない（次回区切りまたは P6 再梱包時に実施）。

### 2026-11-15（後半）：複数棚スコープ移動・作品からの棚ジャンプ・3棚要約（frontend-product16 / 候補16）

- 実装（`d1367f88d687b02ac05aeb53cea152072e35c7aa`）：
  - 複数棚スコープ操作：棚ハブに `BtnOpenMultipleShelves`（「複数棚を開く」）、検索対象バー `ShelfScopeBar` に `BtnChangeShelfScope`（「棚を変更」）を追加し、`PickShelfIdsAsync`（`ScopeShelfChoice`、全解除で絞り込み解除）で複数棚を一括表示・切替できるようにした。棚削除時（`DeleteShelfAsync`）にスコープ内の残余棚を保持し、また棚スコープ閲覧中に左ナビの `NavShelf` を押した際は `Navigation_ItemInvoked` から棚ハブへ戻れるようにした（`MainPage.Settings.cs`）。
  - 選択作品からの棚ジャンプ：詳細ペインの棚行へ `BtnOpenActiveShelves`（「開く」）、一覧カードのコンテキストメニューへ `OpenItemShelves{id}`（「所属する棚を開く」）を追加し、作品の所属棚スコープへ直接移動できるようにした。
  - 3棚までの要約表示：`ShelfProtocol.SummarizeNames` を `Aredoko.Core` に追加し、3棚までは全件、4棚以上は先頭3棚＋`ほかN棚` を表示しつつツールチップに全棚一覧を保持するよう `TxtShelf`、`TxtSelectionSummaryDetails`、`ItemMeta{id}`、`LibraryHeading`、`TxtShelfScope` を統一した。
- 検証と確認範囲：
  - `Aredoko.Core.Tests`（`dotnet.exe run --project tests\Aredoko.Core.Tests\Aredoko.Core.Tests.csproj -c Release --no-restore`、終了コード `0`）で `ShelfTests.cs` の `SummarizeNames` 4件を含む全件が PASS。
  - 独立ホスト GUI 試験 `data/gui-shelf-scope01/check.py` `run03`（`summary.json`、`exit_code: 0`、`db_intact: true`、`originals_sha_match: true`）で、単一作品詳細（`棚A、棚B、棚C ほか1棚`）、2件選択サマリー（`現在: お気に入り 0/2 件 · 棚: 棚A、棚B、棚C ほか2棚`）、`BtnOpenActiveShelves` 遷移（`2 件`）、`BtnChangeShelfScope` での `棚E` 絞込（`1 件`）、`NavShelf` → `BtnOpenMultipleShelves` での `棚A、棚E` 表示（`2 件`）→ `BtnClearShelfScope` 全4件復帰の5シナリオが PASS。先行 `run01` は `winapp ui invoke` の存在しない `--action add-to-selection` 引数による試験側失敗（PowerShell `SelectionItemPattern` へ修正）、`run02` は `NavShelf` 選択中再押下の `Navigation_ItemInvoked` 未処理（`MainPage.Settings.cs` 修正）と終端 `cp932` コンソール出力時の `\xb7` `UnicodeEncodeError`（`ensure_ascii=True` 出力へ修正）を解消した。なお `SelectRangeTo{id}` 右クリック実機操作・実日本語IME・物理DPI・ハイコントラストは引き続き未確認。

### 2026-11-15（夕方）：設定〜各サブダイアログ・管理画面の往復導線整理（frontend-product16）

- 実装：
  - `MainPage.Settings.cs`：設定ダイアログ内 `SettingsTools` を5行へ拡張し、「登録フォルダを管理」（`BtnSettingsOpenFolders` → `OpenFolderHubAsync()`）・「棚一覧を管理」（`BtnSettingsOpenShelves` → `OpenShelfHubAsync()`）を追加。あわせて初回案内・バックアップと復元・診断情報・AI自動構築・ストレージとキャッシュを `fromSettings: true` で開くようにした。
  - `MainPage.Settings.cs` / `MainPage.Backup.cs` / `MainPage.Restore.cs` / `MainPage.RuntimeCache.cs` / `MainPage.AIAutoEnvironment.cs` / `MainPage.GettingStarted.cs`：設定から開いたサブダイアログへ `BtnBackToSettings`（「設定へ戻る」、処理中無効化・`Dialog.Closed` 同期付き）を、バックアップと復元から開いた `BackupGuideDialog`・`RestoreDialog` へ `BtnBackToBackup`（「バックアップと復元へ戻る」、`fromSettings` 引継ぎ）を追加。
  - `tools/prepare_portable.py`：`verify_release(release)` 後に配布直下の `Aredoko.exe --self-test`（`release-bootstrap-cpu`）を実行する検査を追加。
- 検証と確認範囲：
  - ホスト側 Smart App Control がオフ（`VerifiedAndReputablePolicyState = 0`）になった状態で `Aredoko.Core.Tests`（`dotnet.exe run --project tests\Aredoko.Core.Tests\Aredoko.Core.Tests.csproj -c Release --no-restore`、終了コード `0`）、`frontend-product16` Portable publish（終了コード `0`・`portable-build.json` 再生成）、`tests/test_portable_startup.py`（19件・`33.190s` OK）、および既存 `dist/portable-managed-20261115-16/Aredoko/Aredoko.exe --self-test`（終了コード `0`）が PASS。
  - 独立ホスト GUI 試験 `data/gui-settings-roundtrip01/check.py` `run01`（`data/gui-settings-roundtrip01/run01/result.json`、`exit_code: 0`、`sqlite_integrity_ok: true`、`originals_sha_match: true`、`passed: true`）で、`SettingsDialog` ⇔ `DiagnosticsDialog`、⇔ `BackupDialog` ⇔ `BackupGuideDialog` / `RestoreDialog`、⇔ `RuntimeCacheDialog`、⇔ `GettingStartedGuideDialog`、および `BtnSettingsOpenFolders` → `FolderHubView`・`BtnSettingsOpenShelves` → `ShelfHubView` の6経路を実機確認。先行起動1回は試験スクリプトが 50x50 `UAC_InputIndicatorOverlayWnd` を主ウィンドウに誤選択した試験バグであり、`WinUIDesktopWin32WindowClass` 絞り込み修正後に `run01` として全件 PASS。なお `AIAutoEnvironmentDialog` の実機 `BtnBackToSettings` クリック・上記変更を含む配布再梱包・`SelectRangeTo{id}` 右クリック・実日本語IME・物理DPI・ハイコントラストは未確認。

### 2026-11-15（夕方後半）：詳細ペインの編集取消・タグジャンプ・類似検索導線改善（frontend-product16）

- UI・実装（[MainPage.xaml](file:///c:/AI/Aredoko/src/Aredoko.WinUI/MainPage.xaml)・[MainPage.xaml.cs](file:///c:/AI/Aredoko/src/Aredoko.WinUI/MainPage.xaml.cs)）：
  - **保存済み状態へ戻す（`BtnRevertEdits`）**：右側フッターを2列 `Grid` とし、`Save`（`BtnSave`）の隣に `RevertEditsButton`（`AutomationId="BtnRevertEdits"`、`Content="元に戻す"`、`RevertEdits_Click`）を追加。`UpdateDirty` で未保存編集時のみ表示・有効化し、取消後は保存済みタグ／メモ／選択中作品の表示を復元する。WinUI の非同期 `TextChanged` が `"未保存の変更を元に戻しました"` を `"保存済み"` へ上書きしないよう `revertStatusActive`（`ApplySelectedRow`・`UpdateDirty` の `blocked`/`Dirty` 時・`ConfirmDiscardAsync` の `accepted && Dirty` 時で解除）と `SaveAsync` フォーカス復帰対象を追加。
  - **保存タグから一覧絞り込み（`BtnFilterByActiveTag`）**：`Tags` 入力欄の下に `FilterByActiveTagButton`（`AutomationId="BtnFilterByActiveTag"`、`FilterByTagAsync`）を追加し、保存済みタグを Flyout（`FilterByActiveTag0`..、最大20件）として提示、選択したタグで `SearchBox` を更新して一覧検索へジャンプする導線を実装。
  - **詳細ペインからの類似検索（`BtnDetailFindSimilar`）**：`DetailOpenActions`（`OpenAudio` の後）に `DetailFindSimilarButton`（`AutomationId="BtnDetailFindSimilar"`、`DetailFindSimilar_Click`）を追加し、画像選択時は直接類似検索を実行、動画／音声選択時は候補フレーム／サムネイル別の Flyout を表示するよう `UpdateDetailActions` を拡張。
- 検証と確認範囲：
  - `Aredoko.Core.Tests`（`dotnet.exe run --project tests\Aredoko.Core.Tests\Aredoko.Core.Tests.csproj -c Release --no-restore`、終了コード `0`、直後の最終変更は WinUI 側 `revertStatusActive` のみで `Aredoko.Core` は無変更）、`frontend-product16` Portable publish（終了コード `0`・`portable-build.json` 再生成 `receipt_ok`）が PASS。
  - 独立ホスト GUI 試験 `data/gui-detail-actions02/check.py` `run01`（生成 PNG 3件・ポート `8769`・独立DB/設定、[result.json](file:///c:/AI/Aredoko/data/gui-detail-actions02/run01/result.json)）で `detail_initial_controls_ready` / `dirty_shows_revert` / `revert_restores_tags` / `tag_jump_search` / `navigation_back_restores_list` / `detail_similarity_button` の6項目がすべて `true`（`exit_code: 0`、`sqlite_integrity_ok: true`、`originals_sha_match: true`、`passed: true`）で PASS。
  - 未確認範囲：動画／音声選択時の `BtnDetailFindSimilar` フライアウト実機操作、候補17への配布再梱包、`AIAutoEnvironmentDialog` の `BtnBackToSettings` 実機クリック、`SelectRangeTo{id}` 右クリック、実日本語IME、物理DPI、ハイコントラスト。

### 2026-11-15（夜）：タグ欄スクロール・詳細ボタン件数表示・カード右クリックタグ検索・動画フライアウト実機確認（frontend-product16 / e29310c）

- UI・実装（`e29310c1635eec4f70631b566e4a0eeb05ed0fd2`、[MainPage.xaml](file:///c:/AI/Aredoko/src/Aredoko.WinUI/MainPage.xaml)・[MainPage.xaml.cs](file:///c:/AI/Aredoko/src/Aredoko.WinUI/MainPage.xaml.cs)）：
  - `Tags`・`Shelf` `TextBox` に `ScrollViewer.VerticalScrollBarVisibility="Auto"` を設定し、長文タグ・多棚表示時に縦スクロールバーで内容を確認できるようにした。
  - `FilterByActiveTagButton`（`BtnFilterByActiveTag`）の静的 `AutomationProperties.Name` を削除して動的 `.Content` が UIA へ正しく反映されるようにし、`UpdateDetailActions()` で 1 件時は `タグ「{tag}」で検索…`、複数時は `この作品のタグで検索（{N} 件）…` および先頭10件のタグを含むツールチップへ更新するよう整理。
  - `SimilarityMenu(MediaRow row)` に作品タグでの一覧絞り込みメニューを追加（1件時は `FilterByItemTag{id}_0`「タグ「{tag}」で検索」、2件以上は `FilterByItemTags{id}`「タグで検索（N 件）」配下に最大20件の `FilterByItemTag{id}_{i}`）。
  - `SaveAsync()` のフォーカス復帰判定・無効時フォールバックに `FilterByActiveTagButton` と `DetailFindSimilarButton` を含め、保存完了時に未変更なら `RevertEditsButton` を非表示化し、`DetailPreview.ContextFlyout` を再生成するよう更新。
- 検証と確認範囲：
  - `Aredoko.Core.Tests`（`dotnet.exe run --project tests\Aredoko.Core.Tests\Aredoko.Core.Tests.csproj -c Release --no-restore`、終了コード `0`、以降は WinUI 側 `MainPage.xaml` / `MainPage.xaml.cs` のみ変更）、`frontend-product16` Portable publish（終了コード `0`・`portable-build.json` 再生成 `receipt_ok`）が PASS。
  - 独立ホスト GUI 試験 [check.py](file:///c:/AI/Aredoko/data/gui-detail-actions03/check.py) `run04`（[result.json](file:///c:/AI/Aredoko/data/gui-detail-actions03/run04/result.json)、生成 PNG 2件 + MP4 1件、独立DB/設定、終了コード `0`・`sqlite_integrity_ok: true`・`originals_sha_match: true`・`passed: true`）で、`detail_tag_button_count_label`（`Item1` の `この作品のタグで検索（2 件）…` と `Item2` の `タグ「風景」で検索…`）、`single_tag_detail_filter_search`（`BtnFilterByActiveTag` → `FilterByActiveTag0`「「風景」で検索」→ `TxtQuery="風景"` / `TxtCount="2 件"` → `BtnNavigationBack` で `3 件` 復帰）、`video_detail_similarity_flyout`（`c-video.mp4` 選択時の `BtnDetailFindSimilar`「似た動画を探す…」から `DetailFindSimilarVideoContent` / `DetailFindSimilarVideoAudio` / `DetailFindSimilarVideoVisual` 展開）、`save_resets_revert_and_updates_tag_label`（`Item3` へ `'夜景, 星空'` 保存後に `BtnFilterByActiveTag` 更新と `BtnRevertEdits` 非表示化）の4項目が PASS。
  - 右クリック項目（`FilterByItemTags{id}` / `FilterByItemTag{id}_0`）の起動検証はロック中セッションのため `card_context_right_click: "BLOCKED: No interactive desktop is available"`（先行試行 `run01` は静的 `AutomationProperties.Name` バグ検出、`run02` は同ロック制約、`run03` は `FilterByActiveTag0` 期待文字列修正のため全ログ保持）。カード右クリック実機操作（`FilterByItemTags{id}` / `FilterByItemTag{id}_0` / `SelectRangeTo{id}`）、音声選択時 `BtnDetailFindSimilar`、長文タグ/棚スクロール実機操作、候補17のクリーンゲスト配布試験、`AIAutoEnvironmentDialog` の `BtnBackToSettings` 実機クリック、実日本語IME、物理DPI、ハイコントラストは引き続き未確認。

### 2026-11-15（夜遅く）：確定タグ絞り込み（B案）・全30タグ選択・棚作成キャンセル案内（frontend-product17 / 1f1ef59）

- UI・仕様・バックエンド実装（`1f1ef5948a82cfd5938d64be8cf274528fe307d9`）：
  - **確定タグの独立絞り込み（B案）**：`items.tags` JSON 配列に対する完全一致（空白含む単一タグ許容、部分一致・同義語展開・ファイル名・未承認AIタグ候補は非対象）として `app/media_filters.py`（`normalize_tag_filter` / `tag_clause`）・`app/ai_scope.py`（`tag`）・`app/production.py`（`ProductionCatalog.search`）・`app/production_server.py`（`/api/items` および `result_provider` 各検索モード）・`app/page_text.py` / `app/tag_candidate_search.py` / `app/tag_semantics.py` / 直接動画・音声検索類似・`Aredoko.Core`（`ResultSearchConditions.cs` / `FolderSearch.cs`）へ `tag` スコープを追加。WinUI（[MainPage.xaml](file:///c:/AI/Aredoko/src/Aredoko.WinUI/MainPage.xaml)・[MainPage.xaml.cs](file:///c:/AI/Aredoko/src/Aredoko.WinUI/MainPage.xaml.cs)・[MainPage.NavigationHistory.cs](file:///c:/AI/Aredoko/src/Aredoko.WinUI/MainPage.NavigationHistory.cs)）へ `TagScopeBar`（`TxtTagScope`「タグ：{tag}」＋ `BtnClearTagScope`「×」）を追加し、`SearchBookmark` / `NavigationHistory` / `ClearSearchConditions_Click` / `StartSimilarityAsync` / `SimilarityBack_Click` 間でタグ絞り込みを保持・復元できるようにした。
  - **全30タグ選択と表記明確化**：`UpdateDetailActions`・`SimilarityMenu` の先頭20件打ち切り（およびツールチップ10件打ち切り）を撤廃し、登録上限30件すべてを `FilterByActiveTag0..29` / `FilterByItemTag{id}_0..` から選択可能とし、ラベルを「〜で検索」から「〜で絞り込む」へ統一。
  - **棚作成後のキャンセル案内**：[MainPage.ShelfPicker.cs](file:///c:/AI/Aredoko/src/Aredoko.WinUI/MainPage.ShelfPicker.cs) へ `ChooseShelfCreateNote` を追加し、作成前および「作成して選択」直後に、作成した棚は「キャンセル」しても棚一覧へ残り作品への選択のみ取り消される旨を明示。
- 検証と確認範囲：
  - `Aredoko.Core.Tests`（終了コード `0`）、バックエンド・起動テスト `tests/test_tag_scope.py` ほか計 `98` 件（`Ran 98 tests in 70.405s OK`）、直接動画・音声検索/類似 `58` 件（`Ran 58 tests in 38.003s OK`）が PASS。
  - 独立ホスト GUI 試験 [check.py](file:///c:/AI/Aredoko/data/gui-tag-scope01/check.py) `run01`（[result.json](file:///c:/AI/Aredoko/data/gui-tag-scope01/run01/result.json)、`frontend-product17`、生成 PNG 4件、独立DB/設定、終了コード `0`・`sqlite_integrity_ok: true`・`originals_sha_match: true`・`passed: true`）で、`all_30_tags_present_and_labeled` / `exact_tag_scope_excludes_superstring_and_filename` / `tag_scope_combines_with_query` / `space_containing_tag_exact_filter` / `history_back_restores_tag_scope` / `clear_conditions_clears_tag_scope` / `shelf_create_cancel_note_and_persistence` の全7項目が PASS。
  - **追加修正（`b8d703e` / `frontend-product18`）**：`FilterByTagAsync` から `Query.Text = ""`、`SearchMode.SelectedIndex = 0`、`if (view == "history" || view == "unreviewed") view = "all"`、`ClearSimilarity()` の自動リセットを除去し、確定タグ選択時も入力済み検索語・検索方法（AI検索含む）・表示ビュー（お気に入り／未確認／履歴／棚）・類似検索状態を保持するよう修正。[check.py](file:///c:/AI/Aredoko/data/gui-tag-scope01/check.py) `run02`（[result.json](file:///c:/AI/Aredoko/data/gui-tag-scope01/run02/result.json)、スタブ `AISearch` 索引併用、終了コード `0`・`sqlite_integrity_ok: true`・`originals_sha_match: true`・`passed: true`）で従来7項目に加え `query_before_tag_preserves_query`（`海` 先入力→`背景` 選択）・`ai_search_preserves_mode_and_query_on_tag_pick`（`両方で探す（AI）`＋`夕焼け`→`背景` 選択で `4 件`→`2 件`）・`favorites_view_preserved_on_tag_pick`（`お気に入り` 維持）の全10項目が PASS。
  - 未確認範囲：実AIモデル組み込み環境でのUI操作、未確認ビュー（`ChkUnreviewedOnly` 有効化時の実UI操作）、カード右クリック `FilterByItemTags{id}` / `SelectRangeTo{id}`、音声類似フライアウト、長文タグ/棚スクロール、配布候補19のクリーンゲスト起動、`AIAutoEnvironmentDialog` の「設定へ戻る」、実日本語IME、物理DPI、ハイコントラスト。

### 2026-11-16（深夜）：実AI日本語検索＋カード右クリック確定タグ絞り込み〜解除・履歴復元（frontend-product18）

- 検証内容（[check.py](file:///c:/AI/Aredoko/data/gui-ai-tag-scope01/check.py) `run02`、[result.json](file:///c:/AI/Aredoko/data/gui-ai-tag-scope01/run02/result.json)、[final-after-back.png](file:///c:/AI/Aredoko/data/gui-ai-tag-scope01/run02/final-after-back.png)）：
  - 既存検証済み AI 環境（`EmbeddingGemma 2` + [ai-cu128](file:///c:/AI/Aredoko/data/auto-ai01/runtimes/ai-cu128-4ca5077c8ad66ea77b93f828)、22,652 ファイル・4,861,676,424 バイト実検証通過）と生成 PNG 4 枚（`blue_sky.png` / `red_sunset.png` / `green_forest.png` / `mono_grid.png`、`indexed: 4`、155.87 秒）を用い、独立 DB・設定・`frontend-product18`（[Aredoko.WinUI.exe](file:///c:/AI/Aredoko/data/development-tools/frontend-product18/Aredoko.WinUI.exe)）をホスト通常デスクトップ（`WinSta0\Default`）上で通し検証した（コマンド実行基盤の隔離デスクトップ `WinSta0\exebox-*` では `winapp ui click --right` の `SendInput` が「No interactive desktop is available」でブロックされるため）。
  - **PASS 項目（`exit_code: 0`・`sqlite_integrity_ok: true`・`ai_sqlite_integrity_ok: true`・`originals_sha_match: true`・`passed: true`）**：
    1. `japanese_ai_search`：`ModeSemantic`（`両方で探す（AI）`）で `"空や森や海などの風景"` を検索し、`4 件`（`Item1` `blue_sky.png` へ `文字一致0/1語 · AI候補\n順位統合値 0.0163`）を表示。
    2. `card_right_click_confirmed_tag_in_ai_search`：カード `Item1` を右クリック → `FilterByItemTags{id}`（`タグで絞り込む（2 件）`）→ `FilterByItemTag{id}_0`（`「青空」で絞り込む`）選択で、`TxtTagScope="タグ：青空"`、検索語・`両方で探す（AI）` を保持したまま `1 件`（`Item1` のみ）へ絞り込み。
    3. `clear_tag_restores_original_ai_scope`：タグチップの `×`（`BtnClearTagScope`）で `TxtQuery`・`両方で探す（AI）` を維持したまま元の `4 件`（`Item1..4`）へ復帰。
    4. `history_back_restores_tag_condition`：履歴の「戻る」（`BtnNavigationBack`）で `タグ：青空`・検索語・`両方で探す（AI）`・`1 件`（`Item1`、スクリーンショット `final-after-back.png` 確認済み）を復元。
  - なお終了時の `PermissionError: [WinError 32] ... derived.sqlite` はテスト終了直前の `sys.exit(0)` 後の Python `weakref._exitfunc` による一時サムネイルディレクトリ片付け警告であり、検索・UI・DB 整合性結果（`passed: true`）には影響なし。
  - 残る未確認範囲：カード右クリック `FilterByItemTag{id}_0` 単一タグ直出し（2個以上時と別分岐の実AI併用）・`SelectRangeTo{id}`・未確認ビュー実UI操作・音声類似フライアウト・長文タグ/棚スクロール・`AIAutoEnvironmentDialog` の「設定へ戻る」・実日本語IME・物理DPI・ハイコントラスト。

### 2026-11-16（UI仕上げ）：スコープバー狭幅応答性・音声類似フライアウト明確化・長文タグ/棚・設定往復（frontend-product19）

- 実装（[MainPage.xaml](file:///c:/AI/Aredoko/src/Aredoko.WinUI/MainPage.xaml)・[MainPage.xaml.cs](file:///c:/AI/Aredoko/src/Aredoko.WinUI/MainPage.xaml.cs)）：
  - `TagScopeBar` と `ShelfScopeBar` の `MaxWidth="360"` ＋ `StackPanel` を `Grid`（`*` / `Auto`）へ変更し、詳細ペインを開いた `1200×800` でも長文タグ・複数棚サマリ表示時に「×」「棚一覧」「棚を変更…」「解除」が右端で見切れないよう改善。
  - `AddSimilarityMenuItems` へ動画・音声類似メニュー構築を集約し、音声の直接音響類似ラベルを「音の響き・音響が似た音声・曲を探す」へ明確化するとともに、一覧右クリック・詳細フライアウト双方へ説明ツールチップを付与。
- 検証：
  - `Aredoko.Core.Tests`（`-c Release` 終了コード `0`）、`dotnet publish -c Portable` で [frontend-product19](file:///c:/AI/Aredoko/data/development-tools/frontend-product19) および `portable-build.json`（`inspect_portable` PASS）を生成。
  - 独立ホスト GUI 試験 [check.py](file:///c:/AI/Aredoko/data/gui-ui-polish01/check.py) `run06`（[summary.json](file:///c:/AI/Aredoko/data/gui-ui-polish01/run06/summary.json)、生成 PNG 2件 + 生成 WAV 2件、独立DB/設定、終了コード `0`・`db_intact: true`・`originals_sha_match: true`）と 5 枚のスクリーンショット目視確認で以下すべてが PASS：
    1. `detail_30_tags`（[detail-30-tags.png](file:///c:/AI/Aredoko/data/gui-ui-polish01/run06/detail-30-tags.png)）：30タグ＋4棚でも `TxtTags` 高さ `120px` 上限内で縦スクロールし `BtnSave` や `BtnFilterByActiveTag`（`この作品のタグで絞り込み（30 件）…`）を押し出さず、`TxtShelf` へ `…ほか1棚` サマリ表示。
    2. `tag_scope_narrow_1200x800`（[tag-scope-narrow.png](file:///c:/AI/Aredoko/data/gui-ui-polish01/run06/tag-scope-narrow.png)）：詳細ペイン展開中かつ 30 番目の長文タグ適用時に `BtnClearTagScope`（`x=803..827`）が `area_right=880` / `detail_left=913` 内に収まり見切れなし、「×」解除で `4 件` 復帰。
    3. `shelf_scope_narrow_1200x800`（[shelf-scope-narrow.png](file:///c:/AI/Aredoko/data/gui-ui-polish01/run06/shelf-scope-narrow.png)）：詳細ペイン展開中かつ長文 4 棚適用時に `BtnShelfList`・`TxtShelfScope`・`BtnChangeShelfScope`・`BtnClearShelfScope`（`x=828..880`）が `area_right=880` 内に重なりなく収まり、「解除」で `4 件` 復帰。
    4. `audio_similarity_flyout` / `audio_similarity_back_ok`（[audio-similar-flyout.png](file:///c:/AI/Aredoko/data/gui-ui-polish01/run06/audio-similar-flyout.png)）：生成 WAV 選択時の `BtnDetailFindSimilar`（`似た音声・曲を探す…`）で `DetailFindSimilarAudioContent`（`内容が似た音声・曲を探す`）と `DetailFindSimilarAudioVisual`（`音の響き・音響が似た音声・曲を探す`）の両項目表示とクリック→`SimilarityBar`→`BtnSimilarityBack` 復帰を確認。
    5. `settings_ai_env_back_roundtrip`（[ai-auto-env-dialog.png](file:///c:/AI/Aredoko/data/gui-ui-polish01/run06/ai-auto-env-dialog.png)）：`SettingsDialog` → `BtnAIEnvironment` → `AIAutoEnvironmentDialog` → `BtnBackToSettings`（`設定へ戻る`）で `SettingsDialog` へ復帰し閉じるまでを確認。
  - 残る未確認範囲：通常デスクトップ対話操作が必要なカード右クリック項目（単一タグ直出し `FilterByItemTag{id}_0`・範囲選択 `SelectRangeTo{id}`）、未確認ビュー実UI操作、実日本語IME変換、物理マルチDPI・ハイコントラスト。
