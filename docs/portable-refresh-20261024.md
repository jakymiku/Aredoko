# 最新基本版ZIP候補（2026-10-24）

## 実物と版

ソース `875f94a6746e8b1631b854d1aca5678f8406a2a1` / 既存開発ブランチ・Draft PR #5。

- `C:/AI/Aredoko/dist/portable-basic-20261024-01/Aredoko/Aredoko.exe`：通常の入口。今回自動起動していない。
- `C:/AI/Aredoko/dist/portable-basic-20261024-01/Aredoko-windows-x64.zip`：新規作成・全ZIP内容照合済み。Gitには大容量ZIPを登録・アップロードしていない。
- 展開後737ファイル / 657,566,956 bytes。ZIP343,811,217 bytes。
- ZIP SHA256 `67c555b166c0aa14f2d936d36f97b1a6ae4b34c8c4e98413ecd0f76b6654a11b`。
- 基本Python・動画ツール・自己完結WinUI・起動画面・最新backendを含む。PyTorch/モデルは含まない。AIカタログ未登録なので自動取得は公開準備中。

同梱文書は準備時snapshot。後続の引き継ぎが加わるため、Git最新HEADと実物のソースIDを混同しない。旧Alpha、ショートカット、03候補、通常DB・元メディアは更新していない。

## 準備と確認

最新Portable publish、実評価propertyに基づくreceipt、Windows標準compilerでのbootstrap build、画面を作らない --self-test、実同梱Pythonの --check、ZIP全entryの照合が成功。既知WUI1001×3/SDK IL2104×2。直前のCore974 PASSを再実行していない。

実同梱Pythonで専用DB・生成PNGのみを使用する `tools/check_basic_release.py` が11項目PASS：torchなし、独立instance、AI/取得未導入の診断、両job idle、登録scan、ファイル名検索、PNG preview、原本SHA/mtime保持、所有EOF exit0、SQLite integrity=ok。PID17572終了0。

ZIPを新しい `data/ai-ui/portable-refresh-20261024/再配置 test01` へ展開（元のZIP/候補は保持）。空白・日本語を含む配置からも別専用DBで同じ11項目PASS、PID43296終了0。これは異なる配置条件であり、22種類の別テストとは合算しない。

初回、旧03候補全体のverify_releaseは未登録のbackend __pycache__で失敗。旧ファイルを消したり全体検査を弱めたりせず、再利用する明示runtime/python・runtime/media領域176ファイルの全SHA・サイズ・正確な一覧だけを元manifestと照合した。旧app/bin/configは再利用していない。旧03全体の正常性を再認定した結果ではない。

## 証拠と限界

ignored `data/ai-ui/portable-refresh-20261024/` の prepare.py、publish/bootstrap/bundled-runtime-check logs、properties、runtime-source-verification.json、preparation.json、backend01/report.json、relocated-backend01/report.json。新規書込みは候補と生成データのみ。

新ZIPからのWinUI/起動画面のGUI・通常DB再起動・全GPU/モデル推論・開発環境のないWindows受入は未実施。今回のCPU結果をLD6/P6/完成版の合格とはしない。取得画面の先行native証拠は[別の専用候補](ai-acquisition.md)であり、新ZIPのGUI受入ではない。旧capsと全raw失敗を維持する。

次は実際に配布するruntime pack/全依存NOTICE/固定公開先を決め、builderの実物catalogとvalidatorを製品へ登録する。推測URLや架空hashで有効化しない。実取得/GPU/新GUIが必要なら具体範囲を提示して許可を得る。P5の復元picker/Start/所有bootstrap完全受入、P3性能/高DPI等の残件も保持する。
