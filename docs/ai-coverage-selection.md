# AI索引の対象選択 — CPU/API実装とGUIの次段階

2026-10-12。**CPU/APIと生成少数件の実CUDAは実装・検証済み。GUI選択欄とユーザー設定保存は未実装**。現行は登録済み・present・除外適用後の候補から最大10,000件。上限を維持したまま、ユーザーが必要な範囲を指定できるようにする。個人フォルダの登録・走査・データ移動を自動で行わない。

## 最初の実装範囲

- 対象は「登録フォルダ」「種類」「棚」。GUIのAI索引画面で範囲を選び、対象件数を確認してから作成する。文字検索とフォルダ登録の同意は独立。検索中の一覧フィルタを索引範囲へ暗黙コピーしない。
- フォルダは登録済みroot IDだけを受け付ける。未登録ID・bool・重複・過剰なID配列を検査。絶対パスや任意SQLをリクエストに受け付けない。空の明示選択はゼロ件で、勝手に全フォルダへ戻さない。
- 種類は既存catalogの列挙を再利用する。棚は現行の単一文字列に対する完全一致。`null`は棚指定なし、空文字は未整理。複数棚・本のフォルダ集約はこの段階に含めない。
- root/種類/棚/除外で絞ってからID昇順の先頭10,000件を選ぶ。除外作品は対象枠を使わない。重複登録・複数locationから同一作品が見える場合は作品IDを重複計上しない。
- GUIには「条件に合う件数」「今回の対象枠」「fresh vectorがある件数」「残り」を区別して表示する。`coverage_limit=10000`やAPI `total`を全ライブラリ索引済み件数と表示しない。

## APIと保存

既存index/searchリクエストのscope省略は現在の挙動を維持する。追加scopeは同じ正規化関数で検査する。実装済みの契約は次の形。index/searchは任意scopeを受け付け、POST coverageはCPUだけで件数を取得する。

```json
{"scope":{"root_ids":[1,2],"kind":"image","shelf":"デザイン素材"}}
```

`root_ids:null`は登録済み全root、`[]`は対象なし。配列は最大256個の正整数・重複不可、削除済み/未登録IDはエラー。`kind`は空文字（すべて）または既存TYPESの単一値。`shelf:null`は指定なし、文字列は現行棚上限80文字の完全一致（空文字は未整理）。部分省略はこの三つの既定値へ正規化、未知キーや型不正は拒否する。明示scope:nullは400。scope省略との区別もCPU/HTTP契約テストで確認済み。

scopeで絞ったID昇順・最大10,000件を索引/検索の共通の対象枠にする。検索画面のkind/viewはその対象枠に対する追加フィルタとして適用する。検索時だけkind/viewで別の先頭10,000件を選び直して、索引した集合と食い違わせない。既存scope省略の互換経路は契約テストを維持する。

候補件数は上限前のpresent・除外適用後の件数、対象件数は上限後、freshは同一profile/revisionのtext vectorレコードがある作品数（vector破損や検索品質は別検査）、残りは対象件数からfreshを引いた数。表紙対応/表紙成功/失敗は別の指標とし、音楽や壊れた表紙を永久に未完成の作品として数えない。件数と選択集合は取得時点の結果で、変更があると更新が必要と表示する。

対象scopeはjob開始時に固定し、進捗/stateへ保存する。処理中にGUIを変更しても実行中jobは切り替えない。表示用の候補件数取得はGPUを起動しない。索引作成中の競合・フォルダscan・除外/presence/revisionのpublish前再確認は既存規約を維持する。

scopeはmodel/vector-space identityに含めない。同じprofile・item revisionのvectorを再利用し、範囲を切り替えても他の範囲のvectorを削除しない。保存されたscopeでrootが消えていた場合は通知して選び直しを求め、全rootへfallbackしない。設定はローカルに保存し、profile/resource設定のatomic更新・同時保存対策を保持する。

## 小さい生成データでの合格条件

異なる登録root二つ、複数種類・棚・未整理・除外・消失を含む生成データで、索引/検索の同一候補集合、対象件数、60件paging、scope切替後のcache再利用を確認する。未登録/空/型不正root、job中の選択変更、restart後のscope復元、削除済みroot、token/Origin拒否も確認する。元byte/mtime/hashは不変。

上限境界はCPUの偽encoderで検証し、対象選択追加だけのために実GPU10,000件測定を繰り返さない。まず小さな実CUDA sliceとWinUI Light/Dark・狭幅で範囲表示を通す。1TB実ライブラリ、ANN、複雑な表紙の品質は別の評価である。

## 現在のAPI sliceと残作業

- `POST /api/library/ai/coverage` 本文 `{}` または `{"scope":{...},"limit":10000}`。既定limitは10000、1..10000の整数のみ。本文の未知キーを拒否。戻り値 `scope,candidate_total,target_total,fresh_total,remaining_total,coverage_limit,index_limit,refresh_required_on_change`。省略scopeはnull、明示scopeは既定値を補ったobject。scan中は409。encoder推論/起動を行わず、読み取りは256行単位。
- 候補/集計は取得時の観測値で、catalog変更をまたぐtransaction snapshotではない。表示は更新が必要になる。indexは開始時ID/正規化scopeを固定し、publish前に再検査。検索の対象枠は現在catalogから再取得する。
- indexの小さいlimitは今回のjob量のみを制限する。searchはscope内の最大10000件の枠を維持し、fresh vectorだけを返す。GUIでは最初は既定10000を使い、custom job limitと検索枠を同一件数と誤表示しない。
- scopeはai_stateのjob情報として保存済み。GUIが使う次回対象scope設定・保存APIはまだない。scope省略の既存GUIは従来通り動作する。
- CPU11件、全suite137件、実CUDA15checks（生成6件/PNG4件、document4/image4/query3、所有3handles全終了）がPASS。native182checks/29PNGは既存GUI・グリッド・解放画面の証拠で、未実装のscope選択UIを操作した証拠ではない。
