# WinUI Analyzer（開発専用）

2026-10-20、ユーザーの明示許可により `Microsoft.Windows.SDK.BuildTools.WinUIAnalyzer` **0.7.1** をWinUIアプリのみに導入した。ビルド時のAPI互換性・XAML・interop等の静的点検で、見栄えや日本語、実機動作の受入を置き換えない。

## 配布に含めない設定と確認

`Aredoko.WinUI.csproj` のPackageReferenceは `PrivateAssets="all"` と `IncludeAssets="analyzers;build;buildTransitive"` を指定。runtime/compile/content/native assetsを取り込まない。パッケージ自体もdevelopmentDependencyで、依存パッケージは0件。

公式NuGetから77,426 bytesだけを合計6,000,000 bytes/s以下で取得した。SHA256は `52414e1f589557318b177a58df6050c88ece551b19b9d108afc2235ed52b37f3`。Release用restore前後の既存依存名・バージョン・ハッシュは一致し、追加はこの1パッケージのみ。システムPython/PyTorch/ドライバーは変更していない。

compilerへのAnalyzer DLL入力を確認。全bin出力にAnalyzer DLLがなく、4つの既存runtime deps.jsonにもAnalyzer依存がなく、project.assetsの全targetでこのパッケージにruntime/compile/native/runtimeTargetsがないことを確認した。最終clean-machine/MSIX受入自体はR13に残る。開発パッケージの本体はignoredのlocal feed/通常NuGetキャッシュにあり、Gitへ追加しない。

## 実行結果と警告の判断

WinUI x64 self-contained **Release成功、0 errors / 5 warnings**。内訳はWUI1001が3件と、従来のSDK IL2104が2件。警告抑制・NoWarn追加はしていない。

| 場所 | 検出 | 判断・次の対応 |
|---|---|---|
| `RelatedTermsEditor.cs:50` | FileSavePickerの新APIへの移行提案 | 既存pickerは所有HWNDで初期化済み。新API移行時に日本語/空白パス、取消、JSON出力を再確認する。 |
| `RelatedTermsEditor.cs:62` | FileOpenPickerの新APIへの移行提案 | 所有HWND初期化・16MiB入力上限・既存検証を維持。移行時に選択/取消/読み込み検証を実施する。 |
| `MainPage.xaml.cs:1025` | FolderPickerの新APIへの移行提案 | 所有HWND初期化済み。移行時に実プロジェクト参照でAPIを確認し、選択/取消を検証する。 |

WUI1001は即時のcrash判定ではない。今回の差分レビューで新たな必須修正は見つからず、既存pickerは一括置換せず警告を可視のまま残す。移行は独立した小変更として扱う。HC/DPI/Narrator/ICC/EXIFの未受入も残す。

今回の静的解析導入後にGUI/GPUの繰り返し試験はしていない。先行UI確認は [現行UI受入記録](ui-current-build-acceptance.md) の範囲に限る。

## ローカル再現

通常は既存のbuild手順で自動実行される。restoreを分ける場合はbuildと同じConfiguration/Platform/自己完結設定を指定し、ReleaseのILLink検査を保持する。

```powershell
dotnet restore src/Aredoko.WinUI -p:Configuration=Release -p:Platform=x64 -p:SelfContained=true
dotnet build src/Aredoko.WinUI -c Release -p:Platform=x64 -p:SelfContained=true --no-restore
```

取得とrestoreは今回だけignored local feedから行った。通常のNuGet source設定は変更していない。生ログはignored `data/ai-ui/winui-analyzer-20261020/build-release.log`、依存/配布出力確認は同ディレクトリの `verification.json`。

[公式パッケージ](https://www.nuget.org/packages/Microsoft.Windows.SDK.BuildTools.WinUIAnalyzer/0.7.1) / [Microsoftのrule catalog](https://github.com/microsoft/winappCli/blob/main/src/winapp-Analyzer/RULES.md)
