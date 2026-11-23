# R06：既存EmbeddingGemma 2の音声直接入力・予備評価

2026-10-26。通常の画像/本文profileとDBは変更しない。R06方式選定とM2の完了ではなく、次の試験実装に向けた限定証拠。

## 条件と結果

- 固定版`google/embeddinggemma-2` / `914f7f89142e33e77833254d9c9b90c3cef7303b`、既存AI Python、CUDA/bfloat16、実験用audio ON・vision OFF。新規取得0。個別のGPU許可後、1バッチのみ。
- Windows既存Haruka Desktopのファイル出力だけで日本語4発話を合成。さらにノイズ/旋律/速いリズム/旋律の音量違いを生成し計8本、各約3–4秒。全ファイル名は`001.wav`等の数字だけ。モデルへは検証済みPCM波形と検索queryのみ渡し、ファイル名/正解文/ラベルを音声入力に含めない。
- 検証済み`PreviewReader.audio_pcm_window`→16kHz mono f32le→実モデルの768D出力→float64 cosineで順位付け。同点はID順。今回の生成library以外のDB/索引へ保存しない。

| 軸 | 問数 | Top1 | 平均Recall@3 | MRR |
| --- | ---: | ---: | ---: | ---: |
| 日本語発話の日本語意味query | 4 | 4/4 | 100% | 1.0 |
| 同じ日本語発話の英語query | 4 | 4/4 | 100% | 1.0 |
| 合成ノイズ/旋律/リズム | 3 | 3/3 | 100% | 1.0 |
| 音量違いの同旋律を相互に類似検索 | 2 | 2/2 | 100% | 1.0 |

日本語query例は「赤い傘を教室に忘れた話」「水曜日の午後三時からの会議」「図書館で青い本を探す話」「温かいコーヒーとチョコレートの注文」。正解は音声内容から取得した。文字起こしを検索へ注入していない。旋律queryは音量違いの2本を正解集合とし、Recall@3は上位3内の正解数/正解集合数。類似は起点自身を除外。

最初の音声encode1.75秒、後続0.109–0.219秒（単回・約3–4秒の生成音声）。PyTorch peak allocated1,177,221,632bytes / reserved1,201,668,096bytes。driver/nativeを含む総VRAM、長時間処理、通常UIの速度保証ではない。元生成ファイルSHA不変、所有process exit0。

## 再現と残件

生成：`tools/create_audio_eval_fixture.py`（既存Pythonのpywin32/SAPI、スピーカー/マイク/OS設定変更なし）。実評価：`tools/evaluate_audio_input.py --gpu`（事前回答が必要）。証拠は`data/ai-ui/snapshot-review-20261026/audio-quality-fixture02/manifest.json` と `audio-quality-gpu01/report.json`（Git対象外）。

初回fixture01はWindows PowerShellのfile実行ポリシーで停止。ポリシー/OS設定を変更せず、既存PythonのCOM APIでファイルを生成した。初回失敗ログを保持し、GPU評価を無変更反復していない。

実録音・雑音混じりの会話・複数話者・実楽器/曲・長時間区間・無音誤検出・ASR方式との比較は未評価。同じ4発話の2言語queryを8本の独立発話の結果と数えない。候補A（既存モデルの直接音声入力）の試験実装へ進める根拠にはなるが、専用ASR不要/全音声理解/全媒体完成の証明ではない。

次の小単位は、明示的なtext/audio profileとbounded PCM worker契約。現行text/cover profile・legacy namespaceを保全し、直接音声768Dの契約を分離する。512Dの既存音響保存へ強制変換しない。自動索引/検索UIの接続は後続の独立単位とする。
