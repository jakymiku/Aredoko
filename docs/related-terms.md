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
| `GET /api/items?q=…` | 展開があった時だけ`expansions:[{term,added,truncated?}]`と各item`match`を追加。展開なしの応答は従来と同じ形 |

### WinUI

- 検索ツールに「関連語」ボタン（`BtnRelatedTerms`）を追加。dialog（`RelatedTermsEditor.cs`）で見出し語・別名・関連語を「、」区切りで保存/削除。登録済みは先頭200件をComboBoxで表示。
- 既存dialogと同じ`transitions`/`dialogOpen`ガード。辞書はタグを変えないため未保存draftを破棄しない。閉じた後は**未保存draftがなく**名前・タグ検索中のときだけ再検索する。
- 文字検索の案内に追加された関連語（1語につき3表記まで＋「ほかN語」）を表示。
- C#契約は`src/Aredoko.Core/RelatedTerms.cs`とProtocolの`Expansions`/`Match`（reflectionなしDOM）。

## 検証（2026-10-13、Linux sandbox）

- Python: `tests/test_search_terms.py`（6件）、`tests/test_term_relations.py`（8件）を含む全**195 tests PASS**。生成一時ファイル・一時DBのみ。
- C#: `dotnet run --project tests/Aredoko.Core.Tests -c Release` **81 checks PASS**（Linux、.NET SDK 10.0.401をsandboxにだけ導入）。
- WinUI: `python tools/compile_check_winui.py` で **C#のみのコンパイルPASS（0 error/0 CS warning）**。XAMLはwell-formedのみ確認。
- **未検証**: Windows x64 SelfContained Release build、XAMLコンパイル、関連語dialogと案内文のnative表示/操作、狭幅・高DPI・Narrator、Windows実機での速度。AI検索（意味/表紙）には辞書を使っていない。

## 次の候補

1. Windowsで関連語dialog・案内文・「関連語の候補」表示と再検索をnative確認。
2. 「東方 巫女」評価シナリオを生成素材の固定評価セットに追加し、辞書あり/なし・AI混合とのRecall@k/MRRを比較。
3. 辞書のJSON import/export（ユーザー明示操作）と、AI混合検索で辞書展開を文字側の根拠として扱うかの設計。
