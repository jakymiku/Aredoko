# ALPHA-0：ランタイム梱包・起動所有権の準備（2026-10-20、Windows未検証）

開始upstream HEAD `05e0c60f7ec89de2855be77ec79850a3d261ebea`。現在の状態は **R13 DOING / ALPHA-0未完 / staging-only**。Windowsバイナリ、Python配布物、FFmpeg、モデルはこのLinux作業で取得・生成・実行していない。以下の実装とCPU検証を、ダブルクリック版の完成やclean-machine受入と読み替えない。既存の[ALPHA-0条件](alpha-packaging-milestone.md)と[製品ビジョン](product-vision.md)を維持する。

## 今回の実装

- `tools/package_release.py` に `--python-runtime` / `--media-tools` / `--include-ai-runtime` を追加。作業者が**明示指定した準備済みのローカル資産**だけを新規出力へコピーする。インストール済みPython/モデルの探索、ダウンロード、venvの勝手な流用、既存出力の削除は行わない。入出力の包含関係、リンク/junction/hardlink、欠落したruntime構成を拒否する。
- コピー先のPython `._pth` に配布内のstdlib/site-packages/backend/toolsを設定する。入力側は変更しない。各workerと起動コマンドに `-B` を付け、配布フォルダへbytecodeを書かない。Python公式の[モジュール探索パス仕様](https://docs.python.org/3.12/library/sys_path_init.html#pth-files)を参照。依存ライブラリ自身のWindows上の副作用やDLLロードは実機で別途確認する。
- `tools/release_runtime.py` はmanifestとSHA256リスト、全記載ファイル、必須payload、未知の追加ファイル、Windowsで不正なパス、合計件数/サイズを照合する。これは欠落・取り違え検出であり、署名・配布元認証ではない。manifestの `runtime_imports_verified` / `clean_machine_activation_verified` は常にfalseのまま。配置検査を実起動検査と偽らない。
- `tools/launch_release.py` は同梱Pythonだけで起動する。起動ごとのinstance IDを `/api/session` と照合し、他のlocalhostサービスへ接続しない。ユーザー領域のleaseで多重起動を拒否し、別プロセスを名前で探して終了しない。モデル・profile・AI worker位置は明示指定可能。UI/モデルの自動取得はない。
- バックエンドは `--exit-on-stdin-close` で起動元の専用pipeを監視する。GUI終了/起動失敗/起動元pipe消失では所有backendを通常終了し、worker・SQLite・leaseを解放する。8秒以内に終了しなければ**その所有子プロセスだけ**を強制終了する。既存workerのparent監視は維持。起動途中のbind失敗も `ExitStack` で後始末する。
- `--ai-python` / `--models-root` をEG2/Laya/WD/GUI profile診断へ一貫して渡す。WD子workerにも外部models rootを伝える。指定のない開発起動は従来の `.venv-ai` / `models` を使い、モデルidentity・索引namespace・ランキングは変更しない。明示指定先が欠落しても別Pythonへフォールバックしない。
- 動画ツールは配布起動の子プロセス環境 `AREDOKO_MEDIA_TOOLS` で固定する。この指定下ではFFmpeg/ffprobe不足をPCのPATHで隠さない。指定のない従来の開発起動は従来動作を維持。
- `Install-Shortcut.cmd` / `install-release-shortcut.ps1` は明示実行時だけcurrent-user Desktopへ `Aredoko Alpha.lnk` を作る。リンクは同梱 `pythonw.exe -B tools/launch_release.py` を指し、日常起動にPowerShellを介さない設計。既存リンクは上書きしない。**生成/ダブルクリック/Windows App SDK identityは今回未実行**。MSIX登録・管理者設定変更を行うスクリプトではない。
- `Aredoko.cmd` / `start-aredoko.ps1` は診断用wrapperとして保持。同梱Python不足時にシステムPythonや隣の開発venvを探す経路を廃止した。ソースからの開発起動は従来の `tools/start-winui.ps1` を使う。

## Windows担当者が準備する入力

| 入力 | 必要な内容 | 今回の検査の限界 |
| --- | --- | --- |
| `--python-runtime` | 再配置可能なWindows x64 Python 3.11+、`python.exe`、`pythonw.exe`、対応する`python3xx.dll`/`python3xx.zip`、`LICENSE.txt`、`Lib/site-packages/PIL`と必要DLL | 既存venvをそのまま指定しない。3.11以上は既存WDの`hashlib.file_digest`とも整合。ファイルの存在だけではABI/再配置成功を保証しない |
| `--include-ai-runtime` | 上記にtorch/transformers/sentence_transformers/numpy/onnxruntimeとそれらの依存DLL/許諾文書を含める | オプションの静的確認は主要package入口まで。全依存importは後段、実モデル/GPU動作は実機gate |
| `--media-tools` | `ffmpeg.exe`、`ffprobe.exe`、それらが必要とするDLLと`LICENSE.txt` | 配布予定buildのライセンス/ソース提供義務等は[NOTICE](../THIRD_PARTY_NOTICES.md)と照合。ここで法的な再配布適合を認定しない |
| AIモデル | 明示許可済みの既存モデル親ディレクトリ | このpackerはモデルをコピーしない。revision/provenanceを維持して指定する。新規取得や無断再配布をしない |

新しい依存やモデルが必要なら、その取得内容/容量/対象だけを明確にして既存承認を照合する。今回の一般的な開発継続依頼を追加ダウンロード許可へ広げない。準備済みassetが存在しないことはPythonコード/CPUテストまでを止める理由にはしない。

## 次の実機確認手順（開発者向け、未実行）

既存x64 Releaseがある場合の例。パスは生成テスト用の例であり、ユーザーの実フォルダを表さない。

```powershell
python tools/package_release.py --output-dir dist/alpha-0-candidate --version alpha-0 --skip-build --python-runtime C:/Prepared/AredokoPython --media-tools C:/Prepared/AredokoMedia --include-ai-runtime --check
python tools/package_release.py --output-dir dist/alpha-0-candidate --version alpha-0 --skip-build --python-runtime C:/Prepared/AredokoPython --media-tools C:/Prepared/AredokoMedia --include-ai-runtime
dist/alpha-0-candidate/runtime/python/python.exe -B dist/alpha-0-candidate/tools/launch_release.py --check
```

最初の `--check` は入力構成のみ検査し、build/コピー/ディレクトリ作成/実行を行わない。最後の `--check` は同梱PythonでSQLite/ctypes/Pillow、指定時のAI import、FFmpeg/ffprobeの `-version` を実行する。DB・GUI・モデル推論を開始せず、manifestの実機受入フラグも書き換えない。`--verify-only` は任意OSでハッシュ検査だけを行う。

通常の保存先は `%LOCALAPPDATA%\Aredoko`。必要なら同フォルダの `launch-settings.json` に以下を**実際に存在する許可済みパスへ変更して**設定する。パスは絶対パス限定、未知のキー/不正値は拒否する。settingsファイル自体を配布/Gitへ含めない。

```json
{
  "models_root": "C:/Prepared/AredokoModels",
  "ai_python": "C:/Prepared/ExistingAI/Scripts/python.exe",
  "ai_profiles_dir": "C:/Prepared/ExistingProfiles",
  "ui_theme": "system"
}
```

`ai_python` を省略すると同梱Python、`models_root` を省略すると `%LOCALAPPDATA%\Aredoko\models` を使う。外部AI Pythonを明示指定する例はローカル受入用であり、他PCで開発環境不要とする証拠ではない。`database` / `ai_settings` / `viewer_settings` で既存保存先を指定可能。未指定のcatalog/settings/viewer設定名は既存と同じ。配布フォルダ内へのユーザーデータ保存は拒否する。起動後の失敗ログはユーザー領域の起動別ディレクトリに保存し、自動送信しない。モデル/原本/設定の勝手な移動はない。

展開先を確定して `Install-Shortcut.cmd` を実行し、作成されたショートカットから起動する。ショートカットは絶対パスを持つため、展開先変更/新しい版への切替時は**新しい名前/明示した別Destination**で再作成する。旧shortcutの自動削除はしない。配布フォルダの同時差し替えは避け、新規の版ディレクトリを使い、アプリを終了してから切り替える。

**次の3手**：

1. 許可済み資産からPython/画像処理/AI/動画DLLを含むruntimeを準備し、同梱Pythonのimport probeをWindowsで通す。既存ライセンス・必要容量・runtime配布方式を確認する。
2. 現行WinUIのpackaged identity / Windows App SDK / `.NET self-contained` 条件を解決し、正しいpayloadでショートカット→GUI→既存画像/本/動画/音声再生→許可済みAI推論→終了を一度受入。必要ならMSIX等を選択する。ソースだけを根拠に直接EXE起動可能と扱わない。
3. 開発ツールのないWindowsで再起動・保存維持・更新/解除・日本語/空白pathを確認。ALPHA-0が成立したらR06–R09の実音声/音楽抽出、その後WinUI改善へ戻る。

## 今回の検証証拠と境界

- Linux / Python 3.12.14。関連13モジュール **139 tests = 137 PASS / 2 Windows SKIP、25.925秒**。その後のrequired-payload/配布先移動ケース追加と小修正後にrelease対象 **28 tests = 26 PASS / 2 Windows SKIP、3.924秒**。重複を除く対象は **141 tests = 139 PASS / 2 SKIP**。同じ全体suiteの反復やCIでの確認はしていない。
- 実プロセスで通常終了/GUI起動失敗/存在しないGUI/既存port/別instance/起動timeout/owner pipe EOF/bind失敗とDB lease解放を確認。配布後に日本語・空白入りの別ディレクトリへ移動し、**コピーしたbackend**をLinuxホストPythonで起動・終了して全payloadハッシュ不変を確認。GUI代役は短いPython子プロセス。
- runtime/WinUI/FFmpegの梱包テスト入力は**中身が偽物と明記されたlayout fixture**。これでDLLロード・FFmpeg動作・CUDA・Windows launchを合格にしない。既存backup CLIの生成DB往復・integrity_checkもPASS。
- ホストPythonの `probe_release_runtime.py` はSQLite/Pillow/ctypes PASS。これは同梱Windows Python/AI import/モデル推論の証拠ではない。
- `git diff --check` / Python構文確認PASS。Windows/.NET SDK/PowerShellがないためRelease build、PowerShell AST/COM shortcut、WinUI/clean-machine、実GPUは未実行。R11/R14/P0既存試行記録は不変。
- Actions0、新依存/モデル取得0、私物scan/原本変更0、main merge0。配布物の公開なし。起動時の全ハッシュ検査の所要時間は実際の同梱サイズで測定が必要。


## 2026-10-20 Windows追記：同梱runtimeとfrontend MSIXの実物確認

[Windows実測・生ログ・次の3手](alpha-windows-runtime-validation.md)。既存資産だけでPython/AI/動画runtimeを準備し、同梱環境のimport、EG2 CUDA固定3処理、backend2起動の保存/所有終了と対象CPU38件がPASS。5.52GB stagingの全checkは169.781秒、frontendのみの未署名自己完結MSIXは約65MB。**R13 DOING / ALPHA-0未完 / R14 PARTIAL**。Native activationと所有launcher統合・起動待ち・通常shortcut/署名/install/clean Windowsは未受入。過去のLinux/GUI記録は履歴として保持し、次はALPHAの起動経路を完成させる。成立後の実音声/音楽→WinUI改善は中止しない。
