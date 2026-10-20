# 実使用フィードバックと就寝中の改善（2026-10-21）

## 今回の依頼と検証範囲

ユーザーは16項目の不具合/改善点を報告し、その後「短時間で改良可能なものを切りの良いところまで進め、引き継ぎ後にPCをシャットダウン」と明示。今回に限りGUI/GPU検証を新たに許可した。GPUは今回のUI/閲覧修正には不要。**ビューワーの目標はHoneyViewと同等の表示/ページ切替速度、小さい画像を画面いっぱいに拡大できること。** 未計測のまま同等と称さない。内蔵の実測改善が不十分ならOSS viewerの組込みを検討する（対応形式/ライセンス/再配布/操作統合/索引分離を比較し、未承認依存取得をしない）。

旧GUI上限は消さず、今回の新許可に対する固定flowを`overnight-feedback-20261021`、生成画像/GIF/APNG/CBZ/専用DB、通常1200×820/Light・Dark、initial+最大2修正とする。Windows Sandboxは無効のためlocal。既存Aredoko/portがあるときは拒否し、ユーザーの既存GUI/私物DBへ接続しない。生成原本のbytes/mtime不変、所有GUI/API終了も確認する。通常shutdownの許可であって、他アプリの未保存内容を強制破棄する許可とはしない。

## 要求の全件台帳

| ID | 指摘/希望 | 今回の対応と残り |
| --- | --- | --- |
| U01 | GIF/CBZ表示・切替をHoneyView並みに | GIFは全フレーム個別取得/PNG変換の事前待機を廃止し、原本1取得＋Windows標準animationへ。元streamを再生中保持。CBZのsource段階は計測済み、Windows描画は継続課題。HoneyView同等は未受入 |
| U02 | GIF/APNGのループ時の黒いちらつき | GIFのsource差替えループを廃止。APNGのdefault image（poster）を再生frameから除外。生成CPU回帰合格、全実素材で解消したとは未宣言 |
| U03 | 登録フォルダクリックの反応 | FolderListを標準Single selectionへ変更し、pressed/selected表示を使う。個別settings/複数選択checkboxは保持 |
| U04 | ZIPのExplorer表示がDocumentsへ行く | 文字列の`/select`引数を廃止しSHParseDisplayName/SHOpenFolderAndSelectItemsへ。元path検証/祖先link guardは保持。実shell選択は要確認 |
| U05 | 検索結果/説明footerが不要 | 通常のinformational footerを非表示。error/warningは残し、不具合を無言で隠さない |
| U06 | 未確認/確認済みは削除可 | ユーザーの今回の個別削除指示を、従来の一般的な機能維持より優先してUIを廃止。既存DB/APIのreviewed値は保全。元用途は整理進捗の印で、削除を妨げる必須依存はない |
| U07 | 全フォルダdropdownをやめ、scope中だけ解除付き表示 | 常設root選択を非表示、登録フォルダから絞った場合だけ独立scope badge＋隣接「解除」を表示。AI候補/境界操作はAI用expanderに保持 |
| U08 | ファイル名・タグへ改名 | 主要画面/検索方法/案内をファイル名・タグ、ファイル名・タグの意味へ変更 |
| U09 | フォルダもお気に入りに | **未実装**。現在のitem favoriteはfilesのみ。root favoriteの永続化/既存DB・backupとの契約と一覧統合が必要。旧item型への偽装やscope外データ混入で済ませない |
| U10 | 右クリックfavorite/詳細チェック即時保存 | menu操作とfavorite専用POSTを追加。他の未保存tag/shelfを巻き込んで保存しない。失敗時はチェックを戻す |
| U11 | 棚を選ぶと中身を見る | **未実装**。棚ごとの入口と正確なshelf filterをAPI/AI/ページングまで一貫させる必要あり。取得後のclient filterで件数/ページを偽らない。現在の棚別default/編集は維持 |
| U12 | サイズ変更時の件数/余白再配置 | viewport幅とscaleから列数/セル幅を再計算して行を埋める。選択/draft/サムネイルを保つ。ページ内の表示密度改善であり、APIのページ上限変更は別途 |
| U13 | backup/復旧をGUIで実行 | **未実装**。停止時lease/全DB/AI設定の一貫性を保つ停止→所有worker終了→backup/新規先restore→再起動controllerが必要。動作中DBへCLIを投げるだけの危険な短縮実装はしない。PZ2所有bootstrapと接続する |
| U14 | マウス進む/戻るで前後ページへ | viewer内は既存入力を維持。library検索ページの前へ/次へにside buttonsを接続。全画面/棚/rootの一般的なnavigation履歴は未実装 |
| U15 | 小さい画像を画面いっぱいに | settingsのtoggleで画像/本のfit時に小画像も拡大。原寸との切替も保持。AI超解像/Lanczos指定ではなくWindowsの表示拡大 |
| U16 | 設定からLight/Dark切替 | system/light/darkを保存して反映、旧viewer設定と後方互換。表示サイズ/ホイール設定を相互に消さない |

## 実装・検証記録（今回のバッチ確定）

- 開始HEAD `56d7b3c`、fetch/status一致/未コミット変更なしから開始。既存production branch / Draft PR #5を継続。新モデル/依存取得・GPU推論・私物走査・原本/実DB/元venv変更・Actions/main mergeは行っていない。 更新Markdownの414相対リンク/変更Python構文/diff確認合格、全3 workflowsはmanual dispatch限定。
- **CPU Python31 PASS**：`test_animation_playback_sources.py`3件（APNG poster有/無・GIF）、`test_previews.py`22件、`test_original_viewer_sources.py`6件。既存AI venvのPillowを使用、GPUなし。Core Release **732 PASS**（後方互換/テーマ・拡大・サイズ保存、列数/行幅を含む）。Release **0 errors / 既知5 warnings**（WUI1001×3、SDK IL2104×2、抑制なし）。最終ログは`data/ai-ui/usability-*-20261021*.log`。 最終用語統一後の`usability-build-20261021-final2.log`も0 errors/5 warnings（31.30秒）。この文言差分は上限後のbuild確認のみで、GUIを再実行していない。
- WinUIコードレビュー：新APIのproject参照確認、stream生存/終了、キャンセル/選択競合、favorite単独保存、原本path guard、UIA識別子/theming/設定の後方互換を確認。既存code-behind/日本語文字列構成は維持し、無関係なMVVM全面変更はしない。既知picker/trim警告を未解決のまま記録。

### CPUの表示用データ計測（Windows描画速度の保証ではない）

`tools/measure_viewer_sources.py --output data/ai-ui/viewer-sources-20261021-01`を実行、report PASS / source bytes・mtime不変。生成GIF48 framesの旧manifest+全PNG frame準備 **0.374015s** → 新経路のoriginal source読取 **0.015847s**。生成64ページ/59,501,014 bytes CBZのmanifest+1ページ原本+読書位置保存（10サンプル）中央値 **0.019942s**。HTTP/Windows decode/画面描画を含まず、HoneyViewも計測していないため、約24倍の体感改善や同等速度と解釈しない。 旧経路→新経路の順の1組でOS cache/順序効果を分離していない。CBZはまずHTTP/Windows decode/提示までを分離してボトルネックを確認する。guardを省略するcacheは導入していない。

### native固定flow：3/3で停止、総合PASSにはしない

`tools/test_detail_actions_ui.py --feedback-only --output data/ai-ui/overnight-feedback-20261021-0N`。生成18アイテムの専用DB/設定、所有PID/HWND/実DLL・deps・resources SHAを証明した現行x64 Release、通常1200×820/96dpi、AI/GPU無効。旧flow/capは保持。

1. **01 FAIL（製品不具合）**：Lightのfavorite即時保存・未保存tag保持/配置/設定まで確認後、拡大viewerがXAML stowed exceptionで異常終了。準備時1px仮寸法から小さすぎるScrollViewer.MinZoomFactorを設定していた箇所を修正。minimum1を固定し、小画像の原寸はcanvasサイズで戻す。2 PNG目視済み、失敗/cleanupエラー保持。
2. **02 FAIL（harness）**：修正後GIF/APNG/CBZ表示とCBZページ送り成功。FolderList検査でUIAに存在しない`isSelected`fieldを待って停止。settings表示を検査するように変更、sourceもSelectedItemを明示。6 PNG目視済み、所有GUI正常終了。
3. **03 FAIL（harness）**：Lightはscope表示/隣接解除・folder clickを含む全工程まで成功。Darkはfavorite即時保存/未保存draft保持、footer/dropdown/確認済み非表示、60%6列→180%2列、テーマ切替、GIF/APNG表示が成功。共有DBの保存済み2ページ目からNextで3ページ目へ進んだのに、固定「2 /」を待ってtimeout。製品異常終了はない。停止後read-only DBで`reader_progress.page=2`（0始まり=3ページ目）、18件、favorite=false/タグ[]、`integrity_check=ok`を確認。13 PNG全件目視済み（01/02を含む計21 PNG）。

03の`post-stop-review.json`へ追加目視・DB検査を別記し、raw reportの`pass=false`は変更しない。Libraryの生成APNGサムネイルは黒いposterを表示したままで、**残る別問題**。viewer内は色frameが表示される。snapshotは複数ループ後の時点確認に留まり、すべての瞬間/実素材のちらつき解消を保証しない。03では開始時source digestをprocess内だけで保持し、最後の不変比較へ到達しなかったため、このnative runの開始前後SHA/mtime一致を認定できない（CPU計測では一致）。今後のharnessはbaselineをreportへ保存する。

03 UIA-ready値（CLI往復を含む）：Light GIF0.906/APNG1.390/CBZ1.125秒、Dark GIF0.875/APNG1.329/CBZ1.140秒。小さい生成媒体であり、HoneyView比較・冷起動p95・CBZ大冊ページ送り性能ではない。Light/Darkのsettings PNGは即時切替を確認するため**起動themeと反対のtheme**を選択している。

上限後のharness修正は保存済みページから前後の期待値を計算する変更とbaseline永続化のみ、構文確認済み・GUI再実行なし。Shell APIのZIP選択、favorite右クリック、library side buttonsは実装/静的・build確認で、今回のnative操作対象には含めていない。追加GUIは次回のユーザー明示許可後。所有テストGUI/API終了とport8769解放を確認、GPU0回。

現在インストール済みAlpha1.0.0.1/封印済み`dist/alpha-0-msix-20261021-02`は更新していない。**今回の改善はsource/現行Release buildにあり、旧Alphaショートカットからは反映されない。** ZIP製品は未完成、R13 DOING / ALPHA未完 / R14 PARTIALのまま。

## 次に継続する順序

U01/U02の実素材相当の計測と残るループ/CBZボトルネック→PZ2起動入口/進捗→PZ3 model導入3経路/無制限既定/全runtime→PZ4 ZIP→PZ5 clean Windows。U09/U11/U13/U14全体履歴は別の明確な未完タスクとして保全。ALPHA後の実音声/音楽R06–R09とWinUI改善、P0 2/2閉鎖/OCR保留、原本/実DB/元venv保全/簡潔GUIを維持。新依存/model取得・私物scan・Actions/main mergeなし。

今回の作業が終わったらGitHubへ結果/残件を保存し、所有testプロセスを終了してshutdownする。この一度の指示を、将来の再開時の自動shutdown指示へ転用しない。
