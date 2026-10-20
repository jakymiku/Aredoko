# ALPHA-0 起動前チェックの計測と並列化（2026-10-21）

開始HEAD `58165a0`。R13の起動待ちを小区切りで改善した。**R13 DOING / ALPHA-0未完 / R14 PARTIAL**。Native activation/所有launcherの統合・shortcut・署名/信頼/install・clean Windowsはまだ未受入。画像/音声/検索/AIの機能や設定は変更しない。

## 変更

`tools/release_runtime.py` の全ファイル照合とruntime tree検査を、固定4 workerのThreadPoolへ分散した。ハッシュ照合は64件ずつのbatch、ディレクトリ検査は同時に最大4task。全ファイルを毎回SHA256照合し、差分cache・省略・未知ファイルの除外ルールは追加していない。

各nodeで従来の `plain_path` を使い、lexical祖先・symlink/junction/reparse・file type・hardlinkの検査を維持する。ディレクトリは親で確認してからqueueへ入れ、worker開始時に祖先を含め再確認する。元の逐次iteratorを参照用に保持し、生成treeでファイル集合と全パス/引数ごとのguard呼出し数が一致することをテストした。走査のyield順は内部で不定だが、利用側は集合照合/全件検査のみで、検索順位とは無関係。

`tools/measure_release_preflight.py` は同梱/現行の実装を選んで同じ配布物を計測する開発用tool。GUI・モデル推論をせず、NEWな外部JSONのみへ結果を保存。bytecode書込を無効化し、出力先が配布内/既存ファイルなら拒否する。

## 同日比較

同じ5.52GB / 24,196ファイル、同じ同梱CPython3.11.9、同じimport/tool checksで旧/新の各1回を計測。**warmなファイルcacheでの1組の観測**であり、cold/p95や実GUI起動時間の保証ではない。前日の169.781秒を変更前値に使わない。

| 項目 | 旧（配布内の逐次実装） | 新（現行sourceの4 worker実装） |
|---|---:|---:|
| 全preflight wall time | 73.567秒 | 41.558秒 |
| manifest/hash/未知ファイル検査 | 45.649秒 | 21.679秒 |
| Python layout/tree検査 | 16.033秒 | 8.135秒 |
| media layout検査 | 0.003秒 | 0.003秒 |
| SHA256ファイル数 | 24,196 | 24,196 |
| plain_path呼出し | 80,864 | 80,864 |

全体は32.009秒、約43.5%短縮。`plain_path`/`digest`の累計秒数は並行callの重なりを含むため、wall timeへ足し合わせない。計測は既存配布を読み取って現行checkerを適用したもので、**既存5.52GB snapshotのcode/manifestを更新したわけではない**。新配布を作る際に現行checkerが同梱される。source layoutは生成staging/CLI回帰でも検証済み。40秒以上のcheckは依然長く、native起動統合時の待ち表示/工程分離等は別途設計する。整合性検査を無効化して済ませない。

## 初回の拒否と検証harnessの訂正

最初の計測はunknown filesで拒否された。前日にhost Pythonからstaged moduleをimportした検証helperが `-B` を忘れ、`storage_lease`/`launch_release`/`release_runtime` のcpython-314 cacheを3ファイル生成していた。製品launcherは既に`-B`付きで、この3件はhelper側の副作用だった。

未知cacheを無視せず、既知の3ファイルだけをプロジェクト内の新しいquarantineへ移し、bytesのSHA256を保存した。resolved source/destinationが意図したproject subtree内であることを検証し、既存manifestは変更していない。元のメディア/モデル/ユーザーDBは触らない。以降の計測は`-I -B`＋`sys.dont_write_bytecode=True`。空のcache directoryは消さず、未知fileは引き続き拒否する。

## 検証

- Release関連 **34 PASS / SKIP0**（既存28＋新6）。既存の起動失敗/所有終了・配置移動・manifest/CLI・Windows argvも含む。
- runtime準備 **5 PASS**。合計は重複を除き **39 PASS**。
- 新6件：逐次との全guard一致、全hash各1回/同時最大4、同容量改変と未知cache拒否、hardlink拒否、外向きdirectory linkを降りずに拒否、queue後のdirectory差し替え拒否。
- 全5.52GBの旧/新preflightがPASS。importsとFFmpeg実行を含む。モデル推論/GPU/GUI/Windows設定/証明書操作/新取得はしていない。
- 公開した計測toolは計測済みhelperの可搬版。help/配布内JSON出力拒否/構文を確認し、tool追加だけを理由に同じ5.52GBをさらに再走査していない。

証拠（全てignored）：`data/ai-ui/alpha-preflight-baseline-20261021.json`と`.log`、`alpha-preflight-parallel-20261021.json`と`.log`、`release-parallel-regression-20261021.log`、`alpha-inventory-failure-20261021.json`、`alpha-cache-quarantine-20261021-01/report.json`と退避した3cache。元の2026-10-20の記録も保持する。

## 再現（必要なときだけ、新しい結果先）

```powershell
dist/alpha-0-runtime-20261020-01/runtime/python/python.exe -I -B tools/measure_release_preflight.py --release dist/alpha-0-runtime-20261020-01 --implementation staged --output data/ai-ui/new-before.json
dist/alpha-0-runtime-20261020-01/runtime/python/python.exe -I -B tools/measure_release_preflight.py --release dist/alpha-0-runtime-20261020-01 --implementation current --output data/ai-ui/new-after.json
```

既存結果を上書きせず、staged moduleをhostから確認する際も`-B`を必須にする。新たな変更/失敗/未解決点がなければ同じ測定を反復しない。

次は **ALPHA-0のMSIX activationとbackend所有起動の統合 → 正常shortcut/生成媒体・clean Windowsで保存/更新/削除受入 → ALPHA成立後R06–R09実音声/音楽とWinUI改善**。旧GPU/GUI試行上限・P0 2/2・専用OCR保留・全機能を維持。[ALPHA条件](alpha-packaging-milestone.md)、[前回のWindows実物](alpha-windows-runtime-validation.md)、[完成計画](completion-roadmap.md)を参照。
