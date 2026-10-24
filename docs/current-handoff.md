# Aredoko — 現行の単一引き継ぎ（2026-10-24）

## 現在地と読む順
- ブランチ `feat/winui3-production-mvp-20261011` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)。製品コード到達点 **2f4de23**（基本ZIP03時点は `47acf2f`）。この引き継ぎ自体のcommitは `git log -1 -- docs/current-handoff.md` で確認する。ロードマップ全体の完了ではない。
- 本書 → [製品ビジョン](product-vision.md) → [統合P0–P7ロードマップ](polish-roadmap-20261022.md)の対象節。旧記録は[履歴索引](history-index.md)。WinUI 3/共通Python SQLite/交換可能AI、専用OCR保留、機能を削らず簡潔なUIを維持。
- 開始時の未コミットP5案4ファイルはignored `data/ai-ui/active-selection-20261024-01/starting-diff.patch`/starting-state.jsonへ退避して継続。c30bc34へff後に仕上げた。途中のリモート文書更新ed81d33/07c3f44も4a96d81で統合し、他作業を上書きしていない。main merge/reset/stash/force pushなし。

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

## 次の実装1件
## 最新ラン（2026-10-24）で完了した追加単位（`2f4de23`）
- **P5 形式2 `active`/`pending`・`model_locations` ネイティブ復元一連と `Aredoko.exe` 再起動IPC修正（`2f4de23`）**：`tools/test_native_restore.py --format2 --release` を実装し、通常の `Aredoko.exe` 入口で形式2 ZIPのネイティブ選択→準備→同意再起動（Phase 1：復元active profile一時適用・`launch-settings.json` からの一時 `ai_profile` 解放・`model_locations` 3件と役割別root保全・WD `0.65` 定義復元）→通常終了→次回 `Aredoko.exe` 起動（Phase 2：`local:pending.json` への切替とpending用 `model_locations` 解決、元 `catalog.sqlite`/原本不変）を実証。途中で `launch_release.py` の復元2周目（`attempt == 1`）が `app_ready` 後（`Bootstrap.cs` の `interactive == true`）にも `progress` フレームを送出して `Bootstrap.cs` がプロトコルエラーとなる製品バグを特定し、`tools/launch_release.py` と `tools/startup_ipc.py` を修正。単体テスト25 PASS（`test_restore_handoff.py`・`test_startup_ipc.py`）および修正ステージングでの実機 `run05` 完全PASS（6 PNG全目視、全所有 `Aredoko.exe`/`Aredoko.WinUI.exe` 終了0、残存0）。先行 `run01..04` の生ログも保持。詳細は[P5 active/pending正本](backup-active-selection.md)。
- **P3 永続サムネイルディスクキャッシュ `<db>.thumbs.sqlite`（`2f4de23`）**：`app/thumbnail_disk.py` の `ThumbnailDisk(path=...)` に永続モードを実装し、`app/production_server.py` から `<catalog>.thumbs.sqlite` を接続。`plain_path`/`storage_parent`/`storage_lease` による単一プロセス所有、接続前の残存 `-wal`/`-shm`/`-journal` 掃除、`trusted_schema=OFF`・`quick_check`・`user_version`・厳密 `sqlite_master` 検査（`thumbs` のみ）、再起動をまたぐ `touched` LRU順序の継続と起動時 `_evict()`、ロック競合/破損時の fail-open 再初期化・無効化、およびバックアップ/復元からの除外（`storage_backup.py`/`live_backup.py`）を実装。関連単体テスト **73 PASS**（`test_thumbnail_cache.py`・`test_thumbnail_priority.py`・`test_storage_backup.py`・`test_live_backup.py`）。詳細は[サムネイル正本](thumbnail-derivatives.md)。

- **P3 モニター間DPI（RasterizationScale）自動再取得接続と永続 <db>.thumbs.sqlite 再起動横断実機確認（e46c53d）**：src/Aredoko.WinUI/MainPage.xaml.cs で XamlRoot.Changed を購読し、DIPサイズ変更を伴わないモニター移動時の RasterizationScale 変化でも80ms集約タイマー（itemSizeTimer）から実現済みライブラリカード（containerRefresh）・棚カード（MainPage.Shelves.cs の shelfRefresh）・詳細プレビューの派生edgeを再評価するよう接続（既存bitmapを保持したまま必要時のみ新DPIバケットを再取得、Coreテスト・Portable build/publish 0 errors）。あわせて 	ools/test_native_persistent_thumbnails.py を追加し、最新ステージング data/ai-ui/p3-persistent-thumbs-20261024/staged-release/Aredoko（758 files）＋生成24 PNG/2 CBZ＋独立LOCALAPPDATAで実機検証。初回 
un01（ハーネス側の .owner.lock ファイル非存在検査ミス、生ログ/PNG保全）を with storage_lease(thumbs_db_path): によるロック解放検査へ修正し、
un02 で **25 checks PASS**（Phase 0 で 
ows=30・max_touched=30・ytes=18,779・WorkingSet64=188.1MB、再起動後 Phase 1 で 
ows=30・ytes=18,779 不変のまま max_touched=60 へ進行し全30要求の100%永続ディスクキャッシュヒット・WorkingSet64=187.6MB・生成26原本SHA/mtime完全不変・全所有 Aredoko.exe/Aredoko.WinUI.exe 終了0・残存0、2 PNG全目視）。詳細は[サムネイル正本](thumbnail-derivatives.md)および[結果ウィンドウ正本](p3-result-window.md)。

## 次の実装1件
**P3/P7 大量画像スクロール時の体感速度・High Contrast/Light/狭幅UI監査、または P6 実catalog/完全NOTICE/公開先の確定。**
- P3/P7側：永続 `<db>.thumbs.sqlite` が有効な状態での再起動後サムネイル再表示と実RSS/decoded RAM境界、または未受入のHigh Contrast/DPI/Light・狭幅のUI監査を生成fixture＋独立LOCALAPPDATAで進める。P6側はレビュー済み実artifact・完全なNOTICE・runtime pack公開先が確定し次第source registryへ登録する（推測URL/架空hashで有効化しない。新モデル/依存取得は別許可）。完了済みのP5形式2復元・P6モデル配置・P1B生成再生・P2境界・P3同じflowを毎回再テストしない。

## 直前の実装手順（上記P6で完了済み、再実装しない）
**P6：役割別保存先のAPI・Core・native UIを接続する。** `c7db80d`のbackend解決を再実装せず、以下へ進む。
1. app所有registryのprofile bindingから取得対象の役割/モデル定義をsummaryへ渡し、Coreで検証する。catalog名や単なるkind=modelからWD/embeddingを推測しない。runtime用の既存選択は維持。
2. 所有setup jobで一つの役割を明示保存できるAPIを追加し、他の役割・共通root・runtime・themeを保全する。旧共通folder/resetで全役割指定を解除する動作とは区別する。モデルID/revisionとprofileの対応を保持し、将来の同役割別モデルの選択も壊さない。
3. native setup/取得完了ボタンを役割のcurrent/pending場所へ接続し、明示適用・取消・再表示を生成fixtureで確認する。現在workerのhot swap、profile/namespace変更、P5 active/pendingや復元整合の破壊をしない。通常はSolで可、既存の選択/復元安全性に収まらない設計変更時だけAstraレビュー。

その後、レビュー済み実artifact・完全なNOTICE・runtime pack公開先を確定してsource registry登録へ。WDの公開元とmanaged sidecar方式は確認済みだが、推測URL/架空hash/未監査NOTICEで有効化しない。新モデル/依存の実取得は対象/容量/取得元を示して別許可。

## 未完・運用
- P0/P1B実機/P2/P3性能・完成形UI/P4/P5復元/P6配布/P7総合受入のPARTIALは維持。[完成台帳](completion-roadmap.md)と[実音声等の内容索引](media-content-plan.md)の未完も保持。全音声/音楽、実catalog取得/推論、clean Windowsは未受入。
- 最新[ローカルGUI/GPUテスト方針](local-test-policy.md)に従う。生成fixture/独立DB・設定/既存モデルの通常関連検証は事前許可不要。旧環境2/2、復元3/3、取得1/2、P3等は履歴であり永久禁止ではない。同じ失敗の無変更反復は止め、診断→有意味な修正→対象確認。今回の基本ZIP限定1試行は終了済みで、新機能確認と混同・再命名しない。raw失敗を成功へ読み替えない。
- 私物scan/原本変更/通常DB/旧Alpha/shortcut/新モデル・依存取得/OS・driver変更/外部送信は無断実行しない。Actions0、既存Draft PR継続、main merge/新branch/新PR/force pushなし。**シャットダウンしない**。
- [文書/legacy整理](repository-maintenance.md)、[旧依存監査](legacy-dependency-audit-20261024.md)、[文書案内](README.md)を保全。旧Catalog/server等は製品依存のため削除しない。
- 再開時はfetch/status/HEAD/PR確認後、上記「次の1件」へ。本書だけを短く更新し、AGENTS/互換handoffへ大量追記しない。詳細証拠は対応する技術文書、履歴はGit/履歴索引へ残す。
