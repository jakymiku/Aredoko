# ALPHA-0：MSIX起動と所有バックエンド（2026-10-21）

開始HEAD `a049c87`。R13 DOING / ALPHA-0未完 / R14 PARTIAL。配布側の起動経路と許可済みAlpha併存installは完了し、実shortcut/生成媒体検索・タグ保存は確認。正常GUI終了/再起動・clean Windows受入は未完了。[完成計画](completion-roadmap.md)、[前段のWindows実測](alpha-windows-runtime-validation.md)、[全検査の高速化](alpha-startup-performance.md)も保持する。

## 起動経路

1. コピーしたPythonの`pythonw.exe -B tools/launch_release.py`が入口。配布全件SHA256、未知ファイル、lexical祖先/link/type/hardlink検査、同梱Python/動画toolの検証を維持する。4 worker/batch64の省略なしチェックは前段と同じ。
2. 配布manifestの`frontend_activation=msix`と`frontend/Aredoko.msix`を確認。MSIXのidentity、x64、単一full-trust app、自己完結の条件を検証する。ZIPはサイズ/件数を制限し、元のentry名で親移動・逆slash・大文字小文字の重複・制御文字等を拒否する。抽出には`extractall`を使わない。
3. Windows標準PowerShellの`Get-AppxPackage`から現在のユーザーの登録を読む。名前/publisher/version/architecture/family/full nameが一致する通常インストールだけを受け付け、未登録・開発用登録・別versionを拒否する。別のアプリや開発EXEへfallbackしない。
4. MSIX内の全payloadファイル（Windows管理の署名/block map等footprintを除く）と登録先をサイズ/SHA256で照合し、起動直前にも再確認する。元ファイルのguardを緩和しない。WindowsAppsの実インストール先でも363ファイルが全件一致し、guardを省略せずPASSした。
5. 所有instanceを持つbackendを起動し、既存portへ接続せず、`/api/session`のproduction/instance一致を待つ。その後`IApplicationActivationManager::ActivateApplication`で登録済みAUMIDを正規起動する。GUIのEXEを直接起動しない。
6. APIが返したPIDのHANDLEを開き、作成時刻が今回のactivation以降であること、実行pathとpackage full nameを照合。確認前に既存processを終了しない。確認後は保持した同じHANDLEだけを監視/終了し、PIDで再検索しない。再利用された既存processは触れずに失敗を案内する。
7. GUI終了/起動失敗/backend異常で自分のbackendを閉じる。通常は所有stdin pipe EOFで終了させ、timeout時だけ所有子processを停止する。GUI handleも確実にcloseする。既存開発起動とCPU用の子process代役テストは維持する。

テーマとviewer設定pathは`subprocess.list2cmdline`でWindows引数列へ変換し、shell経由では渡さない。実WinUIでの日本語/空白path引数の受け取り、GUI終了/再起動は今後のnative flowで確認する。Appの標準ログは既存のAppLogへ、launcherのapp.logにはactivation metadataを記録する。stdout転送があるとは案内しない。

## 配布準備

`package_release.py --frontend-msix <明示MSIX>`を追加。この場合は通常build出力ではなく**MSIXの公開用payloadそのもの**をbinへコピーし、同じMSIXをfrontendへ含める。publish時の変換で通常buildと実バイトが異なるため、両者を混ぜない。GUI部品のpackage作成/署名はSDK-native publish、backend/runtime梱包は既存stagerを使う。明示MSIXがある場合は勝手に再buildしない。

MSIXなしの従来staging/CPU fixtureも作成できるが、通常launchは`--frontend-msix`での再作成を案内して拒否する。`--verify-only`はinventory、`--check`はruntime、**`--check-activation`はruntime＋登録済みMSIXのread-only照合**。3つは排他的で、チェック済みでない状態をPASSにしない。shortcut作成は`--check-activation`に合格した場合のみ行い、既存shortcutを上書きしない。

```powershell
# SDK/native publishは開発PCだけで実施。証明書の信頼やinstallはこの操作に含まれない。
winapp package src/Aredoko.WinUI/Aredoko.WinUI.csproj --arch x64 --cert data/alpha-signing/20261021-01/devcert.pfx --no-restore --self-contained -p SelfContained=true -p AredokoPackageChannel=Alpha --output dist/alpha-native-20261021-02/Aredoko-frontend.msix

# 新規先のみ。既存runtime/モデル/配布を変更しない。
python -B tools/package_release.py --output-dir dist/alpha-0-msix-20261021-02 --version alpha-0-20261021 --python-runtime data/alpha-runtime/20261020-python-ai --media-tools data/alpha-runtime/20261020-media --include-ai-runtime --frontend-msix dist/alpha-native-20261021-02/Aredoko-frontend.msix

# 同梱runtimeチェックだけ。DB・GUI・モデル推論を起動しない。
dist/alpha-0-msix-20261021-02/runtime/python/python.exe -I -B dist/alpha-0-msix-20261021-02/tools/launch_release.py --check
```

### 開発版と配布版の併存

初回は同じidentityのversionを1.0.0.1へ上げて更新を試みたが、Windowsは **0x80073CFB（開発用の疎な登録を通常MSIXへ置換できない）** で拒否した。既存登録の削除/アンインストールや`WindowsPackageType=None`への逃避は行わなかった。

正規のMSBuild条件付き`AppxManifest`を採用し、既定の **Development** は元のGUID identity/1.0.0.0を保持、明示の **Alpha** publishだけ`Package.Alpha.appxmanifest` / `Aredoko.Alpha` / 1.0.0.1を使う。Alphaで通常の開発runをしないためのguardも追加した。MSBuildの実評価で各channelのmanifestが1件だけ選ばれることを確認。別channelは同じアプリ/C#/XAML/API/依存を共有し、旧登録を壊さず併存する配布設計である。launcherはこのAlpha identityだけを照合し、任意のpackageを受け付けるようには緩めない。[Microsoftの条件付きmanifest例](https://github.com/microsoft/WinUI-Gallery/blob/main/WinUIGallery/WinUIGallery.csproj)も参照。

ユーザーはこのPCでの証明書trust・配布MSIXインストール・実GUI確認を明示許可済み。同じ操作を改めて確認しない。試験証明書1件（CN=AppPublisher、期限2026-11-20、thumbprint `4304C44116893E109E3CE0F5BFC40DB2E761A323`）を、UAC昇格で **LocalMachine\TrustedPeople** へ追加した。初回CLIの未対応`--json`と非昇格のアクセス拒否も保存。PFXはignored領域だけ、Git/公開配布へ含めない。production署名ではない。

`Aredoko.Alpha_1.0.0.1_x64__1z32rh13vfry6`を通常インストールし、元の開発登録1.0.0.0との併存を確認。開発登録/ユーザーデータの削除はしていない。Alpha自己完結MSIXは新規`dist/alpha-native-20261021-02/`、新しいruntime stagingは`dist/alpha-0-msix-20261021-02/`。同じidentityで拒否された01番の配布も証拠として保持し、上書きしない。

shortcut作成には任意の`-Settings <絶対JSONパス>`を追加した。生成データの明示profileをリンクへ固定でき、Shell起動時の環境継承に依存せず私物DBへ接続しない。既定の利用方法/既存shortcutの上書き拒否は維持。


## 検証

- 新17件がPASS（Windows専用2件も実行）。MSIX全payload改変、unsafe ZIP、異なる登録、開発登録、別version、直前差替え、古いstageの拒否、公開用payload優先、所有時刻/path/package条件、ログ失敗/activation失敗/backend異常時の所有終了/handle解放を確認。
- 既存release34件もPASS。合計は重複を除き**51 PASS / SKIP0**（50件の全体回帰後にbackend異常ケースを1件追加し、新17件を再確認）。テストは生成DB/fixtureとGUIの代役であり、実WinUI activation合格とはしない。
- Windows COMを実際に生成し、存在しないテスト専用AUMIDがエラーになることを確認。既知アプリは起動しない。実際のunpackaged Python子processを誤採用せず、生存したまま拒否することも確認した。
- 初期登録はversion `1.0.0.0`、`IsDevelopmentMode=true`で、配布用checkerが拒否した。その後の許可済みtrust/Alpha併存installは上記のとおり。現在はAlphaの正常登録と全payload照合に合格している。
- 初回67件の試験にはテストclass継承/importによる重複があり、取り除いた。最初の2回はWindowsのZipInfoが逆slashを正規化するケースを再現できず/検出できず失敗。生成ZIPを修正し、検証を`orig_filename`へ変更した後の回帰に合格。失敗ログは残す。このCPU修正自体はGUI/P0試行に数えない。その後のnative flow3/3は下に別記する。

## 残る受入と次の3手

1. CPUのみで起動前の長い待ち表示と配布/利用手順を整備。trust/install/WindowsApps全guard合格を未実施へ戻さず、既存開発登録を保持する。全hash/guardを省略しない。
2. 固定native flowは**3/3上限**。追加GUIにはユーザーの新たな明示許可が必要。名前/folder変更でresetしない。許可後に修正版の新artifactで、実argv/閲覧/通常終了・再起動、clean Windowsの開発toolなし起動/更新/削除/データ保持を受入。既に許可/実施済みのtrust/installを再承認させない。
3. ALPHA-0成立後にR06–R09実音声/音楽producerと検索を再開し、その後WinUI改善/残存R11/R14/M1/M2/RCへ。OCR保留、P0 2/2閉鎖、全機能維持。

参照API：[ActivateApplication](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-iapplicationactivationmanager-activateapplication)、[activation managerの寿命](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-iapplicationactivationmanager)、[package query API](https://learn.microsoft.com/en-us/windows/win32/appxpkg/functions)。新しい依存/modelの取得、GPU推論、私物scan、原本/実DB/元venv変更、Actions/main merge、外部公開は行わない。


## 実物・証拠（途中状態と最終native結果を区別）

- 同じidentityの01番stage：24,325ファイル / 5,619,099,113 bytes、同梱Python3.11.9の全preflight **83.050秒** PASS、旧開発登録の拒否が期待どおり。前段warm41.558秒とは内容/cache条件が異なり、単純な退行/改善率にはしない。
- Alpha channelの02番：SDK-native Release publish/署名成功。WindowsAppsの363 payloadは全サイズ/SHA一致、リンク/祖先/hardlink検査もPASS。Build CLIはwarning詳細を省略するため0 warningとは報告しない。従来のAnalyzer3件/SDK2件の既知警告は抑制していない。
- 固定flow `alpha-msix-owned-lifecycle-v1`、生成PNG1枚/専用DB、通常1200×820のみ、GPU0回。`tools/check_alpha_native.py`は本物の`.lnk`をShell起動し、返された新規pythonwのHANDLE、WinUIの新規HANDLE、backend instanceを確認する。最大initial＋2修正、旧flowのcapsは変更しない。
- attempt-01：実shortcut作成/full check、WinUI正規activation/所有process、backend instance一致、空の生成DBの4 checksがPASS。起動receiptまで87.272秒。UI遷移完了前に次ボタンを探したためFAIL。source/C#/XAMLの退行と断定せず、初期件数/フォルダhub件数の待機と失敗tree/PNGの取得をharnessへ追加。過去の失敗reportを上書きしない。
- 生ログ：`data/ai-ui/alpha-activation-regression-20261021-03.log`、`alpha-activation-final-20261021.log`、`alpha-channel-tests-20261021.log`、`alpha-native-package-20261021-01/02.log`、`alpha-cert-trust-admin-20261021.json`、`alpha-msix-install-error-20261021.log`、`alpha-side-by-side-install-20261021.json`、`alpha-msix-stage-check-20261021.json`、`alpha-native-acceptance-20261021-01/plan.json`と各`attempt-*/report.json`/PNG/UI.log。


### 固定native flowの最終結果（3/3上限）

| 試行 | 実行/失敗の内容 | 起動receiptまで |
| --- | --- | --- |
| 01 | 正規MSIX/所有backend/空DBまで4 checks PASS。フォルダ画面の遷移待機不足で停止。PNGなし。 | 87.272秒 |
| 02 | 同4 checks PASS。登録は成功したが明示ScanRoot未実行のため0件で停止。failure.pngを目視し、登録後にスキャンが必要なことを確認。PNGのログ追記Path JSON化も修正。 | 83.779秒 |
| 03 | 5 checks PASS、登録/明示scan1件/検索/選択/タグ保存成功。表示が「保存しました」なのに「保存済み」を待ち停止。failure.pngで保存済みtag/保存button無効/成功表示を目視。 | 63.984秒 |

これらは制御したcold/warm p95やGUI-ready時間ではない。viewer/実argv検査/正常GUI終了/再起動まで到達していない。テストreportのpass=falseを後から書き換えない。

03の中断時にharnessが**所有を証明したテスト用frontendだけ**を停止したところ、旧launcherが非ゼロ終了を一律「Windows app activation failed」と表示。これがユーザー添付のダイアログであり、正規activation自体の失敗ではなかった。ソースは起動後のエラー型/終了codeを保持し「Aredoko stopped unexpectedly」と分類、起動前の失敗表示と区別した。自動試験だけ明示する`--no-error-dialog` / shortcut `-NoErrorDialog`も追加し、ログ/非ゼロ終了/通常利用の通知を保持。保存captionを実装と合わせた。**上限後にGUIを再実行していないため、このsource修正をnative合格とはしない。**

### 上限後のCPU/読取専用確認

- release全体 **55 PASS/SKIP0、43.971秒**（`alpha-postcap-release-tests-20261021.log`）。新しい4件は起動前/後の分類、無コンソール時の失敗終了、明示flagと既定通知を検証。新規GUI起動なし。Windows不存在AUMIDのCOM negativeとunpackaged子process拒否は実行。
- `alpha-postcap-offline-20261021.json`：生成DBを`mode=ro`で開きタグ`alpha-native-saved`/1件/`integrity_check=ok`、backend port解放、生成PNGのSHA/mtime不変を確認。封印済み02の**24,325ファイル**も全inventory一致（31.068秒）。この数値はimport/installedチェックを含む起動時間ではない。
- PowerShell shortcut AST/Python構文検査PASS。C#/XAML機能/API/依存の変更なし。Alpha SDK-native publishは成功済みで、defaultDevelopment manifestの実評価も元identityを保持。
- `dist/alpha-0-msix-20261021-02`と試験ログ/planはimmutableのまま。planのpending/0回/01番pathは試行前snapshotであり、最終状態は本節とattempt reportを読む。修正後launcherを既存stageへ直接コピーしない。新artifactの準備と未受入部分のnative確認は別作業。

このターンはGPU推論0、新dependency/model download0、私物scan0、原本/実DB/元venv変更0、Actions0、main merge0。実施済みOS変更はユーザー許可した試験証明書1件のTrustedPeople信頼とAlpha MSIX併存installだけ。Windows Sandboxは無効のまま。
