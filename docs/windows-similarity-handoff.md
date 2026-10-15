# 帰宅後のWindowsテストとブラッシュアップ

作業先は `feat/winui3-production-mvp-20261011`、既存Draft PR #5。最新のAGENTS/vision/priorities/両handoffを読み、未commit変更とremote差分を確認してから同期する。mainへのmerge・force push・新PR・CI dispatchはしない。

## 最初の一括確認

既存のPython、.NET 10 SDK、WinApp CLI、WinUI復元済み依存を使用する。Aredoko本体/起動スクリプトを通常終了してから、repo直下で実行する：

```powershell
.\Check-Similarity.cmd
```

同等のコマンドは `python tools/check_similarity_local.py --native`。Python全テスト→Core Releaseテスト→WinUI x64 SelfContained Release→生成素材専用のnative Light/Darkバッチを**一度ずつ**実行する。失敗した段階で停止し、`data/ai-ui/similarity-check-<日時>-<ID>/result.json`と段階別logを残す。モデル・依存の取得、NuGet restore、CI起動、私物フォルダのscanを自動では行わない。Core/WinUIで既存assetsが不足する場合は、エラーを確認し、既存の導入/復元状況を調べる。今回のLinux環境では.NET/Windows実行は未検証。

同一コードのPython合格が既に確認できており、Windows側だけ確認する場合は `python tools/check_similarity_local.py --native --skip-python`。省略はresult.jsonに明記される。理由のない全件反復はしない。

nativeバッチは既存Aredokoプロセスと8769番ポートの使用を検出したら中止し、既存プロセス/DBに接続しない。自分で起動したPID/handle/HWNDだけを操作・終了する。所有プロセスの強制終了が必要だった場合はruntime合格にしない。

## nativeバッチが確認する範囲

- 76件の生成カタログ、同profileの固定3次元vector。実AIモデルを使わず、encoder呼出0で動く。72件の類似結果の2ページ表示、scope外root・自己除外、元の2ページ目とfocusへの復帰。
- list/grid/詳細プレビューの右クリック。dirty取消でdraft不変/要求0、破棄承認→遅延要求→取得取消→元画面に復帰し、二度目の破棄確認や無効化したままの画面を残さない。
- お気に入り・自己除外による0件、未索引fallback、409/503と復帰、Light/Dark・700×620狭幅の証拠PNG。
- 元PNG/CBZ等のbytes/mtime、専用設定が不変、モデル呼出0。

native `result.json`の`runtime_pass`は機械確認のみ。`visual_review`はpendingのままなので**全PNGを目視してから**所見をhandoffへ記録する。今回の環境ではnativeスクリプト自体を実機実行していない。CLI/UIA selectorやpopup動作が実機で異なる可能性がある。失敗したらlog/PNG/treeから当該箇所を修正し、最大2修正cycleで未解決なら原因を残して別の確認へ進む。

Shift+F10、High DPI/Contrast/Narrator、Tab順、実モデル/GPUの精度・負荷、既存画像/CBZ/動画viewerの全回帰はこのbatchの合格に含めない。特に既存viewerのdouble-click/読書位置/Range/seekを必要な範囲で別途確認する。

## 個別実行・手動ブラッシュアップ用

```powershell
python tools/test_similarity_ui.py --output data/ai-ui/similarity-native-01
python tools/test_similarity_ui.py --output data/ai-ui/similarity-unindexed-01 --scenario unindexed
python tools/test_similarity_ui.py --output data/ai-ui/similarity-text-only-01 --scenario text-only
```

各outputは未使用の名前にする。失敗結果/PNGを上書きしない。全scenarioの連続実行は必要な時だけ。既存Release buildを使い、buildを毎回繰り返さない。

手動用のAPIだけを立ち上げる場合：

```powershell
python tools/similarity_sandbox.py --output data/ai-ui/similarity-manual-01
```

別ターミナルで既存のWinApp起動手順に従い、**バックエンドを二重起動せず**Releaseアプリだけを起動する。実際の保存場所・root/作品IDは生成された `manifest.json` を読む。APIは127.0.0.1:8769に固定。Ctrl+Cで専用APIを終了する。通常の `start-winui.ps1` は別バックエンドを起動するため、このsandboxと同時には使わない。

モデルなしのfixture生成だけなら `python tools/similarity_sandbox.py --output data/ai-ui/similarity-fixture-01 --prepare-only`。生成PNG/CBZの見た目と3次元vectorはcontract用であり、検索モデルの精度を示すものではない。

## Codex / OpenCodeに渡す指示

> Aredokoの製品ブランチ feat/winui3-production-mvp-20261011 とDraft PR #5の続きをお願いします。最初にbranch/HEAD/status/未commit/remote/PRを確認し、AGENTS.mdから必読文書・最新handoffを読んでください。docs/windows-similarity-handoff.mdに従い、既存環境だけでCheck-Similarity.cmdを一度実行し、Core/Windows Release/nativeを確認してください。失敗箇所をlogとPNG/treeで特定して修正し、生成素材だけで必要な再検証まで進めてください。全PNGを目視し、未保存draft・取消・元ページ/focus・scope・未索引fallbackを確認してください。実機未確認を合格扱いにせず、既存文字検索/根拠/画像/CBZ/動画/Range/seekを維持してください。CI起動、モデル/依存の無断取得、私物scan、mainへのmerge、force pushは禁止です。同じ評価を無目的に繰り返さず、最大2修正cycleで区切り、実施結果・未確認・次の異なる3手を両handoffと既存PRへ反映してください。

検索品質P0の新固定baseline/実モデル比較は別の未完了項目。類似検索の回帰解消とWindows確認を区切った後、結果観測前に入力を凍結して一度実測する。改善0件または累積2件で区切り、P2の由来付きタグ候補/承認/OCRへ進む。
