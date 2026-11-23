# 英語のWDタグを日本語の意味で検索する

> **2026-10-18**：[R02-B](full-library-search.md)で全scopeの最新pendingを256作品ずつ検索。`pending_total/indexed_total/index_remaining`は全対象、`coverage_limit`は索引job互換の値で検索打切りではない。検索中の承認/版変更は再検索を案内する。

2026-10-17。ユーザー確認済みの方針：**原文の英語タグを保持し、日本語クエリとの橋渡しに交換可能なEmbeddingGemma 2を使う。** 日本語への手動翻訳を必須にしない。OCR専用処理は引き続き保留。

## 使い方

1. 詳細の「AIタグ候補」で候補を生成する。
2. 設定の「AI検索の準備」で対象フォルダ・種類・棚を選び、既存のAI索引作成を実行する。未承認タグ用の索引も同じ範囲・既存の件数上限内で作る。
3. **「タグ候補の意味（AI）」**を選び、「青髪のツインテール」など日本語で探す。英語候補は確定タグへ自動投入しない。
4. 英語のまま承認したタグは、AI索引を更新して**「名前・タグの意味（AI）」**で探す。日本語へ修正承認する機能も保持する。

「未承認タグ候補」は従来どおり文字一致の検索。新しい意味検索と切り替えて使える。新モードでは索引が足りない件数を表示する。承認・却下・別版の候補生成後は古い意味索引を使わず、明示的な更新が必要。元ファイル変更後はタグ候補の再生成も必要となる場合がある。

## APIと表示

`POST /api/library/tag-suggestions/search`へ既存の`query,kind,view,page,root_ids,shelf,model`に加えて**`semantic:true`**を指定。省略/falseは従来の文字検索。bool以外・不明fieldは400。意味検索は空クエリを拒否する（GUIは入力を促し、要求しない）。

意味検索の応答は`search_mode:'pending-proposals-semantic'`, `score_kind:'cosine'`, `pending_total,indexed_total,index_remaining,coverage_limit`。各行の`proposal_match`は元の候補タグ・tagger producer・画像/表紙の根拠・source revision/stateを保持し、`embedding_model`も返す。`semantic_score`は語句とタグ集合の類似度であり、正解率やWD分類の出力値ではない。タグ個別の一致を断定せず、対象のpendingタグ集合を表示する。

結果は作品単位、類似度降順（同点はitem ID順）、1ページ60件。意味検索では正解なしでも近い候補が返りうる。新たな拒否閾値やランキング重みは導入していない。文字一致検索の全語ANDを意味検索へ擬装しない。

モデル未導入503、推論/索引処理中409。**検索要求から候補の索引作成や全画像の再推論はしない。** 準備済み候補が0ならquery embeddingも作らず、件数と準備案内だけ返す。通常の文字検索・未承認候補の文字検索はモデルなしで使える。

## 保存・更新の契約

- 既存profile別AI DBへ`ai_proposal_vectors(item_id,batch_id,source_revision,signature,vector)`を追加。通常の確定タグ/画像vectors、catalog内の`items.tags`やproposalの承認状態と分離する。モデルprofileのkey/dimension/保存先は既存の契約を使い、他モデルのvectorを混ぜない。
- 最新batchのpendingタグだけを、原文のままtitle/相対位置と共に文章embeddingへ渡す。入力は既存4096文字上限。`pending-raw-tags:v1`、batch/source/producer、候補ID・原文・review version、現在の物理metadataをsignatureに含める。任意の翻訳・関連語・外部APIは追加しない。
- 既存の明示AI buildが、主索引の作成/再利用に加えて候補索引を準備する。同じsignatureは再利用。coverageは候補索引の不足もremainingに含める。起動・登録・候補生成・検索だけで自動推論を開始しない。
- 共有inference lockを使い、catalog lockを保持して推論しない。公開前に候補状態・source revision・現在scopeを再確認。取消/競合ではその候補vectorを公開せず、既存のper-item再開契約を維持する。全ジョブ一括atomicは保証しない。
- 承認/却下でpending集合が変われば旧vectorを除外。確定タグからpending結果へ戻したり、却下済みタグを使い続けたりしない。新しいbatch/モデル版でも履歴を上書きしない。元ファイルの再scan後に古い候補しかない場合は索引不足のまま保持し、架空の更新完了にしない。
- 登録root・種類・棚・favorite/unreviewed・tagger modelで絞り込む。空/重複/不明/解除済みの明示root指定はエラーで全体へ広げない。現在presentの全対象をbatchで調べ、保存済み同profile/signatureの候補を検索する。1回の索引job最大10,000件とは分離する。検索の登録root選択と、既存「名前・タグの意味（AI）」の保存済みAI scopeはそれぞれ既存の意味を維持する。
- root完全削除では、catalog本体/正規profile別DBの新テーブルも削除対象。他root/他モデル/元ファイルを保持する。既存の失敗時手動記録保全・profile単位transactionを継承する。

## 固定した日英タグ評価

`tests/fixtures/tag-language-v1.json`を**推論前**に固定。SHA256 `dc3d32e09b86c6b291807ae350c9bc8b7fade1e7dfcccf9562e29fda6a89ff17`。英語タグ集合16件、日本語質問18問（正解あり16/正解なし2）。色・髪型・服装・背景・制作素材・下着・キャラクターを含む人工metadata。個人の画像や購入作品は使っていない。

`python tools/evaluate_tag_language.py --output data/tag-language/v1-20261017-01`を既存offlineモデル/専用venvで一度実行。**実CUDA、所有worker終了**。raw英語とunderscoreを空白にした入力の2条件を事前固定し比較した。

| 入力 | 正解あり質問 | Hit@1 | Recall@5 | MRR | Precision@5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原文の英語タグ | 16 | 1.000 | 1.000 | 1.000 | 0.2125 |
| underscoreを空白にしたタグ | 16 | 1.000 | 1.000 | 1.000 | 0.2125 |

前処理変更は採用せず、原文を保持した。文書16件の推論時間はraw0.809秒/readable0.900秒（先行queryでモデルロード済み、起動時間や実索引全体の時間ではない）。「初音ミク」「東方の巫女」も本fixture内ではTop1に到達。これはタグが正しく付いているという前提での日英検索であり、WDが画像からそのタグを正確に付けた証拠ではない。

正解なし2問は、rawの最上位類似度が0.598310/0.630628で候補が返る。自動拒否の成功として数えない。少数の人工的に分離した集合であり、実ライブラリのタグ精度・難しいDanbooru略語・検索の正解率・NSFW全般の品質を保証しない。P0改善試行累積1/2は消費/再開せず、このP2機能の評価として記録する。

対象テスト・WinUI/実GPU統合の実行結果と失敗記録は[最新引き継ぎ](codex-handoff.md)を参照。
