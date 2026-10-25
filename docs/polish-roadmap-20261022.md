# Aredoko 総合改善・完成形UI移行ロードマップ

2026-10-22。ユーザー承認済みのAstra統合計画を実装用に収録する。**過去のGUI試行上限や事前許可記述より、[現行テスト方針](local-test-policy.md)を優先する。**旧文書・既存機能は保持し、本書の順序を古い「次の作業」より優先する。基点は `8c0a63e` / `feat/winui3-production-mvp-20261011` / Draft PR #5。R13 DOING / R14 PARTIAL / M1・M2未完。WindowsはWinUI 3を維持する。

## 現行実行キュー（2026-10-25、実機フィードバック計画）

[改善計画 U1–U6](usability-followup-20261025.md)を直近の実装キューへ統合する。**U1/U2はsourceと限定UIA確認、U3とU5aは部分実装済み。次はU4a（登録後scan選択と初回ガイド）**。物理入力、報告APNG原本の黒化、大画像/RSS等の残件は追加計画とhandoffを参照する。元のP0–P7/製品ビジョン・実装済み機能・未受入は維持する。

1. **U1/P3/UI**：Ctrl+Homeの吹き出し、ナビ見出し、長名、明示詳細、検索方式のヒント。
2. **U2/P1/UI**：動かない操作バー、下端表示、OSタイトル、ビューア内設定、中心zoom/drag、本の双方向循環。
3. **U3/P1/P3/P7**：WebP/APNGのカクつき/黒化、大容量GIF、既存cacheの改善。先行の高解像度APNG/CBZ性能残件をここへ統合し、無変更の旧試験を繰り返さない。
4. **U4/P3/P4/P6**：初回ガイド・登録後scan選択、一覧とAIの分離、folder別起動時scan、成功した再scan後だけ欠落を通常一覧から除外。
5. **U5/P3/P4**：お気に入り差分更新、Ctrl/Shift複数選択と一括棚/お気に入り。
6. **U6/P3/P6/P7**：ZIP/CBZ共通の圧縮ファイルfilter、限定統合確認、新候補への反映。

単位ごとの実装/完了条件/最小確認は追加計画が正本。独立したU4aはU1後に先行可能。runtime公開権利/host、HC/DPI/clean Windows、M1判定、R06–R09音声/音楽は削除しない。最新の完了IDと次の1件は[current-handoff](current-handoff.md)を参照する。

## 先行実行キュー（2026-10-25、Antigravity引き継ぎ時の記録）

**最新差分**：モデル2件は実転送/再開/全hash検証・限定生成GPU/CPUまで確認済み。runtime通知52配布物の収録とローカル封印packは完了、runtimeの公開監査/輸送単位/公開先/製品catalogは未完。初回案内・使い方はsource実装/build済み、新しい基本ZIP05/source0b21b3eへ反映しCPU11 PASS、次は許可後の限定GUI。[最新再開位置](current-handoff.md)を優先する。

元のP0–P7と製品ビジョンは維持する。以下は実機フィードバック前の作業順で、現在は上のU1–U6と最新handoffを優先する。実装済みと限定確認済みは区別し、未検証を発生中の致命的不具合と呼ばない。

| 順 | 仕上げる単位 | 完了条件・次への移行 |
| --- | --- | --- |
| 1 | Antigravity差分の関連レビュー・永続cache回復 | 破損LRU/整数上限/schema/接続解放を生成CPUテストで確認。既存P5形式2とDPIの成功flowを無変更反復しない |
| 2 | P3/UI-2：日常の主画面を完成形へ | 媒体に適した詳細操作、検索根拠の表示密度、棚との統一。選択・draft・検索条件を維持し、変更画面のbuildと限定確認後に次へ。全配布完成を待たない |
| 3 | P3：大量表示で残る具体的な負荷の削減 | cacheヒット時の書込を集約。保持600件の両方向scroll・最終行・サイズ変更の残受入を一つの生成caseにまとめる。5万件metadata/全体RSS/物理DPI移動は別項目、未計測を達成扱いにしない |
| 4 | P6：実配布でAIを取得できる状態 | WDと現行EmbeddingGemma 2は登録済み。追加検索モデル/runtimeは固定URL/容量/hash・完全NOTICE・公開先の揃ったpackから追加登録。外部情報が欠ける項目は明示して保留し、架空値で埋めず独立実装へ進む。新規取得は具体的な許可後 |
| 5 | P7：残受入をまとめM1日常β判定 | 条件付き連続閲覧、棚管理、復元失敗保全、HC/DPI、clean Windowsを未確認表から一度ずつ確認。再現した欠陥だけ局所修正。M1後はR06–R09の実音声・音楽へ戻る |

**現在の到達点**：P5形式2は `2f4de23` で通常EXEから復元active→次回pendingの限定native一連を確認済み。P3永続cacheは同commit、カード/詳細/棚の再取得接続は `e46c53d`、表示サイズ100→180%と再起動cacheは `56e3c8e` で限定native確認済み。**表示サイズの倍率変更は、実モニター間DPI移動の確認と同一ではない。** 旧20261024基本ZIP03/source47acf2fは履歴。20261025基本ZIP05/source0b21b3eは後続cache/詳細/モデル取得・WD/初回案内を収録。正確な候補はcurrent-handoff参照。

状態は「実装」「確認済み範囲」「残る実装」「残る受入」を分ける。ロードマップ全体は未完。報告には今回の利用者向け変化と次の1件を記し、古いテスト数の列挙を主目的にしない。

## 2026-10-25 継続checkpoint（現行）
- P1/P7：添付10.gifのread-onlyコピーで55frames/2cycleのWebP再生、frame割当453msと正常解放を確認。次は生成高解像度APNG/CBZの初frame・切替・RSSを一つのcaseにまとめる。小素材の単回値をHoneyview同等・全ちらつき解消の証拠にしない。
- P3/UI-2：最終行のlayout/scale anchorを修正、現検索のCtrl+Home/End、空棚/履歴/お気に入り・準備/中断案内を改善。5万metadata（実PNG80）で端への移動とbounded cardを限定native確認。全件初回snapshotはプロファイラー付き約24.5秒で待ち時間が残る。全5万実媒体・長時間RSS/HC/物理DPIは未受入。
- P4：共通list/grid棚一覧→中身→片方の所属解除→削除取消/確定→検索条件解除を生成native確認。棚/原本を再実装・作り直す必要はない。登録フォルダお気に入り等の未確認分は別。
- P6：初回案内/使い方はZIP05で限定native済み。runtimeは単一ZIP輸送と安全な展開/再開/取消を実装、実ローカルpackの全hash roundtrip済み。公開権利/native依存reviewとhostは残り、registry0。復元再選択修正e197723を基本ZIP07へ収録、基本CPU11/通常EXEの失敗→有効backup再選択→未同意block→破棄→元DB再起動を28checks/4所有exit0で限定確認した。正確な候補/次の1件は[current-handoff](current-handoff.md)を優先。

## 日時付きcheckpoint（以下2節は当時の記録）

## 2026-10-24 P5更新

実装 `1ca11d4`。[最新チェックポイント](restore-review-20261024.md)を優先する。復元準備のdirectory/ZIP・認証API・Core・明示破棄、切替のpayload検証/排他/ready条件まで実装済み。当時の次は所有ランチャーの正常停止・再起動とWinUI接続だった。この工程と形式2の限定native一連は後続で完了し、現行キューではP3/UIとP6を進められる。

## 2026-10-24 独立P6基盤更新

[LD4b取得基盤](ai-acquisition.md)：固定catalog/Range再開/検証後新version/認証所有jobまで接続。製品catalogは未登録、実取得/GUI/Core/選択保存/clean Windows未完。P5のGUI picker受入等を完了とせず、独立したCPU実装を進めた。

## 到達点と再開位置

| 作業 | 現在の状態 | 次に行うこと |
| --- | --- | --- |
| P0 基準整理・UI-0 | PARTIAL。[診断・共通surface・下部保存](windows-sync-20261023.md)を実装/build確認。配布照合/nativeは未受入 | 小さな縦切りとして継続する。P0全完了とはしない |
| P1A 画像の実形式判定 | CPU_DONE `0f2e005`。Python37/Core771/Portable build合格、最新handoff参照 | 実機表示未受入と配布未更新を明記 |
| P1B 逐次アニメーション再生 | source/関連Python/Core/native生成限定PASS。[証拠/限界](animation-streaming.md) | 70frame APNG/2loop、GIF、GIF名WebP、open-firstで1要求削減。大画像/RSS/全FPSは未受入 |
| P2 結果セッション・連続閲覧 | PARTIAL。[native接続](result-session-native-connection.md) | 60↔61/120↔121・復号完了後のdetail復帰を生成素材で確認。全検索/ソート/条件のnative受入は残る |
| P3 一覧・サムネイル・UI-2 | PARTIAL。[双方向600件・隠したdraft保全](p3-continuous-browse.md) | 745生成itemで追加/eviction/逆方向/draft明示保存を確認。全thumbnail速度/RSS/HC/DPI/最終row表示は残る |
| P4 複数棚・整理導線 | PARTIAL。[履歴削除](history-deletion.md)と[複数棚の移行/検索/API](multi-shelf-storage.md)を実装 | [Core/棚一覧/複数選択](shelf-ui-20261023.md) source接続・893 Core確認、native3/3でcard/atomic save/create/renameを確認、Open以降の残件は未受入。[画面履歴](navigation-history-20261023.md) source接続。[root favorite](root-favorites-20261023.md) source/904 Core接続。[root複数初期棚](root-shelves-20261023.md) source/911 Core接続。次P5（native残件は未受入） |
| P5 起動中backup/restore | 実装済み・限定確認済み。[形式2 active/pending](backup-active-selection.md)と通常EXEの再起動まで接続 | 大容量・失敗時保全・HC等の残受入はP7へ。形式2の成功flowは再実装しない |
| P6 配布・UI-3 | [基本ZIP03](portable-refresh-20261024.md)・モデル別配置UI、WD/EmbeddingGemma 2の実catalog2件を接続 | 両モデルNOTICE付き。新候補のCPU/画面確認、runtimeの公開先と完全NOTICE、clean Windowsは残る |
| P7 総合検証 | 未実施 | 主要機能を揃えてまとめ確認、M1判定後R06–R09へ |

実装は小単位で進める。P1A完了をP1全体/ロードマップ全体の完了と扱わない。旧Alpha、basic03等の配布候補と現在source/buildは別物で、明示的な新候補作成まで配布済みとはしない。

## 現状分析

- 登録・文字/AI/WD/類似/本文検索、ページ・時刻根拠、閲覧/タグ等の整理基盤は存在する。原本guard、モデル/profile空間、従来の順位を維持する。
- 提供された `10.gif` は実際には367×359/55frameのanimated WebP。既存Pillowで先頭を復号可能。`.gif`名によるnative GIF選択が拒否原因。他のGIFの全原因を断定しない。
- P1Bが逐次アニメーションを実装し全PNG待ち/64frame切捨てを撤去。Core/Portable build確認済み、生成70frame/2loopの限定nativeと先頭割当の単回比較は確認済み。全形式/大画像/RSS/FPSは未受入。
- P2が非同期neighborで60/120境界を越えるsourceへ接続。Core跨ぎテストはWindowsで合格、通常生成素材の60/120境界とdetail復帰は限定native確認済み。全検索条件は未受入。
- 一覧は標準containerの要求に応じてcardを生成する（[実機の範囲と残課題](p3-native-containers-20261023.md)）。P2結果sessionは順位spoolを一回消費し、P3 ResultWindowが120×5で保持する。連続scrollは[双方向追加読み込みsource](p3-continuous-browse.md)まで実装し、実機は745生成itemの追加/600保持/逆方向/draft保全まで確認し、全thumbnail/RSS等の受入が残る。
- P3 thumbnailは派生/shared/可視優先/DPI edge/所有RAM・永続disk cacheまで実装。生成26媒体の再起動hitを限定確認済み。大量画像/実decoded全体RAM・物理DPI移動は未受入。
- 棚は独立ID/空棚/複数所属・atomic移行/全検索条件/API/Core/native編集へ接続済み。棚nativeの未到達工程とroot管理GUIの受入は残る。旧単一値は互換用で、情報を失う更新を拒否する。
- backupは起動中job/API/設定UIまで実装済み。復元の起動先切替/rollbackのsource・CPU契約は実装済み。形式2 active/pendingのnative一連は限定確認済み、大容量・失敗条件の残受入は未完。viewer設定theme/scale等と旧validatorの不一致は2026-10-22に修正済み。P4/P5のschema移行・起動中snapshot/設定整合の全実機受入は残る。

## 実装順と完了条件

### P0 — 基準・UI-0

診断に版/commit/channel/実行場所を示し、実候補とreceiptを一致させる。新候補は新規出力先へ作り旧Alphaを黙って更新しない。既存resource辞書から色・余白・文字・角丸・アイコン・選択/hover/focusを整理する。Light/Dark/High Contrastを扱い、変更した画面から適用。**完了**: 識別と共通styleの関連build確認。全画面適用/全配布受入を待たない。

### P1 — 形式・アニメーション

P1A: 検証済みhandleのheaderでcontainerを判定する。原本名は変更せずMIME/decoder選択を合わせる。真のGIFはnativeを優先し失敗時既存frame経路へ。metadata probeはframe列挙/画像復号を行わない。原本/除外/解除/祖先guardを保持。

P1B: Pillowの所有decode sessionを追加し、開いたまま逐次復号。先頭を先に表示、後続は最大4frame/128MiB以内の先読み。全frame分のPNG/HTTP往復/BitmapImage配列と64frame切捨てを廃止する。合成済みpixelをbinaryで転送し再利用bufferへ表示。poster、blend/disposal、透明度、duration、有限/無限loopを維持。最後の正常frameを保持し黒く消さない。切替/取消/closeは所有sessionを解放し古い応答を拒否。復号作業領域と描画bufferは先読みとは別に計上。静止画元解像度、CBZ先読み/cache、表示後の位置save/close flushを保つ。AI代表frame規則は変更/自動再索引しない。

**箇所**: image inspection/preview API、Core契約、codec/viewer。**確認**: 提供sampleはread-only、生成GIF/APNG/WebP/64超/poster/透過/2loop/取消、関連Python/CoreとWinUI build。実機/同等速度は別。**移行**: 関連確認が通ればP2へ、Honeyview比較の反復で停止しない。

### P2 — 結果セッション・連続閲覧・UI-1

検索語/方式/kind/root/shelf/favorite/sort/AI条件/modelを固定する短命sessionを追加。通常/AI/類似/本文/候補タグ/履歴の共通契約にし、作成・状態/範囲取得/前後の閲覧対象/終了を提供する。旧page APIは互換維持。既存の正確な順位とspoolを再利用し、追加取得のたびに再計算しない。ID/順位/根拠をdiskへ、全件metadata/画像をRAMへ展開しない。同順位はstable ID。最大3session/idle15分/一時領域全体512MiB、上限時に黙って切り捨てない。

順序を固定し閲覧履歴追加で並べ替えない。解除/除外/access範囲/原本版は取得時に再検証する。条件/index変更時は異なる結果を混ぜずrefresh案内。期限切れも条件と現在IDを保持。viewerは未取得画像を非同期で取り、混在一覧では画像だけ検索順に移動する。本の内部page送りとは分け、閉じたら最後のitemへ選択/scrollを戻す。読込失敗を末尾と偽らない。

**箇所**: search/spool寿命、Core API/sequence/MainPage状態。**確認**: 60→61/61→60/120→121、通常/AI/類似/root/sort/混在、古い応答/条件変更/解除/expiry、再順位計算なし。**移行**: 契約が固まったらP3と本格UIを一体で開始。

### P3 — 仮想化・サムネイル・UI-2

全ListViewItemの手作業生成をやめ、標準container再利用とdata virtualizationへ。120件単位/最大5block、可視と近傍のみ保持。過去のWinRT binding crashを踏まえ型情報/x:Bindと変更範囲のWindows Releaseを確認する。連続scrollを既定とし、新たなpage件数設定は追加しない。

backendが表示に近い派生画像を作り、フロントでのPNG再変換を減らす。128/256/512/1024px段階、DPI/表示サイズに合わせる。keyは原本版/page/size/方式版。可視優先/近傍先読み/画面外取消/同一要求共有、片方の取消で共有相手を失敗させない。初期は並列2、decoded RAM64MiB/disk512MiB。cache hitも現在のscope/版確認、壊れたcacheや容量不足で基本閲覧を止めない。

UI-2は左nav/中央検索と一覧/右詳細を本格移行。gridは媒体優先、listは高密度。小tileは画像/名前、種別iconを優先し正常な「登録済み/画像プレビュー」を常設しない。失敗/未接続/scope/AI区分は保持。長名は省略、tooltip/詳細/読み上げで全文へ。size変更は行を自然に埋め、選択/未保存/scrollを維持。右詳細のpreview/property/tag/shelf/AIを整理し狭幅はdrawer。folder操作は内容幅と8DIP間隔/折返し、全folder操作は別group。設定saveは下部closeの隣へ。

**確認**: 5万生成metadataでUI/画像が全件数に比例しない、再利用cellの画像混入なし、size/detail/選択/draft/scroll保持、Light/Dark通常幅1回。**移行**: 利用可能になればP4へ。細かな装飾や全DPI確認待ちで止めない。

### P4 — 複数棚・整理

安定IDの独立shelf、item所属、root初期棚の関連を追加。空棚を保持し、既存items.shelf/default_shelfをtransaction移行。DB版を上げ旧appの書込を拒否しbackup schemaも同時更新。新APIはshelf_ids、旧scalarが複数所属を失わせる要求は拒否する。複数棚はOR、他条件はAND。全検索でbackendに適用、client後filterやjoinの重複件数で代用しない。

棚→一覧→中身を共通library/breadcrumbで実装。作成/名前変更/削除/複数item追加・所属解除。棚削除でitem/原本/tagを削除しない。詳細は複数選択。履歴の個別/全削除（全削除は確認）を追加し読書位置は保持。削除前の遅延saveによる履歴復活を世代管理で防ぐ。root favoriteはitem型に偽装せず保存。画面履歴に条件/root/shelf/scrollを保持し、mouse前後はviewerの画像/pageとlibraryのnavigationを使い分ける。

**確認**: 旧所属の移行一致、2棚→片方解除、空/rename/delete/root初期棚/再起動、全検索とviewerの範囲一致、backup復元/移行失敗の保全。**移行**: data安全確認後P5。

### P5 — 起動中バックアップ・復元

設定内からcheckbox選択: library基本情報（登録/tag/shelf/favorite等）は必須、設定/profile・履歴・読書位置は初期ON、AI索引は初期OFFで容量表示/追加可。前回選択を保持。原本/model/Python/thumbnailは含めない。

backend所有jobとし、全writerを論理操作の安全な区切りでpauseして対象DBのread snapshotとsettingsを同時点で固定する。SQLite backup APIで新規先へcopy中は検索/閲覧を継続。大規模indexは終了までpauseしてWAL増大を抑制。非選択履歴等の除外はcopy先だけで行い、完成manifestは成功時だけ公開。全DB/settingsの整合はアプリ側で調整、live file copyや実行中CLI呼出しで代用しない。

restoreは全bundle検証→新directoryへ→未保存確認/所有job・接続正常終了→起動先切替/再起動。旧libraryは残し、新ready失敗なら旧pointerへ戻せる記録を保持。旧bundleも新規復元後に既知migration。現在/旧settingsを版ごとに検証し、別PCのruntime/model pathは自動実行せず再確認。省略AI/鮮度不一致は明示再索引へ。CLI説明を通常画面に並べず、選択/進捗/取消/結果をUIで完結する。

**確認**: copy中閲覧、選択した棚/設定/履歴/AIの復元、取消/容量/破損/上位版/切替失敗/旧bundle、原本と現在DB保全。**移行**: data損失ケースを必須確認後P6。

### P6 — 配布・UI-3

LD4aからLD4b trusted catalog/transactional取得/再開/検証公開を実装。LD5はアプリ取得/既存指定/手動案内を一つの設定入口へ。default速度無制限・任意cap。基本Pythonと任意AIを分離し、system pip/driverを必須にしない。軽量通常検査/進捗/明示full修復を接続、新規ZIP候補と普通のAredoko.exeを用意。UI-3は設定/初回/進捗/空/エラー/各管理画面を統一し、到達できる機能は削減しない。

**確認**: 生成HTTPの切断/再開/取消/破損、AI未導入/取得中の基本操作、ZIP再配置/再起動保持。新asset実取得は対象/容量/取得元を示し別許可。**移行**: 揃ったらP7。

### P7 — 総合検証・M1判定

各画像/長いanimation/CBZ/folder本、60/120境界と全条件、5万metadata/scroll/cache/取消/RSS、編集/棚/履歴/navigation、online backup/restore、Light/Dark/High Contrast/DPI/keyboard/主要読み上げ、ZIP通常起動/再起動/再配置/開発環境なしWindowsをまとめ確認する。目標は通常素材のcache済静止画/CBZ切替概ね250ms以内、一般animation開始概ね1秒以内、zoom/pan継続freezeなし、距離/loopに比例するメモリ増加なし。API応答/XAML代入を表示完了と同一視しない。Honeyviewは同素材/条件で少数比較、支配的遅延だけ修正し同じ全体試験を反復しない。

M1画像/本/動画の日常βが整ったら実音声/音楽producerのR06–R09へ。M1を全媒体完成と呼ばず、UI微調整を理由に音声を永久延期しない。

## 完成形UIと開始条件（全機能完了を待たない）

[既存方針](design-vision-winui.md)を継承。compact左nav、中央上部検索、広いmedia主役のgrid/list、右preview/property/tag/shelf/AI根拠。charcoalと控えめな紫/青accent、Fluent標準controlとresourceを用い、Light/Dark/High Contrast・focus・未保存・取消を保持。通常1200–1600px優先、極小窓最適化は最低限。過剰な影/発光/常時motionを避け、Mica/Acrylicは任意。技術説明はdocs/logへ、通常UIをテスト用文言で埋めない。

UI-0=P0（token準備）、UI-1=P2後（骨格）、UI-2=P3（主画面）、UI-3=P4–6（管理/設定/導入）。開始gateは登録→検索→一覧→閲覧→編集保存→再起動が使え、起動不能/通常crash/data損失/scope漏れがなく、主要な再生と60件不具合と一覧契約が解消したこと。**配布/全音声/細かな全bug/総合検証はgateに含めない。** 同じSolが機能とUIを小単位で交互に進めてよく、複数agentを前提にしない。新機能は共通完成形UIで作り、仮UI→全面作直しを増やさない。

## 将来の別ネイティブfrontendを妨げない設計

- Windowsのmain frontendはWinUI 3。Linux/macOSの別frontend実装やAvalonia/Qt/Tauri選定は今行わず、WebViewへ移行しない。
- 共通backend: Catalog/tag/shelf/rank/index/result session/job/backup。WinUI: layout/render/input/focus/draft/selection/dialog。Windows launcher: EXE/runtime/process/repair。
- 共通APIはID/条件/根拠/進捗/取消/capability/error codeとbinaryを扱い、HWND/WinUI型を含めない。pixelはwidth/height/stride/format/alphaを明示する。
- 共通PythonへUI依存を持ち込まず、検索/範囲/rankをWinUIに重複実装しない。
- path/物理identity/lock/監視/process/pipe/保存場所は必要な境界でOS処理を分離。単純なlowercaseやslash置換でpathを共通化しない。logical IDと物理版を分け、他OS復元では将来明示root再指定を可能にする。
- portable化を理由に原本/祖先/reparse/symlink/leaseを弱めない。未使用Linux/macOS処理、汎用plugin、別OS CI、大規模移植refactorは今作らない。変更箇所から必要範囲だけ抽象化。
- GPU/model/decoderはcapabilityで表し、Windows/NVIDIA常在を仮定しない。Windows最適化は境界内で許容する。

## OSS判断

Windows標準/WICは維持、Pillowは逐次decode/派生画像へ。Win2D（MIT/WinUI3）は描画が支配的な遅延と測れた場合にcanvasだけ比較。SkiaSharpは今回見送り・Win2Dと同時導入しない。libvips（LGPL）はcache/重複整理後も生成が遅い場合、libarchive（主にBSD）は多形式の明確な必要時、libmpv（default GPL/構成別LGPL）は動画固有の別判断。速度が上がると仮定して全面置換しない。採用版/依存/license/保守/メモリ/実装負担を確認し、新取得は別許可。

## 自律開発・記録

実装→関連build/test→次機能→主要機能後の総合確認。毎回の全回帰/benchmark/再調査は禁止。重大data移行/復元/検索範囲/取消後saveは必要安全確認。GUI待ちだけで独立作業を止めない。過去GUI capsは履歴として保存するが、**新しい差分や原因に基づく修正のテストは禁止しない**。[ローカルGUI/GPU・失敗診断方針](local-test-policy.md)を優先し、生成fixture/独立DB/既存モデルでの関連GUI/GPU試験は許可不要。同じ不具合を別名で繰り返し上限回避しない。CI既定なし、main mergeなし、private scan/原本/普段DBの無断変更なし、専用OCR保留。

commit/実候補/完了小区分/未検証/未完/次の1件だけhandoffへ。AGENTSは入口、完成台帳は状態、本書は実装計画、design文書はUI正本と役割分担し重複checkpointを増やさない。Astra再相談はrank/scope同値性、複数棚移行の情報損失、複数DB/settings整合、全面render構造変更、OS分離と安全/性能衝突の場合だけ。通常実装はSolで継続する。

2026-10-22の終了/shutdown指示は今回だけ。保存/関連確認/commit/引継ぎを確認後 `Stop-Computer` をForceなしで行い、拒否/権限/未保存/data危険があれば強行しない。翌日自動再適用しない。
