# P4 登録フォルダの複数初期棚（2026-10-23）

既存root_shelvesを使い、POST /api/library/roots/shelves {root_ids,shelf_ids,fill_unset}を追加。最大256 root/64 shelf、全root登録中/ID/型/重複を検証し、一つのtransactionでroot初期棚と任意の棚未設定作品へ適用する。既存所属は上書きせず、即時除外・登録解除対象はfillから外す。途中失敗はroot/作品ごと全rollback。旧scalar APIは保持する。

設定の「棚を選択（複数可）」と共通pickerを接続し、単一棚/新規棚の既存導線も新しいID保存へ統一した。複数所属から1つ/棚なしへの明示変更も扱い、同じ主棚でも副棚が異なるbatchを混在として示す。初期棚だけ保存しても除外ルールのdraftは残す。API成功後の再取得失敗は保存済みと区別する。保存中は標準ContentControlでフォームを無効化し進行表示する。

確認: catalog11 PASS/3.060s、root HTTP等6 PASS/1.747s、Core911項目PASS。最初のWinUI buildはGrid.IsEnabledがないCS1061に続くWMC9999で失敗。最初の原因を直しContentControlを使い、正しいproject API確認後のbuildは0 errors/既知WUI1001×3、11.46s。rawを保持しCoreとPythonは無変更なので重複実行しない。GUIの新root picker/一括saveは未受入。既存棚flow3/3は別名でresetしない。

新規登録時の従来単一初期棚は維持。登録後の設定では複数棚が選べ、以後のscan新規作品は全所属を継承する。catalog2/favorite/旧DB拒否/backup互換はecc901aのまま。source/DB移行対応と旧Alpha/配布ZIPを混同しない。

次はP5の起動中snapshot・所有backup job・選択/進捗/取消・安全restore接続。P3/P4 native残件/P6/P7/実音声は未完。今回の終了は残り10%前後の保存/commit/push/handoffのみ、シャットダウンなし。
