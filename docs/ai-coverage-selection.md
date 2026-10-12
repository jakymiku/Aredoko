# AI索引の対象選択 — GUI・設定保存・CPU/API

> 2026-10-13の後続更新：全登録rootを名前/パスで検索し32件pagingで新規選択できるよう改善。選択は非表示ページでも維持し最大256件。長いパスは全文欄で確認。先頭256＋保存IDのみの旧表示制限を置換し、最大32行native controlsを生成。詳細・検証境界は[root-picker.md](root-picker.md)。以下の旧表示/結果は履歴として読む。

> 2026-10-13追記：root欄を最大160 DIPの標準ScrollViewerへ収めた。先頭256＋保存ID（最大512 controls）は未仮想化のまま。生成metadata5万/258登録rootでsaved258への到達・restart/CPU countsを確認。複数rootのID keyset反復sortを修正し、同分布256root countsは14.2→1.41秒。scope配列256・対象1万・settings16KiBの上限は維持。詳細/限界は[規模検証](library-scale.md)。

2026-10-12。**GUI選択欄・ユーザー設定保存・CPU/APIと生成少数件の実CUDAは実装・検証済み**。現行は登録済み・present・除外適用後の候補から最大10,000件。上限を維持したまま、ユーザーが必要な範囲を指定できるようにする。個人フォルダの登録・走査・データ移動を自動で行わない。

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

## 現在のAPIとGUI

- `POST /api/library/ai/coverage` 本文 `{}` または `{"scope":{...},"limit":10000}`。既定limitは10000、1..10000の整数のみ。本文の未知キーを拒否。戻り値 `scope,candidate_total,target_total,fresh_total,remaining_total,coverage_limit,index_limit,refresh_required_on_change`。省略scopeはnull、明示scopeは既定値を補ったobject。scan中は409。encoder推論/起動を行わず、読み取りは256行単位。
- 候補/集計は取得時の観測値で、catalog変更をまたぐtransaction snapshotではない。表示は更新が必要になる。indexは開始時ID/正規化scopeを固定し、publish前に再検査。検索の対象枠は現在catalogから再取得する。
- indexの小さいlimitは今回のjob量のみを制限する。searchはscope内の最大10000件の枠を維持し、fresh vectorだけを返す。GUIでは最初は既定10000を使い、custom job limitと検索枠を同一件数と誤表示しない。
- scopeはai_stateのjob情報と別にユーザー設定へ保存。GUIは保存済みscopeをindex/searchへ明示送信し、一覧kind/viewは暗黙コピーしない。APIでscope省略する外部クライアントは既存互換のまま。
- 今回全CPU142/C#19、scope-native-03は133checks・31PNG全目視、Light/Dark・狭幅・実CUDA・scope保存/restart/空/削除root修復がPASS。前回CUDA15（表紙含む）とnative182/29PNGは過去の検証。詳細と失敗履歴は[引継ぎ](codex-handoff.md)。

## 保存APIとGUIの操作

- GET `/api/library/ai/scope`: `scope,valid,missing_root_ids,error`。削除済みIDは保持してvalid=false、設定破損は409。全rootへのfallbackなし。GETにもlibrary tokenが必要。
- POST同route: 本文は `{"scope":{...}}` のみ。保存した正規化scopeとvalid=trueを返す。未登録ID/明示null/不正型/未知キーは400、scan/AI索引中と保存失敗は409。更新はOrigin/token必須。モデルを起動せず、索引を削除しない。
- AI索引→「AI検索と索引の対象」→条件を選ぶ→件数確認→「保存してAI検索に適用」。未保存で閉じるとdraft破棄。変更/古い応答で件数確認を無効化し、保存中の編集・closeを抑止。保存済みで確認した非ゼロの対象だけ索引を開始できる。文字検索は独立。
- profile/resource/scopeは同じlockとatomic replace、16KiB上限。旧scopeなし設定は従来の全登録root。scope単体の不正値は選び直して修復できる。JSON全体/基礎設定の破損はscope保存だけでは修復できず、モデル選択保存または設定ファイル修復が必要。モデル選択による全体修復では空scopeを設定する。
- 通信エラー後はGETで要求値/以前の保存値と照合、不明な結果ではAIを停止。書込みの自動retryはしない。専用のネット応答喪失fault injectionは未実施。
- 個別root表示は先頭256＋保存済みID（最大512 controls）。大量rootの仮想化、高DPI/HighContrast/読み上げ、意味検索の順位品質は別の評価。
