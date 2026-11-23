# Hark追加実装のWindows確認

> **最新（2026-10-14 続き）**：Light/Darkのreader・辞書native105checks/実入力14、Python31/Core107/Release PASS。readerの操作領域と狭幅で閉じた後の詳細/focusを修正。実JSON picker・zoom/直接Reopen等は残る。[正確な結果と履歴](native-folder-reader-validation.md)。以下は以前の記録。

## 最新：Hark更新をWindowsで確認・不具合修正（2026-10-13、一部GUI確認）

開始HEAD **e406ef257d429289ed18a4f07cd9fa48676c304f**。ローカル8fddcfaから43ファイルをff-only同期。ユーザー追加のAGENTS/vision/agent-start/design-vision・両handoff最新節・Issue4/PR5を確認。今後も「曖昧な手がかり→目的のローカルファイル」、本と素材の両方、交換可能モデル、主要機能安定後のnative UI改善を維持。実装・テスト・記録commit: **dae08a967b1981cef6e56030210c242b4980d6c9**。この後の文書commitでこのSHAを記録し、最終HEADはGit/PRを正とする。

### 維持したHark実装と修正

- CBZ/ZIP reader、関連語辞書/JSON import-export、NFKC等の正規化・複数語/部分一致検索・順位、ErrorText日本語化を保持。新しい評価manifest/順位/model/AI接続・デザイン刷新は行わない。
- Windowsの大きな不正Origin辞書POSTで403前にTCPが切断された。拒否本文を**最大16MiB/64KiB chunk/全体1秒**だけ捨て、JSONとして処理せず元の403/413を返す。遅い/未完uploadもdeadlineで打ち切り、認証・Origin・サイズ制約を維持。新HTTP3/関連語15の回帰PASS。
- ErrorTextはobject以外のJSON error bodyを状態コード案内へfallback（配列/数値/bool/stringのCore4回帰）。未知/既存日本語の扱いは維持。
- RelatedTermsEditorはbusy時に入力3欄/ボタン/listをdisableし「処理しています…」を表示。完了後restore、busy中のdialog closeはCancelして結果の見落としと編集競合を防ぐ。Root.ChangedでScrollViewer高さを更新し、狭幅でdialog全体が画面外へ出ないよう調整。modal中Ctrl+Fを背景へ送らないguard。
- **CoreにあったMatch情報がnativeの手動row描画で使われていなかった**。MatchLabelを共有し、localized kind/availabilityの前へ「関連語の候補」「一部の語のみ一致」を表示。metadata順位/filters/APIは変更しない。Light実機で表示とdirect→related順、partial説明を確認。
- **実行用AppXのdeps.jsonが10月11日のまま**で、Regex DLLは存在してもruntime dependency表にないため日本語エラーがFileNotFoundになった。Rebuild単独では更新しなかった。新しいlayoutへ`winapp run --no-launch`で配置するとdependency表にRegexが入り、旧/新のwindowless比較で欠落/解決を確認。
- `tools/winapp_layout.py`でapp/Core DLL・deps/runtimeconfig・resources/assets・manifest・project/publish設定のbytesをhash化。`start-winui.ps1`は先にbuildし、content hashごとに分かれたignored layoutで起動。変わらないpayloadは再利用。native Python suitesはfixture内のtheme layoutを使用。旧登録AppXを削除/上書きするcleanupはしない。GUIでの新launcher一連の再確認は未実施。

### Windowsで実行した検証

- **全Python211 PASS /127.403秒/skip0**。直前の208 PASS103.079秒にlayout3回帰を追加。最後のproject/publish設定をhash対象へ含める小修正後は対象3 PASS0.010秒と実layoutの起動なし配置を確認。初回205はauth拒否で1error/96.732秒、他204成功。失敗履歴と期待値を維持。
- **Core97 PASS**（Hark93＋error JSON4）。x64 SelfContained Release初回34.39秒、修正後27.26/30.73秒、最終 **Rebuild31.75秒/0error/既存IL2104 2warnings、抑制なし**。Windows XAML buildを今回確認。専用WinUI analyzer未導入・未実行、手動WinUI/transport/deployment差分レビュー済み。
- **native01 全体FAIL15 checks/1PNG全目視/keys0/skip0/正常close0/owned termination fallback1**：2件目saveの前回と同じstatus文字を早く成功判定した。DB待ち/busy状態を補強。02 **全体FAIL21 checks/3PNG全目視/正常close1**：related reasonがUIに未表示。03 **全体FAIL26 checks/5PNG全目視/正常close1**：Lightの辞書保存、busy入力/close guard、direct/related順と理由、partial説明まで確認後、17語エラーで旧AppXのRegex欠落が発生。
- 合計**9PNGを全て個別目視**。Light wide/narrowの辞書と検索理由/partial、各失敗画面のみ。narrowのfields/actionsは独立scrollの境界で一部表示、footer Closeは見える。Dark/reader/JSON pickerには**未到達**で成功扱いしない。DPI96/Contrast off。01のcleanup警告を除き02/03は警告0。3run全て生成sources bytes/mtime/hash不変。終端のAI/settings assertionsは未到達。CPU stub設計で実GPUは使わない。
- UIテストスキルの **“Maximum two fix-and-rerun cycles”** に従い03で停止。新配置にした後のGUI/native再試行はしない。導入済みの`winui-ui-testing/SKILL.md`参照（個人環境の絶対パスはリポジトリへ保存しない）。未到達のGUI gateを全体PASSへ書き換えない。
- **error-runtime-04 windowless PASS**：古いAppX depsでRegex FileNotFoundを再現、新layout depsで検索語制限/入れ子の別名error/object以外503案内の日本語3行が一致。GUIを起動しないC# probeでreader/visualの代替ではない。01はuntrim probeのSystem.Runtime facade欠落、02はtrim runtimeにないFile.WriteAllLines overload、03は生成改行の構文ミスでFAIL。04はappと同じtrim形・File.AppendAllTextを使い期待outcomeを確認。probeは作った1DLLだけを削除し、既存payloadを変更しない。
- `--no-launch`配置2種と最終hash配置でRegex dependencyを確認、元のpackage identityを維持。Python syntax/help/path guard、PowerShell AST、diff check PASS。変更後のnative suites（検索方法/AI profile/keyboard）と通常launcherを実起動で再検証していない。過去のGPU/native成績を今回へ流用しない。
- 生成PNG2/CBZ1/ZIP1・隔離DB/settingsのみ。今回のnativeはreader前で停止し、予定したCBZ revision変更も未実行。model DL/依存追加/OS設定変更/私物scan/CI dispatch/GPU/Laya起動なし。workflow3本manual-only、Draft PR5/base/unmergedを維持。前回shutdown依頼は一時的な完了済み作業として今回へ再適用しない。

### 次の3手

1. 新しい配置を使って独立したnative batchを開始。まず17語日本語error、Light/Darkのrelated/partial/dictionary、JSON save/open picker、busy/dirty保持を確認。今回FAIL履歴を維持。
2. 生成CBZ/ZIP readerのnatural order/画像・ページ番号/前後/破損/503 manual retry/real409/rescan/close cancel/別作品へのlate response/タグdraft/keyboardを確認。`tools/test_hark_ui.py`はその候補runnerだがreader部分は未観測。
3. 上記安定後、別途固定したv6で関連語の過剰展開を測定。AIとの文字側統合、フォルダ本/Komga、実DPI/Contrast/Narratorは段階を分ける。大きな見た目の刷新を前倒ししない。


再現コマンド:

```powershell
python -m unittest discover -s tests -q
dotnet run --project tests/Aredoko.Core.Tests -c Release
dotnet build src/Aredoko.WinUI -c Release -p:Platform=x64 -p:SelfContained=true --no-restore
python tools/test_hark_ui.py --output data/ai-ui/hark-native-new
# windowless probe: staged-layout must be a repository-owned build directory
python tools/check_error_runtime.py --output data/ai-ui/error-runtime-new --layout <staged-layout>
```
