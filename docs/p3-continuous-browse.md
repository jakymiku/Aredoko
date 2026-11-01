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
