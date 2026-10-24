# Aredoko — 現行の単一引き継ぎ（2026-10-24）

## 現在地
- `feat/winui3-production-mvp-20261011` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)。base c30bc34へff済み、元の未コミットP5案4ファイルは退避してから継続した。製品コード以外の変更を巻き戻していない。
- 読む順：本書 → [製品ビジョン](product-vision.md) → [統合P0–P7ロードマップ](polish-roadmap-20261022.md)の対象節。旧大量記録は[履歴索引](history-index.md)から必要時のみ。WinUI 3/共通Python SQLite/交換可能AI、専用OCR保留、機能を削らない方針を維持。
- P5 active/pending保全を実装。[形式2・正確な契約・関連テスト・次の1件](backup-active-selection.md)を参照。起動時のAI/WD定義と保存済み次回選択を分離し、旧version1も復元できる。通常profile枠を減らさず、元設定を上書きしない。
- 形式2の基盤`02f087b`、ready後の一時指定解除`f1bb3cb`をPush済み。一時指定解除はCPU実装済み：初回は保存active、ready後に一時指定解除、次回はpending。元の明示overrideは保持。設定busy/atomic失敗時はcommitted証拠で後処理を再試行する。
- 今回の関連確認：一時指定19、新規owned2、破損記録1、settings/switch40、lifecycle/startup26は各PASS（別実行、合算しない）。C#/GUI/GPU/実モデル/通常DBは未変更。途中失敗や旧検証は技術正本へ。現行作業commitはこのファイルのgit logで確認する。

- P6 `2449c62`：モデルpack用の固定profile/layout validatorとdraft catalog生成を追加。生成9 PASS、既存取得/job/runtime builder25 PASS（別実行）。取得→検証→公開→明示models-root選択が生成HTTPで通る。製品catalogは空のままで実取得を有効化していない。正本は[AI取得](ai-acquisition.md)。

- P6 `2973de7`：取得完了rootを配置画面へ引き継ぎ、明示ボタンで既存の背景検査/保存を開始できるようにした。Core985 PASS、Portable0 errors/既知WUI1001×3。GUI未実行/cap変更なし。

- P6固定registry境界をproduction/配布へ接続。source登録fingerprintとmodel定義SHAを検証し、壊れた任意取得設定で通常起動を止めない。実catalog登録は0のまま。生成registry6/所有backend1/staging1はPASS、途中fixture ERRORは正本で区別。

- 新候補02の同梱CPU基本11、復元契約8、日本語/空白再配置11は各PASS。nativeで見つけた末尾の空区切りとidle progress表示をsourceで整理し、Portable build0 errors/既知3 warnings。微修正はnative未再確認。

## 次の実装1件
**P6：bootstrapとPythonのLOCALAPPDATA保存先を一致させる。** 新基本候補GUIで、bootstrapだけOS KnownFolderにログを作り、backendは環境変数の専用先を使う不一致を確認した。原本/通常DBは無変更。sourceを揃えて純粋bootstrap self-test/関連CPUだけ確認する。追加GUIは実行しない。

## 継続する残件と制約
- P0 UI基準/P1B実機/P2連続閲覧/P3性能・完成形UI/P4整理/P5復元/P6配布/P7総合受入はPARTIALまたは未受入。[完成台帳](completion-roadmap.md)と[音声等の内容索引](media-content-plan.md)の未完も保持。全ロードマップ完成ではない。
- [P6 AI取得](ai-acquisition.md)の製品catalogは空。本物の自動取得・実推論・clean Windowsは未受入。既存配置/取得のCore/UIと生成HTTP基盤はある。
- [新基本ZIP候補02](portable-refresh-20261024.md)は344MB/展開658MB、sourcef508b82で今回の形式2/P6を含む。専用DBの通常起動/設定/1回再起動を追加許可1/1で確認（初回終了code欠測の誤FAILはraw保全、再起動時app/bootstrap0）。4 PNG目視済み。旧01/Alpha/shortcut未更新。通常DB/実AI/clean Windowsは未受入。後続UI微修正はZIP未収録。
- GUI cap：新基本ZIP1/1（予定内の初回＋再起動の2起動）、環境2/2、復元3/3、取得1/2。旧P3/shelf/backup等も保持。GUI/GPUは具体範囲を示し事前確認する。私物scan・原本変更・通常DB操作・モデル/依存取得は無断実行しない。
- Actions起動0、main merge/新branch/新PR/force pushなし。3本のworkflowはmanual-only。**シャットダウンしない**。前回同様、利用枠終盤には安全な単位でcommit/push/本書更新を完了する。
- 文書/legacy整理はc30bc34で同期済み。[main/旧コード整理方針](repository-maintenance.md)、[旧依存監査](legacy-dependency-audit-20261024.md)、[文書案内](README.md)を保全。旧Catalog/server等は製品依存のため削除しない。

## 記録のルール
本書だけを短く更新し、AGENTSや互換handoffへ過去全文を追記しない。詳細証拠は対応する技術文書へ。引き継ぎ時に完了commit・利用可能になった機能・実証/未検証・次の1件を明示し、既存Draft PRとremote一致を確認する。
