# フォルダ検索・初期棚・登録解除とAI候補の表示

2026-10-14 続き：folder-finish-03の50checksで検索/候補Light/Dark、棚・context設定・解除/復元除外Lightを確認。[最新結果](native-folder-reader-validation.md)。実モデルの精度保証ではない。

## 使い方

- 左ナビの登録フォルダを選ぶと、そのフォルダとサブフォルダを検索。「すべて」で全体へ戻る。お気に入り等の条件も併用可能。検索欄の下のExpanderでもフォルダを選べる。AI検索には既存のsaved AI対象と索引済み範囲が引き続き適用される。
- フォルダ登録で「初期棚」を選ぶ。既存棚か「新しい棚を作成」＋名前を指定。登録だけではscanしない。scanで新しく見つかったファイルへ初期棚を付与する。
- 左ナビの登録フォルダを右クリック→設定（Lightで実機確認済み）、または「フォルダ管理」から対象を選択で初期棚を保存できる。既存空棚への適用はcheckboxで明示する。個別に解除した空棚もこの一度の適用対象になるが、非空の個別棚やタグ等は維持。
- 登録解除は設定画面の許可checkbox→登録解除。元ファイルと整理情報は保持し、検索/preview/reader/scanの対象から外す。解除済み一覧から再登録でき、同じパス/IDのタグ・棚を復元する。元ファイルが移動/別内容に変わった場合の同一性保証は対象外。
- AI候補は上位/参考/すべてを切替。AI画像・表紙/AI文章の類似度の区切りは空欄で自動、数値で手動。値は同じ検索内の類似度であり正解率ではない。自動境界なしはすべてが上位側となり、参考側は空。名前/タグ全語一致checkboxは任意で、画像だけの手がかりを使う検索ではoffのまま使える。

## API

- `GET /api/items?root_id=<registered ID>`：通常検索の対象root。省略で全体。不正/未知/解除済みIDは400。
- `GET /api/library/roots?include_inactive=1`：解除済みを含める。通常省略はactiveのみ。`default_shelf`/`enabled`追加。
- `GET /api/library/shelves`：既存item棚とactive root初期棚の名前。新棚はroot登録/初期棚設定で保存する。
- `POST /api/library/roots`：従来のpath/consent/excludesに任意の`default_shelf`（80文字まで）を追加。
- `POST /api/library/roots/shelf`：`root_id`/`shelf`/任意の`fill_unset` bool（既定false）。active/scan idleのみ。
- `POST /api/library/roots/unregister`：`root_id`のみ。active/scan idleのみ。実体削除ではない。
- AI searchの任意引数：`result_group=all|leading|other`（API既定all）、`group_threshold`（cosineの[-1,1]、省略でauto）、`literal_only` bool。応答に`group_boundary`/`leading_total`/`other_total`、itemに`similarity_group`/`literal_hits`/`literal_words`。分類とfilter後にcount/paging。rank順は維持。
- library GETはsession token、POSTは従来同様loopback Host/Origin/tokenが必要。通常items GETの既存認証契約を維持。解除済みmetadataを削除するAPIは追加していない。

## 検証

最新：folder-finish-03 **50checks PASS/10PNG全目視**。右クリック設定・一括適用checkbox解除・再登録除外の残gateを確認。失敗履歴と詳細は[最新の実機結果](native-folder-reader-validation.md)。

## 履歴：フォルダGUI確認・設定状態の修正（2026-10-14、追加確認は一部残る）

開始HEAD **e4a7bc98631c845862f4f60b38b90c20f3b6d688**。Issue4/既存Draft PR5・AGENTS/両vision/両handoffを確認し、同じ製品作業ブランチを継続。実装commit **d29d3fe340cca937ae9dc3a3d7f27728482c5e14**。続く記録commitでこのSHAを保存し、最終HEADはGit/PRを正とする。

### 今回確認できたことと修正

- 新batch `folder-resume-01` **46 checks PASS**。生成9 PNG/隔離DB・settings/CPU契約encoderのみ。最終flat sidebarからfolder検索、全体へ戻る、AI画像・表紙の上位3/参考3/全6とmanual境界、未保存取消/破棄、Light/Dark・list/grid・700×620狭幅、およびLightで既存/新棚への登録、空棚への明示適用、解除/再登録とタグ・棚復元を通過。実モデルの精度評価ではない。
- 目視と手動コードレビューで、登録直後に棚choicesを作り直して「棚なし」へ表示が戻る問題を発見。**棚choices更新後に登録rootを選び直す**順序へ修正。修正後の02/03は新棚「背景」の実表示まで確認。
- 再登録prefillが別のactive rootの除外設定を使う問題を修正し、**解除root自身の保存済み除外を表示**する。root変更で**空棚一括適用checkboxを解除**し、別rootへ操作を引き継がない。これら2点はsource/Release確認、追加GUI assertionsは未到達。
- 追加runnerはsidebar右クリック→当該root設定、初期棚表示、root変更のcheckbox解除、再登録前後の除外一致を検証する。既定の保護除外を含む全リストを期待値にする。

### 検証結果と限界

- `python -m unittest discover -s tests -p test_folder_search.py -v` **11 PASS /5.789秒**、`test_ai_result_groups.py` **3 PASS /0.240秒**、`dotnet run --project tests/Aredoko.Core.Tests -c Release` **107 PASS**。変更はWinUI/runnerでPython実装・model・rank未変更のため全225件は今回再実行していない（前回225 PASSは履歴）。
- `dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore` **PASS35.25秒/0error/既存IL2104 2warnings、抑制なし**。手動差分レビュー・Python構文・git diff check PASS。専用WinUI analyzer未導入/未実行。AOT/installer未確認。
- 01 **PASS46/10PNG/正常close2**、02 **全体FAIL24/6PNG/正常close1**、03 **全体FAIL24/6PNG/正常close1**。**22PNGを全て個別目視**。01のLight/Dark、後続Lightの候補/grid/狭幅・棚状態と失敗時context menuを確認。modalの設定は意図した縦scrollでfooter Closeを保つ。名前/類似度は色以外でも区別し、raw scoreを正解率にしない。高DPI/High Contrast/Narrator/physical keyboardは未検証。
- 02はright-click後に列挙された補助HWNDのUIA inspectで`AppNotFoundException`。main/PopupHostへ対象を絞って03でも同じ失敗（missing HWNDはmainと異なり、失敗画像には別の有効menu popupが見える）。**メニューから設定へ入る操作は未完了**。最後に当該エラーの補助HWNDだけを記録して除外するrunner修正を加えたが、これ以降のGUI再実行はしていない。mainの不達・他CLI error・menuが見つからない場合は引き続きFAILとする。
- インストール済み`winui-ui-testing/SKILL.md`の **“Maximum two fix-and-rerun cycles”** に従って03で停止。01の成功を、追加修正の未到達assertionや全体GUIの成功へ流用しない。前回native01/02/03のfailed evidenceも保持。
- 全3runで生成9 sourceのbytes/mtime/hash不変。01ではsettings bytes不変も終端で確認、02/03は終端assertion未到達。cleanup warning0、正常終了後に所有appなし。個人素材scan/変更/外部送信、model DL、GPU/Laya、依存追加、OS変更、CI dispatchなし。3workflow manual-only、既存Draft/base未マージ。

### 次の3手

1. 最終runnerで新native batch：有効context menuからroot設定へ入る、root変更の空棚適用checkbox解除、再登録時の当該root除外・棚・タグ一致を確認。FAILED補助HWND記録と既定除外の期待値を保持。
2. Hark追加reader/関連語の残gate：17語日本語error、Light/Dark辞書・JSON picker、CBZ/ZIP readerのページ/破損/retry/revision/late-response/dirty/keyboard。今回のfolder Dark確認と辞書/reader Darkは別。
3. 検索方法/AI profile回帰と固定の新入力で候補境界の取りこぼし評価。自動区切りをconfidence/キャラ精度として扱わず、OCR/VLM・フォルダ本・Komgaは別工程。

---

## 履歴：フォルダ検索・棚設定・登録解除・AI候補の表示分離（2026-10-13、GUI部分確認）

開始HEAD **35cd6f43f3e0ba7c2232d94a15ec271be0a7b189**。既存Draft PR5/baseを継続。実装・テストcommit: **fe92117354b170eacde30b26a92ec18527fef5a1**。この後の文書commitでSHAを記録し、最終HEADはGit/PRを正とする。ユーザーから実ファイルのキャラ名・NSFW語・画像内文字でヒットした報告あり。これはユーザー観察で今回の精度評価ではない。添付画像/私物/パスをテスト・保存・外部送信していない。

### 追加した実装

- 通常検索`root_id`をcount/順位/ページング/関連語/partialより前に適用。未指定は全体、登録フォルダの全サブフォルダを含む。未知/解除済み/不正IDは400、全体へfallbackしない。GUIの選択rootはAIのsaved scopeと積集合（空/非交差を保持）。AI対象・索引上限10,000・モデルnamespaceは既存のまま。
- rootの`default_shelf`/`enabled`を追加移行（旧rootは棚なし/enabled=1）。登録時に既存棚か新規棚を選択。初期棚は新しく作るitemだけへ適用、再scan/再起動は個別棚の変更・解除/タグ/お気に入りを上書きしない。選択rootの初期棚編集と、**明示的なcheckboxで既存の棚未設定present itemに一度適用**するAPI/UIも追加。この操作は個別に空へ戻した棚を含むことを表示し、既存の非空棚や他rootは変更しない。
- 登録解除は`enabled=0`。元ファイル、location/item、整理情報、vectorは削除しない。通常/AI/preview/readerから外し、scan中は409。解除済みルートの再登録は同じroot/itemを利用し、整理情報を復元。復元時も全active rootとの重複/入れ子を検証。変更/移動した別ファイルの同一性追跡機能を追加したわけではない。
- 左ナビに登録rootと解除済みroot、root設定のcontext menu、解除済みrootからパス・初期棚をprefillする再登録入口を追加。GUI修正の最後に**階層menuを直接並ぶnative項目/見出しへ変更**。広幅/狭幅のpane制御、未保存取消の検索条件rollbackを維持。最終ナビ/設定/再登録の実GUI確認は残る。
- AI画像・表紙/文章は**上位の類似候補・その他の参考候補・すべてのAI候補**を別表示へ切替（GUI初期値leading、既存API既定all）。検索結果内のcosineの落差から表示境界を提案し、手動境界[-1,1]にも対応。先頭32件の最大gapが0.03以上かつgap中央値の4倍以上の場合のみ、その隣接値の中間を提案。**未校正の表示heuristicでありキャラ判定の確度/正解率ではない**。明確な落差なしは自動で切らない。同値を分断しない。全件を分類/絞り込みしてからpagingし、元のscore順位を維持。RRFはcosineの閾値を受け付けず、別尺度として表示。
- 名前/タグの全語一致・一致語数とraw scoreを表示。文字一致フィルターは任意/既定offで、名前を持たない画像ヒットに必須にはしない。score表示を2行にし、検索範囲/候補設定をExpanderへまとめて狭幅の一覧を圧迫しない。model/weights/embedding/vector/rankingの変更なし。

### 実施した検証と限界

- **Python225 PASS139.602秒/skip0**（前段223 PASS106.547秒）。新folder11 PASS5.996秒、group3 PASS0.212秒。旧schemaのテスト初回9でSQLite接続を閉じずWindows cleanup error→テスト接続を修正して9 PASS4.365秒。その後棚編集/解除済みrouteの2件を追加。scope/paging・related/partial・初期棚/個別解除/再起動・旧schema・再登録/preview拒否/重複・認証・AI境界/同値/尺度/解除後のvector不可視を確認。
- **Core107 PASS**（従来97＋request/protocol/evidence10）。最終 **x64 SelfContained Release PASS29.27秒/0error/既存IL2104 2warnings、抑制なし**。中間Release32.43/29.99/28.94/30.46/30.40/30.29秒もPASS。左ナビ追加直後はCS0136＋付随XAML errorでFAIL6.52秒→変数修正。C#source/XAML、既存refsのComboBox/NumberBox/Expander/NavigationView/header APIとcached sampleを確認。手動差分レビュー済み。専用WinUI analyzer未導入/未実行、AOT/installer未確認。
- **native01 FAIL7checks/1PNG全目視/正常close1**：閉じたpaneで階層root peerが現れず。02 **FAIL15checks/4PNG全目視/正常close1**：Lightのfolder filter、上位3/参考3/全6切替、score/根拠、gridまで確認。manual0.850は画面に表示したが、最後の要求値の完全等値assertがFAIL（失敗時の要求ログ未保存のため原因は断定しない）。比較を許容誤差へ変更、以降は失敗時も要求を保存。03 **FAIL7checks/1PNG全目視/正常close1**：変更したpane表示でroot peer未出現、AI要求0。
- 合計**6PNG全て個別目視**。native03後に階層を直接項目へ変更しbuild確認、追加GUI起動はしていない。**最終flat nav・棚選択/一括適用・解除/再登録・dirty rollback・Dark・narrow・最終2行scoreは実GUI未完了**。これらをnative PASSとしない。全3runの生成PNG9ファイルbytes/mtime/hash不変、正常終了・cleanup warningなし。終端のsettings bytes assertionは未到達。DPIはtree96、High Contrast/読み上げ/physical keyboardは未検証。
- UIスキル`winui-ui-testing/SKILL.md`の **“Maximum two fix-and-rerun cycles”** に従い03で停止。修正後の最終GUIは次の独立batchで確認する。backend/Core/build成功をGUI成功の代わりにしない。
- runtimeはCPU契約encoder＋手動の生成vector、実GPU/検索精度の証拠ではない。私物scan/元メディア変更/依存追加/model DL/GPU/Laya/OS変更/CI dispatchなし。workflow3本はmanual-only。前回のHark reader等のGUI未到達は今回も未完了。

### 次の3手

1. `tools/test_folder_ui.py --output data/ai-ui/folder-native-new`を新batchで実行し、flat nav・棚設定・解除/再登録・dirty/Light/Dark/narrow・候補切替と手動境界を実機確認。初期tree/失敗ログを保持、floatの差を内容判定の失敗と混同しない。
2. 既存の検索方法/keyboard/AI profile GUI回帰、およびHark reader/JSON pickerの未完了gateを別に確認。解除rootを含むsaved AI scopeは明示的に選び直す（全体へ黙って広げない）。
3. 候補境界の便利さ・取りこぼしを新しい固定評価とユーザーが明示選んだ小サンプルで測る。現在のheuristicをconfidenceや実キャラ分類精度として扱わず、自動内容索引/OCR/VLMは別工程として進める。
