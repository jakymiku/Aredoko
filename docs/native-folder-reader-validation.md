# フォルダ管理・読書画面のWindows実機確認

## 最新：フォルダ設定gate通過・読書画面の修正と実機確認（2026-10-14 続き）

開始HEAD **ff87f99a35f4027dc172d9d3d1e0f837a1a22038**。AGENTS/vision/design/両handoff/Issue4/既存Draft PR5を確認。同じ製品branch/baseを継続。実装commit **83851e1b7582772695786ee1376c046cb1ed1963**。続く記録commitでこのSHAを保存し、最終HEADはGit/PRを正とする。

### できるようになったことと修正

- **folder-finish-03 50 checks PASS**。Lightのsidebar右クリック→当該root設定、root切替時の空棚一括適用checkbox解除、初期棚の実表示、解除root自身の除外prefillと再登録後一致、タグ・棚保持まで確認。Light/Darkのfolder検索・全体復帰・AI上位/参考/全候補・手動境界・dirty取消/破棄・list/grid・700×620狭幅も完走。実モデル品質の評価ではない。このbatchはreader修正より前。
- 読書を狭幅で閉じると詳細paneが隠れたため、**元と同じ選択itemの詳細paneとopener focusを復帰**。未保存のタグを保存/破棄せず保持する。readerのGridを有限高さ＋先頭star rowへ変更し、画像だけを伸縮、wideで切れた再試行/再openを表示内へ収める。
- **reader-followup-03 105 checks PASS /実入力14/skip0**。Light/DarkでCBZ自然順（page2赤→page10青→page20緑）、最初/最後の前後disabled、ZIP破損ページの旧画像消去/スキップ、503手動retry、生成CBZ更新による実409→閉じる/rescan/再openで4ページ、遅延要求cancel→別本へのlate response混入防止、タグdraft保持とEsc/opener focus、modal内Ctrl+S/Ctrl+Fを確認。
- 関連語のLight/Dark保存・busy入力disable/close延期・再起動保持、direct-before-related理由、partial説明、17語の日本語errorも通過。**JSON save/open pickerは今回操作していない**。辞書と検索順位/model/worker/APIは変更なし。
- runnerはowned popupを優先し、expired auxiliaryを記録、window/tree証拠を保存。検索は既存300ms debounceのrender後にready/inspectしてから明示button操作する。失効したpeerは画面更新後のAutomationIdで取り直す。

### ローカル検証・失敗履歴・限界

- **Reader API16 PASS8.007秒 /関連語15 PASS10.211秒 /Core107 PASS**（Coreは既存Releaseのno-build）。全Python225やfolder/group14は今回は再実行していない。backend/Core/model未変更のため前回のfull成績を今回へ移さない。
- **x64 SelfContained Release PASS27.16秒/0error/既存IL2104 2warnings、抑制なし**。app refsのGrid/IsPaneOpen/Control.Focus API、Gallery ContentDialog例、layout-reviewを確認。Python構文・diff check・手動WinUI差分レビューPASS。専用WinUI analyzer未導入/未実行、AOT/installer未確認。
- folder01 **FAIL24/6PNG/正常close1**（menu候補判定；初回候補数の記録なし）、02 **FAIL37/7PNG/正常close2**（Light設定完走後、Dark検索buttonのpeer失効）、03 **PASS50/10PNG/正常close2**。**計23PNGを全て個別目視**。補助popupに同じmenuが重複していたとは初回の証拠だけで断定しない。
- reader01 **FAIL1/0PNG/アプリ未起動**（query helperのインデント誤りでowned HWND取得前のreadyを実行）。02 **FAIL40/9PNG全目視/実入力3/owned termination fallback1**（狭幅readerを閉じるとTxtTagsが非表示；タグ削除ではない。wide下部actionの切れも目視）。03 **PASS105/24PNG全目視/正常close2/cleanup warning0**。**reader計33PNG、今回全体56PNGを全て個別目視**。前回失敗と旧AppX dependencyの履歴も保持。
- 両batchともUIスキルの **“Maximum two fix-and-rerun cycles”** の範囲で終了。最後のrunはPASS。追加GUI再実行なし。readerの最初/最後・破損/503/409・cancel後とLight/Darkを目視し、操作/状態/閉じるが表示内に収まることを確認。辞書のnarrow bodyは意図した縦scroll、footer Closeを保持。
- **実DPI96 /High Contrast off**。High DPI/Contrast/Narrator/Tab全順序/reader zoomと直接Reopen button/元解像度品質・大規模負荷は未検証。今回は小さな生成素材の接続/状態確認で検索精度の証拠ではない。
- folder全3runで生成9file bytes/mtime/hash不変、03終端でsettings bytes不変。reader全3runでsource境界確認、03では明示した生成book.cbzの4ページ化/テーマ前resetのみ許可、他PNG/ZIP bytes/mtime/hashとsettings bytes不変。AI推論/worker0、ユーザー素材scan/変更/外部送信、model DL/依存導入/OS変更/CI dispatch0。最終owned appなし。3workflow manual-only、Draft PR5/base未マージ。

### 次の3手

1. 生成JSONのみで辞書save/open picker：export実count、importのmerge/replace/cancel/invalid/サイズ上限を実操作で確認。所有picker HWNDを検証し、私物fileを選ばない。
2. readerの直接Reopen/zoom/Tab、検索方法/AI profileと既存keyboard回帰を小さな専用batchで確認。High DPI/Contrast/Narratorは実施条件を分け、OS設定を無断変更しない。
3. 新しい固定入力で候補区切り・関連語の取りこぼし/過剰展開を測定。confidenceや実キャラ精度の宣言にしない。フォルダ本/OCR/VLM/Komga・将来ビジュアル刷新は別段階。

---

