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

## Tauri first-page debounce race (2026-10-11)
- 起動直後の検索入力欄は`query`と確定検索`search`が同値でも220msタイマーを作成していた。ページ2へすぐ移動するとタイマーが遅れて`setPage(0)`を呼び、ページ1に戻る競合がEdge回帰テストで検出された。
- `query === search` の間はタイマーを生成しないよう修正。検索内容が変わるときのみデバウンスしてページ1へ戻す。
- GUI比較の採用評価は、Tauri/WinUI両方で正常なページ切り替えと編集操作を確認後に実施。

## 5. 日本語・GUI自動操作つき比較BAT（2026-10-11）

`experiments/gui-compare/GUI-Compare.bat` をダブルクリックする。**最新版を一度git fetch/mergeしてから**実行する。選択は「1: お試し10秒×1回」または「2: 本測定20秒×3回」のみ。GUIへの英語指示・手作業は不要。

### 自動実行される工程
- 既存のベンチ用Tauri/WinUIウィンドウが開いていたら停止するよう案内（勝手に既存アプリを殺さない）。TCP 8768使用中なら中断。ユーザーの既存DB・個人ファイルを変更しない。
- npm/Vite+Tauri Releaseビルド、既存WinUI `generated` のソース差分をバックアップ付き更新。.NET 10のWindows UI Automationドライバー `ui-automation/GuiDriver.csproj` をReleaseビルドしCLI自己診断。
- 毎回固有の `cache/gui-compare/runs/<日時>-<短いID>/synthetic.sqlite` へ5万件の架空データを作り、共通Python APIをlocalhost:8768で起動。Tauri → WinUIの順に**片方ずつ起動**する。
- 各GUIで、実際のWindows UI Automationツリーから入力欄・リスト・保存ボタンを特定。検索「雨の街」とクリア、スクロール、3作品の選択と右側詳細一致、タグ編集・保存とバックエンドDB反映の**事前自動チェック**を行う。
- 事前チェックがPASSした場合、同じドライバーが待機/検索/スクロール/詳細選択/タグ編集を操作しながら `measure.ps1` でCPU/メモリを同時計測。操作した**つもり**で成功扱いにしないため、操作の反映を検証し、失敗した場合はその回で中断。
- 結果は生CSV、`summary.json`、`summary.txt`、`comparison.html`（グラフ付き日本語・オフライン）、各操作の検証結果 `*-automation.json`、診断用 `*.stdout.txt`/`*.stderr.txt`、失敗時の`*.tree.txt`、`session.log`。終了時はこの実行で作成したアプリとサーバーのみ停止し、結果フォルダを開く。

### 大事な制限
- WindowsのUI AutomationはネイティブWinUIとWebView2でアクセシビリティツリーが異なる。利用するボタン名・AutomationIdをソース側で揃えたが、**Windows実機での全自動操作の検証はまだ済んでいない**。失敗時はフォルダの `*-automation.json` と `*.tree.txt` と `session.log` を送って調査する。**CIはドライバーのWindowsコンパイルとCLI自己診断・Python集計・ブラウザー回帰テストまで**で、Tauri/WinUI実ウィンドウ操作の成功を証明するものではない。
- ベンチ中は同じWindowsセッションのマウス・キーボード・フォーカスをドライバーが使用する。**ユーザーがPCを並行操作しないこと**。リモート接続が切断/ロック中、UAC画面中、異なるDPIやモニター構成では失敗することがある。
- 自動編集はその回専用の架空データのみ。GUI経由で保存し、APIの読み取りでタグ反映を検査する。既存の利用者データへAPI経由で編集はしない。
- CPUはプロセス累積時間による概算。Working Set合算は共有ページの二重計上あり。WebView2子プロセス取りこぼしに注意。Tauriの仮想行レンダリングとWinUIの60ネイティブ行は異なる。**FPS・コールド起動時間・GPUメモリ・入力遅延は測定しない**。3回の測定でも採用判断は暫定。

```powershell
cd C:\AI\Aredoko-gui-compare
$repo = 'C:/AI/Aredoko-gui-compare'
git -c "safe.directory=$repo" fetch origin
git -c "safe.directory=$repo" merge --ff-only origin/feat/gui-framework-comparison-20261010
explorer.exe .\experiments\gui-compare
# GUI-Compare.bat をダブルクリック
```

## Windows UI Automation初回実機で発見したエラー（2026-10-11、GUIドライバー修正）
- ユーザー実行ではビルドとAPI起動まで成功し、Tauriの`Check`段階で`操作対象「変更を保存」がアクセシビリティツリーにありません` として停止した。Tauri Reactは作品の選択前に右側の詳細・編集欄（保存ボタン含む）をレンダリングしない。一方ドライバーは作品を選ぶ前に`FindRequired(SaveLabel)`を実行していた。**GUI本体の保存不具合を示すログではない**。
- 修正: 初期確認は検索欄・一覧のみに絞り、`EditOnce` で作品選択後、右側詳細を確認してからタグ欄と保存ボタンを探す。
- 同時点検: native `SendInput` 用の `INPUT` 共用体に `MOUSEINPUT` を定義して、x64では40-byteサイズとなるよう修正（旧コードの32-byte宣言はキーボード入力失敗の恐れ）。ドライバー自己診断でサイズを検査。
- スクロール時、Tauriの非フォーカス可能な `role=group` に`SetFocus`しないよう、表示中の行へフォーカスしてホームキーを送る方式に修正。
- 再実行は最新版をgit fetch/ff-onlyで取得後、同じ`GUI-Compare.bat`のモード1を使用。**Windows実機での一連のUI操作の成功は未確認**。再度止まれば`Tauri-Check-0-automation.json`、`Tauri-Check-0-automation.tree.txt`、`Tauri-Check-0-automation.stdout.txt`を送る。

## Tauri UIA タグ入力の非フォーカス可能要素（2026-10-11 21:32、ドライバー修正）
- Windows実機でTauriのCheckが検索・スクロール・詳細選択を通過し、`EditOnce` → `Type` → `AutomationElement.SetFocus()` で「ターゲット要素は、フォーカスを受け取ることができません」となった。
- WebView2アクセシビリティツリーではReactの`<label>`と`<textarea aria-label="タグ（カンマ区切り）">`の名前が一致する場合、旧`FindRequired(TagLabel)`がフォーカス不可のラベルを返す可能性がある。実ツリーが未提供のため断定はせず、型検査を追加。
- GUIドライバーに`FindEditRequired`を追加し、指定AutomationId/Nameに一致する要素またはその配下から`ControlType.Edit`かつ`IsKeyboardFocusable`・`IsEnabled`・画面内の入力欄のみを採用する。入力直前にも検証し、入力先がラベル等だった場合は安全に停止する。
- 検索欄とタグ欄の両方に使用。失敗時ツリーにフォーカス可否と有効状態を出力する。Regression testでフォーカス可能なEditor選択を静的確認。
- **修正版のWindows実機UIA操作はまだ未検証**。CIビルド通過後、最新版で`GUI-Compare.bat`モード1を実行。次の失敗時は`Tauri-Check-0-automation.tree.txt`と`Tauri-Check-0-automation.json`の提出が診断に有効。

## GUI自動検索2回目の空入力（2026-10-11 21:39、ドライバー修正）
- 実機 `20261011-213826-4e6942` のTauriでは`Check`が検索/スクロール/3作品の連続選択/タグ保存の4項目をすべてPASS、Idleの記録もPASS。Search計測も最初の入力・クリアはPASSしたものの、**2回目の`Type("雨の街")`でUIA ValuePatternが空文字となり失敗**。
- 失敗時の`Tauri-Search-1-automation.tree.txt`にはフォーカス可能な検索Editと通常の一覧（「雨の街」「夜の図書館」が混在）が存在。入力が失われた直接原因はまだ実機トレースなしでは特定できない（フォーカスやReact再描画・検索リクエストとの競合など）。
- ドライバー側で、`Type`を検索・タグごとに現在のUIA `Edit`を再取得してフォーカス確認、必要時は実際のクリックで再フォーカス、Win32 Unicodeキー入力、**入力欄の値を再取得して一致するまで確認**に変更。失敗時は最大3回まで再操作し、期待/実測値と再試行状況をログへ記録。3回失敗なら続行しない。
- 旧検索検証は通常一覧にも「雨の街」が含まれるのに、タイトルが見つかるだけで成功扱いしていた問題があった。修正後は`「雨の街」の結果に絞られていること`（全行に「雨の街」）と`検索クリアで「夜の図書館」の行が戻ること`の両方を待つ。純粋な判定関数の自己診断と回帰テストを追加。
- 本測定のCPU/メモリCSVは自動操作が途中失敗した場合**有効な比較結果として扱わない**。あらためて`GUI-Compare.bat`モード1の完走を確認し、次の失敗時は新たな`*-automation.json`、stdout、`*.tree.txt`を確認する。CIの成功は実機の自動入力完走の保証ではない。
