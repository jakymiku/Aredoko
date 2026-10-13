# 画像ビューア

登録済みの単体画像を選び、右の詳細にある **「画像を大きく表示」** を押します。画面に合わせて中央に表示します。暗いcanvasとcompact操作バーを採用し、[Honeyview公式画面](https://www.bandisoft.com/honeyview/)を操作感の参考にしています。既存WinUI/Fluent部品を使う専用ウィンドウで、Honeyviewのコピーや全機能互換ではありません。

| 操作 | 動作 |
| --- | --- |
| ← / →、前後アイコン | この検索結果ページの前/次の画像へ。端では止まる |
| 縮小 / 拡大アイコン | 画面fitを100%として100–400% |
| 表示リセットアイコン | 画面に合わせる、scrollを先頭へ |
| scroll / wheel | 拡大した表示内を移動。未修飾左右は画像送りを優先 |
| 再試行アイコン | 読み込み失敗時の手動retry |
| Esc / 閉じる | 元の詳細paneと未保存編集へ戻る |

Windowsのタイトルバーは上部に残し、左右・下端にダイアログの余白は設けません。上部情報バー/下部操作バーはcanvasの端に接します。マウス静止2.5秒で隠れ、動かすと再表示。Tab/F10でキーボード操作部を保持、Escは非表示でも使えます。エラー時は操作を表示したままにします。サムネイルdouble-clickは追加コードの実機確認が残るため、現時点では詳細ボタンからの開始を使用してください。

タイトルと「何枚目 / このpageの画像数」を上部に表示します。現在pageの読み込み済み結果から画像だけをsnapshot化し、検索順を保ちます。root/棚/query/AI候補groupなどの絞り込みを解除しません。別pageへは自動で進みません。閲覧中に別画像を表示しても、背景の選択itemや編集中のタグ・棚を保存/破棄/変更しません。壊れた画像はエラー表示し、前後へ進めます。読み込み中の移動と閉じるは先行要求を取り消し、古い画像が新しい表示へ混ざることを防ぎます。

## 対象と上限

- presentな `.png/.jpg/.jpeg/.webp/.gif/.bmp` の単体画像が入口対象。実codec対応はWindows環境に依存します。今回のnative fixtureはPNGとbroken PNGのみで、全形式対応を実証したわけではありません。
- 認証されたloopback APIの既存previewを使用。active root/除外/link/索引stat検査を継承し、最大8MiB・16M画素、受信body40秒、表示PNGは長辺2048pxまで。元解像度/1:1 pixel品質を保証しません。GIF等は静止表示です。
- 1個のload/decode pipelineで最新の指定targetへ切り替え、表示用bitmapは1枚。prefetch・永続viewer cache・ファイル書換えなし。
- SVG/PDF/動画は対象外。本は既存CBZ/ZIP readerを使います。全画面、pageまたぎ、スライドショー、元画像編集・変換・回転・EXIF表示、読書位置保存は未実装。

## Windowsでのローカル検証

```powershell
dotnet run --project tests/Aredoko.Core.Tests/Aredoko.Core.Tests.csproj -c Release --no-restore
python -m unittest discover -s tests -p test_previews.py -v
dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore
python tools/test_image_viewer_ui.py --output data/ai-ui/image-viewer-fresh-run
```

native batchは既存アプリがあると停止します。生成4fileと孤立したcatalog/settingsのみを使い、fresh app layoutを起動して所有PID/HWNDを保持します。物理入力はprocess/window/foreground/focusを検証し、Windowsがforegroundを拒否するとskipを記録。無関係なアプリを操作/終了しません。cleanupはWM_CLOSEを優先し、終了しない場合は所有test processのみのtermination fallbackを記録します。結果・スクリーンショット・要求履歴は指定したignored evidence folderに保存します。

最終検証は[共通ビューアのWindows記録](viewer-reader-validation.md)。専用window画像/読書・Light/Darkを生成素材で確認。Core147/Python preview12・reader16/Release PASS（既存IL2104 2警告）。double-click入口は実装コードあり・実機未検証。High DPI/Contrast/Narrator/全Tab順序・修飾左右/実素材/大量負荷・全形式は未確認。専用WinUI analyzer未実行。動画thumbnail/再生は次の段階。
