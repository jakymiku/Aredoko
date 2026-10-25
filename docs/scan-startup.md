# フォルダスキャンと起動時更新

## U4a引き継ぎレビュー（2026-10-25）

基点51b4302。APNG修正cdf7a35と登録後dialog/初回3段階案内は維持する。

- AI索引の対象を「今回走査したroot ∩ 保存済みAI範囲 ∩ 登録中root」に限定。kind/棚条件を保持し、保存済みscopeを書き換えない。従来hookは全保存範囲を渡していたため、選択外rootまで索引化する可能性があった。
- scanの所有AI workerを既存guardで固定し、終了まで監視。後続の別ジョブの進捗をscanとして表示したりcancelしたりしない。AI実行中のタグ編集は維持し、二重scanは拒否。実際のAISearchも偽エンコーダーで確認。
- 複数rootは成功したrootごとにcatalogへ公開。後続rootの失敗で先行rootの一覧が未同期にならない。途中失敗/取消で原本・保存metadataを削除しない。
- nested/bool/重複root IDをvalidation errorにし、AI例外から私物path等を返さない。AI設定へのdialog遷移は排他制御の解放後へ移した。
- CPU確認：scan follow-up9、既存production8、AI search13、animation14 PASS。Portable publish成功（既知WUI1001/SDK IL2104残存）。実モデル/GPUなし。GUIは今回ユーザーの事前回答待ちなので未実施。
- 証拠：ignored `data/ai-ui/continuation-20261025b/`。試験frontend01は上記補強まで。後続U4bを含むcandidateと混同しない。

## 起動時更新の実装単位

ユーザー承認計画U4b：rootごとに「しない（旧root既定）／一覧のみ／一覧＋AI」。初画面後、指定された登録中rootだけをbackend所有queueで一度処理する。重複起動要求は再実行しない。失敗rootを無限retryせず、scan/backup/取消/終了の所有を守る。

成功した全走査で確定したmissingだけを通常検索・棚・お気に入りから除外し、タグ・棚・読書位置等は保持。切断・権限失敗・取消でmissingに確定させない。再出現時は同じ論理IDとmetadataを復元する。

### U4b実装（2026-10-25）

- catalog `user_version=3`。root preferencesへ `startup_scan=none/list/list_and_ai` を追加。旧v1/v2のfavorite・棚を保持して既定OFFへ原子的に移行する。v3を旧アプリで開くことは拒否する。復旧manifestはv2のまま、catalog v0–v3の厳密な列検査を維持。歴史的な同居vector storeもv3を扱う。
- フォルダ設定で単一/複数rootへ即時保存し、次回起動から適用。除外・棚の未保存draftには触れない。初画面のrender完了後に一度だけ認証付き `POST /api/library/startup-scan/start {frontend_ready:true}`。backend生成時やpref保存時には走査しない。
- backend所有queueは手動scanを優先し、rootごとに順次実行。取消は所有job IDだけへ送る。完了job状態は直近16件を保持し、後続manual scanの結果/取消と混同しない。個別失敗で他rootを止めず、AI失敗でも一覧を保持する。終了時はqueueを先に止めてからAI/catalogを解放。
- 専用InfoBarで更新中/中止/部分失敗を表示。完了時は既存の選択・タグdraftを勝手に置換せず「一覧を更新」で反映。既存結果sessionはcatalog世代の変化で無効化される。
- 成功scan後のmissingは通常・favorite・history・棚一覧の件数/代表から除外。IDとmetadataは残し、再出現時に復帰。原本の削除や私物走査は行わない。
- CPU: startup15（認証/重複JSON/一度限り/owned取消/backup fence/移行rollback/復旧/metadata回復）、root preferences6、live backup12、storage backup29、missing結果session1 PASS。Core契約・Portable build確認済み。GUI/GPUは現ユーザーの事前回答が必要で、未実施。証拠はignored `data/ai-ui/continuation-20261025b/`。
