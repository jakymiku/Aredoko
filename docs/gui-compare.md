# Aredoko: Tauri/React と WinUI 3 の比較キット（試作）

## 現状と前提

- **2つの最小試作コードと測定用ツールを同じブランチで準備。** これはGUI採用の判定結果ではない。
- Windows固有のTauri/RustおよびWinUI/.NETビルドは作成環境（Linux）では未検証。公式CLIでテンプレートを作成するWinUI側は初回ビルド調整が必要な可能性あり。
- 50,000件の架空データを共通Python APIから取得する。1ページ60件、検索、メディア種別、詳細、単体タグ・棚・お気に入り・確認済みの保存を比較する。
- ネイティブAPI、音楽再生、漫画ページ展開、サムネイルはこの段階では**測定しない**。WinUIはListView仮想化、Reactは固定高さ行の簡易仮想化。
- このブランチはUI試作PR #1をベースとし、インデックス基盤PR #2には依存しない。実ファイルは使わない。
- アプリの外部公開、メディア走査、自動ダウンロードはしない。PC環境のインストールはJakyの許可が必要。

## 0. 開発環境の確認（読み取り専用）

Windows PowerShellでルートから：

```powershell
.\experiments\gui-compare\scripts\preflight.ps1
```

必要: Python 3.12+、Node.jsとnpm、Tauri側のRust（cargo）とWindows C++ビルド環境、WinUI側の.NET SDK（8.0.100以上かつテンプレートが要求するSDK）・WinApp CLI 0.7+。不足ツールは**自動インストールしない**。WinUI開発者モード変更など管理者権限の必要な操作は事前承認が必要。

参照: [Tauri公式](https://v2.tauri.app/start/prerequisites/)、[Microsoft WinApp CLI](https://github.com/microsoft/winappCli/blob/main/docs/usage.md)、[Windows開発スキル](https://github.com/microsoft/win-dev-skills)。

## 1. 共通バックエンドの起動（別のPowerShell）

```powershell
cd C:\AI\Aredoko-gui-compare
$frontend = Resolve-Path .\experiments\gui-compare\tauri-react
cd $frontend
npm install
npm run build
cd C:\AI\Aredoko-gui-compare
$fixture = Join-Path $env:TEMP ("aredoko-gui-" + [guid]::NewGuid().ToString('N') + '.sqlite')
python app/server.py --port 8768 --db $fixture --benchmark-dist .\experiments\gui-compare\tauri-react\dist
```

デモサーバーは `127.0.0.1:8768` のみ。ページ: `http://127.0.0.1:8768/bench/`。`/bench/` と必要な静的ファイルのみ追加し、既存 `/api` と `/` は変更しない。ベンチ中はこのPowerShellを開いておく。既存 `data/demo.sqlite` は使わない。終了はCtrl+C。`$fixture` のデモDBは終了後に削除可能。

## 2. Tauri + React（Releaseビルド）

2つ目のPowerShell:

```powershell
cd C:\AI\Aredoko-gui-compare\experiments\gui-compare\tauri-react
npm run tauri build -- --no-bundle
```

Tauri 2のビルドが成功すれば `src-tauri\target\release\aredoko_tauri_bench.exe` などに実行ファイルが生成される。起動には上記ローカルPythonサーバーが必要。`dist` はReact用の比較ページ、Tauriウィンドウは同じローカルURLを表示する。Webpack等の別サーバーや外部通信は不要。

## 3. WinUI 3 + C#（Releaseビルド）

3つ目のPowerShell:

```powershell
cd C:\AI\Aredoko-gui-compare
.\experiments\gui-compare\winui3\setup-winui.ps1
cd .\experiments\gui-compare\winui3\generated
winapp run . -c Release --detach --json
```

`setup-winui.ps1` は**新規ディレクトリだけ**に公式 `winapp new --template winui` を実行し、`MainWindow.xaml` とそのC#コードビハインドのみ差し替える。既存ディレクトリがある場合、上書きせず中断。生成される他のWinUIファイル（Package.appxmanifestや.csproj）は公式テンプレートを保持。環境によりコンパイルエラーが出たらそのログを使って調整する。

## 4. フェアな測定手順

1. OS、画面サイズ（1440×900）、Windows表示スケール、電源設定を固定。同じPython APIと5万件を使用。アプリは片方だけ起動し、Pythonは常に共通。
2. **Releaseビルドのみ**比較。DebugとReleaseは混ぜない。最初の起動（cold）と2回目以降（warm）を区別し、少なくとも3試行。
3. 片方のアプリを起動、タスクマネージャーでアプリPIDとPythonサーバーPIDを特定。WebView2の子プロセスも測る。
4. 開いているウィンドウが同じサイズのとき、Idle / Search（「雨の街」で検索） / Scroll（往復） / Detail（作品を開く） / Edit（テストタグを保存）の順に、各20秒計測。
5. 別のアプリに切り替えて同じ順序・同じ時間・同じ入力を3回繰り返す。検索時間は画面表示の参考値であり、体感遅延やFPS測定の代用ではない。
6. 毎試行でスクリーンショットを取得してUIが正しく動いていることを確認。操作性・キーボード動作も別に評価。

同時に両アプリを起動して比較しない。1アプリの計測例（PowerShellを別ウィンドウで実行）：

```powershell
.\experiments\gui-compare\scripts\measure.ps1 -Variant Tauri -Phase Scroll -AppPid 1234 -BackendPid 5678 -Seconds 20 -Trial 1
# もう一方は -Variant WinUI に切り替える。PIDは毎回実測の値を入力。
```

出力はGit除外済みの `cache/gui-compare/*.csv`。次で集計：

```powershell
python .\experiments\gui-compare\scripts\report.py .\cache\gui-compare\*.csv --json .\cache\gui-compare\summary.json
```

レポートはプロセスツリーごとのPrivate Bytes中央値/最大値、Working Set**合計**中央値/最大値（共有ページの二重計上あり）を表示。Python分を分けて記録。親子関係が切れたWebView2プロセスは取りこぼす可能性があるため、タスクマネージャー/Process Explorerで追加確認。**FPS、描画遅延、GPUメモリ、正確な起動時間はこのスクリプトでは測定しない**。これらは別に計測方法と検証を確立する。

## テスト状況

- Python既存テストと比較用レポートの単体テストを実行。
- Python HTTPルーティング/ディレクトリ境界のテストを追加。
- React/WinUIの**Windows Releaseビルド、UI操作、パフォーマンス計測は未検証**。この文書に結果の数字を作らない。
- 機能の完全一致や性能順位は現時点で保証しない。WinUI固有のシステムウィンドウ/スクリーンリーダーやTauri WebView2の比較は実機確認が必要。
