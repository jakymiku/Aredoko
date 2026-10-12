# Swappable embedding models

Aredoko chooses a validated local embedding profile at startup. The default remains EmbeddingGemma 2. A compatible derivative can be selected without rewriting catalog, API, GUI or ranking code. A model with a different architecture needs a registered adapter; arbitrary models are not guaranteed to load.

## Selecting a profile

Copy config/ai-profiles/embeddinggemma-2.json into an ignored local directory such as data/ai-profiles/custom.json. Edit the model ID, immutable revision (40-character commit SHA or 64-character content hash), model directory, label, dimension and supported inputs to match the actual model. directory is relative to models and cannot escape that directory. Use a different directory for different weights/revisions.

Stop Aredoko and launch:

    pwsh -File tools/start-winui.ps1 -AIProfile data/ai-profiles/custom.json

Omit -AIProfile to return to the original model. Selection takes effect on restart; no hot swap can race an in-flight index job. The AI索引 dialog shows the active model, input capabilities and its own progress. For a new profile, click 索引を作成・更新. Existing tags, shelves, favorites and file catalog remain shared.

The backend also supports --ai-profile. Invalid settings disable optional AI while literal search remains available.

## WinUI 3での選択（2026-10-12追加）

**「AI索引」→「次回起動で使用するAIモデル」** からモデルprofileを選べます。通常の文字検索はいつでも利用可能です。

- 選択肢は既定のEmbeddingGemma 2と、`data/ai-profiles/*.json`（ignoredのローカルJSON）のみ。既存の`config/ai-profiles/embeddinggemma-2.json`を複製したファイルをローカルフォルダへ置き、モデルの情報を編集します。**GUIはモデル自体をダウンロードしません。**
- 対応adapter・identity等のスキーマは `app/ai_profiles.py` が一元検証します。無効なJSON・不明なadapter・逃避パス・リンク先のモデルprofileは選択禁止。重みフォルダ、`.venv-ai/Scripts/python.exe`、`aredoko-revision.txt`の不足やリビジョン不一致は、モデル選択画面に警告を表示。検出できた場合でも実モデルのロード成功までは保証しません。
- モデルを選び「次回起動に設定」を押すと、`%LOCALAPPDATA%/Aredoko/settings.json`（デフォルト）へ**原子的に保存**します。現在のworkerとベクトル索引は**そのまま**。**Aredokoを閉じて起動し直す**と新しいprofileが有効になります。既定モデルへ戻す場合は同じ欄で既定を選び直してください。
- **優先順位は明示 `-AIProfile <JSONパス>` ＞ GUIの保存済み選択 ＞ 既定profile**。毎回 `-AIProfile` を付けて起動した場合、GUIの選択は保存されても優先されません。引数を外して再起動すると反映します。
- 起動時に保存profileが消失・JSONが無効なら、そのAI機能を無効にして**文字検索を維持**。GUIのモデル選択画面で修正方法を案内します。既定へ戻すと設定を復旧できます。起動引数で有効なprofileを明示した場合は破損した保存済み選択より優先されます。
- 既存のvector identityとprofile別SQLite索引は変えません。新profileへ切り替えたら必要に応じ「索引を作成・更新」。旧profileへ戻れば以前の対応する索引を再利用できます。text-onlyモデルは画像/表紙の入力に非対応なので、AI画像・表紙では既存の非対応メッセージが表示されます。
- profile選択APIは `GET /api/library/ai/profiles` / `POST /api/library/ai/profile`（body `{"id":"default"}` または `{"id":"local:custom.json"}`）。既存のlocalhost／トークン／Origin境界を維持し、POSTは候補IDしか受け取りません。任意ファイルパスやPythonモジュールをPOSTさせず、remote codeも読みません。
- テスト専用の設定パスはサーバー `--ai-settings <path>` で指定可能。デフォルトの個人用設定をテストで汚さないためのものです。自動ダウンロード・hot swap・LayaのGUI統合は実装しません。

## Supported adapters

- embeddinggemma2: compatible EmbeddingGemma 2 Sentence Transformers exports; text and optional image/cover inputs. Audio is unloaded; a text-only profile also unloads vision. Named task prompts default to SearchQuery and Document.
- sentence-transformers: conventional text-only Sentence Transformer exports, with their actual vector dimension and prompt names or explicit prefixes. Set modalities to ["text"]. This is a generic loading contract; no additional model has been downloaded or validated on this PC.
- Other architectures: add a registered class in app/ai_adapters.py exposing dimension, encode_text and encode_image, then extend profile validation and tests. Neither arbitrary Python module paths nor remote model code are accepted. Laya will have a separate decision interface; its decisions are not embedding vectors.

Prompt names and explicit prefixes are mutually exclusive. To use a prefix, set the corresponding prompt name to null. Empty explicit prefixes intentionally disable model-default text prompts. Precision supports auto-bf16 (CUDA bfloat16 when available, float32 otherwise) and float32. Float16 is not supported.

## Index compatibility and rollback

Vector-space identity includes model ID, immutable revision, adapter, dimension, modalities, query/document prompt settings, precision and the preprocessing contract. Changing any of these selects a separate sibling AI SQLite database. Same dimension alone never makes two models compatible. Worker startup must echo the exact identity and actual dimension, and all returned vectors are validated.

Cosmetic labels and relocating the same weights do not change identity. The exact default profile retains the original <catalog>.ai.sqlite and its legacy identity: no initial rebuild required after this application upgrade. Other profiles use <catalog>.ai.<identity hash>.sqlite. Their stored full identity is also checked. Legacy recognition is frozen to the historical settings, independent of future default changes. Changing preprocessing requires bumping VECTOR_CONTRACT and then selects a new store even for the original model.

Switching back reuses the previous index; source/title/tag revision checks still exclude stale records. Old indexes are preserved for rollback and consume disk until explicitly managed. Raw cosine scores from different profiles are not mixed or compared as calibrated probabilities.

## Preparing local weights

Runtime is offline, local-files-only, with remote code and telemetry disabled. Switching does not download or install anything. For an explicitly approved new model setup:

    pwsh -File tools/setup-ai.ps1 -AIProfile data/ai-profiles/custom.json

Inspect the profile/model size first. The next command opts into installation/download:

    pwsh -File tools/setup-ai.ps1 -AIProfile data/ai-profiles/custom.json -InstallAndDownload

The existing project-local dependency pins and shared aggregate 6,000,000 bytes/s proxy also apply to custom downloads. No new setup/download was performed for this feature. The downloader records model ID/revision before retrieval to allow interrupted setup to resume, and rejects overwriting another revision in the same directory.

Already installed exports need an aredoko-revision.txt marker containing the declared immutable revision. A manually altered checkpoint must use a new revision/content hash and a separate directory/profile. The marker is a user-managed provenance declaration, not a cryptographic verification of all local weights.

## Validation

Known-vector tests cover different dimensions and same-dimension revisions, identity changes, wrong worker handshake, source capabilities, malformed/oversized settings, prompt routing and interrupted-download guards. They are protocol evidence, not model quality evidence.

The actual local-model test tools/test_ai_profile_switch.py uses existing weights in default text+vision and text-only float32 profiles, then switches back without rebuilding. This validates loader/config/cache switching on CUDA, not an unreleased derivative or a second independent model. Generated filenames only; source hashes unchanged.

[Sentence Transformers API](https://sbert.net/docs/package_reference/sentence_transformer/model.html) documents local loading and prompt options.

## Windows実機へ戻した初回確認（2026-10-12・以下は当時の記録）

チャット側で実装したGUI選択/API設定をf4273ffまでfast-forwardで取り込み、Python96/C#13/WinUI Releaseをローカル確認した。SDK IL2104 2件は未解消。新規重み取得・依存導入はない。

起動/検証のPlatform差で古いbin/Releaseが起動することがあったため、launcherを `--arch x64 -p Platform=x64 -p SelfContained=true` へ揃えた。テスト用の `-AISettings <path>` も追加し、個人AppDataの保存設定を変更せず検証できる。指定しなければ従来の保存先を使う。

    pwsh -File tools/start-winui.ps1 -Database data/profile-test/catalog.sqlite -AISettings data/profile-test/settings.json

モデル候補に安定したAutomationId、現在のモデルに人向けラベルを表示。設定保存中は再選択と重複保存を止める。索引のidentityや現在のworkerは変更しない。

**実機で確認できた範囲:** 新dialogの表示、生成17件のGUI CUDA索引、GUIで文字専用設定を次回用に保存、保存後も旧モデル/索引がactive、再起動案内。probe旧/最新、02保存後/失敗、03失敗の計5枚のスクリーンショットを目視確認。完全なGUI通しテストはFAILで、検索方法ComboBoxのPopupHost検出時に停止した。ウィンドウ待機とpopup待機の2回修正再実行後も残り、成功としない。文字専用/不足/破損のGUI再起動画面、最新変更後のタグdirty通し回帰は未完。

**独立した実HTTP/CUDA再起動検証はPASS:** GUIで保存できた設定と生成DBをコピーし、その設定を起動時に読ませた。text-only索引分離/17件構築/日本語hit/cover非対応、保存時hot swapなし、defaultへ戻して旧17件vectorとcoverを再作成なしで検索、不足重み/不正JSONのoptional AI停止＋literal17件、破損保存設定に対する明示起動profile優先、sourcehash不変を確認。これは設定/API/GPUの証拠であり、未完のGUI通しテストの代わりではない。別checkpointではなく同じ既存重みの2設定。

再現用 `tools/test_ai_profile_ui.py --output <fresh-ignored-directory>` はnative Windows/local専用で、現在上記のpopup検出問題が残る。`tools/test_profile_preference_gpu.py --gui-evidence <generated-ui-evidence> --output <fresh-ignored-directory>` は保存済みtest設定/DBから独立HTTP/GPU再起動を検証する。モデル取得は行わず、作成したtest profileだけ終了時に削除。対応重みとx64 SelfContained Releaseが必要。

ignored結果: `data/ai-ui/profile-probe-01/dialog-latest.png`, `data/ai-ui/profile-picker-01/02/03/result.json`（FAIL/部分到達）、`data/ai-smoke/profile-preference-01/result.json`（PASS）。private/元AppData設定は未変更。検証用API/GUI/workersは終了。Sandbox/analyzer/高DPI/theme/reader/AOTは未検証。


## nativeモデル切替の到達結果（2026-10-12・以下は当時の記録）

前回の検索方法popup問題を修正した。03のUI treeではPopupHostがmain HWNDのchild paneで、独立window列挙からは見つからない。検索方法は既知の選択肢へ実キーボード操作し、表示値もUIAで確認する。前景が必要なので `focus` の成功を確認してから入力する。モデル候補のpopup HWND操作は維持。

生成17ファイル、専用DB/settings、既存重みで06を実行し、以下はnative GUIと実CUDAで確認できた。

- default GUI索引17件、次回text-only設定の保存、実行中モデルを変えないこと、日本語意味検索。
- 再起動でtext-only適用、別索引0→17件、CUDA日本語検索。画像検索の非対応案内をGUIに表示し、名前・タグ検索へ戻れること。
- GUIでdefaultへ戻し、再起動後に元の17件索引を再作成せず再利用、日本語検索。
- 不足モデルとinvalid JSONの再起動でAIを無効にし、GUIの索引ボタンを無効化/理由を表示しながら文字検索を維持。invalid状態からdefault設定をGUI保存。
- 破損settingsに対して明示 `-AIProfile` が優先し、検索/起動引数の説明/default設定の再保存ができること。

**通しバッチ全体はFAILのまま。** 04はdialog表示直後の索引操作でidleのまま、05は前景条件でkeyboard操作を安全に拒否、06は上記モデル段階を終えた後のfavorite保存直後のAPI確認で停止した。最後はボタンが親editorの無効化で先にdisabledになることを、保存完了と誤認したテストの待機条件。失敗時PNGには「保存しました」とfavoriteチェックがあり、終了後read-only DB/保存UI treeでもfavorite=true/onを確認した。dirty保持とfavoriteのnative再起動段階には未到達で、過去のGUI成功を今回の結果として転用しない。

06の7状態＋failureの計8 PNG、04のfailure、05の3 PNGをすべて目視確認した。標準1200×820/96 DPI/darkのモデル説明は欠けず読める。02の索引文はAPI完了より1秒pollが遅れた「作成中14/17」のsnapshotで、次の操作では完成索引を使った。04-restored-indexのPNGにはCLIが合成したCtrl+F tooltipもある。小画面/高DPI/Light/HighContrast/readerは未検証。画像非対応時の中央「再接続」汎用案内は具体的なstatus説明と合わず、後続UX改善候補。

索引クリックの準備待ち、実クリック、foreground focus、失敗時にもAPIを必ず終了するcleanupを実行済み。最後に `TxtEditStatus=保存しました` とAPI反映を待つ修正、実UI treeのfavorite toggle assertion、`--editor-only`（AIをロードせず編集/dirty/restartだけ実行）、初期source-hash保存と失敗時hash記録を追加した。**この最後の修正はpy_compile/--help/diffチェックのみで、native再実行していない。** winui-ui-testing skillの同依頼で2回のfix/rerun上限に達したため、修正済みだから通ったとは扱わない。

次回の軽い再確認:

    python tools/test_ai_profile_ui.py --editor-only --output data/ai-ui/profile-editor-01

Python96 tests、C#13 checks、x64 SelfContained Releaseは今回もPASS。SDK IL2104は従来の2件を維持。C#/XAML/モデルworker/API本体は今回無変更。独立HTTP/CUDAの前回PASSも保持し、今回は再実行していない。

ignored evidence: `data/ai-ui/profile-picker-04/05/06/result.json`（全体FAIL/到達段階は上記）、06の`post-run-check.json`（read-only確認PASS）。後者はfavoriteのdisk保存と失敗UI treeのon、17元ファイルのscan時size/mtime不変、別fresh fixtureとの全payload一致を確認した。ZIP container timestampは生成時刻で異なるため、別生成ZIPのbyte hash比較を源変更の証拠とは扱わない。06開始時のbyte-hash記録は残っておらず、全byte hash不変と主張しない。新しいharnessでは開始hashを残す。

個人AppData/私物ライブラリは無変更、download/installなし。05でcleanup例外により残った所有APIを確認して停止し、cleanupを修正。06終了後は所有GUI/API/embedding/Laya workerなし、作ったtest profileだけcleanup。補助read-only favorite監視はeditor-restart未到達のため終了し、成功証拠に含めない。


## 残った編集/再起動回帰と小画面UI（2026-10-12・当時の記録）

aee9421から続行し、AIをロードしない `--editor-only` で前節の未到達部分を確認した。`profile-editor-02/result.json` は11 checks PASS。UI整理後 `--editor-only --layout-checks` の `ui-polish-02/result.json` は32 checks PASS。保存表示とAPI反映を待ち、favorite保存→dirty保持/DBタグ不変→再起動→UI checkbox on/API favorite=trueを確認した。生成17元ファイルの開始/終了hash一致。

今回の製品変更は検索/操作欄の配置・文字の強弱・初期詳細pane非表示、狭いwindowの二段操作群、AI dialogのスクロールと検索失敗時の具体的案内。1200×820一覧/タイル、700×620操作欄と不足profile dialogで候補/警告/閉じるのboundsを確認し、最終6 PNGをすべて目視。4回の所有GUI終了は正常、cleanup warning/所有GUI/API/worker残留なし。詳細と再現コマンドは[ui-polish.md](ui-polish.md)。

このバッチは `actual_model=false / profile_verification=not_run`。前回profile-picker-06をPASSへ書き換えず、nativeモデル段階の履歴と今回の独立した編集PASSを分ける。全GPU/profile切替および新しいAIエラー文を伴う非対応modeの操作は今回再実行していない。Light/HighContrast/高DPI/readerも未確認。

Python96/C#13/x64 SelfContained Release PASS（既存SDK IL2104 2件）。追加取得/依存導入/私物走査/個人AppData変更なし。作成した検証profileのみcleanup。モデルidentity/namespace/重み/worker/APIは変更していない。


## 最新: 実非対応エラーからの文字検索復帰（2026-10-12）

`appearance-03` のLight/Darkでtext-only profileのcover検索が実503/画像非対応文を返し、GUI中央の具体的な案内と古い件数/ページの消去、文字検索に戻した実1件と成功InfoBarを確認。missing profileの意味検索でも同じ復帰をLightで確認した。capability/availability判定は推論前なのでGPUモデルをロードしない（actual_model=false/profile_verification=not_run）。CUDA検索/全profile切替/別checkpointの追加検証ではない。

UIA68項目はPASS、9 PNG目視でLight AI dialogのDark不一致が見つかり、視覚レビューはFAIL。全3dialogのRequestedTheme修正はRelease build済み、native未再実行。docs/ui-polish.md/chat-handoff.mdの最新節を参照し、次回まず新規outputで修正後dialogを確認すること。生成元hash不変、6回正常終了、所有test GUI/API/worker停止済み。重み/依存/モデルidentity/APIは無変更。


## 索引の対象拡張とモデル互換（2026-10-12）

eligible上限2,000→10,000、256件metadata/vector取得と進捗16件保存を実装。profile identity/store namespace/vector schema/worker/model weightsは変更しない。保存済みfresh vectorを再利用し追加分のみ生成する。生成2,105件の旧2,000→追加105互換、生成768次元text-only 10,000件のcancel/restart/reuseをCPUで確認。別checkpointや実GPU大規模推論の検証ではない。[index-scaling.md](index-scaling.md)参照。

ゲームの前面表示を維持するユーザー指定によりnative起動は今回保留。前節のLight dialog最終修正と今回の上限表示はbuild/reviewのみ。appearance-03 visual FAILを変えず、前面操作が可能になってから新規outputで確認する。


## 続行: 小画面操作と実GPUの上限表示（2026-10-12）
通常GUIテストを許可された後、明暗AI dialogとLightのdirty/roots、17件text-only CUDA索引/日本語検索/10,000上限表示を実確認。新batch appearance-06は75 successful checks/13 PNG目視だが全体FAIL。Dark fresh cache時にもdevice=cudaを要求したテスト条件を修正、最後はnative未再実行。全17revisionをread-only diskで確認。全profile切替/独立checkpoint/実GPU大規模は再検証していない。正確な到達・cleanup warning・skill上限・次回コマンドは[ui-polish.md](ui-polish.md)末尾。現在は通常のGUIテスト許可済み、ゲーム前面制約は解除。


### 後続のGUI再確認
生成17件/editor-only+appearance+coverageのappearance-09は105 checks/17 PNG目視PASS。Light/DarkのCUDA検索・model unavailable/cover unsupported復帰・dirty/再起動まで完走。full profile chooserバッチを再実行した意味ではない。Dark cached rebuildのsnapshotは非同期で厳密な開始/終了計測ではない。詳細はui-polish.md最新節。過去FAILを保持。
