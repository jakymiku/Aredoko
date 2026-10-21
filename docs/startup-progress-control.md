# 起動前チェックの実進捗と取消（PZ2の処理基盤）

> **後続実装**：[継承pipe protocol](startup-pipe-protocol.md)で、上記callbackを一回限りの検査workerへ接続した。hello/cancel/所有EOF/有界queueをCPU確認、83 PASS/Windows5 SKIP。native起動画面/所有bootstrap/portable launch/app-readyは未実装。以下は処理基盤実装時の記録を保持する。

基点 `137e147c785a2f1c4e0ef77e146465b63c6c4be4`。2026-10-21の開発継続依頼で、Windows実機なしに検証できる処理を実装した。**起動画面・ルートAredoko.exe・portable frontend起動・GUI-ready通知は未実装**。PZ2は処理基盤のみPARTIAL、R13/ALPHAは未完のまま。通常利用の起動UIが完成したとは案内しない。

## 実装した範囲

`tools/startup_progress.py`の`StartupProgress`を、配布検査`verify_release`、Python/media layout検査とruntime probeを行う`preflight`、既存`launch`へオプションで渡せる。新しい依存関係はない。sink未指定の既定動作では通知ファイル/pipe/画面を作らず、既存`--verify-only`のJSON出力も維持する。

```python
from startup_progress import StartupProgress, StartupCancelled
from launch_release import preflight

# 開発担当向け。sinkは短時間で最新snapshotを受け取るだけにする。
control = StartupProgress(sink=accept_snapshot)
manifest = preflight(release_root, imports=False, progress=control)
# 別のUIスレッドからcontrol.cancel()。例外StartupCancelledで中止を区別。
```

一つの検査coordinatorが段階/件数を更新し、別threadからの取消とsnapshot取得を許す。sinkはGUI描画や遅いpipe書込みを同期実行せず、最新snapshotを渡す用途にする。native UIとのIPC/EOF/所有process handshakeは次の実装であり、今回のcallback APIだけで代用したことにしない。

| stage | 実際に行う処理 | 進捗の意味 |
| --- | --- | --- |
| manifest | manifestの制限/相対path/重複/digest metadata検査 | 総数未確定、indeterminate |
| file_hashes | 全列挙fileを4worker・最大64futureでSHA256照合 | 実際に照合完了を回収した件数と、そのファイルのbytes。総量は検証済みentriesから算出 |
| inventory | 全directoryの祖先link/type/hardlink確認、余分/欠落、必須file、checksum一覧/totals照合 | 総数不明、indeterminate。hashが全件終了してもこの段階は残る |
| runtime_layout | 同梱Python/Pillow/AI依存配置、media配置と全祖先検査 | indeterminate |
| python_imports | 同梱Pythonを`-B`で起動しimport probeの結果を確認 | indeterminate |
| media_probe | 同梱ffmpeg/ffprobeの`-version`結果を確認 | indeterminate |

通知は`aredoko-startup-progress-v1`、段階sequence、stage、state、completed_files/total_files、completed_bytes/total_bytesのみ。ファイル名/path、token、例外文、原本内容を通知へ入れない。`state`はrunning/complete/failed/cancelled。各completeはその段階だけの完了で、アプリ起動成功ではない。全体%/ETA/readyを出さない。

通知は通常最大10回/秒、段階開始/完了/失敗/取消は必ず通知する。件数は通知を間引いてもsnapshotへ蓄積する。sinkへ渡すdictはcopyで、書き換えられても内部状態を変えない。総数未達・超過・負数は成功にせず失敗にする。sinkが壊れた場合は検査を中止し、二次的な通知失敗で最初のエラーを隠さない。

## 取消と保全

- 取消を検査開始前、manifest各entry、hash前と1MiB読込境界、directory巡回/worker開始に確認。残りのqueued hashは開始前に中止し、既存workerの終了を待ってから戻る。次の検査batch/段階/GUIを開始しない。
- runtime probeは保持している今回の`Popen`だけを約100msごとに確認する。取消/timeout/異常時にはそのchildをreapし、pipeを閉じる。別instance/PID/名前検索による停止はしない。既存backendのinstance ID/port/lease/owner EOFやMSIX正式activationの契約は変更しない。
- 取消は協調的で、OS内のファイルopen/read/列挙やprocess終了待ちを即時割込みする保証ではない。probe停止には既存の終了待ち上限が適用される。計測なしに「常に100msでキャンセル」とは言わない。
- SHA/祖先link/type/hardlink確認を省略・cacheしない。通知あり/なしの実hash呼出数と全`plain_path`呼出のmultisetが同一であることを生成fixtureで検証した。対象payloadは読取のみ。
- 今回の制御対象はpreflightまで。backend/frontend待機中の取消、DB書込み開始後の終了、既存ユーザー操作中のGUI停止へこの仕組みを無断拡張しない。`launch`はpreflight取消を別例外として維持し、backend/frontendを起動しない。既存のローカルlauncherログ処理は残る。

`package_release.py`は新moduleを明示して新しい配布へコピーし、manifestでSHAを保護する。旧封印済み02へ新moduleやコードを追加しない。既存manifest必須file集合を増やして旧版のオフライン検査を不必要に拒否する変更は行っていない。

## 実行した検証

Linux/Python3.12.14、生成payload/一時DB/明示した検査用childのみ。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests python -B -m unittest test_startup_progress test_release_parallel test_release_staging test_release_lifecycle test_release_activation test_release_reporting -v
```

**71件実行：66 PASS、Windows専用5 SKIP、失敗0（21.004秒）**。新規進捗/取消16件を含む。実件数/bytes・段階順・通知間引き・途中取消・hash読込停止・別child保全・timeout/reap/pipe解放・失敗状態・通知内容制限・snapshotコピー・guard同等性を確認。既存の生成MSIX照合/正式activation境界、host Pythonによる再配置backend HTTP/DB保存/終了・lease解放、実梱包後CLIの無余分出力/無payload書込みも通過した。

Windows import/media probeの段階分岐はstub検証、実processの取消/timeoutはhost Python childで確認したもの。**同梱Windows PythonやFFmpegのABI・native GUI・起動画面・clean Windowsの受入結果ではない。** 初回の開発テスト20件にはimportした既存6件の重複が含まれたため、test moduleのimportを修正し、最終71件では重複させていない。過去のテスト数へ重複加算しない。

## 次に進めること

PZ2の残りは、重いPython/WinUI初期化より前に現れるnative起動UIとroot bootstrap、信頼できる進捗IPC/取消/所有EOF、backendと初期画面のready handshake。process生成やpreflight完了だけで起動画面を閉じない。最小UIを先に出す信頼境界、絶対path/作成時刻/保持handle/子processの所有確認を保つ。CPUで異常/切断/取消を先に確認し、既存依存だけでWindows build後、新たな明示許可を得た範囲でnative検証する。旧GUI3/3上限は維持。

その後PZ3全runtime/既存model rootと導入導線→PZ4新規ZIP/再配置→PZ5 clean Windows。前回のviewer実機比較、新Core/WinUI確認も未完として維持する。Actions0、main mergeなし、新downloadなし、私物走査なし、installed Alpha/封印済み02無変更。一回限りの旧shutdown指示は再実行しない。
