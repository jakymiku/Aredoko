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
