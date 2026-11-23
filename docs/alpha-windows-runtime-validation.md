# ALPHA-0 Windowsランタイム受入（2026-10-20）

> **最新2026-10-21**：[MSIX正式起動・実機結果と再開条件](alpha-packaged-activation.md)。許可済み証明書trustとAlpha1.0.0.1通常installは完了し、元Development登録を保持して併存。363 installed payload全件照合PASS。実shortcut→新規所有GUI/backend→生成画像検索・タグ保存まで確認したが、native flowは待機/スキャン/保存captionのテスト不備で**3/3上限**。誤った起動失敗通知とテスト期待値をsourceで修正し、追加GUIなしでCPU55 PASS、停止後DB保存/整合・source不変・封印済み02全24,325ファイル一致を確認。02は修正前artifactのまま。**R13 DOING / ALPHA-0未完 / R14 PARTIAL**。次はCPUのみ起動待ち/配布整備、追加GUIは新たな明示許可後に残るargv/閲覧/正常終了・再起動/clean Windows更新削除受入。過去のcaps/全機能/guardを維持し、ALPHA後の実音声/音楽→WinUI改善へ戻る。

開始HEAD `b27410b`。Workの7コミット（`ab81b3c..b27410b`）をfetch/fast-forwardで取り込み、既存コードと引き継ぎを保持した。**R13 DOING / ALPHA-0未完 / R14 PARTIAL**。以下は同梱ランタイムとGUI部品の検証で、完成したダブルクリック版ではない。

## 今回の実装

- `tools/prepare_python_runtime.py`：明示した既存CPython本体・明示したsite-packagesだけから、新規の独立runtimeを作る。新規取得・インストーラー・元環境の変更・モデルコピーなし。stdlib ZIP、DLLs、Pillow ABI/メタデータ/ライセンス、必要時の全AI依存を保持。venv本体の流用、入出力の包含、編集可能package、リンクや既存出力を拒否。`--check` は出力を作らない。cache/debug PDBだけを省き、bytecode-only依存は残す。
- `configure_embedded_python` に `DLLs` 探索先を追加。通常のCPython配置からコピーしたSQLite/ctypes/SSL等の拡張が読めるようにした。既存のroot直下.pydを持つ埋め込みruntimeも維持する。
- Windowsで新たに見つかった終了テストの後片付け失敗は、テスト自身の `sqlite3.connect` contextが接続を閉じなかったもの。`closing` で明示解放し、メモリDBを使うruntime probeも同様に修正。backend所有終了の不具合とは混同しない。
- `tools/check_staged_encoder.py`：同梱Python/コピーしたbackendに限定した、固定のdocument/query/生成imageの互換性smoke。host fallback・既存JSON上書き・配布内への結果保存を拒否する。新規DL/私物走査/精度測定/ランキング調整はしない。

## 実物と検証結果

| 対象 | 結果・境界 |
|---|---|
| 既存資産からのruntime準備 | CPython3.11.9 x64、AI依存込みの明示入力26,211ファイル / 4,977,454,036 bytes。元venv/元Pythonには書かない。新runtimeのprefix/base_prefix/sys.pathは新runtime側だけで、元venv/システムPythonへのfallbackなし。 |
| コピーしたruntime import | SQLite・ctypes・PillowでPNG処理、torch/transformers/sentence_transformers/numpy/onnxruntimeのimport PASS。これはモデル精度や全codecの保証ではない。 |
| 配布runtime | `dist/alpha-0-runtime-20261020-01`。24,196ファイル / **5,516,015,686 bytes（約5.52GB）**。Python/AI依存/FFmpeg/ffprobeを含み、モデルは含まない。metadata/ライセンス原文は保持、公開配布/再配布条件の受入はしていない。 |
| 同梱起動前check | 全manifest/hash照合、同梱PythonのAI import、同梱FFmpeg/ffprobe9.0実行 PASS。**169.781秒**。通常のダブルクリックごとに約3分待つのは未解決の起動課題で、検査の無効化・弱体化はしていない。 |
| 実モデル互換性 | 同梱Pythonとコピーした`ai_process`/workerで既存EG2をCUDA実行。固定document/query/384×384生成画像の3処理が768D・finite・単位norm PASS、21.844秒。所有worker終了、modelサイズ/mtime不変。**検索精度の新試行ではなく、P0/RRF予算は変更しない。** |
| コピーしたbackendの所有起動 | 同梱Pythonで2回HTTP起動。生成フォルダを登録し、再起動後に同じroot ID/設定を保持。各終了後の所有backend終了/lease解放、DB integrity_check=ok、生成原本bytes/mtime不変。3.526秒。GUIの代役は短いPython子processで、native GUI受入ではない。 |
| WinUI部品のMSIX | `dist/alpha-native-20261020-01/Aredoko-frontend.msix`、65,413,168 bytes。SDK-native publishによる**未署名GUI部品のみ**。.NET/WindowsAppSDKを自己完結で含み、外部PackageDependency0、Analyzer/Python混入0。証明書作成/信頼追加/インストール/起動は未実行。 |
| 対象CPUテスト | Release関連28、runtime paths5、新runtime準備5の**計38 PASS、SKIP0**。初回のWindowsテストは27 PASS/1 cleanup ERROR、修正後28 PASS。新準備テストには独立layout/source不変/ライセンス/ABI拒否/上書き拒否/bytecode-only保持を含む。 |

GUI部品はMSIX向けであり、現在のPython launcherが配布binのEXEを直接起動する方式と、正式なMSIX activationの接続は未完成。**このフォルダのAredoko.cmd/shortcutを完成版として案内しない。** 実機での全機能/モデル/WD/Layaの受入、証明書/identity、インストール・更新/削除、開発ツールのないWindowsは未確認。

## 再現手順（必要時のみ、新しい出力先）

準備元は既存の許可済みCPython3.11と対応するsite-packagesを明示する。環境を自動探索/取得しない。

```powershell
python tools/prepare_python_runtime.py --base-python C:/Prepared/CPython311 --site-packages .venv-ai/Lib/site-packages --output-dir data/alpha-runtime/new-python --include-ai-runtime --check
# 上のパスを実在する許可済み入力に変更してから、--checkを外して新規先へ作る。
python tools/package_release.py --output-dir dist/new-alpha --version alpha-0 --skip-build --python-runtime data/alpha-runtime/new-python --media-tools C:/Prepared/Media --include-ai-runtime
dist/new-alpha/runtime/python/python.exe -I -B dist/new-alpha/tools/launch_release.py --check
# 最新ユーザーのGPU許可を確認した場合のみ、既存モデルで実行。
dist/new-alpha/runtime/python/python.exe -I -B tools/check_staged_encoder.py --models models --output data/ai-ui/new-runtime-smoke.json
```

GPU記録は事前固定した3処理harnessで取得。後で公開した`check_staged_encoder.py`の起動元/出力先ガードと結果保存の強化は構文・host拒否・同梱Pythonのhelpのみを確認し、GPU処理の重複実行はしていない。新しいsourceless .pyc保持も生成テストで確認し、実入力にcache外.pycは0件だったため同じ約5GBを作り直していない。

## 生ログ（ignored、書き換えない）

- `data/ai-ui/release-windows-20261020-tests.log` と `release-windows-20261020-tests-fixed.log`
- `data/ai-ui/alpha-runtime-prepare-20261020.log` / `alpha-runtime-import-20261020.json` / `alpha-media-runtime-20261020.json`
- `data/ai-ui/alpha-full-stage-20261020.log` / `alpha-staged-preflight-20261020.log`
- `data/ai-ui/alpha-runtime-smoke-plan-20261020.json` / `alpha-staged-encoder-20261020.json` と`.log`
- `data/ai-ui/alpha-staged-service-20261020/report.json`、2起動分のbackend/app logs
- `data/ai-ui/alpha-native-package-20261020-01.log`

## 次の3手

1. **R13/ALPHA-0**：MSIXの正式activationとPython launcherの所有起動を統合する。frontendだけでなく既存機能を持つ全体を通常shortcutから起動する経路へ。署名/信頼/インストールは必要な具体物と操作を用意してから既存許可を照合する。毎回170秒のcheckは原因を分けて測り、整合性/source guardを落とさず解決する。
2. **R13実受入**：生成媒体でshortcut→GUI→既存検索/閲覧/許可済みAI→終了/再起動、続いてclean Windowsのinstall/update/uninstall/データ保持。旧GUI上限はresetせず、ALPHAの新flowを事前固定する。未受入のままALPHA-0完了にしない。
3. **ALPHA-0後**：R06–R09の実音声/音楽producer・内容検索、次にWinUI改善と残るR11/R14/M1/M2/RC。通常実装Sol可、R06/R08方式選定はAstra推奨（委任権限ではない）。

新しい依存・モデルの取得0、原本/実DB/元venv変更0、私物走査0、GUI起動/証明書操作/アプリinstall0、Actions0、main merge0。既存の[ALPHA条件](alpha-packaging-milestone.md)・[Linuxの実装と境界](alpha-runtime-staging.md)・[UI受入](ui-current-build-acceptance.md)・[完成計画](completion-roadmap.md)を保持する。


## 2026-10-21 R13起動前検査の追記

[同条件の全検査計測と安全性](alpha-startup-performance.md)：固定4 workerでwarm73.567→41.558秒、24,196 hash/80,864 guard保持、対象CPU39 PASS。既存配布を書き換えず現行checkerを比較した結果で、前日の170秒・cold/p95やnative起動完了と混同しない。前日helper由来の未知cache3件は無視せず退避/保存済み。次はALPHA-0のnative activationと所有backend連携。R13 DOING/ALPHA未完/R14 PARTIALと後続音声/音楽→WinUIの順序を保持する。


## 2026-10-21 R13 MSIX実機結果と誤通知修正

[MSIX正式起動・実機結果と再開条件](alpha-packaged-activation.md)。許可済み証明書trustとAlpha1.0.0.1通常installは完了し、元Development登録を保持して併存。363 installed payload全件照合PASS。実shortcut→新規所有GUI/backend→生成画像検索・タグ保存まで確認したが、native flowは待機/スキャン/保存captionのテスト不備で**3/3上限**。誤った起動失敗通知とテスト期待値をsourceで修正し、追加GUIなしでCPU55 PASS、停止後DB保存/整合・source不変・封印済み02全24,325ファイル一致を確認。02は修正前artifactのまま。**R13 DOING / ALPHA-0未完 / R14 PARTIAL**。次はCPUのみ起動待ち/配布整備、追加GUIは新たな明示許可後に残るargv/閲覧/正常終了・再起動/clean Windows更新削除受入。過去のcaps/全機能/guardを維持し、ALPHA後の実音声/音楽→WinUI改善へ戻る。
