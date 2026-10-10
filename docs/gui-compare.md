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

## Windows初回ビルドで判明した不具合と再検証（2026-10-10）
- Tauri: 旧版は下へスクロールしたあとにページ切替すると、仮想表示範囲とDOMスクロール位置がずれて空白になった。両者をページ/検索条件の変更に合わせてリセットした。自動Edge回帰テストを `tools/check-gui-bench.cjs` に追加。
- WinUI 3: Release実機起動時に `Reflection-based serialization has been disabled` が出て一覧表示できなかった。HTTP GET / POST のJSONを `LibraryJsonContext` のソース生成メタデータ経由に変更した。
- 以前に `setup-winui.ps1` で生成した `winui3/generated` は削除しない。最新版を取得後、変更された `overrides/MainWindow.xaml.cs` を、バックアップを取ってから既存生成プロジェクトの同名ファイルへコピーし、WinUIを再ビルドする。
- Tauri試作のWindows向け `src-tauri/icons/icon.ico` は初回Windowsビルドで不足したため、既存環境では `npm run tauri icon -- .\\src-tauri\\app-icon.svg` でローカル生成済み。そのファイルは消さない。
- この修正以降のWinUI/ Tauri Release実機再ビルドと画面操作は、ユーザーのWindows環境で再確認が必要。動作確認が済むまで性能比較を開始しない。

## WinUIの起動時JSON例外（再修正・診断用 DOM-v3）
Windows実機の `Reflection-based serialization has been disabled` は、source-generated JSONへ変えた後にも発生した。ソースコピーとReleaseビルドは正常だったため、「古いコードを使った」と決めつけず、**WinUI側の実行時JSON処理を根本的に変更**した。

- `winui3/overrides/BenchJson.cs` は `JsonDocument` でJSON応答を読み、`Utf8JsonWriter` でPOST JSONを作る。実行時のリフレクション、`JsonSerializer`、`HttpClientJsonExtensions` を使用しない。
- `winui3/overrides/MainWindow.xaml.cs` はこの処理を使用し、起動失敗/読込成功メッセージに `DOM-v3` と表示する。これが出ない場合、実行中のアプリは依然として古い版。
- `winui3/update-winui.ps1` は**既存の生成プロジェクトを削除せず** `MainWindow.xaml.cs` と `BenchJson.cs` をバックアップ付きで更新し、ハッシュ検証する。
- `winui3/setup-winui.ps1` は新規の公式テンプレートに両方のC#ファイルを適用する。すでに `generated` がある場合は再実行しない。
- `winui3/json-smoke` はWinUIに依存しない.NET 10コンソールテスト。反射JSONを明示的に禁止してセッション、一覧、詳細、更新JSONの互換性をチェックする。**これはWinUI実機動作テストの代用ではない**。

更新後、ユーザーのPCでWinUIウィンドウを閉じて次を実行：

```powershell
cd C:\AI\Aredoko-gui-compare
$repo = 'C:/AI/Aredoko-gui-compare'
git -c "safe.directory=$repo" fetch origin
git -c "safe.directory=$repo" merge --ff-only origin/feat/gui-framework-comparison-20261010
.\experiments\gui-compare\winui3\update-winui.ps1
cd .\experiments\gui-compare\winui3\generated
winapp run . -c Release --detach --json
```

新しい起動結果には必ず `[DOM-v3]` が表示される。新しい版でもエラーが出る場合、そのメッセージ（例外型と段階）と実行PIDを保存して次の調査に進む。**GUI両者が動作するまで性能の優劣を判定しない**。

## WinUI ListViewの空白表示（LIST-v4、実機確認待ち）
- DOM-v3でWindows実機のJSON例外は解消。50,000件、全834ページ、約223msの読込を確認。ただし画面の一覧は空白。読込時間は描画完了時間ではない。
- `MainWindow.xaml` から Window 直下の `ItemsSource="{x:Bind Items, Mode=OneWay}"` を外し、`MainWindow.xaml.cs` の `InitializeComponent()` 直後に `ItemList.ItemsSource = Items;` を設定。ListView仮想化とメディア行テンプレート自体は維持する。
- 画面に `[LIST-v4]`、`API n / ListView n`、ListView高さ・最初の行が実体化したかを表示する。空白が続く場合は、この表示が次の調査材料。
- **WinUIネイティブ描画はこの修正で未検証**。WinUI性能比較は依然として開始しない。
- 既存の `generated` は削除しない。最新版取得後に `update-winui.ps1` を実行すると `MainWindow.xaml`、`MainWindow.xaml.cs`、`BenchJson.cs` がバックアップとハッシュ検証付きで更新される。WinUIウィンドウを閉じてから `winapp run . -c Release --detach --json` で再ビルドする。

## WinUI LIST-v4 startup crash: WinRT collection marshaling (NATIVE-v5)
- Windows実機でLIST-v4のReleaseビルドは成功したが画面が出ず即終了。ユーザーの`winapp run . -c Release --debug-output` とデバッグログで `NullReferenceException` (`0x80004003`) を確認。スタックは `AredokoWinUiBench.MainWindow..ctor` → `IItemsControlMethods.set_ItemsSource` → `WinRT.ComWrappersSupport`。したがって **`ItemList.ItemsSource = Items;` の.NET `ObservableCollection<MediaRow>` 受け渡しが今回のクラッシュを起こした処理** と確認できた。
- 修正: `MainWindow.xaml` のMediaRow型`x:Bind`テンプレートを除去。C#では管理モデルを`List<MediaRow>`として手元に保持し、ListViewの`Items`へWinUIネイティブの `ListViewItem` / `Grid` / `TextBlock` を追加。選択された行は `SelectedIndex` から管理モデルへ対応させる。JSON DOM-v3も維持。
- `update-winui.ps1` はNATIVE-v5識別子を検査して、MainWindowのXAMLとC#、BenchJsonをバックアップ付きで更新する。
- 1ページ最大60行についてネイティブ行を明示生成する安全性重視の試作。**Reactの仮想行表示と完全に同じ描画方式ではない**ため、性能の結論には描画条件統一が必要。
- 静的テストは管理コレクションの`ItemsSource`代入と型付きx:Bindが再導入されていないことを検査する。**実機WinUI Release起動・描画は未検証**で、ユーザーのPCで再確認してから比較する。

Windowsでアプリを閉じて修正を適用するには：
```powershell
cd C:\AI\Aredoko-gui-compare
$repo = 'C:/AI/Aredoko-gui-compare'
git -c "safe.directory=$repo" fetch origin
git -c "safe.directory=$repo" merge --ff-only origin/feat/gui-framework-comparison-20261010
.\experiments\gui-compare\winui3\update-winui.ps1
cd .\experiments\gui-compare\winui3\generated
winapp run . -c Release --detach --json
```
成功すると診断表示は `[NATIVE-v5]`。まだ問題があれば診断表示・ビルドログ・クラッシュログを確認する。

## WinUI false-positive unsaved warning on selection (EDITOR-v6)
- 実機NATIVE-v5でライブラリの50,000件表示・作品詳細取得を確認。ただし次の作品をクリックするだけで「未保存の変更があります」と出て、選択行（左）と詳細（右）が不一致になった。
- 原因: `TextChanged` / `Checked` イベントで、保存前との差分判定なしに無条件で `_dirty = true` にしていた。作品を切り替えて入力欄へ値を反映する際にもイベントが起こる。
- `EditorState.cs` の保存済み値のスナップショットと実際の入力値を比較する方式に変更し、未編集ならそのまま別の作品へ移動できるようにした。編集して戻した場合も保存ボタンが再び無効になる。
- 実際の編集があるときだけ `ContentDialog` で「破棄して移動／キャンセル」を選択させ、キャンセル時は元の作品の選択位置を復帰する。詳細APIのリクエスト重複や一覧更新時の古い応答も破棄する。
- 保存完了時は入力欄の実際の保存状態をベースラインに更新し、その後再読込する。
- WinUIの公式テンプレートから生成済みの`generated`フォルダは削除しない。`update-winui.ps1` がC#、XAML、`BenchJson.cs`、新規 `EditorState.cs` をバックアップ付きで反映する。
- `json-smoke`（.NET 10、リフレクション型JSON無効）にC#での編集状態の単体テストを追加。**Windowsネイティブの画面操作はユーザー実機で再検証が必要**。
- 再検証: ①未編集で作品を連続選択 ②実際にタグを編集して別作品をクリック→破棄/キャンセル ③値を戻したら保存ボタンが無効化 ④保存後に再選択。
