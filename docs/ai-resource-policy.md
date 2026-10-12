# 実装状況（2026-10-12：Python/API/WinUI実装、CPU検証済み）

**手動解放・選択式自動idle解放・索引処理の待機設定を実装しました。** 以下の古い「未実装」記述は元の設計の履歴として残します。GPU解放の実機測定および新しいWinUIダイアログの実画面操作は未検証です。

- 手動解放: WinUI「AI索引」→「AIをメモリから解放」、またはtoken/Origin認証済み`POST /api/library/ai/release`、本文`{}`。索引や検索が進行中は即時409 Busy（強制中断しない）。返値`released`は所有workerの停止有無。解放後はstatusの`resident=false`、`worker_state=unloaded`、`device=""`、`telemetry={}`となり、次の検索で同一profileを自動再ロードする。モデル重み・catalog・vectors・index identityを削除しない。
- 選択式自動解放: **初期値0（無効）**。候補は無効/60/300/900秒（APIの整数許容範囲0..3600秒）。`time.monotonic()`で推論/索引完了後のアイドル時間を測り、共有inference lockを通す。処理中のworkerには触れず、アプリ終了時にtimerの停止と終了フラグを保証。処理中の再起動や高頻度timerを導入しない。
- 索引の待機: **初期値0（無効）**。候補は0/50/200/500/1000ms（APIは0..2000ms）。1作品の処理後、次の作品まで`cancel.wait(ms/1000)`で中断可能な待機を入れる。interactive検索には入れない。これはGPU使用率やゲームFPSの上限を保証しない。
- 設定保存: `%LOCALAPPDATA%/Aredoko/settings.json`に`resource: {"idle_release_seconds":0,"index_pause_ms":0}`を追加。既存の`{"version":1,"profile":"default"}`のような**旧profile-only形式は引き続き読み書きできる**。GUIの変更は保存直後に反映され、profile/embedding index identityは変更しない。テストは一時settingsと生成ソースのみを使用。
- API: token認証済み`GET /api/library/ai/resource`、token+Origin認証済み`POST /api/library/ai/resource`で両設定を整数・境界チェックして保存。API外部公開をしない。`GET /api/library/ai/status`にも`resident`と`resource_policy`を追加。
- **検証済みの範囲**: `python -m unittest discover -s tests -p test_ai_release.py -v`によるCPU専用偽encoder/workerテストがGitHub ActionsでPASS。解放→検索/worker再生成、busy中は即拒否、closeとの競合、VectorStoreを読み直した一致、token/Origin拒否、idle timer・索引待機キャンセル・終了、legacy設定互換を検査。PythonフルスイートとWinUI x64 ReleaseビルドはActionsで別途確認する。
- **未検証**: 実GPU workerのVRAM/物理メモリ減少量、Windows GUIの新ボタン・Light/Dark・狭幅、ゲームとの同時動作。旧GPU 10,000件126項目とHTTP 28項目は**今回再実行していない**。

# AI動作設定の次段階仕様（未実装）

2026-10-12。これは次回実装用の方針であり、現行アプリに設定や自動解放があるという意味ではない。現状は既存の所有GPU workerを必要時に起動し、アプリ終了まで保持する。逐次推論・画像byte/pixel制限・中断再開・10,000件上限を保持する。

## 最初に実装する範囲

まず「AIをメモリから解放」を追加する。実行中の検索/索引と同じinference guardで競合を拒否し、アイドル中の所有workerだけ停止する。モデルの重み・保存済みvector・catalog・profile identityは変更しない。次の検索で既存modelを再ロードする。実行中の索引を無断で止める操作にしない。

自動解放は次に追加し、初期は選択式にする。検索や文字/画像推論の完了時刻から経過時間を測り、処理中は解放しない。timerとencode/closeのlock順序を一つに固定し、アプリ終了後のtimer再起動や新worker起動を防ぐ。停止後はdevice/telemetryを現在の状態へ更新し、過去のCUDA表示を常駐中と誤解させない。

さらに索引中の待ち時間を設定できるようにする。GPU使用率の厳密な上限やゲームのFPSを保証する設定ではない。item間のキャンセル可能な待機で負荷を間引き、検索にはこの待機を入れない。resource policyはvector spaceと別扱いで、設定変更により全件再索引を要求しない。

GUIは既存の小画面AI dialogで固定status/start/cancelが隠れないようにする。解放状態を「AI待機中／次の検索で準備」と示し、未導入/失敗と区別する。WinUI design/review/native UI検証を伴う段階で実装する。

## 合格条件

- 生成素材だけで実CUDA query→明示解放→所有launcher/実workerの終了→次のqueryで再ロードを確認。source/vector hashは不変。
- build/query中の解放は速やかにbusyを返し、進行中結果・保存済みcheckpointを壊さない。
- 自動解放の短い試験間隔で、encode中/直後/closeとの競合とtimer終了を確認。実行時間計測用の単調時計を使う。
- 新しいsettingsは保存/不正値/古いprofile-only設定と互換。個人設定を試験で変更しない。
- GUIで常駐/解放/準備中/失敗を区別し、Light/Darkと狭幅を実確認。実際の解放量をPyTorch allocatedだけで総VRAMと主張しない。

## この後の範囲

上限を超えた対象の選択（root/種類/棚など）とcoverageの説明を整える。無制限に1TBを処理する機能を自動で有効にしない。一般的な検索品質、複雑な実表紙、ZIPのサイズ/I/O、多数の個人フォルダは明示指定の小サンプルから別途評価する。Layaは現在の精度gateを満たすまで実験APIのままとする。
