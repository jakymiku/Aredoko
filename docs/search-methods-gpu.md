# 検索方法の実GPU・文章専用profile検証

2026-10-13。GUIの「AI文章」追加後、既存の専用環境・固定EmbeddingGemma 2重みを用いてRelease WinUIとproduction HTTP/AISearchを実CUDAで検証。画像非対応時の案内を旧「AI意味検索」から「AI文章」へ修正した。モデル・ランキング・GUIコード・自動routingは今回変更しない。

## 実行条件と結果

```powershell
python tools/test_search_methods_ui.py --cuda --output data/ai-ui/search-method-cuda-new
python tools/test_search_methods_ui.py --cuda --text-only --output data/ai-ui/search-method-text-cuda-new
```

出力先は未作成の `data/ai-ui` 配下のみ。任意のprivateフォルダやprofileを入力する機能はない。`--cuda` を付けない既定のencoderは従来のCPU契約stubで、`--cuda` だけが既存GPU環境を使う。`--text-only` は `--cuda` を必須とし、同じ固定重みのmodalitiesだけをtextへ限定する。画像機能のない別モデルそのものの互換性検証ではない。

| 条件 / 証拠フォルダ | checks PASS | GUI要求 | document / image / query | peak allocated | PNG全目視 / 正常close / owned handles |
|---|---:|---:|---|---|---|
| 画像対応 / `search-method-cuda-01` | 75 | 19 | 2 / 2 / 15 | 931.8 MiB | 6 / 2 / 6全終了 |
| 文章専用 / `search-method-text-cuda-01` | 75 | 19 | 2 / 0 / 13 | 527.6 MiB | 6 / 2 / 6全終了 |

- 両runとも初回PASS・fix/retryなし。cleanup warning/errorなし。Light/Dark各1200x800の文章/dirty restoredと700x620の画像または非対応案内、計12PNGを個別に目視した。DPI96/HighContrast offを観測。検索欄・種類/方式・説明・ボタン・狭幅の案内にclipping/overlapなし。
- 生成3PNG/2rootだけを登録し、AI scopeはroot1の2件。3画像は同一の白背景/赤丸でタグも同じ。索引は文章2件と、画像対応profileのみ画像2件。これはモード接続・条件維持の検証であり、検索精度/ランキング品質の評価ではない。
- model `google/embeddinggemma-2`、revision `914f7f89142e33e77833254d9c9b90c3cef7303b`、768次元、SearchQuery/Document、auto-bf16。modalitiesをvector identityに含め、2profileのkeyと保存先を分離した。各成功encodeのdevice=cudaを検証。peak allocatedはworkerのPyTorch割当で、総VRAM/ゲーム影響の測定ではない。

## 確認した動作

- 索引開始前のCPU coverageはモデルを読み込まずに2件を確認。GUI起動時は名前・タグの3件を表示し、空queryでAI文章を選んでも新規AI要求を発行しない（Light開始時のworkerは索引作成で既にresident）。再起動時は名前・タグへ戻る。AI文章・混合・対応する画像検索の要求がsaved root scope/種類/お気に入り/page0を保ち、scope外の結果が混入しない。
- 文章専用profileの画像検索は推論前に拒否し、query encode件数を増やさない。「選択中のモデルは画像・表紙検索に対応していません。AI文章を使ってください。」を実GUIで確認。件数とページ番号は「—」、前/次ボタンはdisabled。AI文章へ戻ると検索できる。
- 未保存のモード変更をcancelすると文章mode・説明・query accessibility name・未保存タグが戻り、新規AI要求が出ない。discardしても元タグは変更されない。
- 注入した推論エラーで件数/ページ番号/前次ボタン/復旧案内を個別assertし、名前・タグ検索へ戻るとAI scope外のfavoriteも検索できる。前回CPU nativeのpagination名checkが件数/案内だけをassertしていた範囲を今回補った。
- Light/Darkそれぞれowned workerを解放後、保存済み索引を再利用する。追加encodeもworker再ロードもなくcomplete2件になる。次の検索で必要なworkerだけ再起動し、最後に全owned process-instance handlesの終了を確認。全query/sessionを通じvector digest不変。設定bytesと元PNG bytes/mtime/hashも不変。
- テスト後処理の例外を結果JSONで成功にしないよう補強。画像対応run中の補強後、文章専用runが最終ハーネスの後処理を使用した。画像対応runでも元の終了チェックで全6handlesの停止を確認している。

## 回帰確認と境界

- Python profile **10 PASS / 0.400秒**、retrieval **13 PASS / 5.003秒**。Core **35 PASS**。全Python155/scope12は前回の履歴で今回再実行なし。
- x64 SelfContained Release **PASS / 37.28秒 / errors0 / 既存IL2104 2warnings（抑制なし）**。Python syntax/CLI guards/diff検査、変更の手動レビュー済み。WinUI/XAML変更なし。専用WinUI analyzerは未導入・未実行。
- UIA操作のみ。physical keyboard・高DPI/HighContrast/読み上げ・全面editorのauditは未実施。部分captureにowned Ctrl+F tooltip/追加HWND edgeが含まれ、詳細paneは独立scroll。WindowsSandbox executable不可のためlocal owned appを使用し、OS機能/設定は変更しない。
- 私物走査・元メディア変更・モデルDL/依存導入・Laya起動なし。大規模索引/1TB/検索品質は別証拠。DB/設定/PNG/結果/重み/handles情報はignoredでcommitしない。CI manual-onlyを維持し、Draft PR #5を自動mergeしない。

## 次の3手

1. 高DPI/HighContrast/読み上げ・全面keyboardの独立確認計画を作り、OS設定を変えずに可能な確認から進める。
2. 品質判断は未観測の固定入力で別実験にする。既に観測したv1/v2や今回の同一3PNGにfusionを調整しない。Laya日本語gateも別実験、既定無効を維持。
3. 読書/Komga連携・フォルダ本groupingは既存仕様から次の小さなsliceを選ぶ。
