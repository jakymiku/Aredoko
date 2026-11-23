# 固定評価v6と語ごとの検索根拠（2026-10-14 夜）

検索が正解を上位に出すことと、余分な候補を出さないことを分けて測る。今回の本体変更は語別の根拠APIの追加のみで、検索順位・関連語展開・部分一致fallbackの方式は変更していない。

## 評価セットと読み方

`tests/fixtures/literal-related-v6.json`は**初回の検索実行前**にcommitして固定した。SHA256：`6ac38d61d0703eb9e3e5a69f9f2de78e198574313f9ebd29d9ebf73d1a30d9b3`。16件の架空metadata/placeholderと24query。kindはimage/book/audio/video/materialを含む。検索は内容をdecodeせず、元ファイル/モデル/私物データにアクセスしない。

辞書・query・正解候補は同じ作者が作成したため、**開発寄りの小さな検証**であり、独立した実ライブラリの精度ではない。旧v3/v4/v5は変更していない。v6を見て順位や展開を調整しておらず、今後の変更を同じv6だけで最適化しない。

- Recall@5/MRR：正解候補を見つけたか。正解なしqueryは従来どおり対象外。
- Precision@5：実際に返された先頭最大5件のうち正解候補の割合。5件未満を空slotで埋めない。空結果＋正解ありは0。queryごとの値を平均する。
- `correct_empty_rate`：正解候補がないqueryに空結果を返した割合。部分一致・関連語の参考候補も、ここでは返答ありとして数える。これは現在のfallback方針を測るもので、参考候補を返す動作を直ちに不具合と断定しない。

## 実測（現在の関連語辞書あり）

| グループ | query数 | Recall@5 | MRR | Precision@5 | 正解なしで空結果 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 完全一致control | 4 | 1.000 | 1.000 | 1.000 | — |
| 表記ゆれ | 2 | 1.000 | 1.000 | 0.750 | — |
| 複数語 | 4 | 1.000 | 1.000 | 1.000 | — |
| 関連語 | 4 | 1.000 | 1.000 | 0.875 | — |
| 過剰展開control | 3 | 1.000 | 1.000 | 0.833 | — |
| 部分一致control | 2 | 1.000 | 1.000 | 1.000 | — |
| 正解なし | 5 | — | — | — | 3/5 = 0.600 |

Recall/MRRが高くても余分な候補はある。「灰谷カノ」に「カノープス」が候補として混ざる例を保持した。正解なしの「潮騒 魔王」は1件、「雨 砂漠」は2件のpartial候補を返した。「水中都市」「幼なじみ（video限定）」「[」は空結果だった。

同じqueryで正規化検索＋辞書なしの空結果率は4/5、旧LIKE参考も4/5。ただし旧LIKEの失敗はJSON構文「[」の16件ヒット、現在の辞書なしの失敗は「雨 砂漠」のpartialであり、同じ数字が同じ挙動を示すわけではない。

## 検索根拠API

通常`GET /api/items?q=...`の各itemに、queryがある時だけ`search_evidence`を追加する。

```json
{
 "search_evidence": {
  "direct_words": [],
  "related_words": ["東方"],
  "missing_words": ["未知"]
 }
}
```

これは「東方 未知」、タグ「博麗霊夢」、辞書「東方→博麗霊夢」のpartial例。`direct_words`は入力語が名前/実タグに直接含まれた場合、`related_words`は辞書で展開した表記でのみ一致、`missing_words`はどちらでも未一致。語はNFKC/case/kana正規化・重複除去済みで、3配列の合計はqueryの最大16語。名前/タグのどちらで一致したかや、根拠の実表記を列挙する詳細機能はまだない。

既存の`match`/`partial`/`expansions`・filter・root・paging・順位は維持。説明は返す行だけに付加し、タグ・設定・DB schema・model/vectorは変更しない。queryなしの一覧/個別GETには付加せず、推定精度やconfidenceとして扱わない。

### WinUI表示とCore解析（2026-10-14 Windows続行）

- `src/Aredoko.Core/Protocol.cs`に反射不要の`SearchEvidence`（最大16語・1語最大64文字、サロゲートペア境界保護）と`DescribeEvidence`（各区分4語＋「ほかN語」）を追加。
- `src/Aredoko.WinUI/MainPage.xaml.cs`の一覧/グリッド行で、全語直接一致（`AllDirect == true`）では余分な行を出さず、関連語一致または欠落語がある場合（`AllDirect == false`）に`SearchEvidence<id>`として「入力語で一致：… / 関連語で一致：… / 一致なし：…」を表示。

## 検証と再現

```
python tools/evaluate_literal_search.py --manifest v6 --output data/literal-eval/v6-current.json
NO_PROXY=127.0.0.1,localhost python -m unittest discover -s tests -p test_search_evidence.py -v
dotnet run --project tests/Aredoko.Core.Tests -c Release
python tools/test_image_viewer_ui.py --evidence-only --output data/ai-ui/search-evidence-01
```

- Windows実機：全Python **263 PASS / 142.293秒 / skip0**、Core **157 PASS**、x64 SelfContained Release **PASS**、`tools/compile_check_winui.py` **exit 0**。
- `search-evidence-01`：**PASS 30 checks / keys 0 / skip 0 / PNG 6全目視 / graceful close 2 / cleanup warnings 0**。Light/Dark・1200×820と700×620狭幅で、直接一致のみでの非表示、`入力語で一致：東方 / 関連語で一致：巫女`、`関連語で一致：東方、巫女`、partial時の`一致なし：未知`、未保存draftの検索キャンセル保持、`魔法"少女`・`C:\textures`タグ検索、`[`の0件を確認。
- Linux（前段）：根拠6 PASS/0.543秒、文字検索10 PASS/0.689秒（生成50,001行2語0.219秒）、固定評価3 PASS/0.132秒、共有metrics5 PASS/0.157秒。**全Python263 PASS/28.142秒/skip0**。API追加前/後のv6全72行・指標・順位は完全一致。

実model/GPU/私物検索品質は未検証。次は別の固定入力やユーザーが明示した小サンプルで過剰展開を測り、辞書・fallbackの変更は別工程で比較する。
