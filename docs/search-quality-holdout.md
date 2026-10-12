# 新規入力の根拠別評価 holdout v2（実行前固定）

2026-10-13。開始HEAD `7d7facc749103eaf7798a3d0345831fc4163fd33`。v1の観測後に別の架空30素材/日本語30問を作成し、推論の観測前にmanifestとSHA256を固定する。v1と同じquery/file名を再利用せず、text/pixelの根拠を分類。単純図形の人工データであり実私物の一般的な品質gateは定義しない。一度観測したら以後development evidenceとして扱う。

- 30実ファイル：PNG12/CBZ6/灰SVG8/無音WAV4。18種類のunique geometric covers（同一PNGの表紙再利用なし）。SVGの用途と音源の設定/本の物語はassigned metadataだけで、実内容理解ではない。
- metadata-only12問、pixels-only6問、両方一致4問、pixel優先の誤タグ2問、metadata優先の誤タグ2問、filename対照2問、no-answer2問。kind指定/なしとliteral/text/cover/combinedで220行・160AI query calls予定。相関した条件違いであり220独立問ではない。unsupported coverはmaterial/audioのqueryでは使わない。
- 正解は固定primary grade2（qrels変更なし）、各入力/モードのeligibilityに射影。Hit1/Best-grade1/Recall5/MRR/nDCG5とno-answer返却を分ける。no-answerはaccuracy平均から除く。scoreはconfidenceでなく、結果後の閾値・fusion重み変更/自動routingはしない。
- existing dedicated venv/EG2 auto-bf16/CUDA、mean-RRFの製品実装。LayaとGUIは対象外。source bytes/mtime/digest、frozen manifest、検索前後vectors、owned process-instance handlesの終了を確認する。downloads/私物/OS変更なし。

```powershell
python -m unittest discover -s tests -p test_search_holdout.py -v
python tools/evaluate_search_quality.py --suite holdout-v2 --output data/ai-ui/search-holdout-new
```

この時点ではGPU測定未実施。先にCPU契約と全18coverの目視を確認し、入力固定をcommitしてから推論する。baseline-v1は既存CLI既定のまま。詳細なSHA/測定結果は後続記録に追記。

推論前SHA256 **021e0984797727c6a79c97fb588165ce49db7c4e12fcdb1f265e02a7793b08fa**。18coverの一覧を目視し、色/数/位置/白背景・誤タグ2枚の見た目を確認。全実画像/CBZ抽象表紙はdistinct pixels。CPU契約の結果は凍結commitの後続記録で確定する。
