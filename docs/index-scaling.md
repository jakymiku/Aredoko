# 1万件までのAI索引拡張（2026-10-12）

AI索引・検索の対象上限を2,000→10,000件へ拡張。旧モデルidentity/vector schemaを変えず、保存済みの現行revisionを再利用する。単なる上限変更と区別して、候補・metadata・vectorの読出しを制限した。数万件全体/1TBの実ライブラリに対応済みとは扱わない。

## 実装

- 対象はpresentかつ現行root除外に一致しない作品。kind/viewを先に適用し、eligibleなitem ID昇順の先頭10,000件。除外済み行が先頭に多くても対象枠を消費しない。検索APIのcoverage_limit、statusのlimitは10,000（実際の索引済み件数ではなく対象上限）。検索totalは選んだ対象中のfresh vector件数。
- 候補列挙は最大IDを開始時に固定し、256行ずつkeyset取得。新しいIDの追加で無限に伸びない。大量除外時は10,000件を得るまで更にページを読むため、走査量まで10,000行以内とは限らない。
- buildは候補IDのリストだけ固定し、metadataは256件ずつ現在値を取得。後続batchのタグ変更は取得時点の最新値を採用する。推論中にpresence/revision/除外が変わった作品はpublish直前に再確認してskip。catalog全体の同一時点snapshot/複数DBのatomic transactionを保証する設計ではない。
- vectorは従来通り1作品ごとにatomic commit。進捗は16件間隔と最後に保存し、表示は最大15件遅れる。cancelは実行中の1作品処理後に終了。次回は保存済みrevisionを調べ、fresh分を再推論しない。起動時のrunning/cancelling→interrupted復旧を保持。
- 検索vectorは候補IDの256件IN batchだけ読む。1vectorずつ扱い、無関係な保存済みBLOBの全走査を避ける。mean-rrfの順位は全batchのscoreを集めてから一度だけ計算し、batch内順位を融合しない。
- 検索時のmetadata/score/rankは最大10,000件保持する。buildのIDリストも件数に比例する。constant-memory/ANN索引ではない。60件paging・明示text/cover・max rollbackを維持。
- GUIはサーバー既定値で索引を作成し、APIが返す上限を表示する。古いliteral応答にcoverage_limitがなくてもC#は受け取れる。APIの明示limit=2000は引き続き有効。

## 生成データの測定

`python tools/test_index_scaling.py --output data/index-scaling/<fresh-folder>` は新しい出力先だけ受け付ける。生成10,010個の小さいWAV名ファイルを製品scannerで登録し、うち10,000件を索引化。音声としては読まず、768次元text-onlyの決定論vectorを返すテストencoderを使う。actual_model=false / gpu_used=false / native_gui_run=false。EG2/Layaをロードしない。

smoke-01は **14 checks PASS**。2,300件でcancel→別AISearchへ再起動→残り7,700件だけdocument encode、全10,000件完了、最後の対象作品がtop1、60件/最後40件paging、お気に入りfilter、再起動後document encode 0で再利用。対象外10件は文字検索に含まれる。生成元の全byte/size/mtime digest一致。

| 測定 | この実行の値 |
| --- | ---: |
| scanner 10,010件 | 3.15秒 |
| start候補ID収集 | 0.33秒 |
| 初回2,300件まで＋cancel | 28.50秒 |
| 再起動＋残り7,700件 | 97.40秒 |
| 10,000件検索 | 1.23秒 |
| 再起動後fresh 10,000件のbuild | 9.72秒 |
| 全測定processのpeak working set | 53.34MiB |

Windows processをHidden/BelowNormalで起動しゲームの前面操作を避けた。上記はこの負荷下の1回測定で、768次元BLOBのcatalog/SQLite/ranking plumbingの値。実EG2推論、画像/CBZ読込み、2modality、GPU/GUI/1TBの速度・総メモリ・精度を示さない。vectorの多数のatomic commit/接続は今後も測定対象。既存の画像byte/pixel/並列数制限は維持し、新しいGPU使用率制限やidle検出は実装していない。

## 回帰確認と残件

生成2,105件で旧2,000件cache→105件追加、タグ1件変更だけ再生成、stale除外、再起動再利用。先頭300除外、256件境界を越えたcancel/checkpoint、推論中の除外変更、270作品/2modalityのglobal fusionも単体テストで確認。認証付きHTTPの既定10,000/明示2,000/不正limit、C# optional coverage互換を追加。

最終Python103 tests/C#15 checks/WinUI x64 SelfContained Release PASS（既存IL2104 2警告）。

ユーザーがゲーム中のため、製品GUI起動/Activate/クリック/キーボード入力/OS設定変更は今回行わない。GUIの新しい上限文と前回のContentDialogテーマ修正はRelease build/code reviewまで。前回appearance-03はUIA68 PASS / visual FAILのままで、今回のCPU検証によって視覚合格へ変更しない。WinUI analyzer未導入、既存SDK IL2104 2警告は抑制しない。

次は前面操作が可能なときLight/Dark dialogと新上限表示のnative確認、ゲームとGPUを共有しない時に生成素材で実EG2の段階的な負荷/メモリ測定、10,000件超の対象選択・進捗/資源設定の設計。私物は明示指定された小サンプルから。Layaは引き続き既定無効の実験APIのみ。
