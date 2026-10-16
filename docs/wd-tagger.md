# WD Tagger：交換可能な画像分類アダプタ

2026-10-16。P2の[候補保存/承認API](tag-suggestions.md)へ接続する初版。実装・契約テストと実モデルの導入/動作/品質は分けて記録する。**WinUI承認画面・未承認候補検索も接続/Windows検証済み。OCR/複数ページのタグ解析、動画/音声のタグ解析は未実装。**

## 導入と実CPU確認済み（2026-10-16）

ユーザーの明示回答「導入してCPU検証まで進めてよい」を受け、専用venv/modelsへ固定版を導入した。**モデル取得/実CPU動作gateは完了**。WinUI承認画面も後続で実装・検証済み。代表素材での実タグ精度は未評価、OCR専用処理は2026-10-17のユーザー方針で保留。

- 上限6,000,000 B/sの共有TLS proxyでsetupを1回実行。実TLS受信量 **482,628,627 bytes / 139.813秒**（全体平均約3.45MB/s、上限設定値と平均を区別）。model/CSVサイズ・SHA256検証、hash固定wheel、offline/no-deps install、pip check/CPU runtime import成功。
- 導入前後inventoryの **既存46packageすべて同じ版**（torch2.9.1+cu128等を保持）、追加は許可済み6packageだけ。モデル/実測ログはignored領域で、Gitへ重みやDBを保存していない。
- `check_wd_runtime.py --output data/ai-ui/wd-runtime-cpu-20261016-approved-01`：**35 checks PASS**。実ONNX CPUによるPNG2枚/CBZ1冊の候補作成、承認/修正/却下、重複承認409、手動タグとの和集合、同一batch再利用（新workerなし）、物理revisionと棚/お気に入り保持、破損PNGの503/部分候補なし。source bytes/mtime・model hash/mtime不変、起動worker **4/4終了・pipe close**。

| 固定した生成fixture | 候補数 | HTTP一回の時間（worker起動・hash・load・推論込み） |
|---|---:|---:|
| red-shapes.png | 6 | 2265.573ms |
| blue-shapes.png | 6 | 2181.779ms |
| fiction.cbz先頭画像 | 5 | 2119.390ms |

profile key `921f5736f7fccb4580cbb5e0d5734781827487cb2aea9d3e7d9318332c914ab2`。図形の出力例にはred_background/blue_background/green_backgroundがある一方、comic/solo等も混ざった。**これは精度指標ではなくruntime/API確認。図形での過信を避け、未承認候補のまま保持する。** キャラクター・日本語・写真・実ライブラリ・大規模精度/性能は未評価。threshold/topKは結果を見て変更していない。

## GUIでの使い方・現在の動作

通常起動のbackendは既定のWD profileを読み、導入済みの固定モデル/専用venvを使う。アイテムを選択→詳細の**「AIタグ候補」→「候補を生成」**で明示実行する。起動やフォルダ登録だけで全画像へ自動タグ付けする機能ではない。

候補のraw英語タグと根拠を確認し、必要なら「承認するタグ」を日本語へ修正して**「承認して保存」**する。確定後は「名前・タグ」検索、未承認の英語候補は専用の「未承認タグ候補」モードで探す。自動翻訳は未実装。表紙1枚から本全体の人物関係や物語を判定したとは扱わない。

## 実モデルのWinUI接続確認（2026-10-17）

`test_tag_review_ui.py --wd-runtime-only --output data/ai-ui/wd-native-cpu-20261017-01`：**48 checks PASS / Light・Dark PNG8枚全目視 / 正常終了2 / WD worker2/2終了**。既存Releaseと許可済みCPUモデルで、生成画像/CBZからの候補生成、日本語へ修正承認して通常検索、raw英語pending候補の分離検索、由来/再利用/手動タグ/棚/お気に入り/モデル・元データ不変を確認した。実装`ad426ff`。再現には導入済みローカルモデルと空きport8769が必要で、このscriptからダウンロードはしない。

図形2件の実接続smokeであり実素材のタグ精度/日本語自動翻訳の成績ではない。全文/複数ページのタグ付けにも拡大していない。詳細は[最新引き継ぎ](codex-handoff.md)を参照。

## 役割・限界

[SmilingWolfのモデルカード](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3)による、Danbooru画像で学習したgeneral/character/rating分類器。Aredokoでは一般/キャラクターの分類出力から**未承認候補**を作る。埋め込みを生成モデルと称さず、EmbeddingGemma/Layaとは別の交換可能な役割にする。写真・風景・制作素材全般や日本語漫画の関係性/物語を理解できる保証はない。

- モデルのraw英語ラベル（underscore等も保持）を候補にし、承認時に日本語へ修正することも可能。現時点で日英辞書の自動翻訳はしない。
- category0（一般）`>0.35`、category4（キャラクター）`>0.85`、最大30件。閾値は[作者のONNXデモ](https://huggingface.co/spaces/SmilingWolf/wd-tagger/blob/main/app.py)の既定値に合わせて事前設定し、生成図形の出力を見て調整しない。category9（rating）は内容タグにしない。NSFW語を理由に一般/キャラクターラベルを除く処理はない。
- 説明に分類出力値と「正解確率ではない」「画像/表紙のみ、本文・人物関係は未確認」を記録する。根拠は取得したimage/coverのpage0。関係性タグの正しさを表紙から断定しない。未判定0件を許す。
- 合成図形によるAPI動作確認は、イラスト・キャラクター・実ライブラリの精度評価ではない。精度/日本語での検索貢献は別の固定した代表素材で測る必要がある。

## ライセンス（2026-10-16 配布元を確認）

- 今回の固定revisionのWD SwinV2 Tagger v3は、[作者のREADME metadata](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/blob/627aef95638667ddcaa3ac8ae625e88ea5b02f51/README.md)で **Apache License 2.0** と表示されている。
- [Apache 2.0本文](https://www.apache.org/licenses/LICENSE-2.0)は無償の利用・改変・再配布（商用を含む）を許諾し、このライセンスによりAredoko全体のソース公開を求めるものではない。再配布時はlicense copy、関係する権利表示の保持、変更箇所の明示、NOTICEがある場合の引継ぎ等の条件に従う。
- 今回の推論runtime **ONNX Runtime 1.23.2はMIT**（[固定版LICENSE](https://github.com/microsoft/onnxruntime/blob/v1.23.2/LICENSE)）。再配布時には著作権/許諾表示を保持する。追加packageやruntime内third-party noticesは各配布物を別途保持する。
- 今回はユーザーPC内の専用環境での利用・動作確認。配布用インストーラーや全依存のlicense/NOTICE同梱を完成したという報告ではない。配布工程でモデルとruntime/依存それぞれのlicense表示を整備する。

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
