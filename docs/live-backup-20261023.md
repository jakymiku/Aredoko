# P5A 起動中capture・所有backup job基盤（2026-10-23）

## 到達点

live_backup.capture_liveは明示的な全writer所有者のquiesce factoryを必須とする。catalog操作guardと複数SQLite DBのwriter予約→全reader snapshot固定→SQLite backupで所有stageへcopy、という順で同じ停止境界を取得する。検索readは続けられ、snapshot接続を閉じてから既存の厳密backup/restore形式へ梱包する。ライブファイルの生copyやCLI subprocess呼出しではない。

ライブラリ基本情報は必須、設定/profile・履歴・読書位置ON、AI vectors OFFが初期値。履歴/読書位置の除外はcopyだけで行い元DBは不変。manifest not_includedに省略を明記し、復元時に虚偽の省略宣言を拒否する。従来v1 bundleは受理する。backup関数の従来既定は互換維持し、新しいUI初期値はBackupSelectionを使う。

BackupJobsは所有thread/ID/進捗/単一実行/取消/closeを実装。取消判定と完成manifest公開は同じlockを使い、受理した取消後の公開を禁止する。公開後の後処理失敗は作成済みと報告しrollbackと偽らない。ブロック中のOS readは強制終了できないがclosed ownerは後からpublishしない。stageの再帰掃除は作成時の絶対parent/physical identityを検証した新規childだけ。

## 確認

初期live5 PASS/1.123s。最終live7 PASS/1.556s（複数catalog/vector DB、検索readとの両立、source writer再開後も旧snapshot、選択除外、取消、設定bytes、既存出力保全、虚偽policy拒否）。所有jobs5 PASS/0.456s（cancel-vs-publish、stale ID、close後publish禁止、公開後失敗、thread start失敗、実capture→restore）。既存backup/restore28 PASS/26.829s。重複合算しない。Pythonだけの変更なのでCore/WinUI/GPU/GUIを反復しない。

## 接続前に残る必須gate

**P5 PARTIAL。製品HTTP/GUIには未公開。** 仮のnullcontextを製品quiesceに使わない。catalog/vector/index/configの全所有writerを安全な論理境界で止め、取消で復帰できる本番fenceを接続する。その後認証API/保存する前回選択/進捗UI/設定保存、restore新規先検証→正常終了→起動先切替/ready失敗rollbackを実装する。現在の設定内CLIガイドはまだ残っており完成ではない。

初版は整合stageを作ってから既存bundle処理へ渡すためDBを2回copyする。空き容量はstage前に推定3倍+16MiBを要求し、各段階でも既存上限/容量/identity検査を維持。高速化や実容量/速度の受入は未実施。元DBのread snapshotはstage作成後に解放するのでpacking中に長いWAL snapshotを保持しない。モデル/Python/元メディア/サムネイルを含めず、普段のDBやAlphaは今回未起動。

P4の直近commitは8e6c3dd、shelf描画修正260e7dc、root favorites ecc901a、画面履歴efbc403、棚Core/UI b0a00c4。各native未受入と3/3上限を保持。今回シャットダウンなし。
