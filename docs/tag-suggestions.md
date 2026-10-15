# P2：由来付きタグ候補・承認APIの最初の縦切り

2026-10-16。[製品ビジョン](product-vision.md)・[開発優先順位](development-priorities.md)に沿うバックエンドの基盤。**P2全体の完成ではない。実タグ生成モデル、WinUI承認画面、OCR/複数ページ解析、候補を対象にしたライブラリ全体の検索は未接続。** EmbeddingGemmaの既存埋め込み処理をタグ生成モデルとして扱わず、固定の偽アダプタによる契約テストと実モデルの品質を区別する。

## 保存と承認

- 通常起動時、既存DBに `tag_proposal_batches` / `tag_proposals` / 参照用indexを追加する非破壊の `CREATE IF NOT EXISTS`。元ファイルや既存 `items` の値を移行・書換しない。
- batchにitem、物理source revision、adapter/version、model/model revision、前処理version、画像/表紙の区別、根拠page（0始まり）、作成時刻を保存。proposalに元の候補タグ、説明、pending/accepted/rejected、修正確定タグ、review version、日時を保存する。モデルスコアや正解確率はこのsliceでは作らない。
- 候補は `items.tags` に自動投入しない。**承認時だけ、現在保存されているタグとの和集合を同一SQLite transactionで保存**。修正承認も可。却下は整理情報を変更しない。タグは既存同様最大30個/60文字。上限超過・stale・競合・末尾のsource再確認失敗はタグと承認を両方rollback。
- 元の候補と修正内容を別に保持。既存の棚・お気に入り・確認済み・読書位置を変更しない。通常の文字検索が使うのは保存済みの確定タグで、未承認/却下候補は混ぜない。
- source revisionはreader同様のroot/相対位置・file identity・size/mtime/ctimeによる**メタデータtokenであり全内容のhashではない**。手動タグ/タイトルとは独立。タグを1個承認しても残り候補をstaleにしない。元ファイル変更後は再scan/再解析が必要。source不在・root解除/除外中は候補の操作不可、DB履歴は保持する。再登録後も履歴を確認できる。
- 同じitem/source/producerは一つのbatchに制約。生成再実行は既存batchを返し、承認/却下を消さない。「未判定」は候補0件の完了batch。source/producer版が変われば新batch、過去の決定は履歴として残る。別モデルの新提案を自動的に過去の却下へ同一視する仕組みは未実装。

## ローカルアダプタ契約

`TagSuggestions(catalog, adapter=None)` が入口。公開APIから任意path/model/proposalを注入できない。現在の製品serverは `adapter=None`、生成要求に503と未接続理由を返す。検索・手動タグは利用可能。

将来の信頼されたローカルadapterは、固定の `TaggerInfo(adapter, version, model, model_revision, preprocessing)` と `suggest(payload, cancelled)` を提供する。payloadは検査済みの最大8MiB画像またはCBZ/ZIPの自然順先頭画像のbytes/mime/source tokenだけ。パスは渡さない。現在は根拠page=0のみ、最大30個の `TagProposal(tag, explanation, page=0)` を返す。未取得のページを根拠にしない。人物関係/物語タグを表紙から断定する設計ではない。

登録/在席/除外/reparse・リンク/サイズ・handle identity/変更確認は既存 `PreviewReader` を再利用。ZIPは既存の512MiB archive、4MiB directory、8MiB画像、圧縮比/暗号化等の制限を継承する。画像/表紙以外（動画・音声・PDF・論理フォルダ本）はこのsliceの入力対象外。

サービスは一度に一生成、推論中にcatalog guardを握らず手動保存を妨げない。32桁hex request IDで取消。adapterは取消関数を定期確認する必要があり、**協調取消であってworkerの強制停止/時間制限を実装したものではない**。完了時に全候補を一括検証してから原子的に公開する。失敗・取消・source/adapter変更時は部分batchを保存せず、再実行可能。完了後の取消はfalse。クラッシュ時の途中進捗や永続job queueはまだない。

実adapterを接続する際は、既存AI索引/検索とのGPU排他、timeout、worker解放、profile設定/切替、モデル仕様・入力前処理と小規模な固定品質評価が別途必要。新モデル/依存を黙って取得しない。

## API（loopback・session token）

| Method / route | 入力 / 動作 |
|---|---|
| `GET /api/library/tag-suggestions/{item_id}` | 履歴/由来/状態と現在source revision、各batchのstale、生成available/reason。`limit`既定10・最大20、`before`で古いbatchを取得、`next_before`を返す。item固有の履歴であり全体検索ではない。 |
| `POST /api/library/tag-suggestions/generate` | `{item_id, request_id}`。設定済みadapterだけを実行、または既存同一batchを再利用。未接続503。 |
| `POST /api/library/tag-suggestions/cancel` | `{request_id}`。対応する実行中要求だけを取消。 |
| `POST /api/library/tag-suggestions/review` | `{item_id, proposal_id, version, decision}`。decisionは`accept`/`reject`、acceptだけ任意`tag`で修正。pending/version一致・現在source一致が必須。再承認/古い状態409、他itemのproposal404。 |

すべて正のInt64 ID（bool不可）、余分/重複queryや余分body keyを拒否。POSTは既存のHost/Origin/tokenと32KiB body上限を継承。GETも正しいHost/tokenが必要。busy/scan/変更競合409、source不在404、不正入力400、adapter障害503。未設定/モデル障害を候補成功として返さない。

## 検証境界

`tests/test_tag_suggestions.py`：生成PNG/自然順2ページCBZ・一時DB・偽adapterだけ。由来/未承認非混入、修正承認/却下、manual edit後の承認、再起動/版変更/再解析/未判定、source変更/差替え/rollback、30タグ上限/重複、cancel/再試行/並行manual edit、2 service同時生成、入力上限、scan/除外/root解除復元、履歴pagination/ID、HTTP認証/厳密引数/409/503を確認。

これは**保存・承認・境界の契約検証**。実AIタグ精度・GPU推論・OCR・WinUI操作・実ライブラリ・大規模性能の検証ではない。C#は既存ErrorText辞書への日本語エラー追加のみ。XAML/GUI構造は未変更。Core契約テストとWindows x64 SelfContained Release buildを実施、native GUI操作/WinUIAnalyzerは今回未実行（既存projectにanalyzer参照なし、新依存は追加しない）。具体的な最終テスト結果と失敗履歴は[最新handoff](codex-handoff.md)参照。

次は (1)既存ローカル資産/モデルの仕様確認と実adapterの小さな接続、(2)WinUIの候補/根拠表示・修正承認/却下・draft保持とWindows実機確認、(3)候補を明示選択した検索とOCR/複数ページ根拠への拡張。P0 baseline済み・改善累積1/2は維持する。
