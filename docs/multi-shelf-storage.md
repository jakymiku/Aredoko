# P4 複数棚の保存・移行基盤（2026-10-23）

**保存基盤のみ。製品での自動移行・新API・複数棚UIは未接続。** app/shelves.pyのShelfStoreは明示的に呼ぶtransaction module。通常ProductionCatalog起動/普段DBを変更していない。現行ProductionCatalog/Catalogはversion0まで対応し、移行済みversion1を旧アプリとして拒否する。新しい起動・検索・scan・update adaptersを揃えてから製品側の許容版を上げること。

## 実装

独立shelves（AUTOINCREMENT安定ID）、item_shelves、root_shelvesを一つのBEGIN IMMEDIATEで作成し、既存items.shelf/library_roots.default_shelfから完全一致の棚名・所属を移す。古い空白/大文字小文字も勝手に統合しない。成功時だけPRAGMA user_version=1。途中失敗はDDL/所属/user_versionごとrollback。既に移行済みなら再移行しない。将来版や半端なschemaは拒否。

空棚作成、改名、削除、item/rootへの複数所属置換（1〜256対象・最大64棚）、片方だけの解除、旧scalar置換を実装。複数所属を失わせる旧scalar更新は全batchを拒否。未知ID・重複・bool/不正ID・名前衝突は原状維持。互換scalarは最小棚IDの名前を表示し、削除時は残る所属へ再計算。棚削除はjunctionだけを消し、item・タグ・favorite・原本は削除しない。

backup validator/storage_schema_v1を同じ単位で更新。catalog version0（旧tables）とversion1（新3tablesすべて必須）を受理、混在/未知table/columns/壊れたFKは拒否。vector DBは引き続きversion0。v1 catalogの複数所属・空棚を含む実際のbackup→新規restore roundtripを確認。旧schemaの復旧テストを維持。

## 確認と失敗記録

新7+既存storage_backup28＝35 tests、34 PASS/1 cleanup ERROR（18.695s）。失敗は新testがsqlite3.connectのwithをcloseと誤解し、Windowsで復元先DBを保持したこと。contextlib.closingに修正し**失敗1件だけ**再実行:1 PASS/0.217s。元の失敗ログを保持し、合算して36成功と数えない。raw ignored data/ai-ui/shelf-storage-{tests,corrected-test}-20261023.log。

新テストは移行所属/空棚/idempotence、注入失敗rollback、2棚→片方解除、旧scalar batch拒否、rename/delete/ID非再利用、未知ID/衝突時の原状維持、旧app/将来版拒否、backup roundtrip/version不整合を確認。通常DB/私物素材/GUI/GPU/新依存/モデル/CI/旧Alpha変更なし。

## 次の実装単位

Product owner guard下へ接続する。ProductionCatalogと基底Catalogの明示対応版を揃え、scan新規itemへroot_shelvesを適用、旧scalar update/root設定も同じtransactionでjunctionへ同期、root purge時の所属掃除を追加。全検索方式へshelf_idsのOR（他条件AND）を共通backendで適用し、JSON応答/結果sessionのscopeを維持。新APIを公開する前に各adapterを完成させる。単なる基盤commitを複数棚機能完成と扱わない。その後Core/棚一覧→共通library/複数選択詳細を接続。
