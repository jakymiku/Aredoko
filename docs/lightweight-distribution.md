# 通常起動とAI追加環境を分ける配布計画

## 2026-11-10 開発再開：専用フォルダのSDK

ユーザー承認で計画段階を終了し実装を再開。開発はホストの専用フォルダ方式を第一選択とする。以下の「SDK導入は検索受入後」「ビルドはSandbox」は11月9日の計画で、この変更により置き換える。システムへのSDK登録や永続PATH変更を避け、配布版の通常起動へ開発環境変数を引き継がない。完全な開発環境未導入条件の受入はSandbox等で別に行う。GUI/GPU試験は実行前にユーザーへ知らせる。

`tools/prepare-dev-dotnet.ps1`はMicrosoft公式の.NET SDK 10.0.403 win-x64 ZIPを固定SHA512で照合し、ignoredの`data/development-tools`へ新規展開する。版/hashの根拠はMicrosoftの[10.0 release metadata](https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json)。既存SDK directoryは上書きせず、取得/hash失敗時は未完fileを実行しない。これは開発用で、製品の初回取得経路ではない。

利用例：`./tools/dev-dotnet.ps1 build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Portable '--property:Platform=x64' '--property:AredokoPackageChannel=Portable'`。PowerShellのコロン付き短縮引数解釈を避けるため、MSBuild propertyは引用した長形式で渡す。SDK/CLI home/NuGet cacheは専用directoryに集約し、成功・失敗ともプロセス環境変数を復元する。永続PATH/registryを書き換えず、Visual Studio/WinApp GUIを導入しない。OSの完全隔離ではない。

SDK初回起動が開発HTTPS証明書を生成したことを観測した。信頼操作は未実施。wrapperへ`DOTNET_GENERATE_ASPNET_CERTIFICATE=false`を追加して以後の生成を抑止した。システム全体の変更が一切ないと報告しない。

製品用Pythonは未選定。公式NuGetの3.11系列は照会時3.11.9までのため、開発互換性だけで古い版を標準採用しない。更新される公式配布形式と対応AI依存の組合せを次に実証する。既存backendのABI検証はPython 3.11以上を受け入れるが、これだけで新しいPython版の推論互換性を保証しない。

### Pythonなしの取得処理：最初のCPU実証

`src/Aredoko.Bootstrap/PythonSetup.cs`はWindows同梱.NET Frameworkで動く独立console helper。公式CPython NuGet 3.13.17を候補として固定URL/公開SHA512で照合し、新規stagingに展開してから指定した未使用directoryへ公開する。既存環境は上書きしない。hash不一致・異常path・取得失敗を拒否し、失敗stageは証拠として保持する。downloadはTLS1.2・redirect拒否・128MiB上限。検証から展開までarchiveをwrite不可で保持する。SHAの根拠は[NuGet公式registration](https://api.nuget.org/v3/registration5-semver1/python/3.13.17.json)から参照するcatalogEntryのpackageHash。

開発入口は`./tools/prepare-native-python.ps1 -OutputDirectory <新規directory> [-Package <取得済nupkg>]`。Package省略は実downloadのため明示した取得操作としてのみ使う。初回GUIや通常bootstrapからの自動呼出しは未接続。現在の配布検証は同梱Pythonを前提としており、このhelperだけで新方式の配布完了とはしない。取得済環境の再利用・取消/再開・進捗通知・修復・AI venv導入・製品runtimeへの接続は次の実装。

2026-11-10 CPU証拠：公式公開SHA512一致のnupkgでnative helperの展開成功、実downloadも成功。初回downloadのTLS失敗はTLS1.2明示後に解決。破損fixtureはhash不一致で公開directoryなし、既存destinationは拒否。展開したPython3.13.17のSSL/SQLite/import正常、SQLite in-memory integrity ok。別の同じ公式packageからvenv作成→pip26.2.2起動を確認。AI依存・実モデルload/検索・通常DB・GUI/GPUは未実施。ignored `data/development-tools`に取得物/専用SDK/venv/失敗stageを保持する。

専用SDKでWinUI Portable build成功（0error/既存WUI1001×3）、Core CPU suite exit0、既存取得登録CPU8件PASS。wrapperは成功/失敗時のPATH/DOTNET_ROOT/NUGET_PACKAGES/CLI_HOME復元を確認。初回のPowerShell引数解釈とnull環境変数復元の不備は修正済み。全媒体/配布先の受入ではない。

## 2026-11-09 ユーザー指定の完成形（以下の旧方式より優先）

- 配布物にはPythonを含めない。Pythonなしで動くネイティブbootstrapが初回起動で取得内容・容量・進捗を示し、アプリ専用の基本Pythonを取得・検証して基本機能を起動する。システムPythonやPATHに依存しない。
- 初回設定でAIを選んだ利用者だけ、取得したPythonを基にアプリ管理venvへPyTorch等を導入する。AIを選ばない場合はAI依存・モデルを取得しない。基本環境へAI依存を直接追加しない。
- AI環境は利用者PCで公式のビルド済み配布物から構成する。通常導入でPython/PyTorchのソースコンパイルを要求しない。完成済み巨大AI packの自前ホスティングを必須としない。
- **2026-11-09 user確認：AI有効化の条件**：Python/依存package/モデルを固定した公式配布元から取得し、公式に提供されるSHA等を信頼済みの版別取得定義へ束縛して照合する。モデルは既存profile/revision/namespaceを維持する。取得未完・hash不一致・依存不足の状態ではEmbeddingGemma 2を使用可能にしない。
- 構築後は、取得済みartifactの検証結果とwheel等の配布inventoryを根拠に、実行環境/依存/モデルの必要fileと整合性を確認する。構築後の自分自身からhash一覧を作っただけでは公式原本との一致証明としない。生成される設定・cache・pyc等と検証対象の実行fileを区別する。
- 整合性確認後に隔離した生成fixtureでimport/モデルload/推論の動作確認を通し、初めてAI-readyとする。hash一致と実行互換性は別に判定する。失敗時は原因を表示して基本機能を保ち、不完全なstagingを使用中環境へ昇格しない。次回起動/更新/修復でも既存の改変検出を維持する。
- 公式配布元でも対応版/依存集合/取得元/hashを固定する。取得・導入の進捗、取消、再開、失敗理由を示し、未完の環境をreadyにしない。既存DB・モデル・稼働環境を保全した新規staging→検証→公開を使う。
- 既存のpack検証/配置経路は互換・再利用候補として保持するが、新しい標準導入経路とは区別する。以下の「基本Python同梱/完成済みruntime pack取得」は旧到達点。

現在のbootstrapは同梱Pythonを前提としているため、上記は未実装。最初の単位はPythonがなくても起動するbootstrapの取得導線と基本Pythonの検証・配置・再起動再利用。次に基本機能、AI選択時だけのvenv構築へ進む。Windows embeddable Pythonは通常のpip管理に制約があるため、venv/pip対応を実証できる配布形式を選定し、既存embedded runtimeへ単にpipを足して完成扱いにしない。

環境初期化後のホストを初回配布テストに活用する。開発SDKの復旧許可は取得済みだが、2026-11-09の最新指定により、導入からAI検索までの受入が済むまでホストへの開発環境導入を延期する。既存Python 3.13があるためホストを「Python未導入」とは呼ばず、SDK未導入・既存Python非依存の試験とする。完全なPython未導入条件はSandbox等で別に確認する。

### 実装再開時の計画（2026-11-09、現在は計画のみ）

**到達点**：配布EXEから案内に沿って基本環境と任意のAI環境・モデルを取得し、整合性確認と実推論を経て、生成素材の索引作成と日本語AI検索ができる。その後でホストの開発環境を復旧する。今回はソース実装・SDK/依存/モデル取得・環境変更を行わない。

| 順序 | 利用者にできること／作業 | 完了条件 |
| --- | --- | --- |
| 0 | 配布契約とビルド場所を決める | Pythonの公式配布形式、venv/pip対応、対応Windows/CPU/GPU、全依存の固定版・取得元・容量・ライセンス・検証根拠を一覧化。Sandbox等の隔離ビルド環境で自己完結した配布物を作り、ホストにはSDK/WinApp/開発venvを入れない。GitHub Actionsは使用しない |
| 1 | Pythonのない状態でも初回案内を開ける | 既存native bootstrapで取得前に内容・容量・保存先を提示。公式Pythonを取得・検証しアプリ専用領域へ配置。基本依存も固定版で導入し、システムPATH/既存Python/py launcherに依存せず再起動後も再利用できる |
| 2 | AIを使わず基本機能を使える | 生成素材の登録→ファイル名/タグ検索→閲覧→終了/再起動と保存保持。AIを選ばなければtorch/モデルを取得しない。Python取得自体が失敗した場合は基本backendも未起動であることを明示し、再試行できる |
| 3 | 「AI検索を使う」から必要環境を準備できる | 取得済みの専用PythonからAI専用venvを作成。対応確認済みの公式wheelと全推移依存を固定し、検証済みローカルartifactから導入。通常経路でソースbuildや無制限な最新版解決をしない。CPU/GPUの対応条件を案内し、driverを自動変更しない |
| 4 | モデル取得からAI使用可能まで進める | モデルの公式repo・不変revision・必要file/hash・利用条件を確認。artifact照合→構築済み環境/モデルの整合性→import/load/生成fixture推論を順に通す。すべて成功後にのみEmbeddingGemma 2をreadyにする |
| 5 | 実際にAI検索して使い続けられる | ホストの配布EXEから生成素材登録→AI索引完了→日本語で検索→結果を開く→再起動後に同じ索引で再検索。単なるモデルload成功では検索受入にしない。通常DB/私物は使わず、原本不変・独立DBの整合性を確認 |
| 6 | 失敗から復旧できる | 取得取消/通信断/hash不一致/容量不足/構築失敗の対象確認。未完はreadyにせず、既存正常環境・DB・model profile/namespaceを保持。再試行・修復・更新が可能で、必要な証拠を保存 |

**取得と検証の境界**：信頼済みの版別取得定義には公式artifactの出所とSHA等の根拠を記録する。公式がhashを提供しないfileを「公式hash照合済み」と扱わず、署名等の代替根拠または方式変更を決めてから採用する。構築後の検査は検証済みwheelの内容・インストール時の正当な変換・生成fileを区別する。自身で採番したinventoryだけで公式原本との一致を証明しない。配布EXE/取得定義自体の真正性の扱いも実装前に決め、hashだけであらゆる改ざんを防ぐと称さない。

**実装の切り方**：まず0の未決事項を解消してから1を実装し、各行の関連確認後に次へ進む。取得中/検証中/構築中/動作確認中/使用可能/失敗・取消を区別し、stagingから検証成功した環境だけを公開する。既存の取得job・原本guard・atomic配置・startup検証・model identityを再利用する。再開時は途中fileも検証し直し、未検証の環境でbackendやAIを起動しない。

**試験場所と開発環境導入の解禁**：ビルドは隔離環境、初回導入と実GPU/検索はホスト、完全なPython未導入条件はSandbox等として結果を分記する。ホストへ入れるのは製品自身が管理する実行環境だけで、開発ツールを先に導入しない。上記1–6の対象受入と未検証範囲を報告し、検索できる状態になってからホスト開発環境の復旧へ移る。隔離ビルドが利用できない場合も、ホストSDK導入で黙って代用しない。

> **2026-10-25 現在**：基本ZIP、背景検査/配置保存GUI、EmbeddingGemma 2/WDの実取得が進んだ。現行の次作業は[current-handoff](current-handoff.md)、モデルは[AI取得](ai-acquisition.md)、runtime配布の通知不足は[収集結果](runtime-notice-inventory.md)。以下のLD4/LD5 TODOは当時の計画で、再実装指示ではない。runtimeの実公開物/完全NOTICE/clean Windowsは依然未完。


> **最新2026-10-22**：[LD4a既存folderの背景検査job](ai-setup-jobs.md)。非同期開始/実hash進捗/中止/atomic保存/終了cleanupまで。LD4はPARTIAL、次trusted catalogとtransactional取得の生成HTTP検証。basic03は前段snapshotのまま、GUI/download/clean Windowsは未受入。

2026-10-21。ユーザーが「ZIP解凍→本体を開く、AIを使う場合だけ画面から追加」「初回/更新時の完全検査、普段は軽い確認」の方針で開発を明示承認した。新しいPortableの通常起動に関して、以前の「毎回全SHA必須」を本書で置き換える。原本/DB/source guardの緩和や既存配布の書換えは許可しない。

## 利用者から見た完成形

1. 基本ZIPを解凍してAredoko.exeを開く。Python/.NET SDK/winapp CLI/pip操作を要求しない。
2. AI未導入でもファイル名/タグ検索、登録/整理、画像/本/動画の閲覧を利用できる。
3. 「AI検索を使う」から必要な追加環境とモデルを取得する。対応済みの配置済み環境/モデルの指定、公式から手動取得する経路も提供する。
4. 追加取得は容量/実進捗/取消/再開/不足理由を表示。初回から黙ってダウンロードしない。製品の速度上限は既定なし、任意上限のみ。
5. 普段の起動ではGPUライブラリ全量を毎回読み直さない。完全検査は初回/更新/変更検出/明示修復時。Check-Startup.cmdは開発確認用で通常利用に要求しない。

## 今回の実装と到達点

### LD1 通常起動の検査を分離 — CPU_DONE

tools/startup_validation.pyを新規実装し、Portable launcherに接続。初回は既存preflight（全SHA/全inventory/通常path/祖先link/type/hardlink/実import/media probe）を通し、その前後の全file metadataが安定した時だけ外部のrelease-validationへreceiptをatomic保存する。失敗/取消/更新途中のreceiptを成功として公開しない。

次回は全inventoryの増減・file identity/size/mtime/ctime/mode/link属性を確認し、bin/backend/tools/bootstrap/Python coreとDLLsを再hashする。bulk site-packagesとmedia runtimeはmetadata照合とする。root絶対位置/manifest SHA/probe契約が変わる、receiptが壊れる、metadataが変わる場合は完全検査へ戻す。既知のhash不一致は拒否し、現在の壊れた内容を新しい正常値として学習しない。空間的な原本guardや旧MSIX経路は保持する。

**保証の違い**：metadata方式は通常の破損/変更検出であり、bulk fileの全bytesを暗号学的に再証明しない。metadataを意図的に保存/偽装した改変や、同権限でのcache/manifest改変に対する署名の代わりではない。元のmanifest自体もpublisher signatureではない。この方式を「従来の全SHAと同等」と報告しない。完全検査API verify_release/preflight/--check/--verify-onlyは以前のまま。developer launcherの--full-checkで強制完全preflightを追加したが、ルートAredoko.exeの修復ボタン/引数はまだ未接続。

走査は既存_parallel_treeの全lexical guardを維持し、最新leafの通常file/reparse/hardlink検査を追加。metadataだけのために同じ祖先走査を重複しない。内容を読む主要hashは従来の_verify_fileで再guardする。cacheは配布の外に置き、lease/通常path検査/新しいtempへの書込/flush+fsync/replace/取消を使う。user media/modelsのmetadataを収集しない。

full/軽量とも進捗は実際に処理する件数/bytesのみ。軽量時のhash総量を5GBと表示せず、完了していないfull検査を装わない。初回receipt作成の追加metadata走査はコストがある。起動ごとのmetadata取得もゼロにはしておらず、即時起動は保証しない。

### LD3 AI追加環境とモデル配置 — CPU_DONE（製品GUI未接続）

[独立契約・実装・検証・限界](ai-runtime-setup.md)。既存packの明示検証/保存、runtime不足とmodel不足の別診断、next-restart適用、現在app worker隔離起動を接続。最新sourceのbasic03候補696files/656,061,210bytesで実同梱Python/backend/診断/生成PNG登録検索preview/正常終了/DB整合をCPU確認。初回3.982480s/通常1.488302s（warm単発、GUI未確認）。02を上書きせず、新docsは準備時snapshot。GET診断と開発CLIまでであり、自動download/製品設定画面/重い検証のHTTP保存jobはLD4/LD5。任意packの推論互換性・配布元認証・clean Windowsを受入済みにしない。

### LD2 PyTorchなしの基本候補 — CPU_DONE（native未確認）

既存prepare_python_runtime.pyの非AIモードを利用し、明示した既存CPython/Pillowだけを新規data/basic-runtime-20261021-01へ構成。元のPython/venv/モデルは変更しない。さらに新規dist/portable-basic-20261021-02/Aredokoへbootstrap/自己完結WinUI/基本Python/動画toolを梱包した。torch/transformersは含まない。

| 実物 | 展開後のfiles | 展開後bytes |
| --- | ---: | ---: |
| 従来の全AI入り候補 | 24,329 | 5,554,470,502 |
| 新しい基本候補 | 692 | 656,009,829 |

約656MBは**ZIP圧縮前のフォルダ容量**。ZIPは未作成。FFmpeg/ffprobe約444MBは基本候補にも含む。別取得に分けても、GPU追加環境を導入した後の合計容量が消えるわけではない。

実基本候補の同梱Pythonを-I/-B・無関係なcwd・無効なPYTHONHOME/PYTHONPATHで実行し、torchを発見しないことを確認。実production backendを専用空DB/ephemeral loopback portで起動し、所有instance/session→stdin EOF正常終了0→SQLite integrity_check=okを確認。基本環境のSQLite/PIL/importとFFmpeg probeもPASS。通常利用のGUI/画像登録・閲覧の一連/clean Windows/既存DB再起動保持をこの結果から完成としない。 同じ実同梱環境で生成PNG1枚だけの登録→scan完了→ファイル名検索1件→画像preview686bytes→AI未導入状態の確認もPASS。生成原本SHA/mtimeは不変、EOF正常終了/DB integrityもPASS（basic-portable-cpu-20261021-02/report.json）。GUI操作の受入とは区別する。

通常起動のcacheは通常data/release-validationへ保存する。Check-Startup.cmdは毎回新しい専用dataのため、既存通常cacheを使わず初回完全確認になる開発用モードで、日常の入口ではない。

### 実測とテスト

- 初期の新規テスト16 PASS/4.343s。
- 既存配布/起動/IPC/所有権を含む120 PASS/127.228s（最後の重複走査整理前）。その後の整理と追加境界3件は関連25 PASS/6.405s。重複加算しない。
- 最初のregression01はrunnerのtests. prefix指定ミス9 import errors。02は配布fixtureに新モジュールを含め忘れ15 errors。fixtureを製品契約に合わせ03で120 PASS。失敗logを保持。
- 基本候補の完全preflight+receipt **3.994672s**、変更のない2回目 **1.527048s**。real probeを含むがGUI表示までの時間ではなく単発/warmな観測でありcold/p95ではない。
- 旧5.55GB候補では最初のcache試作が55.795823sとfull hash/inventory46.595100sより遅いと判明。重複祖先チェックを整理し24.045317sへ。ただしbulk入り版には多数file走査の負担が残る。最初のreceipt作成は151.235581s。計数instrumentのfull hash bytes加算にthread raceがあったため、その古いbytes値は採用しない。全hash検査の成功やwall timeとは別の計測不備で、元logを保持する。
- 最終の5.55GB再計測は同じ完全検査済みreceiptを使い、重いfullを不要に繰り返さず、hash-only計測契約をproduct probe契約と分離。実model/GUI/GPUは0。

証拠はdata/ai-ui/startup-validation-*、basic-portable-cpu-20261021-01/report.json、basic-runtime-20261021-01-prepare.log、portable-basic-20261021-0{1,2}-package.log。02基本候補が最終source snapshotで、01は整理前。旧candidate/installed Alpha/shortcutsは更新していない。既存GUI固定flow3/3は維持し、今回GUI再試験はしていない。

## この後の実行順（R13/PZ3を具体化）

| ID | 次の作業 | 状態/受入 |
| --- | --- | --- |
| LD3 | AI追加環境の独立契約と既存folder選択 | CPU_DONE。[契約/サービス/診断/検証](ai-runtime-setup.md)。独立pack ABI/SHAと明示保存、next-restart適用、worker隔離。製品GUI/取得はLD4/5、実GPU互換性未確認 |
| LD4 | 追加環境/モデルの取得job | TODO。承認された取得元/版/hashを持つcatalog、未完stage→検証→新version公開、取消/再開/破損/容量/認証/オフラインを生成HTTPでCPU検証。既存の正常pack/model/indexを上書きしない。システムpip/driver導入をしない。実downloadは別途具体物を示して許可 |
| LD5 | 簡潔な初回/設定GUI | TODO。AI追加/既存指定/手動案内、実進捗、再試行、修復の完全検査を一つの入口に整理。基本閲覧を取得でblockしない。旧GUI capを別名でresetせず、具体buildを用意して新GUI範囲を確認 |
| LD6 | 基本ZIP・AI追加後のclean Windows受入 | TODO。SDK/Python/開発用登録なしで解凍→通常起動→生成素材登録/検索/閲覧/終了→保存保持、AI追加/既存指定、更新/再配置、完全修復を受入。NVIDIA driver要件とアプリ同梱runtimeを区別。今回のhost isolationだけで代用しない |

上記は機能の廃止ではなく導入時期/梱包の分離。モデル交換/既存索引identity、全機能、P0 2/2閉鎖、専用OCR保留、U09/U11/U13/U14、ALPHA後実音声/音楽を維持。R13 DOING/ALPHA未完/R14 PARTIAL。新しいGPU/GUI/依存取得/Actions/main merge/旧shutdownなし。
