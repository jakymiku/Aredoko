# Portable起動通知の依存欠落修正

## 2026-10-21 Portable起動タイムアウト修正・実機受入（限定範囲）

最新のユーザー許可「お願いします」を受け、専用空DB/GPUなしでlocal Portable実機診断を実施。旧配布・installed Alpha・普段のDB・モデルは未変更。新しい確認先は **`dist/portable-startup-diagnostic-20261021-02/Aredoko/Check-Startup.cmd`**。旧`portable-wincheck-20261021-02`は失敗版として保持し、これを再案内しない。[修正・証拠・限界](portable-startup-console-fix.md)。

**実原因と修正**：本体は初期一覧とRenderingまで成功していたが、`System.Console.dll`が物理的に存在してもtrimmed `.deps.json`のruntime graphから欠落し、ready通知時にFileNotFoundException。Portable限定TrimmerRootAssemblyで依存を保持し、配布receipt検査でDLL+runtime graph両方を必須化。生成回帰で「DLLあり/graphなし」を拒否し、実失敗publishも拒否・実修正publishはPASS。送信済みflagはwrite/flush成功後にだけ設定する。timeout60s・full SHA・原本/identity/first-frame guardsは緩めていない。

**結果**：Portable build0 errors/既知WUI1001×3+IL2104×2、CPU **30 PASS / 52.864s**。固定flow `portable-startup-gui-20261021`は**3/3消費**。01は実不具合再現（失敗画面の閉じる名も2候補でambiguous、所有bootstrapを別途通常close）。02はreadyと本体表示成功だがposted Alt+F4がWinUIに届かずraw FAIL、記録済み可視CloseボタンUIAで通常cleanup。03は**PASS：実ready/起動画面が消える/空ライブラリ表示/UIA通常close/所有backend等終了/別のfresh smoke起動を早期cancel/所有cleanup**。cancel操作後待ち0.859s。7 PNGを全部目視確認。01/02のraw FAILを成功にしない。3/3後の再試験・別名resetはしない。

修正版は24329 files / 5554470502 bytes、manifest 90c47fe3b6c9c21bacf49ef05d29a1588f7ade4f37ecf9e386989a1beb2bc81d。配布/テストlog・raw reports・全PNG・最終harness snapshotとvisual-and-artifact-review.jsonはignored `data/ai-ui/portable-startup-gui-20261021`とadjacent logに保存。旧sealed manifest SHAは以前の値と一致。新配布内のdocsは準備時snapshotであり、最新状態はrepo handoffを正とする。

**限界と次**：この不具合とfresh smokeのready/close/cancelは解決。初回paint/普通DBのrestart保持・clean Windows・ZIP/再配置・model3経路・viewer速度/実媒体比較は未受入。全件チェック込みの03 main確認57.948s（単発・controlled cold/p95ではない）；full SHAの待ちは引き続き課題。PZ2限定native受入済みだがR13 DOING/ALPHA未完/R14 PARTIALを維持。次はPZ3既存モデルfolder選択/明確診断→手動/app取得（既定無制限、任意cap）と通常データ/ZIP受入。U09/U11/U13/U14/ALPHA後実音声・音楽も保持。Downloads/Actions/main merge/GPU/私物scan/旧shutdown再実行なし。

## 変更した箇所

- `src/Aredoko.WinUI/Aredoko.WinUI.csproj`: PortableだけSystem.Consoleをtrim rootに指定。通常MSIX設定や依存versionは変更しない。
- `StartupReady.cs`: write/flushが成功するまでsent扱いにしない。nonce/instance検査とRendering条件は維持。
- `tools/portable_frontend.py`: 既存receipt SHAと追加file集合に加え、bounded deps JSONのactive targetにConsole runtime entryがあることを検査。
- `tests/test_portable_startup.py`: 生成publish fixtureを実際のdeps contractに合わせ、DLLがあってもruntime graphが空の失敗を再現。

Console DLLを手でコピーして済ませたり、timeoutを延長したり、例外/trim警告を隠したりしていない。新しいモデル/依存取得・OS設定・証明書変更なし。WinUIのコードレビューでchannel限定、通常起動保持、例外通知/guard保持を確認した。

## 手元で開く入口

`dist\portable-startup-diagnostic-20261021-02\Aredoko\Check-Startup.cmd`は専用空ライブラリの起動確認。通常利用は同じfolderのAredoko.exeで従来の明示設定/データを使うが、通常データのrestart保持は今回のGUI試験範囲外。旧インストール版やショートカットは更新していない。

今回のGUIはユーザーが明示許可したlocal unpackaged Portable診断。主なCLIはwinapp ui screenshot/inspect/invoke/list-windowsで、所有bootstrapのPID→所有Python→そのchild WinUIの実pathを確認し、画面操作をそのPIDに限定した。終了は実UIA Closeボタン、起動取消はbootstrapのキャンセル。最終harness snapshotをrun directoryへ保存。ready/通常close/cancelをもう繰り返さず、追加の受入範囲が必要になった時に新しい許可と固定予算を設定する。
