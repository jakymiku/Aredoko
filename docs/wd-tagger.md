# WD Tagger：交換可能な画像分類アダプタ

2026-10-16。P2の[候補保存/承認API](tag-suggestions.md)へ接続する初版。実装・契約テストと実モデルの導入/動作/品質は分けて記録する。**WinUI承認画面、OCR/複数ページ、動画/音声の内容解析は本件に含まれない。**

## 役割・限界

[SmilingWolfのモデルカード](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3)による、Danbooru画像で学習したgeneral/character/rating分類器。Aredokoでは一般/キャラクターの分類出力から**未承認候補**を作る。埋め込みを生成モデルと称さず、EmbeddingGemma/Layaとは別の交換可能な役割にする。写真・風景・制作素材全般や日本語漫画の関係性/物語を理解できる保証はない。

- モデルのraw英語ラベル（underscore等も保持）を候補にし、承認時に日本語へ修正することも可能。現時点で日英辞書の自動翻訳はしない。
- category0（一般）`>0.35`、category4（キャラクター）`>0.85`、最大30件。閾値は[作者のONNXデモ](https://huggingface.co/spaces/SmilingWolf/wd-tagger/blob/main/app.py)の既定値に合わせて事前設定し、生成図形の出力を見て調整しない。category9（rating）は内容タグにしない。NSFW語を理由に一般/キャラクターラベルを除く処理はない。
- 説明に分類出力値と「正解確率ではない」「画像/表紙のみ、本文・人物関係は未確認」を記録する。根拠は取得したimage/coverのpage0。関係性タグの正しさを表紙から断定しない。未判定0件を許す。
- 合成図形によるAPI動作確認は、イラスト・キャラクター・実ライブラリの精度評価ではない。精度/日本語での検索貢献は別の固定した代表素材で測る必要がある。

## 設定・入替・起動

`config/tagger-profiles/wd-swinv2-v3.json` を既定で読む。製品serverの `--tagger-profile <local-json>` でWD互換profileを変更し再起動する。localhost APIで任意path/model/候補は受け取らない。profile/assetが不正・未導入でも通常検索/手動タグは残り、タグ生成は理由付き503になる。起動/検索から自動取得しない。

固定版 `SmilingWolf/wd-swinv2-tagger-v3` revision `627aef95638667ddcaa3ac8ae625e88ea5b02f51`。画像サイズ448、10,861 labels。model.onnx **467,460,978 bytes / SHA256 e6774bff34d43bd49f75a47db4ef217dce701c9847b546523eb85ff6dbba1db1**、selected_tags.csv **308,468 bytes / SHA256 298633d94d0031d2081c0893f29c82eab7f0df00b08483ba8f29d1e979441217**。公開metadataとCSVを読み取り照合した。重みの取得・導入実行の有無は最新handoffを参照。

profileはmodel ID/revision・project内modelsサブディレクトリ・artifactサイズ/SHA256・label数/input shape・threshold・topK・timeout/thread数を厳密検査。正規化JSONのhashをproducer versionへ記録するので設定変更も別batchとなり、過去の承認/却下を消さない。model/source/前処理由来は従来通り保存する。

実際に入替えるモデルは**この初版のONNX NHWC float32 BGR 0..255とCSV形式に互換であることが必要**。任意のVLM/別モデル形式を設定だけで利用可能とは約束しない。その場合は別adapterを追加する。model directoryのescape/リンク・非固定revision・不正hash/過大/不正型を拒否する。worker起動ごとにartifact hashを確認する。

## CPU初版とプロセス/入力境界

- **CPUExecutionProviderのみ・4 threads**。ONNX Runtime GPU、CUDA/cuDNN/ドライバーの導入や変更はしない。GPU版・GPU性能を検証済みと扱わない。
- 専用`.venv-ai`のprivate子プロセスへ最大8MiB画像bytesのみ渡す。モデルはローカル固定artifactだけを開き、offline環境、画像パスや外部URLは渡さない。元画像はディスクへ展開/再エンコード保存しない。
- EXIF回転・最初のanimation frame・白背景alpha合成・正方形白余白・bicubic resize・BGR NHWC float32 0..255。[作者のONNX入力処理](https://huggingface.co/spaces/SmilingWolf/wd-tagger/blob/main/app.py)を基に、画像byte/16Mpixel制限とEXIF処理を追加。timm用0.5正規化と混同しない。
- workerは1要求で終わる。最大90秒、取消/closeを約50ms間隔で確認し、完了/失敗/取消/timeoutで**自分が起動したPopen instanceだけ**を終了・wait・pipe closeする。Windowsでは親process handleも監視。名前/PID一覧から他アプリを終了しない。
- CPU初版でも既存AISearch.inferenceを共有し、AI索引/検索/解放と競合したら409。終了後last_activityを更新。モデル未設定のAI検索とは独立してタグ分類を利用可能。catalog guardは推論中に保持しない。
- signature/label数、応答上限、profile key、有限な0..1出力を検査。異常/取消では候補を公開せず503/409、手動タグを維持。永続job queue/途中ページresume、モデル常駐、batch推論は未実装。

## 明示的な専用環境導入

通常の `python tools/setup_wd_tagger.py` は**計画表示のみ**。AGENTS.mdの明示許可を得てからだけ、既存のWindows x64 Python3.11専用環境で次を使う。

```powershell
.\.venv-ai\Scripts\python.exe tools/setup_wd_tagger.py --install-and-download --rate 6000000
```

追加固定packageはonnxruntime1.23.2、flatbuffers25.9.23、protobuf6.33.5、coloredlogs15.0.1、humanfriendly10.0、pyreadline3==3.5.4。モデル/CSV **467,769,446 bytes**、wheel計 **14,152,326 bytes**、総計 **481,921,772 bytes（約482MB）**。各wheelは公開PyPIのSHA256へ固定。既存numpy/Pillow/packaging/sympy/huggingface-hubを利用する。

共有TLS proxyで全取得を合計6,000,000 bytes/s以下（設定下限1MB/s）。高速転送/Xet bypass無効。wheel取得は`--no-deps --only-binary --require-hashes`、インストールは`--no-index --no-deps --require-hashes`。導入前後inventoryで既存packageの版が同一・追加が6packageだけを確認し、pip checkとCPU runtime importを確認する。既存packageが異なる版なら変更せず停止。専用環境以外/未知model provenanceへの上書きを拒否。既存PyTorch・システムPython・OS設定を変更しない。承認後のruntime markerは実インストール成功時だけ書く。

この手順は自動承認ではない。実行/取得/CPU推論が済んだかどうかは最新handoffの実測結果を読む。

## 検証

- `tests/test_wd_tagger.py`：profile/不正値/固定checksum・設定変更由来、threshold/topK/category・NSFW除外なし、missing runtime、共有lock/scan/close、**実子processで模擬JSON**の通信/不正/timeout/取消/終了、dry-run/no-installとmock導入の順序/保全。モデル精度ではない。
- `.venv-ai/Scripts/python.exe tools/check_wd_preprocessing.py`：生成pixelを実Pillow/numpyで処理しshape/dtype/BGR/白背景/padding/EXIF/画像上限・模擬session signature/出力を4testで確認。
- 導入許可後だけ `python tools/check_wd_runtime.py --output data/ai-ui/<fresh-name>`：作成したPNG2枚・CBZ1冊・破損PNGだけを一時DBへ登録。実ONNX CPU→候補API→再利用/承認/却下/手動タグ/元ファイル/モデル不変・所有worker終了を確認し、result.jsonに時刻/候補数を保存。**精度測定ではない**。実行していない段階でこのscriptの存在をPASSと扱わない。

Windows native GUI・実タグ品質・実ライブラリ/大規模性能は別gate。既存P0 baseline済み/改善累積1/2を変えたり、タグ分類のsmokeをP0品質改善と扱ったりしない。
