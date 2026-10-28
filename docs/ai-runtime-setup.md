# AI追加環境とモデル保存先：LD3実装

> **2026-10-25 現在**：既存配置のnative画面、モデル別保存先、モデル2件の取得は[AI取得正本](ai-acquisition.md)まで接続済み。以下の「GUI/取得未実装」はLD3当時の履歴。runtime自動取得はまだ公開していない。[通知収集と同梱](runtime-notice-inventory.md)で実配布の不足を整理し、必要な権利review/公開先が揃ってから登録する。


## 2026-10-26：起動照合・高度な設定

- 設定→「高度な設定」→「AI実行環境の全ファイルを照合する」を追加。`verify_ai_runtime` は省略時/既定オン、厳密なbool。利用者がオフで保存した場合のみ、**次回バックエンド起動から**大きなruntime packの全ファイルSHA-256照合を省略する。実行中の方針/モデル/索引namespaceは変えない。
- オフでもmanifest binding、Python実体/ABI、moduleパス、coreファイルと通常パスの確認を残す。取得時・配置選択時の完全検証は常に行う。基本ZIPの検査やモデル取得検証を一括で無効にする設定ではない。
- `POST /api/library/ai/runtime-verification {enabled: bool}` は既存token/Origin/JSON重複拒否と設定writer fence/atomic replaceを使う。他のlaunch設定を保全。setup GETに保存値/起動時の値を返す。AI環境の選択ジョブ中は409、未知field/整数/文字列は400。
- 起動時の背景照合は終了・復元前に取消/待機する所有jobへ変更。待機時間切れを成功扱いにせず、取消途中のhashを検証済みcacheへ登録しない。待ち行列も進捗対象にし、同じpackの二重起動を抑止。
- HTTPの15分上限はAI検索作成とWD初回生成だけに限定。通常通信40秒/タグ管理100秒へ戻し、照合状態の確認は5秒上限＋検索取消/画面終了tokenを渡す。結果のrange/closeは短い通常transportを使う。旧検索のfinallyが新しいモデル読込表示を消さない。
- UTF-8固定/Portable初期化修正はAntigravity差分を採用。worker stdoutの失敗応答は例外型に限定し、詳細traceはローカルstderrへ。無視する`__pycache__`自体のリンク/reparseは拒否する。選択済みpackを実行中に同じユーザーが改変しないという既存前提は残る。
- CPU：runtime33/WD11/設定job15・Core関連・Portable publish PASS（既知のWUI1001/SDK IL2104を抑制していない）。生成nativeでは高度な設定の既定オン→オフ保存→再起動保持をDark通常幅で確認。中止・終了の所有テストも追加。証拠 `data/ai-ui/startup-review-20261026/`（Git対象外）。
- 既存pack/既存モデル＋生成PNG2枚の実GPU：全照合1回、CUDA索引2件、日本語cover検索2件、モデル解放→再読込を確認。packは23,903 files / 4,947,898,990 bytes、照合87.324s、解放後検索15.386s、warm検索0.162s（各1回、一般性能保証ではない）。原本不変、所有job終了。公開runtimeの権利/hostとclean Windows受入は未完。
- 通常`Aredoko.exe`入口の基本ZIP02/source `42c0743`でも専用設定/生成DBで実機確認（`basic-native-ai03`）。既定オンの背景照合中に検索待機を取消→設定へ移動→オフ保存→照合中に正常終了→再起動で全照合省略→モデル読込表示→日本語CUDA検索2件までPASS。frontend/launcher計4所有プロセスexit0、4PNG目視。追加取得なし、通常DB/設定/元メディアは未変更。01/02の失敗はハーネスselector問題/取消の自動再実行不具合の記録として保持する。取消不具合は`42c0743`で修正済み。

> **2026-10-22 LD4a追記**：[既存folderの背景検査job/API](ai-setup-jobs.md)を実装。下の「GETだけ/HTTP保存未実装」はLD3時点の履歴。現在は非同期start/status/cancelまで対応し、製品GUIとdownloadは引き続き未実装。

2026-10-21。[配布計画LD1–LD6](lightweight-distribution.md)のLD3。基本Pythonと、ユーザーが明示的に選ぶAI実行環境を分離するCPU基盤。**製品GUIでの選択・自動ダウンロードはまだ利用できない**。旧installed Alpha、旧配布、普段のDB/設定/モデルは変更していない。

## 実装したこと

- `app/ai_runtime.py`：追加packのmanifest、Python ABI/arch、CPU/CUDA方式、PyTorch版、必要module、全file SHA/通常pathを検証する。`aredoko-ai-runtime-v1`と`aredoko-ai-runtime.json`が独立した契約。Python3.11以上/x64/PyTorch、必須torch/transformers/sentence_transformers/numpy/PIL、任意onnxruntime/laya/tokenizers/safetensorsを記録する。版の宣言は実行互換性の証明ではなく、今後の取得catalog/adapterが対応版を固定する。
- `tools/prepare_ai_runtime_pack.py`：明示された既存の準備済みstandalone環境を**新しい出力先**へpack化。入力を変更せず、旧アプリへの外部`_pth`参照を出力側だけで除く。Torchのversion.pyはASTの定数として読み、import/実行しない。`--check`は出力も作らない。download/pip/driver操作なし。
- `app/ai_runtime_preferences.py`：実行環境とmodels rootを別々に検証/保存/リセットするサービス。実行環境は全SHA検証後にmanifest SHAと場所を保存する。明示consent、storage lease、fresh temp→flush/fsync→replace、取消に対応し、失敗時は古い設定を保持。database/theme/viewer等の既存fieldは保持。新runtime選択時は旧ai_pythonだけ置き換える。CLIで明示された従来ai_pythonは従来通り優先する。
- `tools/configure_ai_locations.py`：開発用の明示設定CLI。`--settings`必須、保存には`--consent`必須、指定なしなら読取りのみ。利用者にこのCLI/Python操作を要求する製品仕様ではない。JSON出力はWindowsの既定文字コードでも読めるASCII escaping。
- 認証付きGET `/api/library/ai/setup`：runtime不足とモデル不足/版違いを別々に診断する。PythonのexeだけあってもAI libraries missingとなる。旧venvは存在確認のみでlegacy_runtime_unverifiedとし、実行確認済みにしない。選択packの異常はruntime_invalid。壊れた設定も診断結果として返す。
- launcherが保存済み追加packを次回起動からworkerへ渡す。明示`--settings`の場合も同じfileをbackend診断へ渡す。壊れた選択ならAIを無効にし、別の未知環境へ黙って切り替えない。基本閲覧は維持する。実行中のencoder/索引identityを変更しない。
- Embedding/Laya/WD各workerに共通の起動処理。standalone Pythonでは`-I/-B`と現在のアプリのworker directoryを明示し、pack元の旧アプリを誤importしない。legacy venvのargvは維持。packの保存済みmanifest bindingを強制し、marker削除でも検査を回避しない。

## 保証と未完の境界

pack manifestは選択した内容との整合性であり、配布元の認証/署名ではない。ローカル選択には明示したfolderへの信頼が必要。将来のdownloadは信頼できるcatalogの固定URL/revision/サイズ/hashから取得し、受信packの自己申告だけを信用しない。今回、外部取得元を勝手に追加していない。

最初のworker起動前はpack全体を完全検査し、同じbackendの次のworkerではmanifest/coreのみ検査する。immutable packを前提とし、同権限の利用者がsession中にbulk fileを書き換える攻撃の保証ではない。backend再起動/manifest変更時は全検査に戻る。WDの画像ごとのsubprocessで毎回5GBを読み直さないための区別。full SHA読み取り中のfile identity/metadata変更と最終manifest変更も拒否するが、敵対的な同権限の全file同時snapshot保証ではない。

モデル診断は現在のEmbedding profileのrevision marker/config/weight/tokenizerと安全なshard名の**静的存在確認**。model_files_present/pack_files_presentのreadyはファイル準備状態のみで、正常なGPU推論/driver互換性/全adapterモデルの準備完了を意味しない。GPU/モデルloadは行わない。Laya/WD別roleの導入進捗は今後のcatalog/UIで扱う。既存のモデルprofile/索引spaceはそのまま。

選択サービスは同期CPU処理であり、全pack検証をHTTP POSTのhandlerで実行するAPIは追加していない。現在はGET診断と開発CLIまで。LD4で所有jobとして検証/取得を進捗・取消対応にしてから、LD5の簡潔な「AI検索の準備」へ接続する。全runtime検証の初回負荷、cancel/resume/UI応答はそのjobで受入する。

## 検証記録

- 初期契約22 PASS/2.757s、既存48 PASS/27.231s。
- 広い影響回帰は493件中490 PASS/Windows固有3 SKIP、393.668s。最後のbinding欠落/設定file引継ぎ/CLI encoding修正前。単純合算しない。
- 最後の関連56件runは54 PASS/2 ERROR：marker削除拒否の例外型を誤期待したfixtureと、CLI日本語JSONをUTF-8として読めなかった問題。raw失敗を保持。例外期待をStoragePathError(ValueError)へ修正しCLI JSONをASCII出力にして、関連25 PASS/4.043s。既存54件の成功は消さず、56件全体をPASSと書かない。最終API capability表現整理後も関連25 PASS/4.088s。
- 実在の既存prepared runtimeを`--check`で読取り、Python3.11/x64/PyTorch2.9.1+cu128/CUDA12.8、optional4moduleを確認。import/GPU/実AI動作の確認ではない。約5GB packの複製は行わない。
- 実basic候補の同梱Pythonを隔離モード/無効なPYTHONHOME/PYTHONPATHで起動し、生成workerが現在のworker隣接moduleとargvを読むことを確認。旧appへの誤import回避を実プロセスで検証しただけで実AI推論ではない。

証拠：ignored `data/ai-ui/ai-runtime-contract-20261021-01.log`、`ai-runtime-regression-20261021-0{1,2}.log`、`ai-runtime-final-edges-20261021-0{1,2}.log`、`ai-runtime-existing-assets-20261021-01.log`、`ai-runtime-standalone-worker-20261021-01/report.json`。helper誤相対pathによる準備失敗も保持。GUI/GPU0・新download0・実DB/私物scan0。旧GUI固定flow3/3を別名でresetしない。


**最終source/配布CPU確認**：API capabilityの表現整理後も関連25 PASS/4.088s。新規 `dist/portable-basic-20261021-03/Aredoko` は696 files / 656,061,210 bytes（ZIP前）。実同梱Pythonから専用DBのbackendを起動し、GET setupがai_libraries_missing/model_missingと判定、生成PNG登録/scan/ファイル名検索1件/preview686bytes、原本SHA/mtime不変、EOF exit0、DB integrity=okを確認。初回完全確認+receipt3.982480s、変更なし次回1.488302s（単発warm/GUI時間ではない）。証拠 `data/ai-ui/basic-portable-cpu-20261021-03/report.json` と adjacent log。03の同梱docsは準備時snapshotであり最新はrepo handoff。02/旧配布/installed Alpha/shortcutは更新していない。03のnative GUI/通常DB restart/ZIP/clean Windowsは未確認。

## 次の実行順

1. LD4：信頼された固定catalog、所有validation/download job、未完stage→検証→新version公開、実進捗/取消/再開/破損/認証/容量を生成HTTPで検証。既定速度無制限、利用者任意の合計上限。正常pack/models/indexを上書きしない。
2. LD5：既存の「AI検索の準備」へAI追加・配置済み指定・公式手動案内と診断を整理。重い処理をUI threadに置かない。修復の完全検査も接続。
3. LD6：新しい具体buildを用意してから必要範囲のGUI許可を確認し、通常DB restart/ZIP移動/clean Windows/実AI追加を受入する。今回のhost CPU fixtureだけで製品受入にしない。

R13 DOING/ALPHA未完/R14 PARTIAL。専用OCR保留、U09/U11/U13/U14、実音声/音楽、モデル交換等の全機能を保持。Actions/main merge/旧shutdown再実行なし。

### 2026-10-26 追加：中断と直接worker起動
- 通常EXEの限定試験で、照合待ちの中断後にPendingSearchが同じ入力を自動再実行し、設定を開けない不具合を確認。中断クリック時までの入力を記録し、クリック後の新しい入力だけを再検索対象にする。新条件で破棄した旧結果を中断後に再び操作できないようにし、同じ有効sessionの範囲取得だけを止めた場合は元の表示位置へ戻す。
- worker_commandの全照合/ロック待ちへ所有者の取消を渡す。Encoder.closeは照合中にも終了を伝え、WDは取消済みならPythonを起動しない。生成CPUで照合途中close→未起動/未cache/再利用拒否と、既に起動したWDの取消を確認。
- 通常の認証loopback通信はシステムproxyを利用しない。配布先のproxy設定/自動検出に依存せず、tokenや媒体をproxyへ送らない。速度改善の数値はこの設定だけから推測しない。


### 2026-10-29：AI起動失敗を安全な復旧案内へ接続

推論workerの起動時エラーを固定3種類（依存部品を読めない／実行環境の種類が合わない／その他の初期化失敗）で返す。例外の私的pathや任意文字列をHTTP応答へ転送しない。特定DLLやVC++ installerを原因と断定せず、既存の「AI環境の配置」と基本操作の継続を案内する。WDとembeddingの両経路に適用し、音声・動画・動画内音声の準備も有限error_codeを保持する。失敗したembedding起動は所有process/pipe/telemetryを回収し、次の明示操作で再起動できる。旧workerの正常responseは互換、未知errorは一般案内。既存索引・タグ・原本・設定は書き換えない。

生成CPU関連88件（追加wire前）、最終wire6件、基本Python3.11の新経路9件、固定エラー日本語coverage4件、Core worker案内11項目とaudio/video関連、WinUI Portable buildがPASS。初回CPUのsandbox Temp拒否とCore試験の文言条件過剰は別の試験要因としてraw保持。coverageで検出した既存19件の英語エラー未翻訳も補完した。証拠`data/ai-ui/continuation-20261029/`。新しい案内のGUI・実runtime DLL不足・clean Windowsは未確認。依存ファイルの取得/実行/OS導入は行っていない。
