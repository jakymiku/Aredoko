# 基本版ZIP候補（2026-10-24）

## 新候補02（source f508b82）

今回の形式2バックアップ・一時AI指定解除・取得モデル検証・固定registry・取得済みroot引継ぎを含む別候補。旧01/Alpha/shortcutは上書きしない。

- 通常入口：`C:/AI/Aredoko/dist/portable-basic-20261024-02/Aredoko/Aredoko.exe`
- ZIP：`C:/AI/Aredoko/dist/portable-basic-20261024-02/Aredoko-windows-x64.zip`
- 展開756 files /657,657,654 bytes、ZIP343,869,819 bytes。
- SHA256 `dbf54d3d000f7b5f9430f48bb10711666c0b8dbbaea15efc8b12d669fbfdbe7b`。
- source `f508b82d176de208305c0c4b7441953bb14356a9`。後続の表示微修正は未収録。モデル/PyTorchなし、実catalog登録0。

新規publish/実評価receipt/純粋bootstrap self-test/同梱runtime check/全ZIP照合PASS。旧01の明示runtime領域176 filesだけをSHA/サイズ/一覧照合して再利用し、旧app/bin/configはコピーしない。Core985とPortable buildの直前結果を無用に再実行しない。

CPU：同梱Pythonの実所有backendで生成DB/PNGの基本11項目PASS、形式2/復元active/pending/一時解除の8項目PASS（native ready判定の代用ではない）。日本語/空白の再配置先でも基本11項目PASS。初回の再配置probeはZIPの親を指すfixtureミスで起動前に失敗し、正しい`再配置 test02/Aredoko`で成功。raw失敗も保持。

ユーザーの追加1試行許可で、通常EXE→生成ライブラリ→設定→AI検索の準備→配置画面→閉じる→当初許可された1回の再起動を確認。新基本候補cap **1/1**、起動総数2。4 PNGを全枚目視し、今回の通常Dark/1200px相当では重なり/切れを認めない。初回終了時はGet-Processの観測handleが保持されずExitCode=nullで誤FAIL（非ゼロではない）。GUIなしのCPU再現でnull対owned0を確認し、raw report.jsonを保全。初回の終了code自体は欠測。予定内の再起動ではhandle保持でWinUI/通常bootstrapともexit0、生成登録保持を確認。追加launch/fix-rerunなし。post-checkは専用DB integrity=ok/items1、原本SHA/mtimeと起動設定不変、lease解放/対象4PID消滅。実モデル/GPU/通常DB/旧Alphaなし。

bootstrapはOS KnownFolderをログ先に使うため、試験時のLOCALAPPDATA差替えと異なり、通常アプリのログ領域へ今回の空startupログを作成した（削除しない）。backend/DB/settingsは専用領域。次にこの保存先不一致をsourceで揃える。clean Windows/実取得/取得済みrootボタンnative/全復元の受入は未完。旧caps（環境2/2、復元3/3、取得1/2等）は維持。

証拠：ignored `data/ai-ui/portable-refresh-20261024-02/` preparation.json、各CPU report/log、native01のraw report/restart-report/post-check/4 PNG。P5/P6/P7全完了とはしない。後続の末尾区切り/idle progressバー修正はsource buildのみで、この封印ZIPを更新していない。

## 旧候補01（source875f94a）の実物と版


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
