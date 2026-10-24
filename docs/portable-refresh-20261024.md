# 基本版ZIP候補（2026-10-24）

## 最新候補03（source47acf2f、今回の試用入口）

- 通常入口：`C:/AI/Aredoko/dist/portable-basic-20261024-03/Aredoko/Aredoko.exe`
- ZIP：`C:/AI/Aredoko/dist/portable-basic-20261024-03/Aredoko-windows-x64.zip`
- source `47acf2f4222acc6efdb6d073e75ec66e50200223`。758 files /657,735,418 bytes、ZIP343,915,299 bytes。
- ZIP SHA256 `d3fc4b4702ece8f89b089a0a6de3fcfbf4009a640a725e29121fb732e935d5e9`。
- モデル別保存先/API/Core/native、profileごとの準備判定、アニメーションopen-first、ログのLOCALAPPDATA統一、詳細を隠したdraft保持、連続scrollのanchor修正を収録。PyTorch/モデルは含めず、製品取得catalog0件。旧01/02/Alpha/shortcutは上書き・更新しない。後続のQA/handoff commitと封印sourceを区別する。
- clean treeから新規Portable publish/実評価receipt/bootstrap self-test/同梱runtime check/全ZIP内容照合がPASS。02の固定runtime/python・mediaだけを一覧/SHA/サイズ検証して再利用、旧app/bin/configはコピーしない。
- 実同梱Pythonの基本11項目PASS（専用DB/生成PNG、AIなし・取得catalogなしでも起動・登録・検索・preview・正常EOF終了・DB integrity）。
- **通常EXEからのnative1 flow（起動＋予定内1再起動）PASS**：生成ライブラリ→設定→AI検索準備→配置/役割選択画面→正常close→登録保持で再起動。4 PNG全目視。観測handleを最初に保持し、WinUI2回/bootstrap2回すべてexit0、専用startup logs2本・元PNG SHA/mtime・設定不変・DB integrity=okを確認。正常GUI後の全758 payload SHA/inventoryも再確認し、余計なbytecode等なし。
- 同じ実binの125生成PNGで120↔121とclose後detail復帰も限定PASS（[P2正本](result-session-native-connection.md)）。これは通常入口の2起動とは別の専用backend/GUI case。
- 証拠：ignored `data/ai-ui/portable-refresh-20261024-03/` prepare.py/preparation.json/各log/backend01/report.json/native01/report.json/4 PNG/post-check.json/post-gui-inventory.json。実モデル/GPU/外部取得/通常DB/私物media/旧Alpha/OS/Actions0。正式公開/clean Windows/全AI・復元/P7受入は未完。ZIPをGitHub Releaseへ公開していない。

## 新候補02（source f508b82）

今回の形式2バックアップ・一時AI指定解除・取得モデル検証・固定registry・取得済みroot引継ぎを含む別候補。旧01/Alpha/shortcutは上書きしない。

- 通常入口：`C:/AI/Aredoko/dist/portable-basic-20261024-02/Aredoko/Aredoko.exe`
- ZIP：`C:/AI/Aredoko/dist/portable-basic-20261024-02/Aredoko-windows-x64.zip`
- 展開756 files /657,657,654 bytes、ZIP343,869,819 bytes。
- SHA256 `dbf54d3d000f7b5f9430f48bb10711666c0b8dbbaea15efc8b12d669fbfdbe7b`。
- source `f508b82d176de208305c0c4b7441953bb14356a9`。後続の表示微修正は未収録。モデル/PyTorchなし、実catalog登録0。

新規publish/実評価receipt/純粋bootstrap self-test/同梱runtime check/全ZIP照合PASS。旧01の明示runtime領域176 filesだけをSHA/サイズ/一覧照合して再利用し、旧app/bin/configはコピーしない。Core985とPortable buildの直前結果を無用に再実行しない。

CPU：同梱Pythonの実所有backendで生成DB/PNGの基本11項目PASS、形式2/復元active/pending/一時解除の8項目PASS（native ready判定の代用ではない）。日本語/空白の再配置先でも基本11項目PASS。初回の再配置probeはZIPの親を指すfixtureミスで起動前に失敗し、正しい`再配置 test02/Aredoko`で成功。raw失敗も保持。

ユーザーの追加1試行許可で、通常EXE→生成ライブラリ→設定→AI検索の準備→配置画面→閉じる→当初許可された1回の再起動を確認。新基本候補cap **1/1**、起動総数2。4 PNGを全枚目視し、今回の通常Dark/1200px相当では重なり/切れを認めない。初回終了時はGet-Processの観測handleが保持されずExitCode=nullで誤FAIL（非ゼロではない）。GUIなしのCPU再現でnull対owned0を確認し、raw report.jsonを保全。初回の終了code自体は欠測。予定内の再起動ではhandle保持でWinUI/通常bootstrapともexit0、生成登録保持を確認。追加launch/fix-rerunなし。post-checkは専用DB integrity=ok/items1、原本SHA/mtimeと起動設定不変、lease解放/対象4PID消滅。実モデル/GPU/通常DB/旧Alphaなし。

bootstrapはOS KnownFolderをログ先に使うため、試験時のLOCALAPPDATA差替えと異なり、通常アプリのログ領域へ今回の空startupログを作成した（削除しない）。backend/DB/settingsは専用領域。後続sourceでbootstrapも明示LOCALAPPDATAを使用するよう修正済み（純粋self-testのみ、新ZIP/GUI未再確認）。clean Windows/実取得/取得済みrootボタンnative/全復元の受入は未完。旧caps（環境2/2、復元3/3、取得1/2等）は維持。

証拠：ignored `data/ai-ui/portable-refresh-20261024-02/` preparation.json、各CPU report/log、native01のraw report/restart-report/post-check/4 PNG。P5/P6/P7全完了とはしない。後続の末尾区切り/idle progressバー修正はsource buildのみで、この封印ZIPを更新していない。

## 旧候補01（source875f94a）の実物と版


ソース `875f94a6746e8b1631b854d1aca5678f8406a2a1` / 既存開発ブランチ・Draft PR #5。

- `C:/AI/Aredoko/dist/portable-basic-20261024-01/Aredoko/Aredoko.exe`：通常の入口。今回自動起動していない。
- `C:/AI/Aredoko/dist/portable-basic-20261024-01/Aredoko-windows-x64.zip`：新規作成・全ZIP内容照合済み。Gitには大容量ZIPを登録・アップロードしていない。
- 展開後737ファイル / 657,566,956 bytes。ZIP343,811,217 bytes。
- ZIP SHA256 `67c555b166c0aa14f2d936d36f97b1a6ae4b34c8c4e98413ecd0f76b6654a11b`。
- 基本Python・動画ツール・自己完結WinUI・起動画面・最新backendを含む。PyTorch/モデルは含まない。AIカタログ未登録なので自動取得は公開準備中。

同梱文書は準備時snapshot。後続の引き継ぎが加わるため、Git最新HEADと実物のソースIDを混同しない。旧Alpha、ショートカット、03候補、通常DB・元メディアは更新していない。

## 準備と確認

最新Portable publish、実評価propertyに基づくreceipt、Windows標準compilerでのbootstrap build、画面を作らない --self-test、実同梱Pythonの --check、ZIP全entryの照合が成功。既知WUI1001×3/SDK IL2104×2。直前のCore974 PASSを再実行していない。

実同梱Pythonで専用DB・生成PNGのみを使用する `tools/check_basic_release.py` が11項目PASS：torchなし、独立instance、AI/取得未導入の診断、両job idle、登録scan、ファイル名検索、PNG preview、原本SHA/mtime保持、所有EOF exit0、SQLite integrity=ok。PID17572終了0。

ZIPを新しい `data/ai-ui/portable-refresh-20261024/再配置 test01` へ展開（元のZIP/候補は保持）。空白・日本語を含む配置からも別専用DBで同じ11項目PASS、PID43296終了0。これは異なる配置条件であり、22種類の別テストとは合算しない。

初回、旧03候補全体のverify_releaseは未登録のbackend __pycache__で失敗。旧ファイルを消したり全体検査を弱めたりせず、再利用する明示runtime/python・runtime/media領域176ファイルの全SHA・サイズ・正確な一覧だけを元manifestと照合した。旧app/bin/configは再利用していない。旧03全体の正常性を再認定した結果ではない。

## 証拠と限界

ignored `data/ai-ui/portable-refresh-20261024/` の prepare.py、publish/bootstrap/bundled-runtime-check logs、properties、runtime-source-verification.json、preparation.json、backend01/report.json、relocated-backend01/report.json。新規書込みは候補と生成データのみ。

新ZIPからのWinUI/起動画面のGUI・通常DB再起動・全GPU/モデル推論・開発環境のないWindows受入は未実施。今回のCPU結果をLD6/P6/完成版の合格とはしない。取得画面の先行native証拠は[別の専用候補](ai-acquisition.md)であり、新ZIPのGUI受入ではない。旧capsと全raw失敗を維持する。

次は実際に配布するruntime pack/全依存NOTICE/固定公開先を決め、builderの実物catalogとvalidatorを製品へ登録する。推測URLや架空hashで有効化しない。実取得/GPU/新GUIが必要なら具体範囲を提示して許可を得る。P5の復元picker/Start/所有bootstrap完全受入、P3性能/高DPI等の残件も保持する。

## 2026-10-25 基本ZIP：実モデル2件を列挙する候補02

- source **13778ad**、入口 `dist/portable-basic-20261025-02/Aredoko/Aredoko.exe`。ZIP `Aredoko-windows-x64.zip` **343,996,521 bytes**、SHA256 `7405a231679a81194741ab3f92d8cb65a4919d30adec26cd07399526c48a7b02`。展開 **657,889,599 bytes / 766 payload files**。モデル/PyTorchを同梱しない。旧Alpha/shortcutは更新しない。
- 直前の候補01/source4c45636でCoreテストとPortable publish/Bootstrap self-testを確認。その後のCore/tests/Bootstrapソース差分がないことを検査して、02はFrontendだけ現HEADで再publishし、01のmanifest検証済みPython/media/bootstrapを再利用。新backend/config/tools/NOTICEを新規出力先へ収録し、実同梱runtime検査とZIP全entry照合を実行。01はWDのみの途中候補で、試用の案内は02を優先する。
- 同梱Python11項目 PASS、catalog2件とその候補の固定registryの完全一致、AI未導入の区別・idle・生成画像登録/検索/preview・原本不変・EOF exit0・DB integrityを確認。raw `data/ai-ui/embedding-catalog-review-20261025/basic-cpu`。01のCPU11も別実行でPASS。
- ユーザー明示許可の**表示のみ**native1flow＋予定内1再起動：通常Aredoko.exe→専用DB→取得画面のEmbeddingGemma 2/WD・容量/ライセンス/runtime別途必要・consent前disabled→正常終了→再起動・生成画像保持がPASS。全所有WinUI/bootstrap計4 exit0、元PNG SHA/mtime・設定bytes・GUI後の全766payload inventory不変。3 PNG全目視。`data/ai-ui/embedding-catalog-review-20261025/native-display01/report.json`。
- WD PNGは選択popupが開いた状態を含み、閉じた後の表示の最終評価とは区別する。取得開始は一度も押さず、各観測でjob idle。**実1.53GB/468MB転送・推論・clean Windows・runtime pack自動取得は未検証/未完**。この候補を全媒体完成版や正式公開版とは呼ばない。


## 2026-10-25 基本ZIP03：直接取得入口と通信再試行

source **5ddd97a**。入口 `dist/portable-basic-20261025-03/Aredoko/Aredoko.exe`、ZIP `Aredoko-windows-x64.zip` **344,005,307 bytes**、展開 **657,902,853 bytes / 767 payload files**。ZIP SHA256 `f89b84306778d5b397edd1462d8ae469208d8b08affef734448aef5a487cc2c4`。旧02/Alpha/shortcutを上書きしていない。

`e46d9f8` の通信切断時の限定再接続、`d0eb214` のAI設定から「モデルをダウンロード」へ直接移動する入口、`5ddd97a` の開発用通知収集を収録。モデル2カタログ、モデル/PyTorch本体なし。Core/Bootstrapは4c45636以降のsource差分がないため合格結果と検証済み02のBootstrapを再利用し、WinUIを新規publish（既知WUI1001×3/SDK IL2104×2、0 errors）。全payload/ZIP検証・同梱Python `--check` 成功。

生成DBだけを使う同梱backend CPU11項目PASS（2カタログ、AI未導入でも検索/preview/正常EOF終了/DB integrity、原本不変）。ユーザーの追加許可で新しい直接入口だけを確認：通常EXE→設定→AI検索の準備→モデルをダウンロード→EG2容量/ライセンス/runtime別途の表示→正常終了→予定内1再起動、全11 checks PASS。取得開始・同意操作なし、job idle、設定bytes/生成原本SHA・mtime/全767 payload保全、所有WinUI/Bootstrap計4 exit0、残存なし。2 PNGを目視。WD切替は02で確認済みのため反復していない。

証拠 `data/ai-ui/embedding-catalog-review-20261025/basic03-cpu/report.json` / `native-direct03/report.json`、準備記録 `dist/portable-basic-20261025-03/preparation.json`。GUI/GPU推論・実runtime導入・clean Windows受入は別。実モデル転送の成功は[取得正本](ai-acquisition.md)に記録した専用先でのCPU転送確認で、このGUI実行での転送ではない。


## 2026-10-25 基本ZIP04（中間候補）

source **630cc55**。`dist/portable-basic-20261025-04/Aredoko/Aredoko.exe`。ZIP344,008,147 bytes / 展開657,908,397 bytes・767 payload。SHA `0d502f1c6016477cf43c73b0ec0cbc33f724b1a19b372cd89269a0dfc51ca7da`。03からGUI/Core/Bootstrapのsource変更がないことを確認し、合格済みfront/Bootstrapを再利用、backend/config/toolsを新規stageした。全manifest/ZIP/同梱 `--check` と生成専用CPU11項目PASS。04自体のGUIは未反復、03の結果を04実機合格へ読み替えない。後続のWD準備判定・初回案内は未収録。[最新sourceの引き継ぎ](current-handoff.md)を優先。


## 2026-10-25 基本ZIP05：初回案内・使い方と最終WD接続

**現行試用候補** `dist/portable-basic-20261025-05/Aredoko/Aredoko.exe`。source **0b21b3e**（製品コードc6ba386）、最終WinUI `getting-started-20261025/frontend02`。ZIP **344,023,726 bytes**、展開 **657,940,894 bytes / 768 payload**、SHA `23c5e4aa74cc4aa24e7c81ec484087aa97b94516932e74db411ff95156db05f5`。初回の空ライブラリ案内、設定の使い方・scroll、封印runtimeに基づくWD準備判定、全通信修正を収録。モデル/PyTorchなし・取得カタログ2件。旧候補/Alpha/shortcut未変更。

全payload/ZIP/同梱 `--check` PASS。同梱CPU11項目PASS（専用生成DB/検索/preview/2catalog/EOF exit0/integrity）。新しい案内のGUIは**未確認**。03の直接取得入口GUI、別途のモデル転送・GPU/CPU smokeを05のnative受入とはしない。次回はこの新候補と空/登録済み生成DBで初回案内→使い方→登録/AI準備・既存一覧保全をユーザー許可後に限定確認する。


## 2026-10-25 基本ZIP06（途中候補、後続復元修正を未収録）
source cb89799 /製品b54de9d、frontend06。入口 `dist/portable-basic-20261025-06/Aredoko/Aredoko.exe`、ZIP344,056,202 bytes、展開657,995,371 bytes/770payload、SHA256 `43cc88c63ed5c2e3fdce70259166313c141eceec29f4b68503bb7e79f035e3d5`。実runtime/PyTorch/モデルなし。基本CPU11 PASS。通常EXEで新しい一覧Ctrl+End/更新help・1回の再起動・空履歴案内を11checks、4所有exit0、770payload/設定/生成原本不変、3PNG目視（native02）。先行nativeはkeyなしTextBlock/JSON文字列の未decodeの試験誤りでhelp判定FAIL、2PNG目視・所有2exit0、生ログ保持。

追加の復元失敗caseで再選択バグを発見したため、06を最終候補としない。[復元の最新節](restore-review-20261024.md)を参照。旧Alpha/shortcutは変更していない。
