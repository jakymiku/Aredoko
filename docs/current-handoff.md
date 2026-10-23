# Aredoko — 現行の単一引き継ぎ（2026-10-24）

> **更新ルール**：この1ファイルは毎回「置換/更新」して簡潔に保つ。古い全文の追記は禁止。下記は `33d2715c351e` 時点のGitHub記録を基に作成した整理スナップショットであり、再開時には実HEAD/PR/差分を確認する。文書整理では製品コード・テスト・配布物を変更していない。

## 開始時
- 作業先: `feat/winui3-production-mvp-20261011`; [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)（base `feat/gui-framework-comparison-20261010`）。**新規ブランチ/PR不要**。ローカルの未コミット差分と他AIの更新をまず確認。
- 目的: [ビジョン](product-vision.md)（曖昧な日本語からローカルの本/素材/映像/音声を再発見）、[実装順序](polish-roadmap-20261022.md)（P0–P7）を維持。WindowsはWinUI 3、Python/SQLite backend。AIモデル交換可能、専用OCR保留。
- 最終的な製品実装コミット: `30480f8`（P5の明示AI profile保全）。文書整理直前のPR HEAD: `33d2715c351eaa0301717f376e22e1c700972c96`。新基本ZIPの元ソースは `875f94a`。現状は全体完成ではない。

## すでに実装しているものと境界
- 登録、通常/AI/WD/類似/本文・ページ/動画時刻検索、画像/CBZ/画像フォルダ本・動画閲覧、タグ/お気に入り、棚、編集・保存、バックアップ関連API/UI等の基盤がある。**すべての配布版/実機で受入済みとは限らない**。
- 現行ロードマップ: P0 UI基準整理 PARTIAL、P1A形式判定 CPU_DONE、P1B逐次アニメ source/build、P2連続閲覧 PARTIAL、P3仮想化/サムネイル/UI PARTIAL、P4複数棚 PARTIAL、P5起動中backup/restore PARTIAL、P6配布/AI取得 PARTIAL、P7まとめ受入 **未実施**。[根拠と完了条件](polish-roadmap-20261022.md)。
- P5: 明示起動profileがあって保存済みpreferencesがないケースの保全を実装。取消後に元設定/書込状態を壊さないCPU検証あり。**activeとpending両方の正式metadata、および複数tagger profileの保持が未完**。[P5根拠・未受入](restore-review-20261024.md)。
- P6: existing runtime/model選択とカタログ取得用のUI・API・中断/Range再開/検証公開の基盤あり。**製品用catalogは空**、実モデルの自動取得は利用可能ではない。実モデル/GPU/clean Windowsは未受入。[AI取得の仕様と証拠](ai-acquisition.md)。
- 新基本ZIP候補（ローカルのみ）：`C:/AI/Aredoko/dist/portable-basic-20261024-01/Aredoko-windows-x64.zip`、約344MB/展開約658MB、`875f94a`ソース。生成データで同梱backendの基本CPU確認済み。**GitHub未添付、最新実装を反映した製品版ではなく、GUI・通常DB再起動・clean Windows・実GPU/AIは未受入**。[ZIP詳細](portable-refresh-20261024.md)。
- GUI試行上限：AI環境 **2/2**、復元 **3/3**、AI取得 **1/2** 消費。勝手に再設定/再実行しない。今までの部分成功を未受入の成功に書き換えない。[終了前チェックポイント](development-checkpoint-20261024.md)。
- GitHub Actions 3本は `workflow_dispatch` のみ。CIは実行しない。**PC shutdown禁止**。

## 次の実装1件
**P5: active/pending AI-profileのbackup/restore契約を完成させる。**
1. `production_server.backup_configuration`, `live_backup/storage_backup`, `restore_switch` と [restore-review](restore-review-20261024.md) の該当部分のみ確認。前回実装 `30480f8` を重複しない。
2. 起動overrideで実際に選択されたactive profileと保存済みの次回用pending choiceを、**両方保全**する正式metadataを設計・実装。複数tagger選択・旧bundle互換/設定省略も扱い、ファイル名・ファイル順から推測しない。
3. 生成CPUデータで保存・復元・取消・失敗rollback・元設定非上書きを関連範囲だけ検証してcommit/push。大きなスキーマ変更の情報損失リスクが解けない時のみ設計レビュー。GUI試行回数は増やさない。

## P5後に優先すること
[P0–P7ロードマップ](polish-roadmap-20261022.md)の残機能を**縦切りで実装優先**。P6の安全な実体catalog登録/配布導線、既存GUIの受入と仕上げ、P7の一括受入。旧ロジック/資料の全面再調査や毎回の回帰は避ける。UIは主要機能が使える段階から小単位で磨き、全機能完成まで開始を延期しない。音声/音楽実内容索引は長期目標から消さない。


## 関連ロードマップ（未完項目を保全）
- [統合ロードマップ P0–P7](polish-roadmap-20261022.md)が現在の実装順序と完了条件の正本。
- [完成台帳 R01–R14・M1/M2](completion-roadmap.md)も保全。音声・音楽の実内容解析、配布・起動・更新、総合受入の未完タスクを削除しない。P7はM1の日常β判定であり、製品全体の完成ではない。
- [メディア内容索引](media-content-plan.md)、[WinUIデザイン](design-vision-winui.md)、[軽量配布](lightweight-distribution.md)、[開発優先順位](development-priorities.md)は関連工程で必要部分だけ読む。旧文書の過去の「次」は現在の優先順位より上に置かない。
- 上記はすべて参照リンクで、各ロードマップ原文に変更はない。毎回すべてを再読せず、担当する作業の部分を読む。

## 強い制約と報告
- 原本・ユーザーDB/保存設定、登録ルート/検索scope/認証/モデル選択/backup schemaの情報損失を避ける。明示許可のないファイル変更、私物スキャン、モデル/外部依存取得は禁止。
- CIなし、main mergeなし、別PRなし。実機/実GPU/自動取得は根拠なければ未検証。過去の試行上限を再利用しない。
- 作業終了時はこのファイルを**簡潔に上書き**し、次の1件、コミット、操作可能になった新機能、必要な確認、残るblockerを記載。詳細証拠は専用文書へ。古い大量handoff/AGENTSへ報告を追記しない。[履歴索引](history-index.md)を参照。
