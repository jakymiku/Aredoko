# GUIの検索方法

2026-10-13。GUIから文章ベクトルだけを選べるようにし、既存の「AI意味検索」は実際の動作に合わせて「AI混合」へ改称。4方式の索引・条件・モデルの違いを見える説明で補う。[固定生成入力の評価](search-quality-holdout.md)を背景にした明示的な操作で、今回モデル・ランキング・自動routingは変更しない。

| 表示 | 内部index / AutomationId | API | 探す根拠 |
|---|---|---|---|
| 名前・タグ | 0 / ModeLiteral | 通常のitems検索 | 名前・タグに含まれる文字 |
| AI混合 | 1 / ModeSemantic | AI source=all | 利用可能な名前・タグと画像・表紙の順位を混合 |
| AI画像・表紙 | 2 / ModeVisual | AI source=cover | 色・形・見た目を文章で指定して画像・表紙を検索 |
| AI文章 | 3 / ModeText | AI source=text | 名前・タグの意味を文章で指定して検索 |

- AI文章は本の本文・PDF本文・OCR・音声内容を読み取らない。名前/パス/タグ由来の索引を利用する。タグ更新後はAI索引も更新する。AI画像・表紙も抽出可能な画像/表紙の索引が必要。モデルprofileのmodalitiesと検索方式は別の設定で、text-only profileに画像機能を追加する選択ではない。
- 初期選択は名前・タグ。空/空白queryは既存の通常一覧取得経路を維持。選択はセッション内だけで再起動時は初期選択に戻る。AI選択だけでモデルを読み込まない。
- saved scope（登録root/kind/shelf）と一覧側kind/view/pageをそのまま要求に含める。混合・画像の既存index/AutomationIdとAPI sourceを維持し、文章を末尾へ追加。既存scope確認/上限・保存・stale response規約は変えない。
- モード変更に未保存確認を適用する。取り消したらquery/kind/modeだけでなく説明・placeholder・検索欄のaccessibility nameも戻る。説明更新は初期化とpopulating中のrollbackでも行い、検索のdebounceは既存のready/非populating時だけ。
- 標準ComboBoxに「種類」「検索方法」のvisible Header、説明はThemeResourceを使うCaption TextBlockで折返す。狭幅では従来のtoolbarが次行へ移り、説明はその下。危険なmanaged ItemsSourceや新依存は追加しない。

## 検証

```powershell
dotnet run --project tests/Aredoko.Core.Tests -c Release
dotnet build src/Aredoko.WinUI -c Release -p:Platform=x64 -p:SelfContained=true --no-restore
python -m unittest discover -s tests -p test_ai_scope.py -v
python -m unittest discover -s tests -p test_ai_search.py -v
python tools/test_search_methods_ui.py --output data/ai-ui/search-method-native-new
```

- Core **35 checks PASS**（既存29＋route/modality4・filter/page/owned scope・invalid mode拒否）。scope Python **12 PASS / 14.098秒**、retrieval Python **13 PASS / 4.625秒**。全155は前回の履歴で今回再実行なし。syntax/CLI/diff検査PASS。
- 最終x64 SelfContained **Release PASS / 30.23秒 / errors0 / 既存IL2104 2warnings（抑制なし）**。初回もPASS / 36.23秒。WinUI手動レビュー済み、専用analyzer未導入・未実行。今のJapanese-only strings/MVVM移行/AOTは今回の範囲外。
- native03 **65 checks PASS / 6 PNG全目視 / scoped visual PASS / 正常close2 / cleanup warnings0**。local・生成PNG3枚/登録2roots/隔離catalog/settings・実Production HTTP/AISearch/vector store＋CPU契約stub encoder。実モデル/GPU・品質評価ではない。WindowsSandbox executableは利用不可、stale/no-running guestも確認。OS機能は変更しない。
- Light/Dark各1200x800文章・700x620画像とdirty restored、観測DPI96/HighContrast off。query/source/種類/favorites/page0/保存済みroot scopeを実要求20件で記録。選択rootの結果のみ、empty queryはAI要求なし、再起動時literal、設定byte不変。dirty cancel時にmode/hint/query accessibility nameと未保存タグが戻り、AI要求なし。discard後に元タグ不変。注入encoder error時に件数「—」/案内を確認し、文字検索でAI scope外のfavoriteにも復帰。nativeのerror-check名はpaginationだが、そのassertion範囲は件数と案内で、ページ番号/buttonsを別途assertしてはいない。
- native01 **FAIL / 14 checks / 2 PNG全目視 / 正常close1**：CmbKind UIA peer失効。refresh追加後02 **FAIL / 14 checks / 2 PNG全目視 / 正常close1**：「画像」のCLI substring指定が結果ラベルにも一致。03はowned Popupを再inspectし、AutomationIdまたはexact ListItemから一意の観測selectorを選んで成功。2 fix-and-rerun cycles内。失敗履歴を保持し、元PNG bytes/mtime/hashは各回不変。
- 全画像にはowned Ctrl+F tooltip/追加HWND edgeを含むものがある。検索欄・mode・説明・ボタンにclipping/overlapなしを目視。詳細paneは独立scrollで下部editor全体の可視性はこのsliceのauditではない。
- 私物走査・モデルDL/依存導入・OS変更・Laya起動なし。native keyboardはUIAのみでphysical keys・全面keyboard/読み上げ/高DPI/HighContrastは未検証。GPU品質は前回v2と別証拠として扱う。

## 次の3手

1. この検索方式で実CUDAの小さな生成fixtureをnative再確認し、text-only profileの非対応cover案内を確認する。モデル変更や既定routingはしない。
2. 高DPI/Contrast/読み上げ・全面keyboardを独立した確認で進める。OS設定の勝手な変更はしない。
3. 次の品質判断用の新規固定入力とLaya日本語gateを別実験として設計。Laya既定無効、reader/Komga/フォルダ本は後続slice。
