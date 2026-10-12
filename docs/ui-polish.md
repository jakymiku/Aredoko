# WinUI画面の整理と実機検証

2026-10-12。製品WinUI 3を維持し、既存画面を読みやすくする小さな改善。Hallmarkのaudit/anti-pattern/slop-testを画面評価の観点として使い、WinUI design/review/testingの手順で実装・確認した。ネイティブFluentの字体/テーマ/操作を優先し、Web向けCSSやモバイル合格判定をWinUIに転用していない。

<!-- Hallmark · pre-emit critique: P4 H4 E4 S4 R5 V3 -->

## 評価と変更

| 旧画面での課題 | 変更と意図 |
| --- | --- |
| 選択前から右側が空の詳細領域だった | 初期表示と検索更新時は閉じ、作品を選んだ時に詳細を開く。一覧の幅を使う |
| 行のタイトルと補助情報が同じ強さだった | タイトルをSemibold、補助情報をCaptionとsecondaryのテーマ色へ。長いファイル名の一覧を読みやすくする |
| 検索欄/件数/操作欄の関係が弱く、狭い画面で横に詰まった | 検索欄に見出し、検索に標準AccentButtonStyle、件数をヘッダーへ。840 DIP未満で操作群を二段にする |
| 設定の説明が長いと小さいdialogで収まりにくい | AI設定の内容だけを高さ制限付きScrollViewerへ。閉じるボタンは固定のdialog footerに残す |
| AI非対応/失敗時の中央案内が汎用の再接続文だった | 名前・タグ検索やAI索引設定を案内し、古い件数/ページ操作も消す。具体的エラーは既存InfoBarで示す |
| 詳細編集の境界が見分けにくい | ネイティブのCardStroke/角丸/余白で一つの編集領域を示す |

既存のListView.Items/60件paging、AutomationId、タグ保存/未保存確認、async/stale対策、JSON DOM、モデルprofile/index identityは維持した。素材には実際の生成プレビューを使い、表示できないファイルは既存の「プレビューなし」。新ライブラリ/モデル/OS設定変更なし。

## 実機結果

Windowsローカル、生成17ファイル、専用DB/settings。個人ライブラリとAppData設定は使用していない。

```powershell
python tools/test_ai_profile_ui.py --editor-only --output data/ai-ui/profile-editor-02
python tools/test_ai_profile_ui.py --editor-only --layout-checks --output data/ai-ui/ui-polish-02
```

同名outputが存在する時は新しいsuffixを使う。前者はUI整理前の編集回帰11 checks PASS、後者はUI整理後32 checks PASS。どちらもAIをロードしない `actual_model=false / profile_verification=not_run` の軽量バッチ。

- 保存完了表示とAPI反映を待ち、お気に入りの保存、未保存タグで「編集を続ける」、元のDBタグ保持、再起動後のAPI値と実checkboxのonを確認した。
- 1200×820の一覧/タイル、700×620の検索/操作ボタン・件数、同サイズの不足モデルdialogで候補/警告/閉じるが画面内にあることをUIA boundsで確認した。
- 最終6 PNGをすべて目視した。`10-wide-library.png`, `11-wide-tiles.png`, `12-narrow-library.png`, `08-dirty-guard.png`, `09-editor-restart.png`, `13-small-missing-dialog.png`。一覧PNGにはCLI合成のCtrl+F tooltipが写る。
- 所有HWND/PIDを確認したサイズ変更とWM_CLOSEで、4回のGUI終了が正常。最終バッチにcleanup warningなし。所有GUI/API/worker残留なし。
- 開始/終了の生成元ファイルhashが一致。証拠はignoredの `data/ai-ui/ui-polish-02/result.json` とsource-hashes.json、PNG/UI treeに保存し、Gitへ含めない。

初回 `profile-editor-01` は既定の文字検索を再選択する不要なfocusでFAIL。現在値を検査するよう修正して02 PASS。`ui-polish-01` は32 checks PASSだが旧cleanupはforeground依存で警告を残したため、所有HWNDへ通常の閉じる通知を送るcleanupへ改善し02を再確認した。失敗/警告履歴を消さない。

```powershell
python -m unittest discover -s tests -q
dotnet run --project tests/Aredoko.Core.Tests -c Release
dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore -v:minimal
```

Python96 tests、C#13 checks、WinUI Release PASS。従来のSDK IL2104警告2件は抑制していない。native screenshot/UI treeは実行した範囲の証拠で、WinUI analyzerは未導入。

## まだ確認していないこと

今回のnativeはdark/通常DPI。Light/HighContrast/高DPI、スクリーンリーダー、ピッカー全体、Native AOT/配布、1TB性能は未確認。数値的な色コントラスト合格も主張しない。標準のテーマ資源を使い、今回の実画面ではラベル/警告が読めることを確認した。

AI失敗時の案内変更はbuild/code reviewまでで、非対応画像modeの実AI操作は今回未実行。全モデル切替/GPUバッチも今回再実行していない。前回profile-picker-06はモデル段階到達・全体FAILとして記録を保持し、今回の別バッチで残った編集/再起動を検証した。モデル結果は[model-profiles.md](model-profiles.md)を参照。

次はtheme/DPIとAIエラー復帰を実機確認。その後、2,000件超のcheckpoint/増分/resource制限と、明示選択された小さな実サンプル評価を進める。本文/OCR/読書/Komgaは別の実装段階。
