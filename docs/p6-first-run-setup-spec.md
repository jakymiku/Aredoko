# P6予約仕様：初回セットアップ・任意AI環境導入（2026-10-27）

> **状態: P6-S1/S2はsource/関連Core・Portable build/限定UIA確認済み。S4/S5のガイド復帰・安全な復旧案内はsourceと関連確認まで。S3の公開runtimeとS6の実導入受入は未完。** 現行の再開位置は `docs/current-handoff.md` を優先。現行branch・Draft PR #5を継続し、完了済みの取得基盤を再実装しない。

## 2026-10-27：P6-S1の現在地

`POST /api/library/ai/setup/plan`へ用途4種類の複数選択を渡すread-only契約を追加。検索profileのmodel/revision/directoryに一致する信頼済みcatalogだけを提示し、4用途で共有するembeddingモデルを1件へ集約。WDを必須化せず、runtimeとmodelを別要件として扱う。runtime未公開なら既存配置を選ぶ導線と未確定の総容量を返し、モデル容量だけで全導入容量を偽装しない。複数catalogが同じ要件に合致した場合も勝手に選ばない。

AIを使わない選択はruntime/model/catalogの確認すら行わず基本操作を継続できる。現在の配置ファイルの存在と推論/driverの確認は別。planはGPU/モデル/索引/取得job/設定変更を起動せず、絶対ユーザーパスを応答へ含めない。認証・strict JSON/不正選択・重複・revision/role相違・既存配置・未対応profileを生成CPU7件で確認。証拠`data/ai-ui/continuation-20261027b/setup-plan01.log`。新しい用途選択WinUI、選択保存、配布runtime公開、clean Windowsはまだ未完。

### P6-S2：用途から始めるWinUI入口

空ライブラリのAI準備ボタンと「使い方・初回設定」から、用途4種類の複数選択→read-only環境確認→既存の取得/配置/索引画面へ移動するnative画面を追加。AIなしで開始でき、選択した用途と明示opt-outをUI設定へatomic保存、既存backup/restoreでも保持する。backendの依存解決をWinUIへ重複実装せず、モデルだけの容量を全導入容量と表示しない。確認中の条件変更・閉じるで応答を無効化/取消し、取得や推論を自動開始しない。

Core `--setup-plan`（reflection無効）/設定保持、生成backup3件とPortable/frontend04を確認。初回はJsonArray.Add(string)がreflection無効で失敗したため、明示JsonValueへ修正し、新しいIL2026を除去。frontend03は修正前として使わず、04を候補とする。native入力/driver/実導入/clean Windowsを合格にしていない。予約仕様の全工程完了でもない。

個別許可後のsetup-native01は、専用6媒体/既存固定model catalogのmetadataのみを使い、**前面化・物理入力なしのUIA操作**で10checks/3PNG目視/exit0 PASS。4用途→runtime未公開とmodel容量の区別→選択保存→再表示→AIなし選択保存→再表示を確認。download/setup jobはidle、audio/video ownerは未作成、生成原本不変。取得ボタンを押したりGPU/再生を使ったりしていない。モデル取得/配置の遷移後の新しい一連受入、実導入/clean Windowsは未完。

## 目的と対象
### 2026-10-28：P6-S4のガイド復帰（source実装）

用途ガイド→取得/配置/索引設定→ガイドの往復をawait可能な一つのflowへ接続。子画面を閉じると用途を保持してread-only planと既存取得/配置jobの状態を再確認する。取得中/中止/失敗、配置検査中、保存後の再起動待ち、媒体別索引の次手順を区別し、取得済みを設定済み・推論成功と扱わない。閉じる/用途変更で古い応答を取り消す。取得や索引は明示操作のみ、公開runtimeの未解決は保留したまま。

Core関連21項目とPortable/frontend01 build PASS（既存picker3/SDK trim警告のみ）。nativeの取得/配置/索引画面からの復帰と選択保持は許可待ちで、実導入・clean Windows受入ではない。次の確認は`tools/test_p3_native_containers.py --setup-return`（新規専用出力、生成素材、UIAのみ、取得/推論なし）。

### P6-S5の安全な案内（2026-10-28、source）

既存planのstate codeをCoreで保持し、未配置/モデル版の不一致/ファイル不足/実行環境の不正/設定不正を短い日本語で区別。「うまく使えないとき」を折りたたみ表示し、既存の診断情報画面へ往復できる。原本・DB・索引・環境の削除/初期化、システムPython変更、強制的な版マーカー変更は行わない。推論や機器の未確認も明示。未知stateは一般案内にし、生のパスや内部値を表示しない。全機能非対応/依存情報なしを配置正常と表示しない。

関連Core29項目、read-only plan/APIの生成Python7件PASS。Portable/frontend02は最終Coreの境界補強前のbuildであり、最新sourceのnative受入ではない。GUIと実環境修復/clean Windowsは未検証、公開runtime/driver互換診断/自動修復完了とは扱わない。

### モデル選択の再起動待ちもガイドへ反映

使用モデルの保存先とは別に、profile選択は再起動まで旧namespaceで動く。従来planは環境保存先の変更しか再起動待ちに含めず、詳細設定から戻った直後に旧モデルの取得を勧める可能性があった。選択だけの軽量snapshotを追加し、全profile列挙やモデル実行なしでpending/起動引数優先/設定不正をplanへ反映。pending時は旧model catalogを自動選択せず、WinUIの取得入口も無効化し、先に再起動を案内する。現在のモデルや既存索引は切り替えない。

Core33、Pythonのplan8＋profile13 PASS。Portable/frontend03は最新C#/Coreをpublish済み（既存picker3/SDK trimのみ）、backendは上記推薦抑制も補強。最新の一括確認は`--setup-recovery`で取得/配置/索引/診断の往復と、CPU fixtureによる保存profile変更→ガイドのpending表示をまとめる。旧frontend01への許可質問は未回答・未実施。新しい候補のGUIは対象範囲を更新してから確認し、旧許可へ自動拡張しない。

個別回答後のfrontend03限定UIA：`setup-recovery-native01`で取得画面→ガイドを確認。配置後は試験のactiveモデル保存先と保存先設定が異なり、正しい再起動案内をtestが不足表示と誤比較して停止（raw FAIL/3PNGを保持）。cleanupもmodalを閉じずWM_CLOSEを送る旧harnessのため停止し、所有guideをUIAで閉じて通常closeで解放した（exit code欠測、強制終了なし）。試験設定を揃え、modalを閉じるcleanupへ修正後、追加回答による`native02 --setup-skip-download`は成功部分を繰り返さず、配置/索引/診断→ガイド、用途保持、profile pending、job idle/モデルowner未作成を11checks/3PNG目視/exit0でPASS。UI source ffe3998、backend d6acd9c。foreground/物理入力/Clipboard/取得/GPU/通常DB/Alphaなし。配布runtimeや実環境導入・自動修復の受入は別。

ZIP解凍→`Aredoko.exe`でPythonなしの基本機能を起動。初回の用途選択から、必要な任意runtime/モデルの導入・検証、初心者向け使い方、故障時の安全な復旧まで一貫して案内する。WinUI 3ネイティブ、既存Python/SQLite/owned API、既存profile/namespaceを維持。

利用目的は複数選択可能：**意味検索／類似画像検索／動画検索／音声・音楽検索**。基本検索だけで開始する「今はAIを使わない」を必ず設け、後から設定で追加・再実行できるようにする。

## 着手条件（実装順序のゲート）
1. その時点の`AGENTS.md`・`current-handoff.md`・`polish-roadmap-20261022.md`・PR #5と実装を再確認。現在進行中の機能、明示的なGUI/GPU許可制約、他エージェントの変更を優先。P6の独立作業が許される段階でのみ本仕様を実装キューへ移す。
2. 既存Portable同梱Python、`app/ai_runtime.py`、`app/ai_runtime_preferences.py`、`app/ai_acquisition_registry.py`、取得job、モデル別配置/設定画面を調べ、再利用可能部分と未接続部分を一覧化する。
3. AI runtimeの実ダウンロード有効化は**完全なThird-Party NOTICE・権利確認、固定版の配布先/許可host、全ファイル検証情報、runtime trusted registry登録と動作確認**が揃ってから。未解決の場合、GUIとローカル選択/手動案内を先行してよいが、架空URL/hashや任意pip実行で代替しない。
4. 既存のモデル2件（EmbeddingGemma 2、WD Tagger）取得実績と、runtime登録0件を混同しない。音声・動画の未完成能力を完成扱いしない。

## ユーザー導線（基本3段階）
1. **機能選択**：4種類を複数チェック可。機能説明と現時点の対応状況を示し、戻る/スキップ/再開を許可。モデル名はデフォルト画面の主語にしない。
2. **環境診断・取得**：OS/アーキテクチャ、CPU、GPU/VRAM、RAM、driver、ディスク空き、既存runtime/モデルを診断。検証済み対応表のみでCPU/CUDA実行候補を提案。取得元・必要容量・ライセンス・モデル用途・任意帯域制限を示し、明示同意後にruntime/モデルを取得。取得/検証/選択を別状態とし、進捗、取消、Range再開、失敗理由を表示。未公開runtimeは「自動導入準備中」と明示し、既存配置選択/手動案内へフォールバック。
3. **利用開始ガイド**：登録フォルダ→スキャン→必要な索引作成→検索→閲覧まで最小チュートリアル。通常画面からスキップ・再実行可能。許可なしでユーザーファイルを自動スキャンしない。

## 機能→依存の解決
- 意味検索：既存のファイル名/タグ意味・画像/ページ検索で利用するEmbeddingGemma 2 profileを優先。検索方式ごとに異なる索引空間/次元を混ぜない。
- 類似画像検索：既存の画像embeddingと画像起点類似検索を再利用。意味検索と同じmodel/revisionが使える場合は取得を重複させない。
- 動画検索：従来の最大4代表フレーム検索を維持し、別の直接全区間索引/文章検索/直接類似の入口を追加済み。生成動画の限定GPU/WinUI確認済みで、実動画品質・長時間性能は未受入。動画内音声は直接動画索引へ統合していない。
- 音声・音楽検索：既存の直接音声内容検索/保存済み類似/旧512D特徴を区別。実録音・実音楽への品質保証や自動常時解析を宣言しない。必要モデル/runtimeの実catalogが揃わない場合、取得可能と偽装しない。
- WD Tagger：4用途の必須にはしない。希望者が別途選ぶ自動タグ候補機能として提示。
- 依存解決は `capability -> (runtime role + model profiles + readiness + unavailable reason)` の明示的契約で実装。必要機能の集合から重複を排除し、役割別rootの設定を保全する。

## Python / PyTorch / モデル
- 基本ZIPには既存の隔離Pythonを同梱。ユーザーPCのシステムPython・pip・venv・PATH・GPU driver・OS設定を変更しない。
- PyTorch / transformers等は既存`aredoko-ai-runtime-v1`契約に従う独立runtime pack。配布実体と固定catalogの権利/整合確認後のみ明示ダウンロードを可能とする。CPU/CUDAの互換性は実測した組合せのみ推奨。
- 所有jobの原子公開・SHA/inventory/validator・取消/再開を再利用。取得完了と推論成功を別扱い。選択は検証後に明示保存、必要なら次回起動に反映。
- バージョン導入時に既存正常pack、モデル、保存先、手動タグ、旧索引を上書きしない。model profile/namespaceの更新は既存索引と混在させず、必要時だけ再索引案内。

## 初心者ガイド・復旧
- `docs/user-guide.md`の古いMSIX/旧導入/旧未実装説明を事実に合わせて整理。GUIの「はじめての使い方」「AI環境の確認」「修復」を設定/ヘルプから再表示。
- 故障を「基本ZIP異常／runtime不足・破損／model不足・破損／driver/VRAM非対応／通信・容量不足／索引未作成」で区分。個別の再検証/再取得/以前の正常版への戻し/基本検索の継続を提供。
- 強制全初期化を通常修復に使わず、DB/設定/原本/タグ/棚/お気に入り/索引を保全。診断ログはtoken、個人パス、媒体内容を漏らさない。
- セットアップ状態は原子的に保存。途中取消/クラッシュ/再起動は安全に再開し、未検証ファイルを有効にしない。

## 実装単位と完了基準
P6-S1：既存能力/モデル/runtimeの依存表と診断契約（静的CPU確認）。
P6-S2：初回WinUI画面・設定から再実行・AIスキップ（基本機能は非ブロック）。
P6-S3：公開承認済みruntime catalog → 既存所有jobへ接続。実公開が未解決ならBLOCKEDを明示し、架空配布で合格にしない。
P6-S4：モデル取得/既存配置/役割別選択と同意・再起動反映を接続。
P6-S5：初心者ガイド/安全な修復、user-guide更新。
P6-S6：新しいZIPでCPU/所有API/WinUIの限定確認後、Python未導入のclean WindowsでZIP解凍→基本起動→AI導入→実推論→再起動→修復/取消/オフライン/再配置/設定保全を受入。未検証は未検証のまま記録。

**完了判定**：外部Pythonなしで基本検索・閲覧が可能。対応PCかつ公開済み依存では、明示同意だけで必要runtime/モデルを検証導入し実推論が成功する。非対応・未公開・ネットワーク失敗時でも基本機能を失わず、復旧導線がある。

## 守る開発運用
不要な新branch/PR、main merge、頻繁なCI、原本/通常DB/既存Alphaへの無断操作禁止。差分に関係する限定テストだけ行い、失敗は診断して根拠を残す。実行に着手した時点で`current-handoff.md`に実作業と次の1件を記す。この予約仕様を今日の完了済み機能として報告しない。
