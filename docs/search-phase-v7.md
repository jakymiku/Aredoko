# P0 新固定baseline v7（測定前の凍結）

開始HEAD `25034815e45cd3de80866c0056a6e5c2bffa9cfc`。P1と登録フォルダハブの実装・Windows検証済みを引き継ぐ。P0新baseline未実施、改善試行累積0/2。

固定入力：`tests/fixtures/search-phase-v7.json`、SHA256 **8212da5d4c146c8ac1086e04c95a3514d3564a1171cb3f9fe66498389f7e499b**。24素材（PNG12/CBZ4/SVG4/無音WAV4）、24query（metadata8/pixels6/agreement2/label conflict4/架空alias2/no-answer2）、root A/B。旧v1/v2/v6とquery/filename非重複。今回初めて作る入力を、順位観測前にこのcommitで凍結する。作成者と評価者は同じで、独立の実ライブラリ精度ではない。

literal（辞書なし）/related（明示架空辞書）/text/cover/combinedを同じroot選択・種類条件で測定予定。cover非対応種類やrootで正解が除かれる条件は、真の正解なしqueryと区別して記録する。Top1/Recall@5/MRR/Precision@5、no-answer挙動、検索時間、source・vector不変と所有process終了を記録。UIの到達手数・実ライブラリ精度は今回未測定。

既存ローカル専用環境と固定重みのみ使用し、生成素材だけに限定。追加install/download/私物scan/CIなし。入力を観測後に変更しない。評価基盤の実装と測定後に、根拠のある小改善を0〜2件に限定してP0を閉じ、P2へ進める。
