# 最新ビルドUI点検（2026-10-20）

## 2026-10-20 最新UIの実画面点検をユーザー指示で再開

ユーザーの「そのまま続けて作業してください／最新版のUIにも不具合がないか確認しておいてください」を受け、旧AppX取り違えの修正後harnessで検証を再開する。旧3回の失敗記録を保持し、再開の根拠を明記する。過去の復旧/book-batch上限をresetする指示ではない。

今回の範囲：生成PNG/WAV/CBZ、Light/Dark、小窓700×620の詳細操作・固定保存ボタン・スクロール余白。現在のx64 Releaseをbuildし、実PIDのexe pathと配備5ファイルが一致してからUIAを操作する。合格後に一覧/グリッド、登録フォルダ、設定、各viewerの主要導線を追加点検する。私物走査/原本変更/新DL/GPU推論/Actions/main mergeはしない。

今回の初回＋修正再試行は最大2回。生log/PNG/reportを新規先に保存し、結果は次節へ追記する。

## 初回（current-detail-20261020-01）

実PIDのexe pathと配備5ファイル一致を確認。Light画像・音声の操作/保存行/右端gutterはPASS。PNG3枚を目視（画像、音声、失敗時の本）。本の場面でharnessが幅71pxの「本を開く」に80px以上を要求し、不要な追加スクロールを続けて失敗した。製品の書籍ボタン欠けとは断定しない。自然なボタン幅に合わせて下限64pxへ訂正。

実際の不具合：`Page_Loaded` が接続完了後に左ナビを無条件Left/展開へ戻しており、小窓の初期幅判定を上書きしていた。起動時/SizeChangedで同じ幅判定を使うよう修正し、700pxでは48px以下のcompact項目であることをassertする。再試行1で確認予定。旧test報告は上書きしない。

## 詳細パネル再試行1（current-detail-20261020-02）

Light/Darkの700×620、画像/音声/本6状態すべてPASS。実exe path/配備5ファイル一致、起動時compact navigation、ボタン全体の寸法・ヘッダーと固定保存行の間への収まり・右端gutter・音声案内・原本bytes/mtime不変を確認。全6PNGを目視済み。書籍の画像名などが消えているPNGは操作列を表示するための明示スクロール後であり、固定タイトル/保存行は保持している。

## 一覧/フォルダ/設定/viewerの追加点検（実行前に固定）

同じ配備検証/生成fixture基盤の `--daily-only` で別flowを点検する。4項目（PNG2/3page CBZ/WAV）を使い、両テーマのwide list/grid・詳細のタグ保存・narrow grid・設定・登録フォルダの操作/追加・画像送り/読書表示設定/音声transportを確認する。これは旧復旧/book-batch flowの再実行ではない。初回＋修正2回まで、failを残し全PNGをレビューする。実音声意味検索/GPU/コーデック網羅/High Contrast/DPI変更/Narratorは対象外。

## 日常flow初回と、追加ユーザー指示

`current-daily-20261020-01` はLightのwide list/gridまでPASS、保存完了ラベルをharnessが「保存済み」と誤って期待して停止。実画面/既存コードは「保存しました」で、保存自体と詳細維持は正常だった。保存後/一覧/グリッドのPNG3枚を目視、判定文字列だけを修正。

実行中、ユーザーから「白色だとアイテム同士の境界が見えない」「境界線に線/背景色を少し変える」と追加要望。ライブラリ/登録フォルダのlist/gridに共通のCard背景・1px枠・角丸・8px間隔を追加する。ネイティブListViewItemのtemplateは置換せず、選択/hover/focusと全操作を保持する。Light/Dark双方のスクリーンショットで確認する。併せて画像検索の旧「動画対象外」案内を実装に合わせて訂正する。

## 日常flow再試行1と修正

`current-daily-20261020-02`: 生成4項目、両テーマで画像2/2への送り、本表示設定、音声seek/音量、設定、タグ保存、配備照合/終了まで実行。20PNGを全て目視。実不具合は小窓の登録フォルダfilter幅不足とsummaryの過剰折返し。追加formはheader不合格のため未検証。FAILを保持し、残る修正再試行1回で確認する。header/actionsを複数行へ分け、登録formだけを制約付きscrollにする（ListView自体は包まない）。

## ユーザー追加要望：表示サイズ（実行前に固定）

2026-10-20「エクスプローラーのようにアイテムのサイズを可変」に対応。表示サイズflyoutのnative Slider（60–180%、20刻み）、Ctrl+wheel、標準へ戻す、既存viewer設定v1への後方互換保存。一覧/グリッドで既存containerの寸法だけを変更し、再検索/索引/dirty編集破棄を起こさない。短いviewportではthumbnail高を抑えて名前領域を確保する。

新feature flowは同じ配備検証/生成fixtureの `--size-only`。両テーマのlist/grid、小窓、slider、実Ctrl+wheel/通常wheel、選択/タグdraft保持、保存/次起動読込、resetを確認する。初回+修正最大2回、全PNG目視。既存daily/復旧/book-batch枠のresetではない。HighContrast/DPI/Narrator/GPU/私物は対象外。

## 表示サイズflow初回

`item-size-20261020-01` は配備照合/初期100%のflyoutまで確認、実キーボード前の厳密HWND判定で停止。WinUI flyoutは同一PIDのPopupHostがforegroundになるため、main HWNDとの同値だけを求めるharnessが誤って拒否した。failure PNG目視でslider/標準ボタンが収まることを確認。入力先のPID一致を維持し、同一所有popupを許容するようharnessだけを訂正。原本/本番設定には変更なし。

## 追加ユーザー指摘：閲覧中の説明文と自然な日本語（実行前に固定）

2026-10-20添付4枚の指摘を受け、画像/本/動画/音声の表示成功・再生/停止・読書位置保存成功の常設文を畳む。操作は既存tooltip/accessible name、状態は再生ボタン/時刻/ページ数で判断できる。loading/失敗/読書位置保存失敗は表示を保つ。登録フォルダの「和集合」「横断検索」など内部用語を通常の日本語に直す。

2048pxは `PreviewPolicy.ReaderEdge` / `image_animations.VIEWER_MAX_EDGE` の表示用縮小上限。原本変更なし、別途16Mpixel等のsource guardも存在。高解像度/原寸表示は未実装で、拡大時の細部の欠落があるため改善項目へ残す。上限だけ無制限にはしない。

新たな `--quiet-only` flowで、両テーマの700x620のimage/book/audio/videoの通常成功footer不在、loading/失敗表示、読書位置DB保存、folder copyとtoolbar寸法を確認する。生成素材と同じ配備検証を使う。初回+修正最大2回、全PNG目視。既存daily枠は終了し再実行しない。

## ユーザー追加指示：高解像度の通常表示（上の2048px保留方針を更新）

「ビューワーまで軽量化しなくてよい」との指摘により、静止画・本ページは元のストリームをWindows codecで読み、2048pxへの縮小・PNG再エンコードをやめる。サムネイル/AI入力は従来どおり。新original専用routeは既存read-only/source/revision/祖先linkチェックを再利用し、64MiB圧縮source/100Mpixelのviewer専用guardを設ける。CBZ/ZIP/folder本にも接続。画像/本に原寸ボタンを設け、画面のphysical pixelとsource pixelを1:1にする。小さい画像は初期表示で無用に引き伸ばさない。アニメーションの全frame再生は従来のbounded pipelineで別途扱う。

quiet flow初回はまだ実行前。生成6144×4096静止画と4096×3072本ページで元dimensions/原寸100%/fit復帰/表示footer不在を追加検証する。これはLanczos選択やAI超解像実装ではない。専用OCR/モデルDL/GPU推論なし。

## original/quiet初回（01）

Lightは6K/4K元dimensions、原寸100%操作、loading/画像失敗/読書位置保存失敗と再試行、音声/動画/自然なfolder案内までPASS。DarkはLightで保存した2ページ目へ正しく復帰したが、harnessが先頭4Kページを誤って期待して停止。再試行では「最初から開き直す」を明示して比較する。cleanupはdisabled mainへ先にWM_CLOSEを送り子readerが残ったため、追加のprocess確認時には既に終了済み（Aredoko processなし）で、強制終了はしていない。harnessを子→main順へ修正。

実画面のloading倍率にNaNを発見。image.Width未確定時の計算を保護し、読込前は「倍率 —」へ修正する。raw failを保持し、修正再試行1へ。原寸ラベルのみの判定に加え、UIAの実pixel矩形も記録する。clipされる場合はpixel寸法一致を未確認として記録し、100%ラベルだけでHighDPI受入済みとは呼ばない。

## 最終結果と最新のウィンドウ方針

**通常のデスクトップサイズ（幅1200〜1600px程度）の使いやすさと見栄えを優先する。** ユーザーは2026-10-20、Filesの例を示して極小ウィンドウへの過剰最適化を不要と明示した。小窓は閉じる/戻る/保存など主要操作と致命的な欠けを最低限確認し、全情報を700px幅へ詰め込むための追加UIや大量のテスト反復は行わない。既存の有用な折返し/scroll余白は維持し、狭幅対応のために機能削減もしない。通常サイズを主受入、小窓は補助確認とする。

実行済みflowの値は当時の700×620 / 1200×820の記録を保持する。`--narrow`追加後の通常サイズdefaultは構文確認のみで、不要なGUI再実行はしていない。

| 記録 | 自動判定 | 目視 |
|---|---|---|
| `current-detail-20261020-02` | 35 PASS | 6 PNG目視 |
| `current-daily-20261020-03` | 87 PASS | 24 PNG目視 |
| `item-size-20261020-02` | 44 PASS | 14 PNG目視 |
| `original-quiet-20261020-02` | 71 PASS | 16 PNG目視 |

original/quiet再試行1は両テーマPASS、source bytes/mtime不変、正常終了。6K画像/4K本ページの元解像度と原寸100%表示、fit復帰、通常footer不在、故障通知/読書位置保存失敗と再試行を確認。UIAのimage矩形がviewportでclipされるため、実physical pixel数の独立測定は4ケース未確認。96DPI以外のDPI/HC/Narrator、EXIF/ICC/コーデック網羅は未受入。原寸labelだけでpixel精度や高DPI検証を完了扱いにしない。

Python: original-source6、previews22、folder-books16（13 PASS/3 platform SKIP）、reader16、reader-progress7、storage-backup24の計91件（88 PASS/3 SKIP）。Core Release PASS、WinUI x64 self-contained Release 0 errors/既存SDK IL2104 2 warnings。WinUIAnalyzerは未導入につき未実行。旧native harnessの成功caption依存をcontrol readiness/animation名/DB読書位置へ変更、reader故障fixtureをoriginal routeへ追従（構文確認のみ、過去flowの再実行/上限resetなし）。

専用OCR/AIモデル/依存の新取得/GPU推論/私物走査/Actions/main mergeなし。R11のこの範囲は終了し、次はR13。静止画は圧縮source64MiB/decoded100Mpixel、ZIP/祖先link/source freshness等の既存guardは維持。アニメーション全frame再生は旧bounded path（長辺2048px等）のまま。Lanczos選択/AI超解像は未実装で、この対応をそれらの実装とは呼ばない。

## ユーザー許可による開発用Analyzer導入（同日、先行の未導入記述を更新）

[WinUIAnalyzer 0.7.1の設定・検出結果・配布除外](winui-analyzer.md) を参照。Release0 errors / WUI1001移行提案3件 / 既存SDK IL2104 2件。既存依存不変、runtime資産なし、bin/runtime depsへの混入なしを確認。UI/GPUの再実行は不要なため行っていない。新取得は明示許可済み77KBのみ（6MB/s以下）。過去のGUI結果・失敗記録は変更しない。
