# CBZ / ZIP 読書画面

> 2026-10-13後続：Linux sandboxへ.NET SDK 10.0.401を導入し、reader契約を含むC# Core **81 checks PASS**（readerは今回初めて実ビルド・実行）。`tools/compile_check_winui.py`でWindows App SDK 2.5.1参照の**C#のみのコンパイルPASS**（`ArchiveReaderView.cs`/`MainPage.xaml.cs`含む、0 error）。XAMLコンパイル・Windows Release・native操作は**引き続き未検証**。以下の「未ビルド」は当時の記録。

2026-10-13。backend APIはPythonで検証済み。**WinUI接続コードとC#契約テストは作成済みだが、このLinux環境では.NET/Windowsがなく未ビルド・未実行。** 動作する製品版との宣言ではない。

## 操作と境界

- presentなCBZ/ZIPを選択し、詳細の「本を開く」から開始。未保存のタグ等はそのまま保持する。
- 0始まりのAPI pageを1始まりで表示。前/次、再試行、最初から開き直す、拡大scroll、閉じる。目次・ページ直接指定・見開き・読書位置保存・フォルダ本・Komgaはまだない。
- ページ変更開始時に旧画像を消す。404/codec失敗なら現在番号とエラーを残し、前後へ移動可能。409/403ならmanifestを無効化し古い番号では続行しない。409は閉じて再scan後に明示再openする。503は手動再試行。自動retryなし。
- 1ページだけ保持。ページ要求は同時1本、終了でcancel、遅れて完了した応答/decoder結果を捨てる。thumbnailの永続cacheや展開ファイルは作らない。
- JSON最大4KiB/画像8MiB/入力16M画素、読書表示用PNGは長辺2048px（旧thumbnailは256px）。原寸・全解像度表示ではない。decoderのメモリ/実画像品質はWindows検証待ち。
- C#通信は既存session/tokenを使用。MIME・正のContent-Length・実受信長を検査し、bodyを含む40秒deadlineで終了。manifestのID/件数/revision/pageを検証。リフレクションserializerは使わない。

## 今回実行した検証

後続のZIP境界修正後は**全Python178件PASS /16.628秒/skip0**。長い数字名・非十進数字記号・Unicode decimalを3回帰で確認。ZIP64 locatorのlegacy値上書きと偽装件数を明示拒否し、ZipInfo生成前の固定header走査/実10000件上限/可変長境界/entry ZIP64・multidisk拒否/prefix・comment互換を7回帰で確認。C#・native検証待ちは解消していない。以下168件は直前checkpointの履歴。

- Python全168件 PASS /17.242秒/skip0。既存155＋reader13。生成fixtureとfake encoder、実production HTTPを使うCPUテスト。実GPUやWindows試験ではない。
- XAML XML構文とdiff空白チェックPASS。C#構文/type/WinUI runtimeの検証ではない。
- C#の追加ArchiveReaderTestsはmanifest/対象拡張子/固定route/認証header/ページ範囲/エラー分類/受信長/MIME/cancelを検査するソース。未実行なので合格数を記さない。
- snapshot取得時の余分な末尾改行による最初のfixture hash guard失敗を、upstream blob一致の復元で解消。期待hashは変更せず再実行。CI起動0回。

## Windowsでの次のgate

既存依存を使い、通常の作業branchをpullしてから:

```powershell
dotnet run --project tests/Aredoko.Core.Tests -c Release
dotnet build src/Aredoko.WinUI -c Release -p:Platform=x64 -p:SelfContained=true
```

既存起動スクリプトと**専用DB/settings・生成CBZ/ZIPのみ**で、次の操作を確認する。私物のscanや個人設定の変更はしない。GUIを起動しただけで合格にしない。

1. page2/page10を持つCBZ/ZIPで自然順、最初/最後の前後disabled、ページ番号/画像一致を確認。Light/Dark、幅1200/700、高さ620を撮影してfooterとエラーが読めるか確認。
2. タグを未保存にしてreaderを開閉し、値とdirty状態を保持。Ctrl+S/検索/別dialogがreaderの背後で実行されないことを確認。閉じる/Esc/Tabでフォーカスが戻るか確認。
3. 読めない2ページ目で旧画像が残らず、3ページ目へ進めることを確認。元ファイルをfixture内で変更し409、再scan/reopenで新manifestになることを確認。
4. 応答を遅延したfixtureで閉じる→別作品を開き、古い画像が現れないことを確認。キャンセル/タイムアウト/503/認証切れを区別する。
5. fixture元bytes/mtime/hash・注釈・settingsを比較し、所有プロセスを終了。Windowsでのdecode/メモリ/keyboard/実スクリーンショット結果を追記。

AutomationIds: BtnOpenBook / ArchiveReaderDialog / ReaderViewport / ReaderImage / ReaderPageNumber / ReaderStatus / ReaderPrevious / ReaderNext / ReaderRetry / ReaderReopen。

CIは必要時だけ。上記をローカルで通せる場合は不要。新workflowや反復dispatchで代替しない。
