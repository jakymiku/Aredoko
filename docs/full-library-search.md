# R02-B — 保存済み索引全体の検索API接続

2026-10-18。実装 `ae6e982d6500d66a788922bcdeeb328c4f8495ca`。R02-AのSQLite作業DBを通常AI・画像起点類似・未承認タグ意味検索へ接続した。**保存済みvectorが候補の先頭1万件以後にあるという理由で落ちる問題を解消。** 索引作成1回の最大1万件・coverageの先頭job範囲は維持。全件の自動索引/明示継続はR04で、今回完了とはしない。

## 経路・互換

- 全候補をID keysetで読む。SQL取得/score入力は256作品、最終pageのmetadataは最大120件。text/cover/combined、自己除外した画像/本/archive類似、最新pendingのscope/kind/view/shelf/modelを保持。
- `VectorStore.scores_with_content`へ既存の復号/normalization/dot/最良page/time選択を切り出し、旧`rank_with_content`を全件oracleとして保持。batchで得たraw mode scoreを一度だけ全体融合し、literal/group/pageはその後。モデル・vector namespace・スコア式/閾値は変更せず再索引不要。
- 完了応答に`search_complete:true`、`search_candidate_total`（kind/view/モダリティ適用後の全メタデータ）、`indexed_total`（有効な証拠のある作品）を追加。`total`はliteral/group後・page前。未承認のpending/indexed/remainingも全対象を数える。
- `coverage_limit`は旧クライアント互換の索引job上限として維持し、`index_limit`も返す。Coreは完了フラグ/件数の整合を検証し、complete応答では検索上限の説明を表示しない。pending意味の旧「最大1万件」応答拒否も解除。旧応答も読み取れる。

## 競合と公開時の確認

requestが保持するcatalog/profile-store監視接続の`PRAGMA data_version`、catalog epoch、profile、明示scope、scan状態をbatch間/公開前に確認。タグ/棚/favorite変更もepochだけで見落とさない。推論中や全件融合中にcatalog guardを保持せず、変更検出では409相当の再検索案内として破棄する。自動再試行や部分結果のcomplete扱いはしない。

返すpageはmetadata版を再取得し、本文page根拠は物理source版を再確認。類似起点も監視開始後に取得し、公開前に再確認。pendingは署名と表示source状態を確認。これは複数DB/全ファイルのatomic snapshotやTOCTOU完全解消の保証ではない。

closeとworkspaceのSQLite progress handlerによるCPU処理中断、容量エラーの503案内と後始末は接続済み。**このR02-B時点ではrequest ID取消は未実装だったが、現在は[R02-C](search-cancellation.md)で専用ID/API・Coreまで実装/CPU検証済み**。既存index jobのcancelを検索へ流用せず、R02はCPU_DONE。UI全体の取消配線R10・資源/性能R12・必要native/GPU受入R14は残る。

## 検証記録

固定実装 **`ae6e982d6500d66a788922bcdeeb328c4f8495ca`**、テストfixture修正 **`b10e92771243612a5b2e4150d9694ab9784eb0b2`**、Core類似応答の追加互換修正 **`a3b7781a391acf01c7afdb8e32b2f4d8ad14bc46`**。Python製品コードは後2commitで変更していない。

同じR01プロトコル/監査ツールを新しい出力先へ`--require-complete`で実行し、両方終了コード0。source bytes/mtime・保存vectorの論理digest不変、実モデル0、queryは3D固定配列のみ。

| metadata | 対照PASS | 完全性PASS | 一連の監査所要 |
| --- | --- | --- | --- |
| 10,001 | 17/17 | 30/30 | 12.428147秒 |
| 50,001 | 17/17 | 30/30 | 58.592871秒 |

R01では8/21条件が不合格だったが今回は各30/30。全体・単/複数root・棚・favorites・種類・空集合・除外・解除/再登録・類似・pending・page-only本を含む。sparse保存vectorによる候補参加の検査で、全5万件を推論/索引作成した証拠ではない。所要は30条件等を含む単発監査で、単一検索/p95・実1TBの性能値として比較しない。同時に他CPU回帰も実行しており速度改善率は主張しない。

- `r02b-10001-20261018-01/report.json` SHA256 `954991c967c068fa1c01a62d8d45eacc8518ea57920bdf3c297a1c58fa3b4c88`。
- `r02b-50001-20261018-01/report.json` SHA256 `2d08dbdf7033b8ab5cb5db05da746024f74785c13f0f1970fe367692d5899356`。

- **全Python537件：534 PASS /3 Windows platform SKIP /413.63211秒**。`full-python-final.log/json`、記録した製品source SHA不変。
- 専用Python3.11.9対象 **61 PASS /0 SKIP /62.044316秒**。`python311-targeted.log/json`。queryはmock、CUDA無効/offline。
- **Core Releaseテスト501 checks PASS/4.1764111秒**（`dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore`）。complete件数/legacy fallback、1万件超pending/類似のdeep page、誤ったcomplete/count拒否の8チェックを追加。類似にも残っていた旧Total≤10000ガードは、全件完了/件数整合の応答で解除し、旧応答の安全境界は保持。`core-final.log/json`。
- **Windows x64 SelfContained Release：警告0/エラー0、23.08秒**（`dotnet build src/Aredoko.WinUI -c Release -p:Platform=x64 -p:SelfContained=true --no-restore`）。GUIは起動していない。Coreの追加修正前のビルドも23.18秒/0警告0エラーで、最終値とは区別する。`release-final.log`。
- 初回scope対象は旧capを期待する1FAILを確認し、新契約へ更新。初回全Python537件は1FAIL/2ERROR/3SKIP（416.221957秒）。架空のsource版、検索にも発火するbuild用hook、内部rankとAPIのguard順序を混同したfixtureを修正。safe-path一冊一回とepochの即時無効化は`PageVectors.rank`単体で引き続き検査し、APIの変更中破棄は新streaming回帰で検査する。対象23PASS後に全体を1回再確認し合格。初回ログを保持し、製品の検査を省略して旧期待へ合わせていない。

新規streaming7件とpending-review競合1件は、769作品・4batchで旧全件oracleとの全score.hex/順位一致、page根拠、literal/group/page、scope省略/明示、epochを変えないタグ/棚/favorite編集、profile DB書込、最後のbatchの解除、rank後の元本変更、容量失敗のcleanup/inference解放を確認する。request-owned取消はこの合格に含めない。


## レビューと未確認

WinUI Code Reviewを適用。APIのcount cap・検索上限説明の不整合を修正し、async/dirty/focus/列挙の仮想化・既存theme/AutomationIdを維持。XAML/API追加なし。既存code-behind日本語の全面resw化は対象外。WinUIAnalyzer未導入/未実行、native表示・DPI/High Contrast/Narrator/実GPU品質/実私物1TB・全RSS予算は未確認。GUI/GPUは現在のユーザー指示で延期し必要時に事前確認する。
