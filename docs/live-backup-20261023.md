# P5C authenticated backup API（2026-10-23・最新）

P5B `4ecb28b`の実fenceを使用してGET `/api/library/backup`、POST `/api/library/backup/start`・`cancel`を接続した。session/Host/Origin/body上限/重複JSON/厳密fieldsを保持。startは202、同時実行と古い取消は409。進捗・結果・初期選択を返す。既存出力は変更せず失敗する。production終了はbackup ownerをDB/AIより先にcloseし、受理した取消やclose後の公開を禁止する。

APIの設定入力は最大2048bytesの検証済みviewer JSONのみで、HTTPから任意の設定パスを読み取らせない。バックエンドの設定/profileは実際に設定された場所だけを取得する。手動指定tagger profileは同梱対象。viewer JSONを渡さなかった場合はmanifestでviewer設定の欠落を明記する。runtime/Python/model配置はbackup対象外。復元APIは未公開（restore_supported=false）。

確認：新規HTTP4 PASS/3.081s（実capture→restore、設定snapshot、認証・Origin・duplicate/size/field拒否、検索/status/取消の応答、既存先保全/設定省略）、owned jobs5 PASS/0.473s、live capture8 PASS/1.792s（外部設定変更で公開拒否を追加）。生成DB/loopbackのみ。Core/WinUI/UI選択永続化/復元切替は次の小単位、P5全体はPARTIAL。以前の「HTTP未接続」はこの節で更新される。通常DB/Alpha/元メディアは未変更。シャットダウンなし。

---

# P5B shared writer fence（2026-10-23・最新）

Catalog・VectorStore・AI設定・runtime設定の公開を共有WriterFenceへ接続。captureはcatalog guard→pauseの順で取得し、既存writer終了を待ち、新規writerをsnapshot解放まで待機させる。読み取りは拒否しない。設定とprofile一覧はcopy後にも再確認し、外部変更時は完成bundleを公開しない。SQLite commit/close後にwriter tokenを解放する。runtime設定はfenceを先に取得してから所有jobのpublish lockへ入るため、snapshot待ちでも取消/closeを妨げない。

確認：writer fence5 PASS/0.936s、setup jobs15 PASS/2.334s（新規のpause待機中取消を含む）、AI設定13 PASS/2.640s、AI scope12 PASS/18.263s、result sessions21 PASS/33.836s、live7 PASS/1.829s。生成DB・設定のみ、追加Core/WinUI/GPU/GUIなし。古い実績へ重複加算しない。

この時点ではHTTP/UI未接続。次は認証付きbackup start/status/cancelへ本番fenceを使用して接続する。前回選択の永続化、設定UI、復元新規先→正常終了→起動先切替/失敗rollback、実容量/性能受入は未完了。P5全体やロードマップ完了を意味しない。現在の指示はquota残り約10%で安全なcommit/push/handoff、シャットダウンなし。

---

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
