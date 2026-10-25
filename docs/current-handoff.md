# Aredoko — 現行の単一引き継ぎ（2026-10-25）

## ビジュアル素材v1導入（2026-10-25、直近の変更）
- 開始b8147fa、remote/既存Draft PR #5一致・clean、確認できる他の進行中repo作業なし。ユーザー指定ZIPを導入。[適用素材・変更ファイル・保留理由・証拠](visual-assets-v1.md)。
- 採用ICOとMSIXロゴサイズを既存参照へ適用。空状態/索引/AI設定/初回案内/使い方へ小型イラストを追加。Portableの既存画像未収録設定を修正し、アイコンpathもcwd非依存へ。Fluent操作アイコン・広い一覧・右詳細を維持。
- source原本はdesign/visual-assets/v1、配布対象はAssetsの使用分のみ。PREVIEW/reference/promptは配布しない。`tools/sync_visual_assets.py --check`で15出力一致・両manifest解決・ICOサイズ確認。Portable publish成功、Dark/Light各7checks/exit0、12PNG目視。設定の全状態GUI/MSIXインストール/HC/DPIは未検証。
- **既存ZIP07/インストール済みAlphaはこの変更を含まない。** 現在の試験frontendは `data/ai-ui/visual-assets-review-20261025/frontend02`。新規候補作成時に新ICOでbootstrapをビルドすること。
- 今回は素材導入で一区切り。次は既存ロードマップの高解像度APNG/CBZ性能確認へ戻る。以前の一回限りshutdown指示はこの素材導入へ再適用しない。

## 終了checkpoint（2026-10-25、最優先）
- 製品code **e197723**、今回の受入記録 **ef0a5bd**。最終handoffのcommitは `git log -1 -- docs/current-handoff.md`。ブランチ/既存Draft PR #5を継続、main merge/Actions/新PRなし。
- **最新試用候補は基本ZIP07**：`C:/AI/Aredoko/dist/portable-basic-20261025-07/Aredoko/Aredoko.exe`。source e197723、ZIP344,057,243 bytes・SHA `e8e82d354c70768949caba388e2cf88872a99b5b4cbb1cc916549764fd2f5ddf`。同梱CPU11/通常EXE復元28checks/4所有exit0、770payload/設定/生成原本不変。[候補正本](portable-refresh-20261024.md)。06は再選択バグ未収録修正のため旧候補、Alpha/shortcut未更新。
- 今回は初回案内/使い方の受入と明示scan説明、最終行layout/scale保持、5万metadataの端移動、COUNT/OFFSET反復削減、runtime ZIP輸送/再開/取消、棚管理の残操作、状況別空表示を仕上げた。**復元の別ZIP/AI方針の入力上書きも修正し、無効→無効→有効backupの再選択・未同意block・破棄・元DB再起動を確認**。
- 明示添付の10.gifだけを専用mediaへコピーし実機再生、実体WebP367×359/55frames・2cycle到達、first-frame-assigned453ms、原本SHA/mtime不変、decoder0/app exit0。[証拠と途中ハーネス失敗](animation-streaming.md)。全ちらつき/FPS/高解像度/速度同等の保証ではない。
- **未完**：5万実メディアの初回snapshot待ち/長時間RSS・HC/物理DPI、大きいAPNG/CBZの性能、clean Windows、runtimeの公開権利/native依存reviewと不変host、R06–R09実音声/音楽。5万metadata24.5sは開発Python3.14＋cProfile/実PNG80の限定値。Sandboxは無効（有効化していない）。runtime registry0、モデル2のまま。M1/ロードマップ全完了とはしない。
- **次の1件**：P1/P7の生成高解像度APNG・CBZで初frame/ページ切替/終了後RSSを一つの小規模caseへまとめ、再現した遅い処理だけ局所修正する。既に通った初回案内・取得・棚CRUD・復元切替・10.gifを無変更反復しない。その後、残るHC/DPI/clean Windows受入とM1日常β判定を進め、R06–R09へ戻る。
- 今回の新規モデル/依存取得・GPU推論0。添付の明示1ファイル以外は生成fixture/専用DB。通常DB/私物フォルダ/元メディア/旧Alphaは変更していない。
- **このランのみ、ユーザーが終了後のシャットダウンを明示指示**。保存・Push・後処理を確認後にPowerShell `Stop-Computer` を `-Force` なしで実行する予定。未保存疑い/権限エラー時は強行しない。結果はignored `data/ai-ui/continuation-20261025/shutdown.log`。この一回の指示を次回へ再適用しない。

## 今回の継続ラン（2026-10-25、以下の旧checkpointより優先）
- 開始cfb82e6、remote/PR #5一致・clean。確認できる範囲に他AIの更新/同repo処理なし。**今回のユーザーは生成fixture/独立DBでのGUI/GPUを自動実行することを許可し、終了後のシャットダウンを新たに指示した。** 下記の前回「事前確認」「shutdownしない」は前回の制約で、今回へ再適用しない。通常DB/原本/新download/OS変更の許可へ広げない。
- ZIP05の初回案内→help→AI取得表示→生成folder登録/スキャン→1再起動を限定native確認、15 checks・4所有exit0、6 PNG目視。[正本](getting-started.md)。原文に欠けていた明示scan説明を追加して継続中。

## 現在地と読む順
- ブランチ `feat/winui3-production-mvp-20261011` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)。製品source **e197723**。最新基本ZIP07/source e197723は上記で限定受入済み、旧06/05/Alpha/shortcutを上書きしていない。この文書自体のcommitは `git log -1 -- docs/current-handoff.md` で確認する。ロードマップ全体の完了ではない。
- **d199379**：既存ZIP05の初回案内/使い方/AI取得表示/生成folder登録・scan/予定内1再起動をnative確認15 checks・4所有exit0。ガイドへ不足していた明示scanを追加。
- **af95bdb**：最終行でlist/grid/表示サイズを変えると位置が先頭方向へ飛ぶ不具合を修正。745件生成caseで最終行・180/60/100%・逆方向・draft保持を確認。
- **eda972f**：runtime単一ZIPのcatalog v3、逐次展開・再開・取消・全hash/容量検証・検証後公開、Core/nativeの容量と進捗を実装。生成native17checks/exit0。[正本](runtime-archive-transport.md)。実ローカルpackを1回圧縮/展開し23,903payload・4.95GB完全一致。ZIP約3.03GB。**公開NOTICE権利/native依存reviewと不変hostは未完、製品runtime registryは0件のまま**。架空URLで埋めない。
- **5f738f3**：Ctrl+Home/Endで現検索の先頭/末尾120件へ移動、入力欄のキーとdraftは保全。5万metadata/実PNG80のnative14checks/4PNG/exit0。普通検索はCOUNT/増加OFFSET反復を撤去しbounded cursor、原本検証はpage単位1接続+全itemのguard維持。関連27/7/43各PASS。120件0.363→0.048s同値、5万snapshotはcProfile付き24.5s、**初回全件待ち・全5万実媒体負荷は残件**。[正本](result-sessions.md)、[一覧](p3-continuous-browse.md)。
- **b54de9d**：棚grid→開く→片方だけ所属解除→削除取消/確定→条件解除を限定native確認（145生成原本保持）。空棚への誤った登録案内を修正し、準備中→取消→再検索、空履歴/お気に入り/棚を新規native flowで確認、6PNG/exit0。初回ハーネスの失敗と後処理の欠測は[棚UI](shelf-ui-20261023.md)に保存。全HC/DPI/clean Windowsの合格とはしない。

- 本書 → [製品ビジョン](product-vision.md) → [統合P0–P7ロードマップ](polish-roadmap-20261022.md)の対象節。旧記録は[履歴索引](history-index.md)。WinUI 3/共通Python SQLite/交換可能AI、専用OCR保留、機能を削らず簡潔なUIを維持。
- 開始時の未コミットP5案4ファイルはignored `data/ai-ui/active-selection-20261024-01/starting-diff.patch`/starting-state.jsonへ退避して継続。c30bc34へff後に仕上げた。途中のリモート文書更新ed81d33/07c3f44も4a96d81で統合し、他作業を上書きしていない。main merge/reset/stash/force pushなし。

## 以下は以前のcheckpoint（時点別の履歴。現在の次作業/許可/候補へ再適用しない）

## 前回までの完了内容（当時の到達点）
- **P5 02f087b / f1bb3cb**：[active/pending保全・形式2](backup-active-selection.md)。AI/WDの実際の起動定義と保存済み次回選択を別保存、旧version1も復元。通常起動由来は復元初回active→ready後に一時指定解除→次回pending。明示overrideは保持。設定busy/atomic失敗はcommitted証拠から後処理し、誤rollback・通常profile枠の消費・元設定上書きを防ぐ。
- **P6 2449c62 / f508b82 / be60039**：[モデル配置検証・catalog builder・固定registry・bounded inline metadata](ai-acquisition.md)。source所有のfingerprint/profile SHAとレイアウトを結び、壊れた任意取得設定で通常起動を止めない。小さいprovenance/NOTICEはv2に同封可能、weightsは従来通り固定HTTPS/サイズ/SHA。製品registryは **0件**のまま。
- **P6 2973de7 / 82a6bda**：公開rootを配置画面へ渡し、明示ボタンで既存背景検査/次回設定保存。開くだけでは保存せず、runtimeとmodel親rootを区別する。正常終了/取消/未検証rootの扱いは維持。
- **UI/起動 d02e2e8 / 94c9816 / 82a6bda**：空タグ時の末尾区切り、idle時の空progressバーを整理。bootstrap/WinUIログをPythonと同じ明示LOCALAPPDATAへ統一。bootstrapは相対・drive-relative保存先を拒否する純粋self-testで確認。

- **P6 c7db80d**：役割別保存先のbackend/開発launcher。`embedding_models_root` / `tagger_models_root` / `intent_models_root` は絶対path、役割別→共通models_root→従来defaultの順で解決。現在workerは不変、次回起動のみ。旧共通folderの明示選択/resetは役割別指定をatomicに解除し、取消では全旧値を保全する。UI/個別catalog-profile bindingはまだ未接続で、旧ZIP02にこの設定を追加しない。

## 前回までの証拠・旧候補（当時の範囲）
- P5関連の最終79、settings/API22、restore pipeline40、一時解除19、新owned2、破損記録1、settings/switch40、lifecycle/startup26は各PASS。別実行を合算せず、途中FAIL/fixture修正は技術正本に保存。
- P6モデル9、既存取得/job/runtime builder25、registry6/所有backend1/staging1、inline7/関連41/URL拒否1は各PASS。Core **985 assertions PASS**、Portable build0 errors/既知WUI1001×3、publish既知SDK IL2104×2。毎回全回帰は実行していない。
- [基本ZIP候補02](portable-refresh-20261024.md)：**source f508b82**、ZIP343,869,819 bytes/展開657,657,654 bytes・756 files。通常入口 `C:/AI/Aredoko/dist/portable-basic-20261024-02/Aredoko/Aredoko.exe`。SHA等は正本参照。後続のUI/log/inline修正は未収録。旧01/Alpha/shortcutは未更新。
- ZIP02同梱Pythonの基本11、復元契約8、日本語/空白再配置11は各PASS。ユーザーの当該追加1試行で通常EXE→専用生成DB→AI設定→終了→予定内1回再起動を確認、4 PNG目視。初回ExitCode=nullはGet-Process観測handleの欠測（誤FAIL、raw保全）で、初回終了code自体は未確認。予定内再起動はapp/bootstrapともexit0。DB integrity/元PNG SHA・mtime/設定保全と所有PID終了を確認。
- **新機能の別実機確認**：取得済みruntime→明示適用をLight nativeで11項目確認、4 PNG全目視、exit0。検査用Python実行0、選択後の再起動なし。idle progress非表示/空区切り修正も同候補に反映。正確なfrontend/source/diff/test-script SHAと限界は[AI取得](ai-acquisition.md)。専用ログが明示LOCALAPPDATA内にあることも実証。
- WD公式固定tree/HEADのみを読み取り、既存profileの容量・ONNX LFS SHA一致を確認。CSV SHA256は公式treeにないため再検証していない。モデル本体/依存の取得・実モデル/GPU推論・通常DB操作は今回0。

- 役割別rootの新規/復元保全9 PASS、既存setup/job+通常所有backend16 PASS、既存runtime preference11 PASS（各別実行）。dispatcherは非実行factory spy、通常所有backendはmissing-AI条件。GUI/GPU/モデル実行なし。正本[AI取得](ai-acquisition.md)のrole-root節。

## 継続ラン（同日）で完了した追加単位
- P6 `8db7c2f` / `5c000f9` / `2803a46` / `54feb46`：固定catalog→モデルidentity→API/Core/native保存を接続。最大32のモデル別保存先、役割/共通fallback、同役割の別モデルの保全、候補profileごとの準備判定。画像検索モデルとWDを取り違えず明示適用し、現在worker/profile/namespaceをhot swapしない。
- 関連34・38・44 Python、Core1003 assertions、Portable build/publishは各PASS。生成WDのDark/embeddingのLightで個別適用・他設定保持・再表示・正常終了を確認。追加pickerの途中FAIL/仮説不成立/修正/最終native PASSは[AI取得正本](ai-acquisition.md)に記録。モデル本体/外部取得/新依存/GPU0。
- 取得registry0件は維持。実artifact/完全NOTICE/runtime公開先が未確定なので、その部分を架空値で有効化せず独立したP1B実機残件へ進む。

## 追加のP1B到達点
- `451290e`で生成APNG70枚/有限2loop・native GIF・GIF名WebPの限定native確認と計測ログ隔離を完了。その後のopen-first局所高速化も関連Python12＋認証HTTP1/Core1019/publish/native19チェックがPASS。単回のXAML割当はAPNG657→443ms、WebP649→443ms。物理FPS・大画像/RSS等は未受入。[正本](animation-streaming.md)とsource SHA付きreport参照。

## 追加のP2/P3到達点
- 詳細×/Escapeを表示切替に変更し、選択と未保存編集を保持。同一論理IDの再選択でdraftを再読込しない。600件のhead evictionで自分のscroll補正が逆方向追加を起こす点を、layout settle中の所有保持で修正。画面履歴も共通awaitを使う。
- [P3正本](p3-continuous-browse.md)の新run05は745生成PNG・最大600保持・逆方向取得・61番への完全表示後復帰・hidden draftの明示保存・原本不変・終了0がPASS。先行run01〜04の製品/ハーネスFAILと初回build失敗を保全。全P3/P7受入ではない。

## 新しい試用候補と最終確認
- **基本ZIP03/source47acf2f**：[入口・SHA・正確な範囲](portable-refresh-20261024.md)。`dist/portable-basic-20261024-03/Aredoko/Aredoko.exe`。モデル/PyTorchなし・catalog0件。旧Alpha/shortcut未更新。
- 同梱Python11項目、通常EXEの起動/設定/正常終了/予定内1再起動（WinUI/bootstrap計4 exitすべて0）、専用DB/設定/元PNG保全、GUI後全758payload inventoryがPASS。4 PNG全目視。
- 実binの125生成PNGで120→121→120と完全復号後のdetail復帰もPASS（[P2正本](result-session-native-connection.md)）。親ListView focusの初回ハーネスFAILを保持し、所有rowへのfocus操作へ実修正。全AI/検索条件/clean Windows/P7は未受入。

## 最新ラン（2026-10-24）で完了した追加単位（`2f4de23` / `e46c53d` / `56e3c8e`）
- **P5 形式2 `active`/`pending`・`model_locations` ネイティブ復元一連と `Aredoko.exe` 再起動IPC修正（`2f4de23`）**：`tools/test_native_restore.py --format2 --release` を実装し、通常の `Aredoko.exe` 入口で形式2 ZIPのネイティブ選択→準備→同意再起動（Phase 1：復元active profile一時適用・`launch-settings.json` からの一時 `ai_profile` 解放・`model_locations` 3件と役割別root保全・WD `0.65` 定義復元）→通常終了→次回 `Aredoko.exe` 起動（Phase 2：`local:pending.json` への切替とpending用 `model_locations` 解決、元 `catalog.sqlite`/原本不変）を実証。途中で `launch_release.py` の復元2周目（`attempt == 1`）が `app_ready` 後（`Bootstrap.cs` の `interactive == true`）にも `progress` フレームを送出して `Bootstrap.cs` がプロトコルエラーとなる製品バグを特定し、`tools/launch_release.py` と `tools/startup_ipc.py` を修正。単体テスト25 PASS（`test_restore_handoff.py`・`test_startup_ipc.py`）および修正ステージングでの実機 `run05` 完全PASS（6 PNG全目視、全所有 `Aredoko.exe`/`Aredoko.WinUI.exe` 終了0、残存0）。先行 `run01..04` の生ログも保持。詳細は[P5 active/pending正本](backup-active-selection.md)。
- **P3 永続サムネイルディスクキャッシュ `<db>.thumbs.sqlite`（`2f4de23`）**：`app/thumbnail_disk.py` の `ThumbnailDisk(path=...)` に永続モードを実装し、`app/production_server.py` から `<catalog>.thumbs.sqlite` を接続。`plain_path`/`storage_parent`/`storage_lease` による単一プロセス所有、接続前の残存 `-wal`/`-shm`/`-journal` 掃除、`trusted_schema=OFF`・`quick_check`・`user_version`・厳密 `sqlite_master` 検査（`thumbs` のみ）、再起動をまたぐ `touched` LRU順序の継続と起動時 `_evict()`、ロック競合/破損時の fail-open 再初期化・無効化、およびバックアップ/復元からの除外（`storage_backup.py`/`live_backup.py`）を実装。関連単体テスト **73 PASS**（`test_thumbnail_cache.py`・`test_thumbnail_priority.py`・`test_storage_backup.py`・`test_live_backup.py`）。詳細は[サムネイル正本](thumbnail-derivatives.md)。
- **P3 モニター間DPI（`RasterizationScale`）/サイズ変更の自動再取得接続と永続 `<db>.thumbs.sqlite` 再起動横断実機確認（`e46c53d` / `56e3c8e`）**：`src/Aredoko.WinUI/MainPage.xaml.cs` で `XamlRoot.Changed` を購読し、`UpdateItemSizes()` から実現済みライブラリカード（`containerRefresh`）・棚カード（`MainPage.Shelves.cs` の `shelfRefresh`）・詳細プレビュー（既存画像を保持したままバケット変更時のみ再取得する `ShowDetailPreviewAsync(preserveExisting: true)`）の派生edgeを一括再評価するよう統合（Coreテスト・Portable build/publish 0 errors）。`tools/test_native_persistent_thumbnails.py` でステージング `staged-release{,-02}/Aredoko`（758 files）＋生成24 PNG/2 CBZ（540〜640px）＋初期棚 `テスト棚`＋独立LOCALAPPDATAを用いて実機検証し、100%固定の `run02`（25 checks PASS、2 PNG目視）に加え、実機で詳細プレビュー表示＋100%→180%サイズ変更（`128/256/512/1024[元寸560..640]` 全バケット生成）＋棚一覧140%→180%変更（`shelfRefresh` 実行）＋再起動後の180%グリッド/詳細/棚キャッシュヒットを通す `run06` で **28 checks PASS**（Phase 0 で `rows=49`・`max_touched=49`・`bytes=102,469`・`WorkingSet64=218.1MB`、再起動後 Phase 1 で `rows=49`・`bytes=102,469` 不変のまま `max_touched=75` へ進行し全表示要求の100%永続キャッシュヒット・`WorkingSet64=205.2MB`・生成26原本SHA/mtime完全不変・全所有 `Aredoko.exe`/`Aredoko.WinUI.exe` 終了0・残存0、4 PNG全目視。先行 `run01/03/04/05` の生ログ/PNGも保持）。詳細は[サムネイル正本](thumbnail-derivatives.md)および[結果ウィンドウ正本](p3-result-window.md)。

## Codex引き継ぎレビュー（2026-10-24）
- 開始 `fc4ff5f`、リモート/PR #5と一致・clean。AntigravityのP5形式2 nativeとP3永続cache/DPI接続を維持。永続cacheの不正LRU/整数overflow/schema制約/接続解放を局所補強。新規CPU4・関連thumbnail28 PASS。[詳細と再現](thumbnail-derivatives.md)。GUI/GPUは未実行。
- **今回のユーザー指定：GUI/GPUテストは実行前に確認する。** 通常のローカルテスト方針に対する今回の例外で、許可済みとみなさない。CPU/静的/buildを先行できる。

## この継続で完了した単位（2026-10-24〜25）
- `c4de705`：Antigravityの永続cacheをレビューし、破損LRU/SQLite整数上限/schema制約/失敗時接続解放を補強。`3666a55`：ヒット順序の書込を最大64アクセス単位へ集約（128hitのCOMMITは2回）。回復7・既存thumbnail28 CPU PASS。体感/RSS実測ではない。[正本](thumbnail-derivatives.md)。
- `bb79ad6`：詳細の媒体別主操作、AI候補の対象表示、一覧根拠2行＋全文tooltip、棚画像の再Loaded時refresh保持。Portable publish成功。**今回のユーザー許可済み**生成6媒体/独立DBでDark一連PASS、Lightの媒体別表示と保存/棚往復PASS、全所有app exit0/残存0。先行Lightのハーネス待機/期待値/失効FAILと修正は[P3正本](p3-result-window.md)に保持。実媒体再生やGPU推論は未実行。
- `33c8938` P6：WD固定版の実カタログとモデルNOTICEを用意（WD＋EmbeddingGemma 2のregistry2件、runtime0件）。公式metadata/HEAD＋既存CSVの固定Git blob/SHA確認のみで、モデル本体の外部取得・推論なし。[正本](ai-acquisition.md)。**今回のGUI許可は上記detail候補のみ**。新しいAI取得画面/通常EXE候補を試す場合は改めて具体的範囲を確認する。

## 最新の実行候補と確認（2026-10-25）
- **基本ZIP02/source13778ad**：`dist/portable-basic-20261025-02/Aredoko/Aredoko.exe`。EmbeddingGemma 2/WDの実カタログを同梱、モデル/PyTorchなし。[SHA・正確な範囲](portable-refresh-20261024.md)。旧Alpha/shortcut未更新。この時点の試用先。後続04とsource-only更新は下の最新追加を参照。
- 同梱Python11 PASS。ユーザー許可の表示のみGUI＋1再起動は全チェックPASS、4所有exit0/残存なし、全766payload/設定/生成元保全、3 PNG目視。実転送・推論・clean Windowsは未実施。モデル取得は約1.53GB/468MBで、runtimeは別途必要。
- QA終了処理もレビューし、旧P3ハーネスの全体focus helper/launcher強制終了を廃止して、所有HWND検査＋通常終了＋失敗exit codeへ変更。旧合格flowの反復はしていない。今回の通常入口testは所有プロセスhandleを保持して正常終了を観測する。

## 最新追加（2026-10-25、今回の正確な到達点）
- **e46d9f8 / 630cc55**：転送timeout/reset/途中EOFを最大2回だけ再接続し、実partial sizeからRange再開。CPU通信6/既存取得14 PASS。実EG2約1.53GB/WD約468MBはユーザー許可済み専用先で中断・再開・全hash検証後の公開まで完了。途中FAILは `data/ai-ui/real-model-download-20261025-01/report.json` / `resume-report-02.json` に保存、EG2成功は02、WD最終成功は `resume-report-03.json`。失敗記録を成功へ上書きしていない。[取得正本](ai-acquisition.md)。
- **d0eb214 / adb701e**：AI準備からモデル取得へ直接移るボタン。新規基本ZIP03/source5ddd97aはユーザー許可の限定GUI11 checks/4所有exit0/2 PNG目視PASS。旧WD切替/詳細の同一受入は反復していない。最終EOF補強のZIP04/source630cc55はCPU11 PASS、GUI自体は未実施。[候補/SHA](portable-refresh-20261024.md)。
- **5ddd97a / 4217636**：runtime通知収集・source binding・固定上流補完・封印pack同梱。52配布物/91通知を収録し、新しいローカルpackを全hash検証して作成。生成16関連tests PASS。公開の権利/native依存reviewと不変の配布先は未完、runtime取得registry0件。[正本](runtime-notice-inventory.md)。
- **09f72dd**：取得WDが旧venv用model markerを要求して準備済みにならない不整合を修正。封印runtimeの固定onnxruntime metadataを使い、workerの全pack検証・版/CPU provider検査は維持。関連11 PASS。
- ユーザーの追加GPU/CPU許可で、新pack＋今回取得した2モデルを生成2画像/専用DBだけで各1回確認：EG2 CUDA正規化768D・WD CPU候補6、DB integrity/input metadata/生成原本保全・所有worker停止PASS。adapter終了はexit1で、正常exit0とはしない。`data/ai-ui/acquired-runtime-smoke-20261025-01/report.json`。実精度/全媒体/GUI導入受入ではない。
- **4ac518b**：初回の未登録空ライブラリに登録/AI取得/使い方をinline表示、設定から使い方を再表示。[使い方](getting-started.md)。勝手なscan/取得や強制wizardなし。関連Portable publish成功。追加した設定scrollを含む最終publishも0 errors（既知WUI1001×3/SDK IL2104×2）。build02 log参照。**新しい案内のnative GUIは未確認**。
- モデル/packはignored専用先にありGitへ含めない。旧Alpha・shortcut・通常DB・通常設定は未更新。GPU/GUIの一般許可へ拡大せず、次の実機確認は改めて具体的対象を提示する。Actions0、シャットダウンしない。

## 次の実装1件（冒頭checkpointが正本）
P1/P7の生成高解像度APNG・CBZで初frame/ページ切替/RSSを一つの限定caseへまとめる。初回案内/通常EXE/棚管理/再選択復元の今回済み範囲は反復しない。runtime公開監査/hostは外部情報待ちで独立、R06–R09の実入力はM1後へ維持する。

## 直前の実装手順（上記P6で完了済み、再実装しない）
**P6：役割別保存先のAPI・Core・native UIを接続する。** `c7db80d`のbackend解決を再実装せず、以下へ進む。
1. app所有registryのprofile bindingから取得対象の役割/モデル定義をsummaryへ渡し、Coreで検証する。catalog名や単なるkind=modelからWD/embeddingを推測しない。runtime用の既存選択は維持。
2. 所有setup jobで一つの役割を明示保存できるAPIを追加し、他の役割・共通root・runtime・themeを保全する。旧共通folder/resetで全役割指定を解除する動作とは区別する。モデルID/revisionとprofileの対応を保持し、将来の同役割別モデルの選択も壊さない。
3. native setup/取得完了ボタンを役割のcurrent/pending場所へ接続し、明示適用・取消・再表示を生成fixtureで確認する。現在workerのhot swap、profile/namespace変更、P5 active/pendingや復元整合の破壊をしない。通常はSolで可、既存の選択/復元安全性に収まらない設計変更時だけAstraレビュー。

その後、レビュー済み実artifact・完全なNOTICE・runtime pack公開先を確定してsource registry登録へ。WDの公開元とmanaged sidecar方式は確認済みだが、推測URL/架空hash/未監査NOTICEで有効化しない。新モデル/依存の実取得は対象/容量/取得元を示して別許可。

## 未完・運用
- P0/P1B実機/P2/P3性能・完成形UI/P4/P5復元/P6配布/P7総合受入のPARTIALは維持。[完成台帳](completion-roadmap.md)と[実音声等の内容索引](media-content-plan.md)の未完も保持。全音声/音楽、clean Windows、実素材精度の総合受入は未完。実catalogの取得と限定生成GPU/CPU確認は上記で完了。
- 最新[ローカルGUI/GPUテスト方針](local-test-policy.md)に従う。生成fixture/独立DB・設定/既存モデルの通常関連検証は事前許可不要。旧環境2/2、復元3/3、取得1/2、P3等は履歴であり永久禁止ではない。同じ失敗の無変更反復は止め、診断→有意味な修正→対象確認。今回の基本ZIP限定1試行は終了済みで、新機能確認と混同・再命名しない。raw失敗を成功へ読み替えない。
- 私物scan/原本変更/通常DB/旧Alpha/shortcut/新モデル・依存取得/OS・driver変更/外部送信は無断実行しない。Actions0、既存Draft PR継続、main merge/新branch/新PR/force pushなし。**シャットダウンしない**。
- [文書/legacy整理](repository-maintenance.md)、[旧依存監査](legacy-dependency-audit-20261024.md)、[文書案内](README.md)を保全。旧Catalog/server等は製品依存のため削除しない。
- 再開時はfetch/status/HEAD/PR確認後、上記「次の1件」へ。本書だけを短く更新し、AGENTS/互換handoffへ大量追記しない。詳細証拠は対応する技術文書、履歴はGit/履歴索引へ残す。
