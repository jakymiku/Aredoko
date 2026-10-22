# P4 閲覧履歴の個別・全削除（2026-10-23）

既存view_historyだけを削除する。設定→「閲覧履歴を削除」で全件、履歴一覧のアイテム右クリック→「閲覧履歴から削除」で個別。対象を表示して確認し、既定はキャンセル。未保存編集は既存確認を通し、タグ・棚・favorite・reader_progress・元メディアは変更しない。削除後は同じ検索条件を新しい結果sessionで再取得する。

## 遅延記録の防止

Catalog所有のランダムgenerationをGET /api/library/historyで返す（認証必須、count含む）。POST記録は表示イベント発生時に取得済みgenerationをcaptureし、削除でgenerationを更新した後の旧記録は409/history_changedで拒否する。失敗イベントを新generationで再送しない。フロントは次のイベントに向けてstatusだけ更新する。

POST /api/library/history/delete はgeneration・consent:trueと、個別時だけitem_ids（1〜256、重複なし、正の整数）。item_ids:null、bool ID、未承諾、古いgeneration、余分なfieldは拒否。全件はitem_ids省略。SQLite transactionのcommitとresult_generation更新は同じlock内で行い、凍結済み履歴結果も失効させる。単一削除でもgenerationを更新し、削除直前の遅いイベントを拒否する。

DB/schema追加なし。generationはbackendプロセス単位で、再起動時は別generation。旧POST item_idのみは最初の削除まで互換維持、その後は新generation必須（古い無印記録で履歴が復活しないため）。既存のインストール済みAlphaを新backendへ差替えたわけではない。元DB・原本・旧候補は変更していない。

## 確認

新7+既存13＝20 tests PASS/9.841s。個別／全件、metadata/読書位置/source bytes+mtime保全、遅延thread、再起動後の削除保持/旧token拒否、入力不正時の原状維持、凍結history失効、HTTP認証/null/legacy/stale/new記録を確認。Portable x64 build0 errors/既存WUI1001×3、11.98s。最終のdialog UIA IDと翻訳追加はsourceのみ、関連確認を反復しない。rawはignored data/ai-ui/history-deletion-{tests,build}-20261023.log。

GUI個別・全件の実クリック/取消/未保存確認は未実施。全体P4、複数棚・root favorite・画面履歴は未完。次は独立棚schema/旧scalar移行/旧app書込拒否/backup契約を同じ実装単位で進めるか、既存schema内で可能な整理機能を続ける。P3 native continuousは3/3 gateのまま、再実行で埋めない。新モデル/依存/CI/GPU/私物scanなし。
