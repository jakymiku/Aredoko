# 2026-10-24 終了前チェックポイント

## 2026-10-24 final P5 continuation checkpoint

Implementation **30480f8**: [explicit AI profile with absent saved preferences](restore-review-20261024.md). Live11 PASS; final restore-switch/rollback + jobs/HTTP10 PASS separately. Source preferences remain absent/unchanged; saved pending choices keep exact bytes. Full dual active/pending metadata and multi-tagger selection remain TODO. ZIP remains source875f94a; this backend follow-up is source-only. Native caps unchanged, no GUI/GPU/new model/normal DB. Goal incomplete/active; near quota save/push/handoff, **no shutdown**.

Next1: explicit backup active-selection metadata preserving BOTH existing pending preferences and startup override, with older-bundle compatibility; do not solve it by replacing saved choice or guessing from profile filenames. Continue from30480f8 after fetch/status/log.

Previous stopping docs9ec50b1 and implementation606b403 remain below as history. Latest product source is30480f8; no rebuilt ZIP for this follow-up.

最新の実装・検証コミットは **606b403f510c5c5075fc7ee24a815dce5ad40e7c**。本引き継ぎの後続文書commitはこのファイルのgit logを参照する。ブランチ `feat/winui3-production-mvp-20261011`、既存Draft PR #5、open/unmergedを保持。直前fetchでahead/behind0/0、作業tree clean、PR head一致を確認し本文も最新化。Actionsは全workflowが手動起動のみで、実行・main merge・新branch/PRなし。

## 今回の実装単位

| commit | 内容 |
| --- | --- |
| 1f9ce12 | 配置画面nativeで判明したtrimmed picker dependency欠落を修正。特定projectionだけroot、実deps非GUI比較で旧失敗/新成功 |
| 7705e53 | 取得catalog/job Coreとnative設定接続。明示同意、既定無制限/任意cap、受信/検証進捗、中止/再開、公開root |
| 43ff749 | 生成loopbackによるnative Start→中止→Range再開→公開の証拠 |
| bce2056 | 取得元host表示と、進捗ごとの全catalog再集計を撤去。Coreの以前の973表記を972へ訂正 |
| b47ec66 | 取得済みversionを全SHA/構成検証して再利用。ネット取得/置換なし、取消順序維持。setup利用可否も統一 |
| 875f94a | 明示sealed runtimeから実inventoryに基づく固定catalogを準備する開発tool。ネット/実行/登録なし |
| 606b403 | 最新基本版ZIPの準備・実同梱CPUと日本語/空白再配置の確認、再利用可能probe |

前段7883a01の配置済みruntime/models Core/UIも維持。型名・世代・取消・原本/通常DBの安全境界を弱めていない。

## 検証・試行上限

- 最終Core **974 PASS行**。Portable0errors、既知WUI1001×3/SDK IL2104×2。新host fixtureの初回CS1513と修正後logを別保存し成功へ書き換えない。
- 取得/jobHTTP20 PASS/13.894s。最後のcapability変更後HTTP1 PASS/1.310sは再実行なので21種類へ合算しない。catalog builder5 PASS/0.888s。
- 配置画面 **2/2消費済み**。run01テスト側のUIA peerなしGrid待ちで停止、後から所有pathを確認して通常close。run02 native再表示/中止は成功、標準に戻すでpicker依存FileNotFoundを発見・修正。修正後GUI再試行はしていない。4枚のPNGを全目視。原本/設定を失った結果ではない。
- 取得画面 **1/2消費**。run01の12 checks PASS、4PNG全目視、所有PID37176 exit0、残留なし。生成1.5MBだけ、実Range bytes=65536-を確認。再表示・native同意/Start/Cancel/Resume/公開rootまで。以後のhost表示/reuse追加はCPU確認のみ。合格flowを残り枠消費のために繰り返さない。
- 復元GUI **3/3消費済み**。先行flowの制約は[復元の正本](restore-review-20261024.md)。旧P3/shelf/backup等の上限を再設定しない。
- 全nativeは専用DB/生成ファイルだけ。GPU・実モデル・新しい外部artifact取得0。検査用Pythonは実行していない。通常DB/installed Alpha/shortcut/private folders/元メディア変更0。

## 試せる新候補

[実物の版・ZIPハッシュ・限界](portable-refresh-20261024.md)を参照。

`C:/AI/Aredoko/dist/portable-basic-20261024-01/Aredoko-windows-x64.zip`

ソース875f94a、ZIP343,811,217 bytes、展開737files/657,566,956bytes。新しく解凍してAredoko.exeが入口。旧Alphaを更新した成果物ではない。ZIPはGitへ登録/外部uploadしていない。

同梱Pythonで11項目PASS、別の日本語/空白配置でも11項目PASS。両方exit0/DB integrity ok、原本SHA/mtime不変。新ZIPのGUI/通常DB restart/clean Windows/GPU/実AIは未受入。旧03候補の未登録__pycache__失敗は保持し、再利用した176runtimeファイルだけexact inventory/hash照合、旧アプリはコピーも変更もしていない。

## 残件と次の1件

**次の独立実装はP5の明示active-profile backup/restore契約**。production_server.backup_configuration、live_backup/storage_backup、restore_switchとrestore-reviewの残件を読み、起動overrideで選ばれたAI profile/複数tagger profileの選択が、保存済みsettingsやファイル順で別物へ変わらないようにする。旧bundleとの互換、設定省略、rollback、取消後の保存をCPU生成データで確認する。大きな形式変更が既存情報を保全できない場合だけ設計レビューへ切り出す。GUI上限は増やさない。

P6の取得Core/UI/生成転送は進んだが、**製品registryは空**。実runtime packの配布元・全依存NOTICE・固定公開先が揃うまでは本物の自動取得を有効にしない。builderは準備補助で、配布権/公開元の認証/実推論の証明ではない。実catalog登録・既存配置のnative picker/標準復帰・ZIP/bootstrap/clean Windows・P3性能/高DPI等は未完。既存統合ロードマップ/製品vision/全機能/専用OCR保留を維持する。

明日の初手はfetch/status/logで他AI更新を確認し、AGENTS→本checkpoint→該当正本だけを読む。完了済み調査・Core全回帰・native合格flowを無用に再実行しない。実装→必要な関連確認→次の小区分で進める。新GUI/GPUは具体候補/範囲を示してユーザーに確認する。

利用枠は終了前確認時87%使用。残りをcommit/push/引き継ぎ確認へ確保し、新しい大きな作業には進まない。**PCシャットダウンなし。Goal/ロードマップは未完・activeであり、本チェックポイントは全体の完了宣言ではない。**
