# 大規模ライブラリ検索契約 — R01

状態：**R01の実装前契約を固定、R02-B実装/CPU確認済み、R02-C/R04は残る**（2026-10-18）。開始コード `77f24f6`。本書の受入条件を満たすまでは「5万件全体をAI検索可能」と扱わない。実行順は[完成計画](completion-roadmap.md)を正とする。

## 目的とR01時点の境界（変更前）

1回の索引作成の負荷上限と、保存済み索引を検索する対象範囲を分離する。候補のIDが10,000より後という理由だけで落とさない。元ファイル・現在のmodel/profile・全機能を保持し、既知品質セットへの第3回RRF調整や専用OCR追加は行わない。

以下はR01のコード監査時点の順序。[R02-Bの対応と証拠](full-library-search.md)で検索打切りを解消した。10,000はメタデータの候補数であり、正常な保存vectorがある作品数ではない。フォルダ内でのID順序と、全体のID値そのものも別である。

| 経路 | 現在の順序と境界 | 問題/維持する点 |
| --- | --- | --- |
| 通常の名前/タグ | `ProductionCatalog.search`：登録/除外・root/kind/view・語一致→全件count→順位→SQL page | AIの1万上限なし。`present`以外のmissing表示など既存通常検索仕様は維持し、AIへの統一で消さない |
| 通常の未承認タグ文字検索 | `tag_candidate_search.search_candidates`：最新pending batch・条件/語→全件count→60件page→そのページのsource状態 | AIの1万上限なし。未承認/確定の分離を保持 |
| AI検索、scope省略 | `_rows(kind,view)`：present/有効root/除外・kind/view→先頭1万メタデータ→有効vector/ページ/動画→全体融合→literal/group→page | 絞り込み前後で到達範囲が変わる。先頭候補の未索引も上限を消費 |
| AI検索、明示scope（空辞書も含む） | `_iter_rows(scope)`：scope/root/kind/shelf→先頭1万→結果kind/view→cover対象kind→有効vector/ページ/動画→融合→literal/group→page | 保存済み末尾vectorも落ちる。favoritesや結果kindでは上限を救済できない |
| 画像起点類似 | 起点をscope/currentで別取得→先頭1万scope候補→自己/非visual/結果kind/view除外→cover cosine→再検査→page | 起点は末尾でも取得可能。候補側は打切り。page-only起点は従来どおりunindexedでtext fallbackなし |
| 未承認タグ意味検索 | root/kind/shelf/view→先頭1万→最新pending/model/signature/vector→query→再取得/再順位→page | modelやpendingが少なくても先に一般メタデータ上限を消費。`pending_total/indexed_total`も打切り集合の値 |
| 本ページ視覚検索 | `PageVectors.rank(rows,query)`は渡された本を256冊batch・保存pageをstream→各本最良1page→原本/版検査→coverへ集約 | page数の1万candidate制限はないが、外側AI検索が渡す作品を先頭1万へ制限している。内ページを直しても外側の欠落は残る |
| coverage | `all_candidates=True`で全メタデータcount、先頭limitだけfreshness確認 | `candidate_total`は全体、`target_total/fresh_total/remaining_total`は1回のprefix jobの値。全体の準備済み数と呼ばない |
| 索引start | scope/除外→先頭limit（最大1万）IDs→workerが再取得/版確認/原子的に保存 | 再実行も同prefix。未処理分へ進める仕組みはR04。limit自体を検索範囲へ流用しない |

登録rootの除外はAI列挙時にも反映される。通常の名前/タグ検索の未rescan除外やmissingの既存仕様まで本タスクで変えるものではない。

## 固定した再現プロトコル

[fixture定義](../tests/fixtures/large-library-boundary-v1.json)と[監査ツール](../tools/audit_large_library_boundary.py)を実行前に固定する。

- 10,001 / 50,001件、3rootへ交互配置。全体の位置、単root内の位置、複数root内の位置を分ける。MAX_ITEMSのmonkeypatchで規模を代用しない。
- ID=1、上限直前/直後、末尾直前/末尾に3D float32の保存vectorを置く。他のメタデータは未索引。末尾は画像、末尾直前と上限直後の別作品はpage-only本。数枚のPNG/CBZだけを生成し、ページ版確認は実際のPreviewReaderを使う。
- 文字/視覚/combined/cover類似/pending意味の全体・単root・複数root・棚・favorites・kind、空scope・除外・解除・再登録を比較する。通常の名前/タグとpending文字検索は末尾到達の対照群。末尾の保存vectorと本の物理版が有効であることを独立に確認する。
- 同じ`start`を2回通してworkerだけ置換し、選択IDsが同prefixであることを確認する。**実推論・index継続の動作テストではない**。document/image encodeは例外にし、queryも固定配列を返すだけ。
- 出力先は新規専用folderのみ。既存folder/DBの再使用を拒否。元生成素材のbytes/mtime、保存済みvectorの論理digestを前後比較。scan・実モデル/GPU/GUI・私物は使用しない。

`audit_passed`は対照群と原本保持が正常に検査できた意味。`completion_gate_passed`は全保存済み対象の参加を別に判定する。前者だけを製品合格と報告しない。`--require-complete`は後者がfalseなら終了コード2。sparse vectorの試験であり、denseな全5万件のRRF順位/メモリ/速度の証拠ではない。

```powershell
python tools/audit_large_library_boundary.py --count 10001 --output data/large-library/r01-10001-<new-label>
python tools/audit_large_library_boundary.py --count 50001 --output data/large-library/r01-50001-<new-label>
```

実測結果は実行後に末尾へ記録する。fixture/code commit・report SHA・環境を記録し、失敗/旧reportは上書きしない。

## R02が満たす検索契約

### 候補と件数

1. present location・有効root・現在の除外・明示scopeの交差を最初に決める。scope省略と`{}`は同じ全集合、`root_ids:[]`は空集合、解除済み/未知の明示rootはエラー。scope/rootの検証を省略した全体fallbackはしない。
2. 結果kind/viewと検索モダリティを適用してから、**全対象**の正常な同profile/同revision vectorを候補にする。索引jobのlimitは適用しない。literal_only・表示group・pageによって融合poolを先に縮めない。
3. coverは画像/本/archive/動画。1作品につき従来どおり最良の表紙/代表frame/本文pageをcover modeに集約する。time/page根拠・同値時の選択順を保持。類似の画像起点/候補kindを動画へ広げるのはR05で、R02の欠落修正とは分ける。
4. `total`はliteral/group条件後、page前の全結果数。0件を「メタデータはあるが未索引/旧版/対象外」と混同しない。追加する`search_candidate_total`は結果kind/view/モダリティまで適用したメタデータ数、`indexed_total`は融合に有効な証拠を持つ作品数。`search_complete:true`はこの対象集合を全て検査した場合だけ返す。処理不足をcomplete付きの空結果にしない。
5. `coverage_limit`は既存クライアント互換のため当面保持できるが、検索打切り件数としては廃止し、`index_limit`と区別する。Coreのstrict parsing/ユーザー向けの上限表示も確認する。R10で不足状態を簡潔に表示し、既存機能を削除しない。
6. pendingの`pending_total/indexed_total/index_remaining`も全scope/model/viewの最新pending集合に対する値にする。承認/却下・signature変更は旧vectorを使わない。raw英語タグを翻訳して上書きせず、確定タグとも混ぜない。

### 順位・数値・ページング

- 既存のfloat32復号、normalization、sum/dot順、page scorer、profile namespaceは維持。新しいprecision、近似索引、閾値、routingを導入しない。10,000件以下の固定入力はraw `float.hex`・融合score・順位・page/time根拠を一致させる。
- `max`は全体のcosine降順/ID昇順。mean-RRFは**全集合の各modeのcount・min/max・span・同点平均順位**を一度決めてから、既存`fuse_modalities`と同じmode順序/重み/加算順/分母/constant fallbackを適用する。batchごとにRRF/spanを計算した上位結果の連結は不採用。
- literal_onlyは融合後。境界提案は全順位の先頭32scoreから現行`boundary`で決め、leading/other件数は全対象から集計。その後result_groupとpageを適用する。同じ変化のない入力では重複/欠落なくpageへ分割できる。異なるリクエストの間にcatalogが変化した場合まで同じpage内容を保証しない。
- 欠けたmode、constant/tied pool、非常に大きい同点group、破損/非finite/別dimension/vector、page-only/動画-onlyを固定試験に含める。RRFの性能受入を品質調整と取り違えない。

### 採用する実装方針と資源予算

比較した方式：(A)全metadata/vectorをlist化する案は規模比例のPython RAMのため不採用。(B)modeごとの小さいtop-kのみ融合する案はglobal rank/span・深いpageを変えるため不採用。(C)**既存keyset列挙＋request専用のSQLite作業DB**を採用。製品の永続vector schema/検索モデルは変えず、stdlibのみで実装する。

1. 開始時に最大item IDを固定。256件以下ずつ列挙・現行scorerへ渡し、作品ごとのmode scoreと根拠を作業DBへ書く。全metadata、全decoded vector、全page evidenceをPythonの辞書へ溜めない。
2. mode scoreはSQLite REALをsort keyに使い、必要なraw値はhexも保存してsigned zeroを含めPython値へ復元可能にする。modeごとにglobal順序/同点件数をstreamし、Pythonで現行と同じ演算順の融合scoreを保存する。SQLiteのSUM/AVGをそのまま既存Python和の代用にしない。同点group全件のlistも持たない。
3. 作業DBの索引/SQL count/order/pageを利用し、最終pageのmetadata（最大120件）だけ再取得する。literal/groupのfilter/countと先頭32scoreはpageを切る前に処理する。
4. 作業DBはrequestごとの新規TemporaryDirectory、専用cache8MiB、DB上限256MiBを初期値とする。追加Python保持量の目標≤32MiB、モデルを除く追加RSS目標≤256MiB（5万metadata/65,536vector fixture）。上限値は**未測定の設計予算**。SQLite native sort一時領域はDB本体のpage上限だけでは制限できないため、R12で別途計測・容量不足を明示エラーとする。全RAMに対する厳密な保証とはしない。
5. 成功/取消/例外で作業DB/接続を閉じ専用folderのみcleanupする。Windowsでhandleを閉じる順序、ディスク満杯/作業DB上限、cleanup失敗の扱いをCPU回帰にする。過去report/元DB/元素材へ削除を広げない。

### 鮮度・競合・取消

catalog guardを全件rankやquery推論中ずっと保持しない。登録/除外の`_state_epoch`に加え、**通常のタグ/棚/favorite変更は現コードではepochを増やさない**ため、epochだけで一貫性を保証しない。

- 開始時から保持した監視用SQLite接続の`PRAGMA data_version`をcatalog/選択profileのstore双方で取得し、batch間と公開直前に比較する。guard内の短い最終確認も行い、metadata変更や署名/版/登録条件の競合を見つけたら結果を破棄して再検索を促す。自動で無制限再試行しない。複数DBを真にatomicなsnapshotと呼ばない。
- 開始upper ID・profile/contract・scopeはrequest固定。新規追加で列挙が延び続けない。最終pageの作品と類似起点は版・scope・結果filterを再確認。pending source状態、本文の全祖先/handle/物理版再確認は既存経路を再利用し、rawvector cacheで省略しない。現状のmetadata freshnessと物理source freshnessを同一の保証として表示しない。
- batch境界とSQLite progress handlerで取消/closeを確認。query encode自体の停止可能性と、CPU検索の停止を区別する。R02はPythonのrequest-owned取消contextを持ち、互換を壊さない任意request IDと認証済み取消APIを追加してCPUで確認する。別request/古いIDの取消は拒否し、既存索引jobのcancelを検索取消へ無断流用しない。UIからの取消接続はR10で行う。
- 検索中のscan開始、別profile/閉鎖、origin更新、除外/解除/棚変更の競合は、旧条件の結果をcurrentとして返さない。scopeが無効なら従来のエラー、進行中の競合なら再試行可能なbusy/conflict。部分結果を全件結果として返さない。

## R04へ渡す索引継続契約

1要求の既存limit≤10,000は維持してよい。検索候補とは独立。CPU planは全scopeから同profile/現revisionの未準備をID順に選び、最大limit件の固定IDs/revision/scope/profile/upper-IDを返す。推論・自動開始はしない。

明示start/resumeだけで進め、完成した作品vectorを保持する。停止後は保存済みを検出して未処理へ進む。再開記録は最新jobの固定選択だけ、異なる版/scope/profile/除外/解除後の暗黙拡張は拒否。完了後の「次の未準備」を確認して進めば先頭1万を繰り返さない。永続一般queueの新設や起動時の全私物走査は不要。

coverageの従来prefix件数を壊さず、scope全体のfresh/remaining/対象外/失敗・次job件数を別フィールドで明示する。手動タグ/WD候補変更時の再準備、部分失敗、再登録後の再利用を検証。R03のbackup/recovery契約と衝突する保存先を勝手に増やさない。

## R02/R04の受入仕様と次の実装順

| 区切り | 必須証拠 |
| --- | --- |
| R02-A 作業DB engine | 全件oracleとのmax/mean-RRF float.hex一致。256境界をまたぐ同点/constant/欠mode、deep page/件数/boundary、途中例外/取消/close/DB上限cleanup。Python保持量が候補数とともに全metadata量へ増えない |
| R02-B 検索接続 | text/cover/combined・類似・pendingへ接続。現再現2規模でcompletion gate全PASS、最後のID/本pageが参加。旧小規模のscore/順位/根拠/HTTP/Core互換を保持。未索引を0件精度失敗と混同しない |
| R02-C 競合・資源 | metadata/棚/favorite/登録/除外/scan/profile/原本の変更、破損vector、request取消/誤IDを検証。実GPU/GUIはR14まで未確認。対象Python＋必要Core/Releaseのみ実行 |
| R04 索引完走 | 5万metadataのbounded未準備選択→start→cancel→service再作成→同job明示resume→次planでprefix以後へ進む。scope/revision/原本不変、私物・実モデルなしのCPU証拠と実機待ちを分ける |

R02-A/Bは実装/CPU検証済み、次はR02-Cの所有取消API/残契約を実装する。RRF全体式や同点を変えて再現だけ通す修正は不採用。GUIを触る前にengineとAPIの契約を確立する。

## 実行記録

固定commit **`30ceef635f893bc4d3a3a6c3501fe9c66553cde0`**で実行。Python3.14.4/SQLite3.50.4、queryは固定3D配列のみ。出力は`data/large-library/r01-10001-20261018-01/`と`r01-50001-20261018-01/`。各17対照は全PASS、原本bytes/mtime・保存vector digest不変。

| metadata件数 | 監査対照PASS | 検索完全性PASS | 打切りによる不合格条件 | 監査全所要 |
| --- | --- | --- | --- | --- |
| 10,001 | 17/17 | 22/30 | 8 | 17.835834秒 |
| 50,001 | 17/17 | 9/30 | 21 | 82.679017秒 |

所要時間はfixture生成後の複数操作を含む一連の監査で、単一検索やp95の速度ではない。10,001件では全体text/cover/combined・scope省略・明示scopeのfavorites・類似・pending・再登録後の8条件で欠落。50,001件では単/複数root内にも1万超の候補があり、21条件で欠落した。解除・除外した末尾が消えることは対照でPASSしており、同caseの不合格は別の有効な末尾候補が打切られるため。検索精度の正誤を21問測った意味ではない。

両規模のcoverageはcandidate_totalが全件、target_total=10,000/fresh_total=3/remaining_total=9,997。実startのworkerを置換した2回とも同じIDs1〜10,000を選択。末尾画像のtext/coverと遅い本pageは別取得では有効、通常の名前/タグ・pending文字検索は末尾を発見し、棚で1件へ絞った意味検索も成功。未索引ID2との違いを確認した。

- `r01-10001-20261018-01/report.json` SHA256 `e28996f60b56211c5bff8c625dfdac013a610783ed077a442201b550a4a2df53`。
- `r01-50001-20261018-01/report.json` SHA256 `1df6ae97aa715f05b094c8c3a9bcf01e65da9aa040c5b073557606170d084afa`。

**R01はDONE**（再現と実装可能な契約が揃った）。当時は候補打切りが残ったが、現在は[R02-B](full-library-search.md)でAPI接続と両規模30/30を確認済み。[R02-A測定](score-spool-engine.md)は内部engineの履歴。次はR02-Cの所有取消API/残契約。
