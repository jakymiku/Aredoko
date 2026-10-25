# 閲覧速度改善：実装と残る実機検証

基点 `0c2a34b1ad4403aea119b641f533f2d126f063d1`。既存開発ブランチ / Draft PR #5への追加。ユーザーが承認したHoneyView相当の表示速度を目指す改善であり、**同等速度の達成・Windowsビルド・実機受入は未確認**。Alpha更新は後工程とし、既存インストール/封印済み02は変更しない。

## 実装

- 次画像/見開きの準備中は直前の画像を保持する。読み込み失敗時には旧画像を消し、対象ページのエラーを表示する。読書位置は新しい見開き全体を表示できた後だけ更新する。
- 本は次の見開きだけを順に先読みする。操作時には先読みをキャンセルして終了を待ち、前景取得を優先する。見開き2枚は並行タスクで準備するが、原本HTTP取得はビュー単位で1件に制限し、デコードの重なりを許す。大量のページを一括取得しない。
- デコード済みLRUは本6枚/96MiB、静止画像3枚/96MiB。静止画像の隣接先読みは今回対象外で、戻った画像の再利用に使う。推定保持量は幅×高さ×4であり、Windows/GPU/一時バッファを含むプロセス全体の上限ではない。先読みは圧縮原本8MiB、デコード推定24MiBを超えたら省略。大きい前景ページは既存制限内で原寸表示し、キャッシュ予算超過なら保持しない。
- キャッシュ表示のたびに認証付き原本APIへ再確認する。`If-None-Match: W/"<64桁lowercase hex>"` に一致すればbodyなし304、一致しなければ原本200。304にも既存のroot登録/除外、revision、ファイルhandleと前後stat、祖先link/reparse、ZIP entry/サイズ/圧縮率、フォルダページ一覧の検査を適用する。304でもZIP目次確認等のコストは残る。キャッシュはアクセス許可の代わりにならない。
- ETagはmetadataに基づく弱い検証子で内容SHAではない。画像/ZIPは既存revisionとpage、フォルダ本は実ページhandleのdev/inode/size/mtime/ctimeも使う。同名・同size/mtimeの置換を検出する。API失敗時は該当キャッシュを除去、開き直し/破棄で全消去し、古い非同期処理の完了を表示へ戻さない。ETagを返さない旧backendではキャッシュを保持しない。既存非conditional APIも維持。
- 読書位置の自動保存は表示後にキューへ入れ、通信完了をページ移動の条件にしない。保存は1件ずつ、待機中は最新の表示済み位置だけにまとめる。各通信の既存5秒期限を保持し、自動リトライしない。失敗は既存警告とログで通知し、明示保存で再試行する。読書画面の閉じるボタン/Esc/タイトルバー、所有画面の通常終了は未完了保存を待つ。新規表示は閉じる準備開始後に保存しない。保存失敗時の終了は成功保存を保証せず、OS強制終了/プロセスkillも対象外。
- 小さいAPNGの一覧thumbnailでも非再生posterを避け、先頭の実再生frameを使う。AI代表画像の選択は変更しない。原本ファイル/解像度/タグ/モデル/DB schemaに変更なし。

## 実行した検証

Linux / Python3.12.14、生成データのみ。新しい依存関係の取得なし。

```sh
PYTHONPATH=tests python -m unittest test_viewer_revalidation test_original_viewer_sources test_previews test_folder_books test_reader test_reader_progress test_animation_playback_sources
```

関連81件 PASS / SKIP0（13.882秒）。APNG最終調整後に再確認14件 PASS、304のContent-Lengthを省略する最終調整後に再確認11件 PASS（重複分は合算しない）。新規11件にはHTTP認証/200/304/不正ETag/登録解除/削除/置換、再展開しないZIP、後段reparse検査、フォルダ本の同metadata置換、APNG poster除外と原本不変を含む。

既存`test_previews.py`の2つのWindows reparse模擬statを`SimpleNamespace`へ修正した。POSIXの`os.stat_result`は追加のWindows属性を保持せず、従来fixtureがLinuxで検査を再現できなかったため。製品のlink検査は弱めていない。

`ViewerPerformanceTests.cs`を既存Core runnerに追加。304検証/再デコード回数/上限/追い出し/旧session抑止/キャンセル/先読み省略/保存順序とまとめ処理/flush/失敗と手動再試行を記述。**この環境にはdotnet/Windowsがなく、新Coreテスト・WinUIビルド・GUI/GPUは未実行。過去のCore732 PASS/Release成功を今回の結果に流用しない。** Python構文確認と`git diff --check`はPASS。

## HTTPだけの参考計測

`python tools/measure_viewer_transport.py` は一時root/DBと生成PNG（512×768、1,182,114bytes）/4ページZIP_STOREDを使い、200と304を交互に12回ずつ測る。token付きloopbackのみ、停止/一時データcleanupと原本SHA/mtime不変も確認。

| 対象 | 毎回200 中央値 / p95 | 再確認304 中央値 / p95 | 12回の画像body量 200 → 304 |
|---|---:|---:|---:|
| 画像 | 2.652 / 4.292ms | 1.270 / 1.512ms | 14,185,368 → 0bytes |
| ZIPページ | 2.259 / 2.966ms | 1.364 / 2.267ms | 14,185,368 → 0bytes |

この計測は最後の304ヘッダー修正前の作業版。ヘッダー修正後のHTTP機能11件は再確認済み。生成小規模warmデータであり、Windowsデコード/描画/実メディア/冷間I/O/HoneyViewを測っていない。体感の改善率や同等性能の根拠にしない。

## 次のWindows検証

まず既存依存だけでCore runnerとWinUI x64 Releaseをビルドする。追加GUI実行は既存3/3上限を維持し、新たな明示許可後に限る。同一PC・同一生成/許可済みメディア・同一表示サイズで、初回/先読み済み次ページ/逆送り/見開き/連続操作をHoneyView等と比較する。入力から実描画まで、中央値/p95、メモリ、原寸、元ファイル不変を確認。保存遅延/失敗と表示の独立、閉じる各経路での保存、登録解除/置換時のキャッシュ拒否も確認する。

開発用`AREDOKO_VIEWER_TIMINGS=1`で`%LOCALAPPDATA%/Aredoko/logs/viewer-load.jsonl`へ段階時間を出す（通常OFF）。匿名load番号、kind、stage、経過msのみ。ファイル名/path/query/token/原本内容を記録せず、8MiB到達後の追記を止める。ログ自身のI/Oの影響を考慮し、対照測定はOFFで行う。`source-body`/`source-revalidated`、`decode-ready`、見開き`preload-drained`/`assigned`を分ける。**assignedはXAMLへのsource設定で、画面への描画完了ではない。** APNGは`first-frame-assigned`を持つ。

R13 DOING / ALPHA未完 / R14 PARTIALを維持。viewer実機確認後もPZ2→PZ3→PZ4→PZ5、ALPHA後に実音声/音楽を進める。未解決U09/U11/U13/U14等をこの改善で完了扱いにしない。Actions/main merge/新依存・モデル取得/私有メディア走査は行わない。以前の一度きりのshutdown指示を再実行しない。

## 2026-10-26 U3b：実フレーム大容量GIF・高解像度APNG/CBZの限定native

- 正しいPortable frontend06（起動照合/一括操作/アンカー修正と、静止画/native GIF切替時の読み上げ名更新）を生成専用DBで検証。`data/ai-ui/startup-review-20261026/large-viewer02/report.json`、所有frontend exit0、decoder session解放、元生成媒体SHA/mtime不変、7PNG目視。
- GIFはpaddingでなく1024×768の実ノイズ80framesを持つ86,558,428bytes（82.55MiB）。先頭thumbnail/stream再生が成功し、64MiBのnative全量取得へ戻していない。APNGは2560×1920・poster付き18frames×2周、native GIF、GIF拡張子のWebPも確認。streamの現行2048px縮小は維持しており、原解像度APNGの受入とは区別する。
- 3072×2048・8ページCBZで1→2→3→2→1を確認。traceのXAML source割当まで、APNG 811ms/native GIF 498ms/WebP 813ms/大GIF 502ms/CBZ初回249ms・後続232–237ms（各1回）。UI Automation/診断log中、OS cache条件非固定であり、画面present/Honeyview比較/中央値/p95ではない。CBZの再取得は304でbitmap復号を再利用していた。
- native private bytesはAPNG再生時224MiB→終了frame468MiB、GIF/WebP後487–511MiB、CBZ後545MiB。inline backendは58–96MiB。単回系列であり、長時間RSS一定・メモリリークなしの証明ではない。FPS、長時間・複雑な透過/disposal・実72MB級の別素材・物理DPI等は残る。
- 01は無限GIFを閉じた直後に非同期close完了を即断するharness誤りでFAIL。独立closeを最大8秒待つよう修正し、02ではlive session解放→CBZまで成功。旧FAILを消さず、未到達だった後段と区別した。
