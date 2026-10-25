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
