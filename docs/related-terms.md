# 文字検索の正規化・複数語AND・関連語辞書（2026-10-13）

製品ビジョンの「東方 巫女 → 保存済みの博麗霊夢の立ち絵」へ、AIなしの文字検索側から近づける最小実装。**ユーザーが登録した辞書だけ**を使い、知識データの同梱・外部取得・モデル利用はしない。一般的な検索精度や私物ライブラリでの合格を示すものではない。

## 文字検索（名前・タグ）の変更

- 実装: `app/search_terms.py`、`ProductionCatalog.search`（`app/production.py`）。デモ用`Catalog.search`は変更なし。
- 入力と保存済みの名前・タグを **NFKC＋casefold＋カタカナ→ひらがな** で正規化して比較。`ﾚｲﾑ`/`レイム`/`れいむ`、`ＲＥＩＭＵ`/`reimu` を同一視する。
- 空白（全角空白・タブ含む）で語に分け、**すべての語**が名前またはタグのどこかに含まれる作品を返す（AND・語順不問）。上限16語、超過は400。従来の連続部分一致で見つかった通常の検索は引き続き見つかる（NFKC合成が部分文字列境界にかかる稀な例を除く）。`%`や`_`は従来どおりワイルドカードではなく文字。
- 種類・お気に入り・未確認・棚フィルター、60件paging、除外の扱いは不変。辞書が空ならID順の並びも従来どおり。
- SQLiteにはper-searchのPython関数`aredoko_match`を登録し、1行の正規化を1回にまとめる（正規化はLRU20万件）。生成5万件・関連語300見出し（各3表記）で、Linux sandboxの単発検索は約0.15〜0.65秒。Windows実機・1TB・GUI込みの速度は未測定。

## 関連語辞書

見出し語＝ファイル名やタグに実際にある名前、別名＝表記ゆれ、関連語＝ユーザーが思い出す手がかり。

```json
{"term": "博麗霊夢", "aliases": ["霊夢", "reimu"], "related": ["東方", "巫女"]}
```

- 検索語が見出し語/別名に一致 → 見出し語と全別名をOR候補に追加。検索語が関連語に一致 → 見出し語と別名を**候補として**追加。元の語は必ず残り、フィルターは緩めない。
- 「東方 巫女」は「東方」「巫女」の両方が満たされる必要があるため、関連語`東方`だけの霧雨魔理沙（巫女なし）は出ない。博麗霊夢タグだけの作品は両方の語の展開で一致する。
- 並び: 入力した語そのものに一致した数が多い作品を先に、同数はID順。関連語だけで一致した作品は応答の`match:"related"`、一覧では「関連語の候補 ·」と表示。
- 1語の候補は最大256表記。入力語の多くに関係する見出しを優先し、超過は応答の`truncated:true`とGUIの「ほか」で開示する。
- 保存先は製品DBの`term_relations`（見出し語の正規化キーで一意、最大2000件、1項目16語・1語60文字、空白を含む語は拒否）。元ファイル・タグ・AI索引は変更しない。

### API（既存のloopback・token・Origin保護を継承）

| 要求 | 内容 |
| --- | --- |
| `GET /api/library/terms` | `{items:[{term,aliases,related}]}`（X-Aredoko-Token必須） |
| `POST /api/library/terms` | 1項目を追加/置換。検証エラーは400と理由 |
| `POST /api/library/terms/delete` | `{term}`のみ。未登録は404 |
| `GET /api/library/terms/export` | `{format:"aredoko-related-terms",version:1,entries:[…]}`（パス・IDなし） |
| `POST /api/library/terms/import` | 上記文書を**全件か0件**で統合。同じ見出し語は置換、他は保持。文書内重複（正規化後）・不正項目・2000件超過は400。この経路だけ本文16MiBまで |
| `GET /api/items?q=…` | 展開があった時だけ`expansions:[{term,added,truncated?}]`と各item`match`を追加。展開なしの応答は従来と同じ形 |

### WinUI

- 検索ツールに「関連語」ボタン（`BtnRelatedTerms`）を追加。dialog（`RelatedTermsEditor.cs`）で見出し語・別名・関連語を「、」区切りで保存/削除。登録済みは先頭200件をComboBoxで表示。
- 既存dialogと同じ`transitions`/`dialogOpen`ガード。辞書はタグを変えないため未保存draftを破棄しない。閉じた後は**未保存draftがなく**名前・タグ検索中のときだけ再検索する。
- 文字検索の案内に追加された関連語（1語につき3表記まで＋「ほかN語」）を表示。
- dialogの「ファイルに書き出す」「ファイルから読み込む」は、ユーザーがpickerで選んだ.jsonだけを読み書きする（16MiB上限、送信前にformat/versionを確認、結果「N件を読み込みました（追加・置換）」）。
- C#契約は`src/Aredoko.Core/RelatedTerms.cs`とProtocolの`Expansions`/`Match`（reflectionなしDOM）。

## 検証（2026-10-13、Linux sandbox）

- Python: `tests/test_search_terms.py`（6件）、`tests/test_term_relations.py`（10件）、`tests/test_literal_eval.py`（2件）を含む全**199 tests PASS**。生成一時ファイル・一時DBのみ。
- C#: `dotnet run --project tests/Aredoko.Core.Tests -c Release` **86 checks PASS**（Linux、.NET SDK 10.0.401をsandboxにだけ導入）。
- WinUI: `python tools/compile_check_winui.py` で **C#のみのコンパイルPASS（0 error/0 CS warning）**。XAMLはwell-formedのみ確認。
- **未検証**: Windows x64 SelfContained Release build、XAMLコンパイル、関連語dialogと案内文のnative表示/操作、狭幅・高DPI・Narrator、Windows実機での速度。AI検索（意味/表紙）には辞書を使っていない。

## 固定評価 literal-related v3（2026-10-13、Linux）

[manifest](../tests/fixtures/literal-related-v3.json)は**実行前に凍結**（commit `159c202`、SHA256 `c4fa0d94c6ebf4459bf4e9d593af759b39afd8a680404b999d0596f602385091`、LF固定）。架空の作品・キャラクター名15素材、辞書4見出し、15問（完全一致対照2/表記ゆれ3/複数語4/関連語5/正解なし1）。**辞書と質問を同じ評価者が書いたため、辞書条件は仕組みの確認であり実ライブラリの品質ではない。** 結果を見て質問・qrels・辞書・実装を変更していない。

```bash
python3 tools/evaluate_literal_search.py --output data/literal-eval/v3-result.json
```

| 群（問） | 旧LIKE MRR / Recall@5 | 新・辞書なし | 新・辞書あり |
| --- | --- | --- | --- |
| 完全一致対照（2） | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 |
| 表記ゆれ（3） | 0.333 / 0.167 | 1.000 / 0.667 | 1.000 / 1.000 |
| 複数語（4） | 0.000 / 0.000 | 1.000 / 0.750 | 1.000 / 0.750 |
| 関連語（5） | 0.000 / 0.000 | 0.400 / 0.133 | 0.800 / 0.533 |

正解なし1問はどの条件も0件で、平均から除外。テストは「旧LIKEの結果 ⊆ 新・辞書なし ⊆ 新・辞書あり」を全問で検査（点数のgateではない）。

観測された失敗（今後の改善候補。判定には別の凍結セットが必要）:

- 「星灯り 巫女」：辞書は**語の完全一致**でしか展開しないため、見出し「星灯りの社」の一部入力では博麗霊夢型の展開が起きない（キービジュアル1件のみ）。
- 「ほしあかり 立ち絵」：別名→関連語の**2段の連鎖展開**は未対応で0件。
- 「資料 セーラー服」「背景 夜 雨」：関連gradeの素材（ref/uniform、night/bg）は語が一致せず、文字検索では拾えない。AI側の役割。
- 「巫女 キャラ」：「キャラ」が汎用語でANDが厳しすぎ、立ち絵r01・キービジュアルr04が落ちる。

## 次の候補

1. Windowsで関連語dialog・案内文・「関連語の候補」表示と再検索をnative確認。
2. Windows/GPUでv3にAI text/combinedの条件を追加して文字・辞書と比較（v3 manifestはそのまま、AI結果は別出力）。
3. 観測された失敗（部分一致での辞書展開、2段展開、汎用語）への改善案を作り、**新しく凍結したholdout**で判定。AI混合検索で辞書展開を文字側の根拠として扱う設計。
