# Aredoko — 現行の単一引き継ぎ（2026-10-29）

## 2026-10-29 Sandbox有効化（ユーザー明示許可・再起動待ち）

- ユーザーの「そっちでオンに出来ないかな？」を受け、通常のUAC昇格でDISM `/Online /Enable-Feature /FeatureName:Containers-DisposableClientVM /All /NoRestart`を実行。**exit3010、機能InstallState1、Windows再起動が必要**。自動再起動は抑止済み。証拠は `data/ai-ui/continuation-20261029d/sandbox-enable01.json` / `.log`。
- 下段のSandbox未導入/InstallState2は有効化前の履歴。この変更はユーザー許可に基づくOS機能設定。**Sandboxゲストを起動/接続したことや、clean WindowsでAredokoが合格したことにはしない。** app/通常DB/Alpha/モデルは不変。
- 次回Windows再起動後にSandbox readinessを確認し、基本ZIP22＋生成検証セットで通常EXE起動/登録/閲覧/保存/アプリ再起動を確認する。候補と専用素材だけを入力共有し、結果を別保存する。P6の限定検証後は下段のUI主軸キューへ戻る。ユーザーの現在作業を中断する再起動は行わない。


## 2026-10-29d 終了checkpoint（以下より優先）

- **Git/基準**：起点8f741f7→remoteのAGENTS追記6322fc1をclean fast-forward。既存 `feat/winui3-production-mvp-20261011` / Draft PR #5だけを継続。最終アプリsource **68c010020f909519e635b23a8f54cd47aab838ce**。検証セット作成CLIはf9841c2。最終引き継ぎcommitは本書のgit logで確認。AGENTSの過剰防御/抽象化を避けるルールを適用し、旧UI/配布/P7全体を作り直していない。
- **UIでできること**：検索/種類/方式と表示操作を2行にまとめ、必要時だけ折返す。native媒体placeholder、長いタグの折返し/棚の変更ボタン一行化、grid/listの再起動保持、設定操作の2列化、3手順の使い方/詳細展開/フォルダ直行、初回カードの自然な表現、重複戻る/閉じるの整理を完了。fa75131で診断TextBoxが先頭1行だけになる実不具合を修正し、全診断/ビルド元を保持。個別commit/候補baseとworking差分/実証は[p3-continuous-browse末尾](p3-continuous-browse.md)。
- **最小確認**：表示設定の変更後に基本Python3.11関連3method＋Portable梱包1method、Core限定79/全1,441assertions PASS（重複加算しない）。以後Core/Bootstrap/backend無変更を照合して再利用。WinUI build/publishは0errors、既存picker WUI1001×3/SDK IL2104×2のみ。専用DB/生成素材/UIA-onlyで検索/詳細のLight/Dark、幅1100/1600、設定の保存/再表示、ガイドの両導線、登録画面/診断を確認。試験側のstale/不要scrollと診断全文欠落の製品FAILを分けて保存し、修正後を確認。物理キー/hoverの受入へ拡大しない。
- **最新試用候補**：`dist/portable-basic-20261029-22/Aredoko/Aredoko.exe`、source/ProductVersion68c0100、826files/661,850,275bytes。ZIP348,497,442bytes/SHA `fc0cd88edd9ae8373c19dfe1de9abf683bb88e6900f4f6d3c6a1a8d8128f79e3`。publish/全payload/ZIP/同梱check、CPU34（Basic20）を確認。通常EXEから空DB→初回ガイド→生成フォルダ登録→一覧のみ取得→タグ保存→終了→1再起動は17checks/所有4exit0/4PNG目視。Basic21の同ケースは二重合算しない。[候補の正本](portable-refresh-20261024.md)末尾。
- **P6配布**：rootの「はじめに.txt」/簡潔なUSER_GUIDEを追加。Basic21でsealed directoryを日本語/空白の別pathへコピーし、同じユーザーのgrid保存/再起動保持を17checks/4exit0で確認（別Windowsや新ZIP展開そのものではない）。別環境用 `dist/portable-validation-20261029-22.zip` を生成し全6member/原本一致を確認。PNG2枚/2頁CBZ/候補SHA/手順/未記入結果だけ、app/モデル/実行script/私物なし。再作成は `tools/prepare_windows_validation.py`。[別Windows手順](portable-windows-validation.md)。Sandbox未起動/stale・feature InstallState2で、OS機能の有効化やguest取得はしていない。
- **未完/未検証**：別Windows/clean machine受入、実runtime供給元/適用条項レビュー2件/不変host/production registry、実媒体品質/全codec/長時間描画RSS/HC/物理DPI/実キー・pointer等は残る。公開runtime/全ロードマップ/M1/M2の完了にはしない。installed AlphaはZIP10/source0138a58のまま。通常DB/設定/shortcut/モデル/私物は不変。Actions/DL/GPU推論/OS設定変更0。
- **次の1件 UI**：通常幅で常駐している一覧下部の「前へ/次へ・範囲・再接続」を、件数/選択/読み込み範囲が伝わる形へ小さく整理する。範囲移動や復旧機能は削らず、連続スクロール/選択/未保存タグを維持。今回成功した同一Core/GUI/CPU soakを前提なく再実行しない。**P6の次**：用意した検証セットで利用可能な別Windowsの通常入口/保存/再配置を確認。環境有効化/新規取得/公開が必要なら許可要件を守り、未成立を合格で埋めず独立UI作業へ進む。
- **証拠/終了**：`data/ai-ui/continuation-20261029d/` のbasic22-final-review.json、basic22-onboarding01、basic21-relocation01、basic22-validation-kit01.logと対象別reports。保存/commit/push・remote branch/PR5 head一致・cleanを36e2472まで確認、試験Aredoko/Python残存0をfinal-process-check01.jsonへ記録。終了時にdesktop SC_MONITORPOWER offも再送しWindows応答あり（monitor-final-off01.json）。この終了結果の追記後の最終commitは本書git logを参照。wake/常駐offループ/OS電源plan変更/shutdownは行わない。物理的な消灯維持は未観測。


## 2026-10-29d 追加checkpoint（UI実装済み・配布候補へ収録中）

- 6b0bb56で設定6操作を2列3行、bc73b09で使い方を3手順/旧詳細展開/フォルダ直行へ、9fdf07cで登録フォルダの二重戻るを共通BtnRootsへ統一。専用DB/生成素材/UIA-onlyで各対象を確認。[証拠とbase HEAD/作業差分の注意](p3-continuous-browse.md)末尾。
- 診断TextBoxが実際に先頭1行だけになる不具合を追加発見し、AcceptsReturn→Textの順へ修正。frontend10 diagnostic-footer-dark03は全文/ビルド情報保持を含む9checks/exit0/1PNG目視。旧02のFAILを保持。閉じるは標準footer一つ、clipboard未操作。各commitは本節直前のgit logを参照。
- BasicZIP20/source260e577は826files・CPU34/通常EXE16checks/所有4exit0、grid保存/再起動/戻したlist保存まで。後続settings/guide修正を含まない。次はそれらを基本ZIP21へ収録し、通常EXEから空DB→ガイド→生成フォルダ登録→一覧のみ取得→タグ保存→再起動を1ケースで確認する。Coreは260e577以後不変を照合して今回1,441assertionsを再利用する。
- モニター消灯要求済み、復帰/OS電源設定変更/shutdownなし。物理キー/HC/DPI/別Windows/公開runtimeは未検証。Sandbox未起動/feature InstallState2のため有効化やguest新規取得はしない。通常DB/Alpha/私物/モデルは不変。外部条件待ちを理由にUIを止めず、この後の最終checkpointを優先。


## 2026-10-29d 作業中checkpoint（以下より優先）

- 起点8f741f7、remoteのAGENTS追記だけの6322fc1をclean fast-forwardで取り込み。過剰防御/抽象化を避ける新ルールを確認。UI改善＋P6配布の並行指示で実装を再開し、古い「今回は文書だけ」は適用しない。モニターへ一度だけdesktop SC_MONITORPOWER消灯を送信（monitor-off01.json）、wake/電源設定変更/shutdownなし。
- **UI**：cfff134で検索と種類/方式を同じ行、表示操作を見出しへ移し、幅不足時は各群を折り返す。54a08ffで音声等の空白枠へテーマ対応native icon、実画像取得時は非表示、既存Image先頭/再利用/サイズ変更・取消を保持。frontend02/source54a08ffは生成6媒体でLight/Dark各31checks/exit0、両grid/list・未保存タグと保存を確認。sourcecfff134の先行各28を二重合算しない。1100px詳細時の見出しclip27px（自然73px）を目視/矩形で発見し、257f74cで子の自然幅から算定へ修正。frontend03/source257f74cの幅ケースは23checks/exit0、1100pxも見出し73pxを保持し2PNG目視。
- **試験側**：wrap01は検索変更で閉じた詳細へcloseを送ったFAIL、02は選択直後の全tree walkがstaleで停止。source修正を装わず履歴保存。更新完了後の再選択・ID指定待機に直した03は21checks/exit0まで通ったが見出しclipは後の目視で発見し上記製品修正へ進んだ。実pointer/keyの合格とはしない。
- **P6**：84a593dでPortable出力へUTF8 BOMの「はじめに.txt」と簡潔なUSER_GUIDEを追加し、通常入口/フォルダ一覧取得/任意AI/更新/診断用空DBを説明。基本Python3.11の既存Portable梱包/ZIP1件PASS。Sandboxは未起動/stale・OS feature InstallState2、guest受入は未実施/OS変更なし。既存portable-windows-validationへ新規Windowsの最小手順を追記した。
- **依存読取**：4046880で明示frontend/PIDだけのnative module inspectorを追加し、不一致拒否も確認。frontend02の専用UIAで158modules、WinUI本体は同梱先、開発SDK/NuGetからの読込を観測せず。外部3件はIME/securityのhost拡張で配布依存と混同しない。clean Windows/全codec/AI runtime公開の成功ではない。証拠root data/ai-ui/continuation-20261029d/、生pathsはignored reportのみ。
- **次**：frontend03の見出し欠け修正を幅ケースだけ確認→右詳細の棚操作/タグ欄の情報密度へ。P6は最終の新基本ZIPにguideとUIを収録し、通常入口/再起動をまとめる。Alphaは旧ZIP10のまま。最終の候補/commit/未検証/二系統の次を終了時に更新する。


## 2026-10-29 ユーザー決定：UI改善を主軸に配布・別環境起動も並行（以下より優先）

- ユーザーは「一旦使い心地と見やすさの開発へシフト、次の開発指示から」と明示。**今回は文書更新のみで、アプリ実装・GUI/GPU試験・Alpha更新は行わない。** 起点`705194e`、fetch後remote/PR #5 head ref一致・cleanを確認。今回commitは本書のGit履歴。
- **次の1件：主画面の検索・一覧の情報密度と視認性を整える。** 最新sourceと既存生成fixtureで現状を短く確認し、コンパクトな左ナビ/検索バーを維持して中央一覧を広く使う。検索・表示操作のまとまり、余白/文字の階層/項目の境界・選択状態を整え、既存のグリッド/リスト/棚共通表示を活かす。完了済みの省略表示や仮想化を再実装しない。計画の再作成だけで止めず、小さな利用者向け改善を実装する。
- 次は右詳細の情報整理→登録フォルダ/設定/初回案内→閲覧との往復を改善。[順序・完了条件](polish-roadmap-20261022.md#ux-priority-20261029)、[既存デザイン方針](design-vision-winui.md)を使う。通常幅1200–1600px、Light/Dark、短い自然な日本語、メディア中心。機能・未保存タグ・選択/スクロール・検索条件・キーボード・仮想化を保持する。
- **追加指示（起点207fe62、fetch後clean/remote一致）**：配布のしやすさと別環境起動もUIと並行開発する。P6を保留し続けない。基本ZIPの解凍/更新/保存保持→開発環境のないWindowsで基本一連→任意AI環境の導入完成を、[並行キュー](polish-roadmap-20261022.md#ux-priority-20261029)に従い小単位で進める。今回は引き続き文書のみ。
- **配布系の次の1件**：別Windowsの受入に必要な既存Sandbox/VM等の利用可否と、ZIP19で未確認の依存・起動条件を短く確認し、専用データの基本版受入を具体化する。既存ホストの起動成功をclean Windowsの合格にしない。環境が用意できなければ確認手順/必要物/未検証を記録してUI側へ進む。未承認のOS変更/依存取得/公開uploadは行わない。
- P6の公開runtime/条項/host/registry/clean Windowsは未完の**並行実装キュー**、P7の長時間描画/RSS等は必要な変更範囲以外を保留。引き継ぎにはUI/P6各系統の次の1件を残す。旧アニメ測定を自動再開しない。起動不能・データ損失・日常操作を阻害する再現済み不具合は優先修正する。全ロードマップ/配布完成の宣言ではない。
- 検証は変更箇所のbuild/関連確認とLight/Darkの必要な画面・操作に絞る。GUI環境が使えなければ実装/build等を進め、実機未検証を区別する。通常DB/私物/Alphaは変更せず、新依存や全回帰をUI改善の前提にしない。最新候補は下段の**ZIP19/sourcebb0d328**、installed Alphaは旧ZIP10のまま。

## 2026-10-29c 終了checkpoint（以下より優先）

- **Git/方針**：起点`62d2c1a`、既存branch/PR #5を継続。新branch/PR/main merge/Actions/force-pushなし。最終アプリsource **`bb0d328931eeeb7246dd3192f5f99b1e48542850`**、試験待機の訂正`868b2e7`。この引き継ぎcommitは `git log -1 -- docs/current-handoff.md`。PR live metadataは未取得のまま、branch/PR head refで照合する。通常DB/私物/Alpha/shortcutは変更していない。ユーザーは今回GUI/GPUを事前確認不要と再明示。shutdownしない。
- **P6：通知を具体化**：`9fc485b`/`6c0b85e`。CPython3.11.9/native38件の固定hash/通知対応契約、新規pack builder、static auditor連携。通知13原文105,350bytesを取得し、元parent23,918fileを全保持した新pack `data/ai-ui/continuation-20261029c/cpython-runtime01` は23,936files/4,950,977,993bytes、manifest `07b65b6b7a27caeaed8f344f4644f4725172bb4004792e453e89dc4cbb0ff736`。新9＋旧関連21（基本Python3.11）PASS。native335の未所有0/静的VC不足0、**pending notice review2、供給元証明/coverage/再配布承認false**。ZIP3,013,440,816bytes/2partの全member・結合SHAもPASS。公開物/host/registry/clean Windowsを完了扱いしない。[正本](runtime-notice-inventory.md)末尾。
- **完全照合の速度改善**：`0c73cdb`。全file SHA・path/link/size・前後guard・最終markerを省略せず、2reader/queue64/caller-thread progress・取消/全reader joinへ変更。生成8PASS。関連65は64PASS＋旧venv fixture誤認1FAIL→explicit venv/embedded当該2PASS（全65再実行はしていない）。実4.95GBで85.071→**68.373秒（約19.6%短縮）**、同じ結果/全counts/reader残0。1台1組・cache未初期化、起動全体/一般速度の保証ではない。[正本](ai-runtime-setup.md)末尾と `runtime-parallel-production01/report.json`。
- **動画検索の追加品質確認**：`c2c1a64`（実行source）/`e331c09`（後続CPU保全）。承認済み検証ZIP2つから49秒/49秒/4秒の無音slideshow3本を生成、9区間を既存EG2実worker GPUで索引化。日英7問 **Top1 7/7・Recall@3平均1・MRR1・一致区間13/13**、逆順・1秒tailも一致。完全照合85.938sは索引37.047sと分離。解放後cached類似/DB integrity/原本不変/所有worker停止exit1。CPU最終7PASS、重複ID・不正区間・出力上書きを拒否。実写/動作/実音声/音楽の品質ではなく、後続hardening/perf後のGPU反復もしない。[評価正本](video-scene-evaluation.md)、`video-scene-gpu01/report.json`。
- **UIの利用者向け改善**：`053d022`でSlider/Button native keyをpreview shortcutより優先し、画像/本のmenu中送りを抑止。`365d9a1`で動画/音声のファイル名をOSタイトルへ移し、重複上部バーを削除、positionを下部中央、読込/失敗通知をbar外へ。`bb0d328`で既存ViewerChromeControllerを共用し、約1秒/下端表示/操作・失敗中保持/常時表示設定を統一。新null警告はイベント登録前の初期化で解消、Portable build0errors/既存picker3警告。物理キー試験は前面化拒否→locked/secure desktopで入力前停止し、未受入。許可を再質問したりunlock制限を回避したりしない。[U2追記](usability-followup-20261025.md)と `keyboard-baseline01/02`。
- **最新試用候補**：`dist/portable-basic-20261029-19/Aredoko/Aredoko.exe`、実DLL ProductVersion `1.0.0+bb0d328…`。825files/661,796,403bytes、ZIP348,465,989bytes/SHA `a427e4af4625350e0d9d744b5de16c5b76b813050d7dc366c888356da7938592`。publish/全payload/ZIP/同梱check PASS。Core/Bootstrap source不変で従来1,438assertionsを再利用。19と18のbackend/runtime/EXE全entry一致を照合し18のCPU34を再利用（反復なし）。新19のUIA自動非表示4＋常時表示4、通常EXE起動/正常終了/1回再起動11、所有4exit0/6PNG目視。前段18/source365d9a1のtitle/音量5＋503→retry/同一bar座標5は3PNG目視、19の新規成功へ合算しない。17は中間buildのみ。AlphaはZIP10/source0138a58のまま。[候補正本](portable-refresh-20261024.md)、`basic19-final-review.json`。
- **試験の失敗と未検証**：初回controlの候補path誤指定は起動前停止。autohide01は正常にcollapsedでUIA peerが消えたのにIsOffscreenを待ったharness FAIL→`--gone`の02で成功。notice01と両設定はUIA-only/物理入力false、新動画の下端pointer/実キーを合格にしない。新video codec/seek/音声再生・HC/物理DPI・長時間RSS・実媒体品質・clean Windows/公開runtimeは残る。全ロードマップ/M1/M2完了ではない。
- **P7・原寸CPU復号の保持**：生成2560×1440/8frame APNG・WebPを本番Decoderで各256frame/32周処理し、sequence/原寸/budget/解放/原本不変PASS。warm後privateはAPNG約49MiB/WebP約67MiBで増加傾向なし、close後約20/24MiB。7.139/9.143sはCPU処理のみで、HTTP/WinUI/FPS/長時間全RSSは未検証。[正本](viewer-performance.md)末尾、`animation-soak-cpu01/report.json`。
- **次の1件**：P7のAPNG/WebP連続描画・高速切替取消を、生成素材・独立DB/UIA-onlyで小さく確認し、frontend/decoderのメモリ保持を分けて再現したボトルネックだけ修正する。今回成功したCPU32周は再測定しない。10/26の82.55MiB GIF/18frame APNG/CBZや3frame原寸・小10.gifの成功は再実行しない。locked desktop中は物理入力を要求しないUIA/CPUを使い、実入力を必要とする受入は未検証で残す。P6は適用条項/供給元レビューと実immutable hostが揃ってからruntime registryへ進む。推測URL/無承認公開をしない。
- **終了確認/モニター**：`94150a6`で保存/Push、branch/PR #5 head ref一致・clean・Aredoko試験process0を確認。残り約9%で終了準備。最終の有限消灯 `monitor-final-off01.json` は10.1sでoff通知あり→Windows側で再点灯（state1）、helperは正常終了。復帰指示/常駐消灯loop/電源plan/security policy変更なし、消灯維持はできていない。shutdownしない。この結果追記後の最終handoff commitは本書のGit履歴で確認する。

## 2026-10-29c 継続中checkpoint（以下より優先）

- cleanな`62d2c1a`からfetchし、branch/PR #5 head ref一致・他AI更新なしを確認。ユーザーは今回GUI/GPUの事前確認不要、終了時のモニター復帰も不要と明示。shutdownはしない。
- **P6を一単位完了**：`9fc485b`/`6c0b85e` のCPython component契約・通知13件105,350bytes・新規pack builder・static auditor接続が完了。生成9＋関連21（基本Python3.11）PASS。実 `cpython-runtime01` は23,936files/4,950,977,993bytes、manifest `07b65b6b7a27caeaed8f344f4644f4725172bb4004792e453e89dc4cbb0ff736`、旧parent全payload entry同一/追加18通知fileのみ。335nativeのinventory対応は0gapだが、再配布/供給元証明/notice coverage承認はfalse・pending component2。ZIP3,013,440,816bytesと2part全member/結合SHAを確認。公開host/registry/clean Windowsは未完。[正本](runtime-notice-inventory.md)末尾と `data/ai-ui/continuation-20261029c/` の各report。model/GPU成功は不変なので反復しない。
- **UI操作の局所修正**：`053d022` で音量/シークSliderとButtonのnative keyをpreview shortcutより優先し、画像/本の設定menu表示中は背景の送りを抑制。Portable build0 errors/既存WUI1001×3、APIはrestored projectで確認。実キーreproは前面化不可→locked/secure desktopをwinappが明示し入力前停止、両所有exit0。許可不足ではなくdesktop readiness不足で、実キーを合格にしない。既存ZIP16のUIA-only生成無音WAVでは音量75/消音とpause独立・原本不変・正常exit0を確認（getter schema誤認は修正）。新sourceの実キーは未確認、最終候補のpublish/UIAを後でまとめる。[U2追記](usability-followup-20261025.md)と `keyboard-baseline01/02` / `player-uia-state01/02`。Source buildと旧SUTを混同しない。
- **P7の直接動画検索を一段確認**：承認済み検証ZIP2つから3本の無音slideshow（49秒/49秒/4秒）を新規生成、9区間を実worker GPUで索引化。日本語5＋英語2問 **Top1 7/7・MRR1.0・一致区間13/13**、並び逆転と1秒tailも一致。完全照合85.938sを索引37.047sから分離、子の3GiB条件を維持。解放後cached類似/DB integrity/fixture SHA/モデルmetadata不変/所有worker停止exit1。実写・動作・音声品質ではない。[評価正本](video-scene-evaluation.md)、`video-scene-fixture01/` / `video-scene-gpu01/`。初回prepare import誤名は読取前に修正、CPU契約6PASS。tool SHAをreportと照合しcommitする。
- **完全照合の速度を改善**：全SHA/通常path・link拒否/size・前後検査/最終markerを保った2reader・queue64の実装を追加。64file未満は逐次。progress/取消callbackはcaller thread、異常時全readerをjoin。生成8PASS、関連65では64PASS＋venvとembeddedを取り違えたfixture1FAIL→explicit venv/standaloneの当該2件PASS（製品起動の隔離は維持）。実4.95GBで85.071→68.373s（single local pair、cache未初期化、起動全体保証ではない）、結果/全counts同一/reader0。[正本](ai-runtime-setup.md)末尾、`runtime-parallel-production01/`。GPU評価はこれ以前のsourceで、model/rank/decoder不変のため反復しない。
- **次**：現在までの変更を基本ZIP17へ収録し、専用DB/生成無音WAVによる新sourceのUIA-only状態確認＋通常EXEの起動/終了/再起動をまとめる。物理キーはdesktop unlock確認まで試行せず、実キー未確認を残す。公開host/権利承認待ちは維持し、production registryへruntimeを登録しない。
- monitor-off01はC#未使用field warningで指示前停止。修正後off02は消灯通知が来たが直後にWindowsが再点灯。復帰指示は送っておらず、power plan/security policy/他appは変更していない。終了時にもう一度消灯指示を送る。常駐の強制消灯loopは作らない。

## 2026-10-29b 終了checkpoint（以下より優先）

- **基準/Git**：起点`5f9ab9f`。並行Work `a6f6e04346a7fb3f91ef86abdbfdec3eb3c049dc` の初期化前cached類似検証をレビューし、`376ecfa` で双方の履歴を維持して統合。handoffの同位置追記だけ競合し、双方を保存した。基本Python3.11の関連HTTP3件PASS。新branch/PR/main merge/force-push/Actionsなし。最終アプリsource **`292fdf2a2a121caf70e088c0753a8417d682250f`**、本引き継ぎcommitは `git log -1 -- docs/current-handoff.md`。PR metadata connector不調は継続し、remote branch/PR #5 head refで照合する。
- **利用者向けUI**：`2f01d50`/`cbc1c9e` でライブラリ/棚の長いファイル名を実枠幅で省略し、全文tooltip/読み上げ/selection/draftを保持。表示方式・画面切替時にサイズmenuが残る不具合も修正。Light/Dark各25checks＋menu残件7checks、計16PNG目視/正常exit0。初回menu残留と修正後を別証拠に保持。[UI正本](p3-continuous-browse.md)。
- **任意AI環境**：`fe62f60`/`1789142` で固定CRT12DLLを旧環境とは別のpackに組込み、`99e444e` で12DLL/3通知を封印inventoryへbound。候補 `data/ai-ui/continuation-20261029b/crt-runtime01`、23,918files/4,950,784,575bytes、manifest `9ac04f2d56895690dd620971f2d3ae1dcffe731d45ba5225b26a4f86f845f731`。実CPU loaderでrootのCRT解決（ORTのmsvcp140_1含む）を確認。生成PNGの実EG2 GPU 768D/WD CPU各1回PASS、専用DB integrity/原本不変/両worker回収。全文照合は既定どおり行い、GPU計測とは分離。再配布権利/clean Windows受入ではない。[native正本](runtime-notice-inventory.md)。
- **輸送実装**：`292fdf2` でv4分割runtime ZIPの各part Range再開/全SHA/直接seek展開を追加。2〜8part/各2GiB未満、結合済み3GBcopyを作らない。v1/v2/v3・既定速度無制限・取消/所有publication/原本guardを維持。新規15method＋旧関連45、基本Python3.11で関連19/owner22もPASS（重複合算しない）。初回2FAILはpayloadの正規python311.zipを禁止したharness誤りで修正済み。実3,034,460,747bytes ZIPも1,900,000,000＋1,134,460,747bytesへ分割・全member/結合SHA検証PASS。実外部3GB配信/公開/registry登録はしていない。[輸送正本](runtime-archive-transport.md)。
- **最新の試用候補**：`dist/portable-basic-20261029-16/Aredoko/Aredoko.exe`。source/ProductVersion292fdf2、ZIP348,446,465bytes/SHA `556f6f0b5d5a49e574b7db1ca3fd111c14534880815f6a3238cb17a876c21f16`、823files/661,762,612bytes。WinUI Portable publish/全payload/ZIP/同梱check・CPU34項目PASS、通常EXE起動→正常終了→1回再起動 **11checks/2PNG目視/所有4exit0**。Core/tests/BootstrapはZIP15から無変更を照合し過去1,438assertions＋案内11項目を再利用、反復していない。既存picker3件/SDK IL2104×2は保持。[候補正本](portable-refresh-20261024.md)。証拠は `data/ai-ui/continuation-20261029b/` の `basic16-final-review.json`、各report/log。installed Alphaは**ZIP10/source0138a58のまま**、通常DB/settings/shortcut/私物は不変。
- **未完/未検証**：runtimeの適用再配布条項/実不変host/production registry/clean Windows。静的native335件はPython RECORD285＋MSVC component12＋未対応38、静的VC未解決import0。38はCPython本体4＋DLLs34（OpenSSL/SQLite/Tcl/Tk/標準拡張等）の通知対応未確定で、38起動不具合という意味ではない。実3GB外部転送、HC/物理DPI/長時間RSS、実媒体品質/全codec/実再生seek、U7実ダブルクリック/外部起動、音声映像rank統合等は残る。全ロードマップ/M1/M2完了としない。
- **終了前の追加単位**：`tools/inspect_runtime_notice_gaps.py` を追加。native監査/封印SHAに対応する未所有native38件/20,382,600bytesとroot LICENSEだけを照合し、通知内の語句の行番号を人の確認候補として返す。既存owner/権利/registryは変更しない。基本Python3.11の改変/別inventory/越境/重複/未分類維持/独立CLIの5tests PASS。最初のCLI helper import不足は読取前のtool側失敗として保持し、修正後の実reportは `notice-gaps-real02.json`。基本ZIP16のアプリcodeは不変で再buildしない。[正本](runtime-notice-inventory.md)末尾。
- **版/出所の追加整理**：[静的参照JSON](cpython-native-reference-20261029.json)へ38file SHA/bytesとPE版resourceを固定。Python32件3.11.9/OpenSSL2件3.0.13/SQLite1件3.45.1.0/TclTk各1件8.6.12、libffi版なし。公式CPython同版external一覧とlicense原典/OpenSSL同版原文/SQLite案内をブラウザーで読取参照。上流script実行/依存binary追加取得/packへの原文追加/公開承認は行わない。版情報だけを供給元証明にしない。
- **次の1件**：この参照からCPython/native通知のcomponent契約と同梱原文を具体化し、ファイルSHA/出所/通知の全対応が揃った**新規pack**だけを封印する。OpenSSL/SQLite/LZMA/zlib/Expat/decimal等についてroot LICENSEの語句不一致だけを「原文がない」「配布不可」と断定しない。新model/依存binaryの追加取得が必要ならAGENTSの許可要件を守る。旧candidateは改変しない。条項/実hostが揃うまで推測URLでregistryを有効化せず、待ちだけなら独立した完成形UI/既知未受入へ進む。成功済みCRT import/GPU/同一caption/native/全Coreを繰り返さない。
- **終了条件/モニター**：ユーザーは今回GUI/GPUテストを許可。追加取得/installer/公開upload/OS power設定変更なし。消灯要求は通知されたがWindows側で再点灯し、専用helperは復帰処理を終え**初期の点灯状態/残存helperなし**を確認。実行policyは変更/回避していない。消灯維持の常設設定は作らない。今回shutdownはしない。利用枠が切れる前に文書/commit/push/remote一致を確認して終了し、次回は同計画の続きへ。

## 2026-10-29b 継続中checkpoint（以下より優先）

- 起点`5f9ab9f`、remote同一/cleanを確認して既存branch/PR #5で続行。今回はユーザーが通常のGUI/GPUテストを許可。shutdown指示は再適用しない。
- `fe62f60`/`1789142`：固定CRT12DLL/完全通知を新規AI packへ組込み、全SHA封印→実CPU loaderでapp-local解決→生成PNG/実EG2 GPU・WD CPUまでPASS。旧runtime/通常DB/Alphaは不変。pack `data/ai-ui/continuation-20261029b/crt-runtime01`、23,918files/4,950,784,575bytes、manifest `9ac04f2d56895690dd620971f2d3ae1dcffe731d45ba5225b26a4f86f845f731`。公開権利/host/clean Windowsは未完で製品catalogへ登録しない。[正本と証拠](runtime-notice-inventory.md)。
- `2f01d50`/`cbc1c9e`：ライブラリ/棚の長名captionを実際の枠幅へ合わせ、全文到達とselection/draftを保持。Light/Dark各25checks、size flyoutの残り修正7checks、計16PNG目視、正常exit0。frontend01/02はsourceを区別。[UI証拠](p3-continuous-browse.md)。
- 並行Work `a6f6e04` のcached音声/動画内音声の初期化前検証を確認して統合。アプリcode競合なし、handoffの同位置追記は双方を保存。Windows基本Python3.11で新しい不正要求/両cached類似HTTPの3件PASS。双方のcommitを保持したmerge commitでPushする。
- 次は新しいpackの輸送ZIP/公開前のnative通知対応と、今回UIを収録する基本ZIP16の通常入口を小単位で仕上げる。まだこの節は作業中。最終candidate・未検証・次の1件を終了時に更新する。新branch/PR/main merge/Actions/外部取得0。
- 一度限りの依頼でmonitor消灯/復帰を試したが短時間で再点灯し、維持はできなかった。全専用controllerを終了、OS display_state=1へ復帰確認済み。電源plan/実行policy/OS機能は変更しない。以後のGUIは通常表示で続行。

## 2026-10-29 Work軽量継続（類似検索の初期化前検証、以下より優先）

- 起点 **`5f9ab9f34af136579dc1cc84dd7003f3e0ee037e`**。前回Work `9b7d91d`から18commits先行を確認し、変更されたローカルsnapshotを固定HEADへ同期。PR #5 open/Draftを確認。下段のWindows/Core/native/実worker・ZIP15受入を保持し再実施しない。今回commitは本書のGit履歴。
- **軽い修正1件**：通常音声・動画内音声のcached類似が、不正なitem ID/page/limit/対象範囲でも400を返す前にowner/PCM索引を初期化する経路を修正。純粋な共通request validatorと既存catalogのscope検証をFeatureのlazy初期化より前へ移した。scorer側も同じvalidatorを使い、正しい検索・cached検索/上限/取消/原本guardは保全。
- **確認**：新HTTP testは旧実装で1 FAIL/0.634s（ownerが作られる）。修正後、新HTTP＋両cached HTTP＋既存audio similarityは **20 PASS/7.153s**。生成sidecarを未作成状態にして全20不正リクエスト後もowner/monitor/sidecarなし・encode0を追加確認した1件 **PASS/0.577s**。重複を合算しない。py_compile成功。[音声正本](audio-producer-review.md)末尾。
- 新C#/GUI/GPU/配布build・取得・通常DB/settings/私物/Alpha/OS/Actions/shutdown変更なし。下段の一度限りのshutdown指示は再適用しない。ここは部分snapshotで他端末の未push差分は未確認。
- **次の1件は下段P6 CRT pack組込み準備を維持**。今回の軽量修正は次回のbackend同梱候補へ反映する。下段の静的展開許可を実DLLコピー/loader/import/worker確認へ拡張せず、Windows担当が具体的範囲を示して進める。

## 2026-10-29 ローカル継続の終了checkpoint（以下より優先）

- **基準**：cleanな`53c5093`から既存branch/PR #5を継続しremote更新なしを確認。他AIのWork完了分は再実装していない。最終アプリsource **`0edbd409c81e4baf79788deef9830f3b01d86c85`**、文書commitは `git log -1 -- docs/current-handoff.md`。PR metadataはconnector不調で再取得できず、remote branch/PR head refで照合する。新branch/PR/merge/Actionsなし。
- **利用者向け改善**：`136d22b`でAI依存不足/architecture/初期化の固定エラーを日本語の安全な復旧案内へ接続し、起動途中workerを回収。`13ed761`で異常stdoutの満杯queueにreaderが取り残される再現を修正。通常索引/原本を壊す実証ではない。最終案内は実在の「設定」→「AI検索の準備」→「配置済みを指定」。関連CPU/基本Python3.11/Core/WinUI build PASS。[AI環境](ai-runtime-setup.md)。
- **完成形UIを一単位前進**：`31f32dc`で詳細の重複ファイル名を除き、長名を最大3行/省略/全文到達付きへ。階層付き位置と未保存タグは保持、元検索へ戻る表示を短縮。14/source29114e6でLight/Dark各9checks・計6PNG目視・正常exit0。初回Lightのfixture期待145対2は起動前のharness失敗、追加回答後に修正。小gridの長名/全カード、HC/実DPI/clipboard/hoverは未受入。[主画面](p3-continuous-browse.md)。
- **前回のGUI残件を解消**：13のUI/sourcea2bc5d2＋backend136d22bで、動画内音声の準備/中断/再開・処理名・文章/音声類似/両区間/画面履歴14checks、745件一括favoriteの同一session/一覧外選択/favorites fallback12checksがPASS。全9PNG目視、双方exit0。初回のツール実行制限/UIA再利用失敗は残し、追加各1試行の許可範囲だけ実施。再生/seekや実モデル品質の受入ではない。
- **動画内音声の実workerも限定PASS**：`29114e6`のtoolで生成2動画を専用DBへ索引し日本語2問が狙ったTop1、解放後のcached類似と両時刻まで確認。完全runtime照合161.875秒/約4.95GB→index32.547秒、PyTorch peak1,121.5MiB/上限3,072MiB。childは停止（既存kill式exit1）。初回は照合を180秒予算に含めた試験停止でGPU未開始、追加許可後は照合を別CPU工程へ移し省略せず成功。実録音/音楽/長動画の品質とは区別。[動画](video-similarity.md)。
- **P6の正式CRT実体を前進**：`5c83009`/`5af2e86`で固定公式EXEを許可後に静的展開し、READONLY MSI対応表とx64 minimum **12DLL/2,666,168bytes/14.51.36247.0/署名Valid**を照合。既知不足msvcp140_1.dllも含む。[固定inventory](msvc-crt-inventory-20261029.json)/[残件](runtime-notice-inventory.md)。実installer/MSI action/DLL実行・OS install・既存runtimeへのコピー・公開0。今回の静的許可は消費済み。
- **最新候補：基本ZIP15/source0edbd40**、`dist/portable-basic-20261029-15/Aredoko/Aredoko.exe`。822files/661,730,728bytes、ZIP348,427,988bytes。最終publish/全payload・ZIP/同梱check・基本CPU34/EOF exit0/integrity PASS。14の全Core1,438をsource差分照合で再利用し案内11項目だけ追加確認。15自体のGUI通常起動は未実施、14の限定nativeを15の新規受入とはしない。[正確なSHA/範囲](portable-refresh-20261024.md)。Alphaは従来ZIP10/source0138a58のまま。
- **不採用案を残さない**：runtime検査の重複path削減＋handle照合は生成525fileで1.470→2.719秒、速くならず未commit案を戻した。CPU89件成功も高速化の証明にはせず、案と比較証拠だけignored出力へ保存。既定の完全検査/任意オフ/取消を維持。
- **次の1件：P6の新規CRT packへの組込み準備**。上記12DLLの固定実体を使い、適用するVS配布条項/NOTICE、既存root/wheel内の旧CRTとの関係と配置方針を確定する。別出力にだけ組み込めるbuilderを小単位で作り、実DLLコピー/loader/import/worker確認が必要なら具体的範囲を提示して許可を得る（今回の静的展開許可へ拡張しない）。同じ公式EXE取得・一覧・成功済みnative/GPUを反復しない。その後immutable host/trusted registry/clean Windowsへ。UIはこれら全受入を待たず並行継続。
- **残り/保全**：実媒体品質/複数track/rank融合/再生seek、U7実入力、HC/物理DPI/長時間RSS、公開runtime/clean Windows。M1/M2/全ロードマップは未完。生証拠root `data/ai-ui/continuation-20261029/`（Git対象外）。通常DB/settings/私物/Alpha変更0、追加モデル取得0。GUI/GPUは回答済み範囲を消費、次回PC使用中なら再び具体的に質問する。**ユーザーの最新一度限りの指示で、保存/Git/引き継ぎ確認後に `Stop-Computer`（Forceなし）を実行する**。強制終了や制限回避はしない。将来の継続に常時shutdown指示として持ち越さない。


## 2026-10-28 ローカル継続の終了checkpoint（以下より優先）

- **Workの10commitsを同期**：cleanな`bb58c27`→`9b7d91d`へfast-forward。Work「開発引き継ぎ確認」の完了報告とremoteを照合、完了機能を再実装していない。既存branch/PR #5を継続。PR head refは照合、open/Draftの現在metadataはconnector Transport closedで取得できず（Work確認時はopen/Draft）。
- **Windows未確認分を補完**：Coreのvideo-audio59/audio43/video66/favorite26がPASS、Portable frontend01/source9b7d91d成功。同梱Python3.11で生成video stream/video-audio/cleanup44、別のmedia index/search/jobs/PCM92がPASS。通常DBや実model品質の確認とは区別する。証拠root`data/ai-ui/work-sync-20261028/`。
- **追加sourceの利用者向け変化**：`692d66c`で動画内音声の別索引を初期ガイドへ案内し、他kindの進捗誤表示を防止。`33e85bb`で準備中ファイル名を1行表示（basename/160UTF-16/ellipsis、完了・取消で消去）。Core Audio49/Video72・setup35、関連PythonとWinUI build PASS。追加scan/モデル起動/設定変更を自動で始めない。
- **性能と不具合**：`4205e87`でprivate類似pairのSQLite版pollを64pair以内へまとめ、取消/catalog/profileと公開前/返却時のguardは維持。768D生成1万pairはquery10,012→168、0.520→0.467s（trace有/各1回、実素材一般性能ではない）、ID/score/両区間同一。関連39 unique PASS（初回runner71には重複収集あり、新2件は別途確認）。`a2bc5d2`は音声idle解放の一時handover失敗で監視threadが止まる経路を再現・修正し8 PASS。crash/data破損を再現したとは扱わない。[音声](audio-producer-review.md)/[動画](video-similarity.md)。
- **最新試験候補は基本ZIP13/sourcea2bc5d2**：`dist/portable-basic-20261028-13/Aredoko/Aredoko.exe`と隣のZIP。821files/661,695,036bytes、実ProductVersionもa2bc5d2。同梱基本CPU34/正常EOF/元PNG/DB integrity・全payload/ZIP検証PASS。33e85bbの全Coreを、Core/UI/Bootstrap source不変の証拠付きで再利用し、13では同じ全Coreを反復せずPortableを最終版でpublish。[正本/容量/SHA](portable-refresh-20261024.md)。13のGUI/実model/GPU/clean Windowsは未実施、Alphaや旧ZIPを更新していない。
- **MSVCの固定実体を確認**：ユーザーの明示許可後に公式18,731,856bytes/version14.51.36247.0を取得、Microsoft署名Valid・SHA固定。静的inspector/生成7件/Windows metadata確認済み。runtimeとVS2022 Communityの公式原文・REDIST関係も読取。[公開receipt](msvc-runtime-source-20261028.json)/[条件と残件](runtime-notice-inventory.md)。installer実行/展開/DLLコピー/OS導入/catalog登録/公開承認は0。現在の許可はこの静的確認で消費済みであり、導入へ拡張しない。
- **次の1件：質問中のGUI2ケース（回答後のみ）**。frontend01/source9b7d91dで①動画内音声の準備/中断/再開・文章/右click類似・画面履歴、②745生成itemの一括favorite・同一session/一覧外選択/favorites fallback、各1試行を準備済み。**GUIの回答はまだなく、実行0/1＋0/1**。`tools/test_p3_native_containers.py --frontend data/ai-ui/work-sync-20261028/frontend01 --output <新しい専用出力> --video-audio-content`、別出力で`--bulk-favorite-patch`。生成データ/CPU vectorだけ、再生/GPU/通常DB/Alphaを使わない。排他portが使用中なら止め、通常版へ接続しない。前面化を強行しない。
- **試験側の補強**：`15a3a51`の上記2ケースと`09e9a6b`のAutomationId指定で、検索mode追加後の古いEndキーによる誤選択を防いだ。生成UIA-tree3件PASS、GUIそのものの成功ではない。初回basic11の期待503対正しい404、test import漏れ/重複収集、PSModulePath互換問題はrawを保持し、製品不具合と分けた。
- GUI不可の間の独立次候補はP6の正式CRT一式/適用する配布条項・通知・安全な別出力への組込み準備。その後native依存/loader・公開host/trusted registry・clean Windowsへ。固定元を未取得状態へ戻して同じ調査やDLを反復しない。ユーザーのZIP配布方針を維持し、OS installerを自動実行しない。
- **未完**：動画内音声の実model/録音/音楽/動画品質、実再生seek、複数track/rank統合、U7実入力、HC/物理DPI/長時間RSS、runtime公開。全ロードマップ/M1/M2完了とはしない。完成形UIは機能と並行。今回GPU0/GUI0、追加model取得0、Actions/新branch/PR/main merge/shutdown0。installed Alphaは前回更新したZIP10/source0138a58で、当作業から通常DB/settings/私物/shortcutへ変更していない。引き継ぎcommitは`git log -1 -- docs/current-handoff.md`、Push後にremote一致/cleanを確認して終了する。

## 2026-10-28 ローカルWindows作業中の記録（当時、最上段の終了checkpointを優先）

- Work「開発引き継ぎ確認」とGitHubの10commitsを確認。cleanな既存branchを`bb58c27`→`9b7d91d`へfast-forward、PR #5 head ref一致。新branch/PR/merge/Actionsなし。Workの完成済み実装は再作成しない。
- **Windows側の未確認を補完**：Coreのvideo-audio/audio/video/favorite各限定suite、Portable/frontend01 publishがPASS。既存picker3件/SDK trim警告は保持。同梱基本Python3.11＋生成素材の新video stream/video-audio source/index/HTTP/similarity/owned cleanupは44tests/30.544s PASS。source`9b7d91d`、証拠`data/ai-ui/work-sync-20261028/windows-build-review.json`と各log。
- **現在の次**：動画内音声の準備/取消/再開→文章/音の類似→画面履歴、および一括favoriteの同一session/一覧外選択/favorites fallbackを、frontend01・専用DB/生成素材/CPU vectorの2ケースへ準備。GUIは2ケース各1試行の質問が回答待ちで未実施。実再生/seek・実model品質・GPU・通常DB・Alphaは対象外。新しい実装へ入る場合もこの既存binとsourceを区別する。
- **追加の統合改善**：動画用途の初期ガイドに映像/動画内音声の別索引を案内し、共有audio ownerの他kind進捗を自分の進捗として表示しないよう補強。Core setup35/同梱Python setup8 PASS。ユーザーガイドにも新機能の入口とAlpha未収録を追記。この追加UIのnative受入は未実施。
- **追加CPU進捗**：Workの音声/動画のindex/search/jobs/PCM streamをWindows基本Pythonで92tests PASS。`4205e87`はprivate pair内のDB版queryを最大64pair間隔へ削減、取消/catalog/profileと公開前/返却時guardは維持。768D/1万pairの単回は10,012→168query、0.520→0.467s、ID/score/両区間同一。39 unique関連method PASS（初回runner71にはimport再収集の重複あり）、新2件だけも再確認。基本ZIP11/source692d66cは全Core/Portable/同梱CPU34まで、後続perfは未収録。
- **MSVC取得の明示許可は実施済み**：公式ファイル18,731,856bytes/version14.51.36247.0、Microsoft署名ValidとSHAを固定。[公開可能な取得receipt](msvc-runtime-source-20261028.json)。新しい静的inspect tool/生成7件と実Windows metadata読取も確認。installer実行/展開/OS導入/DLLコピー/catalog登録0。runtime EULAとVSの再配布許諾の対応は未承認であり、署名確認を公開承認にしない。GUI2ケースの質問は別で、回答待ちのまま。
- **準備中ファイル名のsource接続**：音声/動画/動画内音声のcurrent progressに任意item_titleを追加し、1行ellipsis/tooltipで表示。basenameだけ最大160UTF-16単位、旧API省略互換・絵文字・制御/path拒否・2item対応/終了消去を確認。関連jobs32/label3、Audio/Video Core/WinUI build PASS。frontend01のGUI質問はこの後続表示を対象としていない。API statusはread-only、開始/取消は引き続き明示操作だけで、新しい自動scanや推論はない。
- **レビューで発見したidle解放の停止を修正**：audio側のpeer handover一時失敗でidle threadが終了する経路を生成encoderで再現。video側と同じ捕捉/既存待ちで再試行し、本人だけ解放・lock回収・監視継続を確認。関連8 PASS。初回test import漏れと旧codeの本来のFAILを別々に保持。アプリcrash/data破損の実証ではない。
- AlphaはZIP10/source0138a58のまま。Work sourceはまだ配布物へ未反映。runtime固定取得物/再配布条件/host/clean Windows、実媒体品質、HC/DPI/RSSは残る。PC使用中のGUI/GPU事前確認を継続し、shutdownしない。

## 2026-10-28 Work継続checkpoint（cached動画音声類似と初期化/終了cleanup、以下より優先）

- 起点`5641dfe`→**`dfaf1f6699ed662279ad63fc2fca1db41a4820ae`**で動画内音声のcached類似backend/Core/WinUI sourceをcommit/push。既存branch/open Draft PR #5を継続。今回cleanup commitは本書のGit履歴。ユーザーの「止まってる？」を受け再開、サブエージェントなし、現在クォータ％取得不可。
- **新機能**：「音が似た動画」を保存済みPCM索引から比較するVideoAudioSimilarity→共有audio owner→認証`video-audio-ai/similar`/固定mode `video-audio-similar`を追加。origin/candidateともvideo限定、音声file/RGB類似と別mode/source。追加decode/推論なし、同profileのcached索引はモデルavailable=falseでも使用可。両区間、自己除外、10万pair cap/最大2item分buffer・破損/取消/原本・DB版/scope保全を継承。
- **GUIはsourceまで**：動画の右クリック「音が似た動画を探す」、両区間の根拠/候補時刻再生、元検索復帰/前後画面履歴へ専用flagを追加。cached検索にmodel resident待ちを追加しない。通常audio/映像/代表frame/旧番号は保持。関連 **24 PASS/9.756s**（新類似5＋既存音声類似17＋両認証HTTP2）、py_compile成功。実model/Windows品質の確認ではない。[動画正本](video-similarity.md)末尾。
- **追加の再現・修正**：audio/video Jobsが開始失敗threadをjoinしてcleanupを止める経路、未初期化Featureの二重encoder.close、音声role登録拒否時の新encoder未close、Feature初期化途中ownerの公開を修正。ownerとmonitorはconfigure後に一括公開、失敗はlocal owner/idle threadを回収し閉じたencoderの再利用を禁止。closeはinit_lockで一回だけ、初期化取消は先にclosed/eventを通知して既存catalog/fence待ちを中断する。
- **失敗時の利用者向け応答**：初期化後段失敗は安全なAIUnavailable→HTTP503、statusは未初期化/failed・`audio_initialization_failed`または`video_initialization_failed`、Core sourceで再起動を案内。私的な例外文は応答へ出さず、causeを保持。通常ライブラリ/原本/既存索引は継続利用できる。
- **cleanup確認**：新6methodの旧実装はsubtest込み**7 FAIL/4 ERROR・0.455s**（thread join例外等と新終了契約の不一致）。修正後のfault/旧初期化取消/動画通常経路/新HTTP3は **18 PASS/5.014s**。開始済みidle threadの回収を追加観測した1件 **PASS/0.076s**、py_compile成功。前段成功との重複合算なし。Coreのエラー表示回帰sourceも追加したが、SDK/Windowsなしで**Core/C#/WinUI/Portable/nativeはUNRUN**。[音声正本](audio-producer-review.md)末尾。
- **次の1件（Windows）**：Core `--video-audio-content`→`--audio-content`/`--video-content`/`--favorite-patch`→既存cacheのWinUI/Portable build。生成fixture/独立DB/settingsで右クリック音声類似→両区間/seek→元検索/前後画面履歴/scope保持、前段専用準備の取消/再表示を限定確認。手順は動画正本末尾。今回packagerはapp全.py同梱をsource確認済み、新build未実施。新しい独立作業は現行queueと発見済み不具合を確認して選ぶ。runtime固定成果物/配布方針は情報待ち、成功1時間性能caseは反復しない。
- 前段`17a6612`音声時刻進捗/`12aa53e`guard入力・atomic保存/`28e5fae`owned API/`5641dfe`専用検索・区間・seek/両cancelのsource照合を保持。通常DB/settings/Alpha/ZIP/shortcut/私物変更0、実model/GPU/GUI/.NET/download/OS/Actions/main merge/shutdown0。AlphaはZIP10/source0138a58、今回source未配布。複数track・音声映像rank統合/実model品質・U7実入力/clean Windows等は未受入。

## 2026-10-28 Work継続checkpoint（動画の区間進捗・1時間生成case、以下より優先）

- 起点 **`fd088c39777cfd0ef0c20ae57890a6a73739b984`**、既存branch / PR #5のHEAD一致・open/Draftを確認。サブエージェントなし。最新commitは本書のGit履歴。部分snapshotで他端末未push差分は未確認、現在クォータ残％は取得不可。
- **今回の利用者向け変更**：動画準備中のstatusへ任意の`item_progress`を追加。解析済み時刻/総尺・読み取り/解析/保存段階を返し、Core/WinUI sourceで現在の動画の進捗を表示。解析済み区間は未保存と明示し、保存成功まではprocessed/indexedへ加えない。取消/失敗/保存成功でcurrentを消し、再開始時にreset。中断した動画自体は次回初めから準備することもtooltipで案内。旧serverのfield省略と旧clientの既存応答を保全。
- **確認**：video index/jobs/認証HTTP/feature **44 PASS /9.514s**、失敗時のcurrent消去の追加focused1 PASS/0.136s、py_compile成功。途中encoderを止めてもstatus取得が応答し、16000/17500ms・未保存区間1・完了件数0を確認。取消では旧索引を保持しcurrent消去、再開始して保存後にcurrent消去。C# parser/文言/ProgressBarはsourceレビューと回帰source追加まで、SDK/Windows不在でCore/WinUI build/nativeはUNRUN。
- **前段単一decoderの1時間CPU比較を一度実施**：生成testsrc2/160×90/1fps/3600秒/MPEG4・疑似3D encoder・独立DBで旧区間方式 **17.237s/FFmpeg225回**、新方式 **3.487s/1回**（各ffprobe1回）。225区間/3600frameのRGBと保存window digestが一致、原本不変、全child回収/slot解放/stage回収。実model/GPU/高解像度/Windows速度の保証ではない。[方法・数値・限界](video-similarity.md)末尾。成功caseを再測定しない。
- **次の1件**：Windows担当はCore `--video-content`と前段`--favorite-patch`→WinUI/Portable build→生成動画で現在時刻/未保存/保存待ち・中断/再開・panel再表示を限定確認。Windowsなしなら音声準備の解析済み時刻表示を同型で検討（音声の総尺不明を推測で埋めない、未着手）。runtime固定成果物/配布方針は情報待ちを保持。
- **未確認/保全**：通常DB/settings/Alpha/shortcut/ZIP/私物変更0、実model/GPU/GUI/.NET/download/OS変更/Actions/新branch/PR/main merge/shutdown0。installed AlphaはZIP10/source0138a58を保持、今回sourceは未配布。実動画/音楽/録音品質、VFR/全codec/総RSS、動画内音声、runtime公開/clean Windows、U7実入力・前段一括favorite/native等は未完。

## 2026-10-28 Work継続checkpoint（動画全区間を単一デコーダーで準備、以下より優先）

- 起点 **`64ec8694fd925ed4defb2a3c8c898a368e74b24b`**、既存branch / PR #5のHEAD一致・open/Draftを確認。サブエージェントなし。最新commitは本書のGit履歴。部分snapshotで他端末未push差分は未確認、現在クォータ残％は取得不可。
- **利用者向け変更**：動画の直接索引準備を、16秒ごとのFFmpeg再起動から **1 videoにつき1 ffprobe＋1 FFmpeg** の逐次RGB producerへ接続。従来は1時間でFFmpeg225回。今回1時間の実速度は測定せず、起動の重複を除いた実装まで。16秒/1fps/384px・端数tail・namespace/保存/検索/類似/旧代表frame入口は保持。
- **所有と保全**：`VideoCoverageStream`を`PreviewReader.video_coverage_stream`のcontextで所有。1windowずつ渡し、queueは1frame、取消/原本・scope変更/早期close/reader開始失敗/出力不足・過多/異常exitでdecoderとthreadを回収。全画素が届いても正常exitと終端guard確認までは成功にしない。20秒/windowのdecode待ちを保持、モデル処理待ちを勝手に全job時間切れへ含めない。原本fd・形式/画素/出力上限・既存atomic stage/commitを保持。
- **確認**：生成3.3/17.5秒、16秒で赤→青、動くtestsrc2で既存区間decoderとRGB全byte一致、端数時刻、FFmpeg実起動1回、原本SHA/mtime不変を確認。新stream初期8 PASS/1.298s、関連index/jobs/認証HTTP/source＋追加2件は**40 PASS/8.815s**（期待した原本変更例外logあり）。最終stream9件＋画素後異常exitのatomic保全1件はPASSだが同runの存在しないclass指定で**11 run中1 runner ERROR/1.828s**を保持。正しいclassの実production起動1回/取消rollback **1 PASS/0.587s**を追加確認。重複を合算せず、py_compile成功。[動画正本](video-similarity.md)末尾。
- **次の1件/Windows残件**：前段一括favoriteのCore `--favorite-patch`→WinUI/Portable buildを行い、今回の新`app/video_stream.py`を含む候補で生成動画の明示準備→途中cancel→再開→区間検索を限定確認。その後長い生成動画でprocess数とdecode時間を一度計測（GPU/model時間を別記）。WinUI/Core変更自体は前段から未buildであり、今回配布済みとは扱わない。runtime固定成果物/配布方針は情報待ちを保持。
- **未確認/保全**：今回既存FFmpeg＋生成素材＋疑似encoderだけ。通常DB/settings/Alpha/shortcut/ZIP/私物変更0、実model/GPU/GUI/.NET/download/OS変更/Actions/新branch/PR/main merge/shutdown0。installed AlphaはZIP10/source0138a58を保持。Windows/VFR/長時間/全codec/実動画品質/動画内音声・native全RSS・runtime公開/clean Windows、U7実入力等は未完。直前の音声破損回復・一括favoriteは保全し再実装しない。

## 2026-10-28 Work継続checkpoint（音声の破損索引除外・明示再生成、以下より優先）

- 起点 **`6057bf6916c2f33ebd8ad9a94db12982a7de8f82`**、既存branch / PR #5のHEAD一致・open/Draftを確認。今回もサブエージェントなし。最新commitは本書のGit履歴。部分snapshotで他端末未push差分は未確認、現在クォータ残％は取得不可。
- **利用者向け修正**：音声の文章検索が壊れたitemの残存windowだけを一致にする不具合、freshが成功markerだけを見て破損索引を再準備対象から外す不具合を再現・修正。marker型/30秒区間数/総PCM frame数、各時刻・vector正規化・実件数を全件照合し、壊れたitemは検索のindexed_totalから除外。明示batchは逐次検証し、破損itemを既存atomic stage/commitで再生成する。検索によるDB自動変更はない。正常な全無音/無音によるordinalの穴を維持。
- **追加修正と保全**：文章検索のrender中の原本消失/変更はAudioSearchChanged→HTTP409へ。短いwindowの後にさらにwindowを返す不正producerは公開前に拒否し旧索引を保持。型/時間の検証をIndex/Search/Similarityで共用し、類似の既存10万pair cap・正規化/順位・buffer上限・所有取消/終了・backup/schema/namespaceを保持。
- **確認**：旧実装で追加6methodに19 FAIL/6 ERROR（subtest含む、1.501s。うち取消API追加は旧未対応）を再現。修正後のaudio search/index/jobs/similarity/HTTP/feature **70 PASS /13.942s**。その後追加した実FFmpegの生成31.25秒WAV→30秒＋1.25秒tail→fresh＋原本SHA/mtime不変と、実認証HTTPの原本変更409の**2件がPASS /1.044s**。重複runを合算せず、py_compile成功。[音声正本](audio-producer-review.md)末尾。
- **次の1件/Windows残件**：前段一括favoriteのCore `--favorite-patch`→WinUI/Portable build→生成libraryの同一session/選択/anchor保持を限定確認。その後、必要なら独立生成音声DBで破損item除外→明示準備→区間復帰をnative確認。今回のCPU成功試験や既に確認済みの動画/初回ガイドは無変更で再実行しない。runtime固定成果物/配布方針は情報待ちのまま、[正本](runtime-notice-inventory.md)の次手順を維持。
- **未確認/保全**：今回CPU/生成WAVのみ。通常DB/settings/Alpha/shortcut/ZIP/私物変更0、実model/GPU/GUI/.NET/依存download/OS変更/Actions/新branch/PR/main merge/shutdown0。installed AlphaはZIP10/source0138a58を保持、今回sourceは未配布。実音楽/録音/動画品質、長媒体/動画内音声、runtime公開/clean Windows、HC/DPI/RSS、U7実入力と一括favoriteのbuild/nativeは未完。

## 2026-10-28 Work継続checkpoint（一括お気に入りの結果保持、以下より優先）

- 起点 **`bb58c27844a02361615fe3d4bcf14a95a3a93a61`**、既存開発branch / PR #5のopen・Draft・未mergeをconnectorで再確認。固定SHAの部分snapshotを更新し既存ローカル差分0を確認して着手。他端末の未push差分は確認できない。サブエージェントなし、現在クォータ残％は取得不可。今回commitは本書のGit履歴。
- **今回の利用者向け変更（Core/WinUI source、build/native未実行）**：通常literal/allの一括favorite保存も既存の`keep_session`契約を利用。最大256件・一覧外選択を保持したまま、serverが保持成功を返せば全件検索・一覧再作成を省き、星印/menuだけ更新する。単一選択の詳細が開いていれば保存済みfavoriteだけ同期し、未保存タグ/棚draftを保存しない。favorite限定/AI/棚操作・旧server・保持失敗は従来の再取得へ戻す。backendの既存複数件対応を再実装せず、Coreの`EditFavoritesAsync`とWinUI入口だけ追加。
- **確認**：生成fixture＋独立DBでselection edit/既存result session **51 PASS /6.666s**、py_compile成功。724件中、一覧外を含む256件の原本確認だけ・provider初回1回・全順位/件数/非対象metadata保持、途中private patch失敗ではmetadata保存済み＋snapshot失効/回収を確認。初回は試験の閉じたDB参照と既存fixtureの列挙順依存、未取得module指定で1 FAIL/2 ERROR（17 run/1.840s）。試験を修正し正本moduleを取得して解消、製品不具合とは扱わない。[証拠とWindows手順](library-selection.md)末尾。
- **runtime次手順は情報待ちのまま**：Microsoft公式で最新版URLは可変、x64/必要toolset以上の要件を確認したが、取得物の版/容量/hash・個別ライセンス・app-local/central導入方針は未確定。DLL/依存download・OS導入・公開なし。[再開時に必要な情報](runtime-notice-inventory.md)末尾。これを理由に独立機能作業を止めなかった。
- **次の1件**：Windows/.NET担当は`dotnet run --project tests/Aredoko.Core.Tests -c Release -- --favorite-patch`→WinUI/Portable build→生成専用libraryで一括favoriteの同一session/再検索0/一覧外選択/anchor保持とfavorites view fallbackを限定確認。以下の動画/初回ガイド/内積高速化/Alpha更新は別側で確認済みなので再実装しない。runtime公開準備は上記固定情報が揃ってから継続。
- **保全/未確認**：今回通常DB/設定/installed Alpha/shortcut/ZIP/私物変更0、download/OS変更/GPU/GUI/Actions/新branch/PR/main merge/shutdown0。installed Alphaは下記ZIP10/source0138a58のまま、今回sourceを配布済みとは扱わない。Core/C# compile・WinUI/nativeはSDK/Windows不在でUNRUN。実音楽/録音/動画品質、長媒体・動画内音声、runtime公開/clean Windows、HC/DPI/RSS、U7実入力等の未完は保持。

## 2026-10-28 終了checkpoint（以下の過去記録より優先）

- **終了後のユーザー追加指示でinstalled Alpha更新済み**：基本ZIP10/source`0138a58`を`%LOCALAPPDATA%/Programs/Aredoko/releases/20261028-0138a58`へ新規copyし、デスクトップ「Aredoko Alpha」の起動先を切替。818files/661,537,190bytes全照合・bootstrap自己検査exit0、通常DBのsize/mtime・launch設定SHA不変。旧07releaseと旧shortcutを保持（`updates/20261028-0138a58/`）。GUI/GPUは起動せず、旧MSIX/Startメニュー登録は変更しない。記録`data/ai-ui/continuation-20261028/alpha-update-final.json`。以下の「Alpha未変更」はこの追加指示前の開発範囲を示す履歴。
- 起点`d3e4885`、開始時fetch後remote/PR head ref一致・clean、新たなMuse差分なし。既存`feat/winui3-production-mvp-20261011` / PR #5を継続。PRのopen/Draft metadataはconnector Transport closedで未再確認。アプリ候補sourceは**`0138a58`**、本引き継ぎのcommitは`git log -1 -- docs/current-handoff.md`。後続の試験tool/文書変更をsealed ZIPへ追加したとは扱わない。
- **`d27a72e` P6-S4＋`62e46d0` S5**：用途保存→取得/配置/索引/診断→ガイド復帰・準備状況再確認を接続。取得中/中止/検査中/再起動待ち、媒体別索引、欠落/版相違/環境不正の安全な案内を追加。削除/初期化/OS変更なし。**`ffe3998`**で保存profileの変更待ちを区別し、再起動前の旧モデル取得推薦を抑止。Core33/plan8+profile13/WinUI/Portable PASS。[P6正本](p6-first-run-setup-spec.md)。
- **ガイドの限定native受入**：frontend03/UI source ffe3998/backend d6acd9c。native01は取得→復帰成功、試験保存先の不一致とmodal cleanup失敗をraw FAILのまま保持し、所有guideをUIA→通常closeで回収（初回exit code欠測）。追加許可native02は残り配置/索引/診断復帰・用途保持・pendingと取得抑制を11checks/3PNG目視/exit0 PASS。実runtime導入/自動修復/clean Windowsの受入とは区別。
- **`d6acd9c` お気に入り変更の全件再作成を回避**：通常literal/allの単体favoriteだけ当該payload/caption/menuを更新し、order/selection/未保存draftを保持。自分の1世代だけを取り込み、favorites/AI/棚等は再取得。保存後snapshot更新失敗は保存済み＋再検索と返す。Python14/session35/Core10/WinUI PASS。既存生成5万PNGのDB copyでsnapshot30.633sと別に保存更新11.949ms/provider初回1回/原本確認1件/元DB不変。ZIP10のUIA nativeは10checks/2PNG目視/exit0、on/off後の再検索0・同一session・タグdraft保持を確認。[選択正本](library-selection.md)。一括操作の同じ最適化は未接続。
- **`3f5da55` 音声/動画内積を局所高速化**：同じ演算順のmapへ共通化、各Python内のbit一致と関連32 PASS。基本Pythonのkernel1万pair0.240486→0.156169s。全検索/長媒体性能保証ではなく、比較cap/取消/guardは保持。[詳細と旧harness FAIL](audio-producer-review.md)。
- **`ec72860` P6静的native依存監査**：PE32/PE32+の通常/delay importをbounded読取、生成18件＋基本PythonPE9 PASS。既存pack325files/2,757edgesの読取956,460bytes、旧manifest/NOTICE保持。ONNX Runtime2filesの必要な`MSVCP140_1.dll`がpack内にない。`nvcuda.dll`も外部依存。静的表の把握であり動的loader/再配布権利/clean Windowsの合格ではない。[証拠](runtime-notice-inventory.md)。
- **最終基本ZIP10/source0138a58**：`dist/portable-basic-20261028-10/Aredoko/Aredoko.exe`と隣のZIP。818files/661,537,190bytes、ZIP348,331,051bytes。Core/Portable/自己検査/runtime/全inventory/ZIP、同梱backend基本27 PASS。個別許可の通常EXE起動→正常終了→予定内1再起動は11checks/2PNG目視/WinUI・bootstrap計4exit0。sealed payloadと元生成PNG不変。pack-time `native_gui_verified:false`はその時点の記録、後続受入はfinal/reviewを正本とする。[候補・SHA](portable-refresh-20261024.md)。
- **U7設定保存のみ限定受入**：ZIP10の`u7-settings-native02`はUIAだけでWindows既定→保存/再表示→内蔵→保存/再表示、8checks/3PNG目視/exit0。01の同名item/text誤選択FAILと所有modal回収exit0を保持。初期Light→system設定保存でDarkへ変わったためLight単独受入ではない。fixture必須version/wheelの欠落は今後用に修正、追加GUIなし。実ダブルクリック/外部関連付け/fallbackは未検証。[U7正本](usability-followup-20261025.md)。
- **次の1件：P6 runtimeのMSVC依存を正式に満たす配布設計**。既存VS Communityの標準redist配置は`14.44.35112/Auxiliary`のみでx64 CRTがないことまで確認。MicrosoftのREDIST一覧/配布案内を参照済み、個別ライセンス承認や実DLL取得は未実施。次は公式の固定取得元/版/hash/条件を揃え、ZIP用app-local CRT一式か利用者に明示する公式runtime導入かを確定する。System32からのコピー/追加DL/OS導入/公開は勝手に行わない。その後native NOTICE・動的依存・不変host/trusted registry・clean Windowsへ。情報待ちならUI/機能の独立小単位へ進み、再調査やガイドの再実装を繰り返さない。
- **未完**：実音楽/録音/動画品質、長媒体比較・decoder、動画内音声、runtime権利/公開host/registry、HC/物理DPI/長時間RSS/clean Windows、U7実入力。全ロードマップ/M1/M2完成とはしない。完成形UIは機能と並行。
- 今回のGUI許可は全て消費、GPU0/外部取得0。PC使用中のため新しいGUI/GPUは具体的な範囲を質問し回答後のみ。通常DB/私物/Alpha/shortcut変更なし（AlphaはZIP07/sourcecaee977）。Actions/新PR/main merge/shutdownなし。生証拠`data/ai-ui/continuation-20261028/`はGit対象外。commit/pushとremote照合後に終了し、次回は上記1件から再開。

## Sol継続checkpoint（Muse引継ぎ後、以下の過去記録より優先）

- **起点`859803d`**へ既存branchをfast-forward（開始時clean）。Museの動画coverage/atomic索引/検索/類似/WinUIと音声取消・終了/比較上限をレビュー。既存`feat/winui3-production-mvp-20261011` / PR #5を継続、不要なbranch/PR/merge/Actionsなし。今回のapp sourceは**`176502f`**、最終記録commitは `git log -1 -- docs/current-handoff.md`。PR head refとremote branch一致。PR state/Draft metadataはconnector Transport closed、gh不在、未認証API404のため再確認できていない（head一致とは区別）。
- **動画の誤一致・回復を修正**：`6ba34e6`で文章検索も全coverage/ordinal/区間/総frame/正規化を検証し、不完全索引の部分一致を公開しない。原本消失は再検索409へ。`693d0f2`でfreshも検証し、壊れたitemは次の明示batchで全区間stage→atomic再生成。生成検索/HTTP14、基本Python検索9、index/jobs28 PASS。[正本](video-similarity.md)。正常な原本や旧索引を無断変換しない。
- **MuseのWindows接続を限定受入**：動画Core/既存CoreとPortable publish成功。生成2動画のGUIで準備lazy/開始/中断/再開/区間付き文章検索/直接類似/自己除外/旧代表frame入口を確認（native02、最後の試験条件不備で全体PARTIAL）。成功部分を反復せず、native03でモデル不可cached類似→登録フォルダ→戻るを確認、10checks/3PNG/exit0 PASS。旧前面化失敗も保持。[根拠](video-similarity.md)。
- **実動画owner/private workerも限定確認**：生成無音の赤3.3秒/青17.5秒を全3区間保存、日本語2問Top1、index29.250s/child peak1424.1MiB/allocator3072MiB、明示release成功。raw GPU reportは最後のharnessのread-only property代入でFAILを保持。GPUを再実行せず同じ基本Python3.11で専用DBをCPU再openし、モデル不可・0推論のcached類似を補完PASS。Python3.14とのWindows revision差は安全に拒否、guardを弱めていない。実動画品質/動画内音声/長時間は未受入、GPU初回の原本pre SHAは欠測。[詳細・review](video-similarity.md)。
- **音声側のMuse差分も確認**：音声jobs/feature/推論所有25件がWindows CPUでPASS。今回新しい音声GPUは実行せず、前回の限定実績を反復しない。
- **U7をsource実装**：`60be42e`、設定の「ダブルクリックで開くアプリ」で内蔵（既定）/Windows既定を切替。既存パス検査とshell経路を共用、失敗時の内蔵選択・重複起動防止・保存/復元を追加。Core/backup/PortableはPASS。**native操作は未確認**：u7-native01/02とも前面化不可、入力前に正常exit0、生成画像削除/外部起動なし。準備待ち変更でも再現したため反復しない。次の確認はUIA設定だけか、ユーザーが実入力可能な時に範囲を限定して質問する。[U7正本](usability-followup-20261025.md)。
- **P6-S1/S2を実装**：`751a7f2`read-only用途計画、`a76784c`WinUI入口/4用途選択/共有modelの重複排除/取得・配置・索引の既存入口/AIなし選択保存。選択はUI設定とbackupへ保持。runtime未公開・model容量と総容量未確定を区別し、driver/推論を検証したと偽装しない。APIは取得/モデル/索引/設定変更を起動しない。Coreのreflection無効JSON失敗を明示JsonValueで修正、frontend03は旧不良候補として使わない。frontend04の**UIAだけのnative10checks/3PNG/exit0 PASS**（用途保存→再表示→AIなし→再表示、job idle/owner未作成）。新しいモデル取得やGPUは使っていない。[P6正本](p6-first-run-setup-spec.md)。
- **最終候補は基本ZIP09/source176502f**：`dist/portable-basic-20261027-09/Aredoko`＋隣のZIP、818files/661,474,739bytes、最終UI frontend05（04から利用案内文を更新）。全inventory/ZIP/runtime照合、同梱backend基本25、通常EXEの生成1PNG/専用DBで起動→正常終了→予定内1再起動（11checks/2PNG/4exit0）PASS。clean Windows未受入。**installed AlphaはZIP07/sourcecaee977のまま**、更新指示なし。[候補とSHA記録](portable-refresh-20261024.md)。guideも現行の媒体別準備・起動・GUI復元へ更新、古い配布記録は保持。
- 生証拠は`data/ai-ui/continuation-20261027b/`（Git対象外）。初回Core JSON/Automation import、harnessの相対パス・foreground・モデル不可query条件・read-only available代入、旧Python revision差の失敗を保持。修正後の成功と混同しない。通常DB/設定/Alpha/shortcut/私物scan/外部取得/OS設定変更0。
- **次の1件：P6-S4の導線仕上げ**。用途選択→既存のモデル取得/配置画面→閉じた後に用途ガイドへ戻って現在の準備状況を再確認→必要な再起動/媒体別索引の案内、を一単位で接続する。選択済みの用途を保ち、取得継続/中止・未公開runtimeを実装済み既存jobと区別する。新しい公開URL/hashを捏造せず、追加DLは明示許可後。GUIが使えなければ関連Core/APIと生成HTTPで先行する。動画基盤/U7/P6-S1/S2を再実装・全面再設計しない。
- 残件：U7の実入力/外部関連付け起動、実音楽/録音/動画の一般品質、長媒体比較とdecoder性能、動画内音声の統合、runtimeの公開NOTICE/native依存review・host・trusted registry、clean Windows/HC/物理DPI/長時間RSS等。全ロードマップ/M1/M2完成とはしない。完成形UIは機能と並行継続する。
- **ユーザーはPC使用中**。新しいGUI/GPUは具体的に質問し、回答後のみ実施。今回の各限定許可は全て消費済み。前面化を強行せず、入力不可時の既知失敗を別名で繰り返さない。Actions/新PR/main mergeなし、shutdownしない。枠が少なくなったらこの正本更新→commit/push→clean/remote一致で終了する。

## 継続開発checkpoint（2026-10-27、音声類似の比較量上限）

- 起点 `5f0c30c48edd76fb8289083f2fcb83f819cc96ff`、既存開発branch / Draft PR #5を継続。小単位の追加作業、サブエージェントなし。最新commitは本書のGit履歴。最後の残量報告19％以降の現在残％は取得不可。
- **今回の利用者向け変化**：直接音声類似の全window pair比較を1検索あたり累計100,000組に制限（動画側と同じ）。超過時はフォルダー/棚を絞る日本語案内で503、途中順位を返さずspoolを回収。上限内は既存の厳密最大cosine・両時刻・scope・無音skip・cached比較を保持。1時間同士は候補1件14,400組、6件86,400組、7件100,800組。単一候補でも上限を超える長音声は依然比較不可で、性能改善完了とはしない。
- **確認**：旧codeで追加境界/cumulative/HTTP回帰3件がFAIL（0.999s）。修正後の音声類似/認証HTTP **23 PASS /8.519s**、py_compile成功。境界一致成功・超過拒否・候補を跨ぐ累計・scope/未索引除外・途中結果非公開・一時file回収を確認。生成WAV/疑似vectorのみ。[音声正本](audio-producer-review.md)末尾に単純演算計測と制約。
- **前段保全**：`5f0c30c`の破損marker/window検証、`2ea69c2`のbuffer/原本変更409、`695fc87`の音声取消/close、`d323db0`の動画Core/WinUI sourceを保持。動画Core/C# compile/WinUI・Portable build/nativeはSDK/Windows不在で未実行。
- **次の1件**：Windows/.NET担当は [動画正本](video-similarity.md)末尾のCore `--video-content` →既存Core/Portable build→生成2動画の限定native確認へ。Windowsなしでは、長音声/動画の厳密比較を上限内で高速化する独立CPU作業を検討（実装未着手）。今回の成功試験を無変更で繰り返さない。
- **未完/保全**：実動画/録音/音楽の品質、長媒体比較/decoder性能、媒体横断、配布NOTICE/host/clean Windows等は未完。通常DB/設定/Alpha/ZIP/shortcut変更0、モデル/依存download0、Actions/新branch/PR/main merge0、shutdownなし。固定SHA部分snapshotで、他端末未push差分は未確認。

## 継続開発checkpoint（2026-10-27、以下の過去記録より優先）

- **アプリsource `bb7e77f`**。起点`6b2448d`、既存`feat/winui3-production-mvp-20261011` / Draft PR #5を継続。最終文書commitは `git log -1 -- docs/current-handoff.md`。リモートbranch/PR head refを照合し、他エージェント差分なし。新branch/PR/main merge/Actionsなし。
- **音声内容検索のGUI残件は限定PASS**：frontend02/sourcecaee977、`audio-search02`で検索方式・2候補・一致時刻・明示詳細を確認。初回はdebounce中の旧UIA行を操作したharness失敗で、製品検索失敗ではない。古い「未対応」案内を`6ec1fdf`で実際の準備入口へ修正。[根拠](audio-producer-review.md)。
- **実private audio worker一連も限定PASS**：`0c1cc3a`の任意CUDA allocator予算を使い、生成WAV2本の原本decode→production owner→private worker→atomic保存→日本語2問がTop1。index16.156s、child peak1121.5MiB、予算3072MiB。画像workerは起動せず、所有closeで回収（既存kill方式exit1でありgracefulとは呼ばない）。実録音/実曲の一般品質は未受入。
- **保存済み直接音声の類似検索を製品接続**：`6e1531e` backend / `c8703fd` WinUI。右クリック「内容が似た音声・曲を探す」で起点除外・両一致時刻・root/棚/favorite範囲・画面履歴を保持。旧512D音響類似も維持。モデル利用不可でもcached768Dを比較し、再推論しない。CPU/HTTP/Core/buildと`audio-similarity-native02`の限定GUI PASS。長音声の全window pair比較性能・実音楽品質は未受入。`fd34129`で取消済みScoreSpool入場時の資源漏れも修正。
- **完成形主画面を前進**：`6209c6a`で重複ラベルと縦余白を減らし、検索filter/actionを実寸で折返し、種類を「音声・音楽」に統一。Light/Dark機能確認後、fit一覧を末尾と誤認してgrid先頭を切る既存不具合を発見し`21d60e8`で修正。`toolbar-reflow03`で先頭144px全表示・未保存タグ保持・保存まで限定PASS。[UI証拠と旧PARTIAL](p3-continuous-browse.md)。HC/物理DPI/長時間RSSは未受入。
- **動画の直接入力は基盤まで完成、通常索引は未接続**：`75ee70c`で最大16秒/16RGB framesの別text/video namespace・private wire/adapter、`87cd800`で原本guard付き1fps区間decoderを追加。生成3frameの実private worker GPUで768D出力/解放を確認（peak965.7MiB）。decoder/source CPUと赤→青/3.3秒tailを確認。通常のtext→動画/動画類似は従来の最大4代表frame方式を維持し、動画内音声は統合していない。[現状・公式仕様・証拠](video-similarity.md)。
- **動画coverage＋直接索引のatomic保存＋text検索接続を実装（production配線は未接続）**：`app/video_coverage.py`が同じ原本guardのfd限定ffprobeでdurationを取得（stream値が使えない場合はformatへfallback、推測で埋めない）し、全区間planを最大16秒windowの逐次イテレータで上記decoderへ接続（probed総尺を公開し、完走照合が可能）。`PreviewReader.video_coverage_stream`が登録/revisionをguardする単一パスproducer。`app/video_direct_index.py`は音声側と同型に、一時stage.sqliteへ逐次spoolし、全区間成功時だけcatalog guard/writer fence下で1トランザクション公開する専用namespace索引（`ai_video_direct_sources/windows`、契約`direct-video-window:v1`）。途中失敗/取消/原本変更/挿入中断では旧公開へrollbackし、宣言総尺に届かないproducerは公開しない。生成3.3秒/17.5秒動画と疑似encoderでCPU関連95 PASS。外部レビュー（78→88→89点）を経て`muse/video-coverage`から採用。続いて`app/video_direct_search.py`が音声側と同型に、共通catalog filter＋ScoreSpoolでtext query→最良windowの両端時刻（`video_match_ms`/`video_match_end_ms`、`direct-video`）を返し、原本変更/陳腐化した索引は一致させない（生成動画・疑似encoderで新規7 PASS、関連111 PASS）。実encoderでのproduction job配線と長動画decode性能（1時間=225回FFmpeg起動）は未検証。
- **大きい通常動画のpreview/AI入力制限を改善**：`bb7e77f`で512MiB→32GiB、seek可能な検証済みfd・時間/画素/出力上限は保持。生成528MiB sparse MP4を実decodeして代表4frameと原本不変を確認。全fileをRAMへ読まず、通常再生rangeの2TiB上限とは別。[証拠](video-thumbnails.md)。私物動画/一般形式性能の受入ではない。
- **最新試用候補は基本ZIP08/sourcebb7e77f**：`dist/portable-basic-20261027-08/Aredoko`と隣のZIP。810files /661,232,667bytes、全inventory/ZIP照合・同梱Pythonの基本CPU23/正常EOF PASS。通常`Aredoko.exe`から生成1PNG/専用DBで起動→正常終了→予定内1再起動も11checks/2PNG目視/所有4exit0 PASS。**installed AlphaはZIP07/sourcecaee977のまま**、今回更新指示なし。clean Windows未受入、モデル/PyTorchは別途必要。[候補の正確な範囲](portable-refresh-20261024.md)。
- 生証拠は`data/ai-ui/continuation-20261027/`（Git対象外）。途中のUIA/枠判定/末尾frame試験失敗を保持。ZIP08のraw reportに残る旧汎用authorization文は許可根拠ではなく、`basic-native08/review.json`に実際の通常起動限定許可を補記した。harnessも誤って一律GPU許可を記録しないよう修正、構文確認済み。再GUIはしていない。
- **次の1件**：直接動画索引のproduction配線。実encoder/所有モデルで`VideoDirectIndex`を呼ぶ明示jobと所有統合（現行`InferenceOwnership`はimage/audioの2owner制限。第三worker同時常駐を許すだけの変更は禁止し、必要な一点レビューは所有統合の範囲だけに限定する）、必要ならproduction入口まで。続いて動画類似（起点動画→両端時刻）も音声側と同型で接続する。通常の代表frame方式は維持する。長動画decode性能の実測も残る。
- **再開時の制約**：ユーザーはPC使用中。新しいGUI/GPUは具体的な質問への回答後のみ。今回の限定許可は全て実施済みで、次回へ自動拡張しない。外部取得0/通常DB・設定・Alpha変更0/私物scan0。shutdownしない。クォータを確認して終了前にhandoff/commit/pushする。
- **残る製品作業**：native動画の通常producer/長動画coverage、動画内音声連携、実録音・音楽/動画場面の品質、媒体横断の検索→再生、runtime公開NOTICE/native依存review・host・registry、clean Windows/HC/物理DPI/長時間FPS-RSS。全媒体配布完成やM1/M2全完了とは宣言しない。UI段階移行はこれら全受入を待たず並行継続する。
- **2026-10-27 追加要望（未実装、既存キューは変更しない）**：右クリックから外部ビューワーを開く機能は実装済み。新規に設定から**ダブルクリック時の起動先＝内蔵（既定）／外部ビューワー**を選択できるようにする。外部起動ではAredokoの検索結果・アイテム並び順・連続閲覧順は継承されないことをUIで明記。詳細と受入基準は[U7](usability-followup-20261025.md#u7ダブルクリック時のビューワー選択2026-10-27-追加要望未実装)。現在の次の1件である動画coverageを差し替えない。

## Alpha更新完了（2026-10-26、起動対象の最新情報）

- 追加依頼により**基本ZIP07/source `caee977`**へデスクトップ「Aredoko Alpha」の起動先を更新済み。新versioned release、前版06/source2cf99b2とshortcut backupを保持。MSIX登録は変更していない。
- 配置先806files/661,173,728bytesをmanifest照合、bootstrap `--self-test` exit0。起動設定SHA256一致・通常DBサイズ/更新日時不変。通常DBを起動せず、GUI/GPU試験は追加していない。既に開いている旧版processを強制終了しない。証拠`data/ai-ui/continuation-20261026b/alpha-update-final.json`。
- 引き継ぎ本体は`2be75c5`までPush済み。この更新記録のcommitは `git log -1 -- docs/current-handoff.md`。07の通常GUI/clean Windows未受入と音声検索GUIのPARTIALは解消扱いにしない。
- ユーザーへの完成距離：画像/本の実検索評価と動画frame/時刻検索の既存実装を維持し、今回音声producer→保存→検索→WinUI入口を追加した。本格UIは並行開始可能。全媒体配布品質の残りは、(1)限定音声GUI＋private worker一連、(2)実録音/音楽と音声類似の品質・媒体横断検索→再生、(3)runtime公開NOTICE/host/registryとclean Windows導入、(4)重大残件の修正とまとめ受入。日数・完了率は未測定で確約しない。UIを全受入まで延期しない。

## 継続開発checkpoint（2026-10-26、以下の過去記録より優先）

- アプリsource **`caee977`**、既存branch/PR #5を継続。起点`b156d6b`。最新記録commitは `git log -1 -- docs/current-handoff.md`。5時間枠95%使用で終了準備、shutdownしない。
- **5万実PNGの限定native受入完了**：`054a7f3`、既存生成fixtureを再利用・専用DBへbackup。進捗/中断/再検索/先頭末尾/条件/未保存タグ/可視thumbnail/正常終了PASS。再検索から初行32.263s（単回、準備待ちは残る）。証拠`data/ai-ui/continuation-20261026b/real-native01`、詳細[result-sessions](result-sessions.md)。全媒体cold性能/長時間RSSの合格ではない。
- **直接音声内容検索を接続**：`f09dab7`逐次PCM、`c5534c8`専用namespace atomic保存、`d0dad91`scope付き検索/時刻、`320c2ad`所有batch/画像音声モデル排他、`8f41af2`認証API/result session、`6f5e367`WinUIの明示準備/中断/続きと検索方法「音声の内容（AI）」、`caee977`展開bodyの可視化。既存文字/表紙/512Dを混在させない。関連Python/Core・PortableビルドPASS、既存picker警告3。詳細[audio-producer-review](audio-producer-review.md)。
- **実GPU限定PASS**：生成2音声の逐次decode→専用DB保存→日本語2問がTop1。load32.718s、index1.875/0.485s。元生成ファイル不変。`audio-pipeline-gpu01`。実private worker GPU一連、実録音/実曲/音声同士類似の一般品質は未受入。M2完成ではない。
- **音声GUIはPARTIAL**：frontend01/source6f5e367のnative01とfrontend02/sourcecaee977のnative02。2試行とも準備/中断/再開・2item保存を確認。01は重複UIA option、02はpopup展開後のcombo focus取得でharness停止（キー未送信）。02でbody/操作の可視化修正を確認。検索方法切替・結果時刻表示は未確認、製品検索失敗と断定しない。失敗ログ/PNGを保持、正常exit0/所有process回収。追加GUI許可は消費済み。
- **次の1件**：個別質問で許可を得て、既存frontend02＋`tools/test_p3_native_containers.py --audio-search-only`で検索方法切替/時刻根拠だけ1試行。今回harnessはpopup前focusに修正し、専用生成WAV2本をCPUで事前準備する。構文確認のみでnative未実行。成功した準備flowは反復しない。新出力先を使い、旧native01/02を上書きしない。
- **新基本ZIP07**：`dist/portable-basic-20261026-07/Aredoko`＋adjacent ZIP、sourcecaee977、806files/661,173,728bytes。receipt/全inventory/ZIP照合・同梱backend基本CPU23/owned EOF exit0 PASS（`basic-cpu07`）。07の通常EXE GUI/clean Windowsは未受入。音声用AI環境/モデルは別途必要。ZIP内docsはbuild時snapshot、再開は本書を優先。
- **Alpha更新の追加依頼あり**：引き継ぎ後に07へversioned配置・旧版/shortcut backup保持で更新予定。完了記録をこの上へ追記するまではinstalled Alphaは06/source2cf99b2。普段のDBを起動してテストしない。
- ユーザーはPC使用中：GUI/GPUは毎回具体的質問への回答後。今回許可分は実施済み、追加取得0/通常DB・設定変更0/私物scan0。新しい大規模作業には入らない。P6 runtime公開NOTICE/host/registry、HC/物理DPI/clean Windows/長時間RSS、実音声/曲品質は残る。
- **UIの開始条件**：全面UIの段階移行は全配布受入を待たず並行可能。「全4媒体が確実に内容検索できる配布品質」は音声実worker/実素材品質、媒体横断の取得→索引→検索→再生、clean Windows導入が残り、現時点では達成宣言しない。次は限定音声GUI→実worker一連→媒体横断受入→配布環境を順に仕上げる。日数を裏付けなく確約しない。

## installed Alpha更新checkpoint（2026-10-26、以下の未更新記録より優先）

- 利用者の追加依頼により、基本ZIP06（app source **`2cf99b2`**）を新しいversioned releaseへ配置し、デスクトップの **Aredoko Alpha** の起動先を切替済み。前版`e52c8ec`と切替前shortcutは保持。MSIX登録は変更していない。
- コピー先でmanifest全800 files / 661,032,596bytesのハッシュ照合、bootstrap `--self-test` exit0。起動設定SHA256一致、通常DBのサイズ/更新日時一致。通常GUI/DBを起動せず、GPUも使用していない。06そのもののGUI受入は引き続き未実施で、既存04の実績と区別する。
- 生証拠：`data/ai-ui/snapshot-review-20261026/alpha-update-final.json`、更新script同所（Git対象外）。今回の更新は文書commitに記録するため、正確な記録commitは `git log -1 -- docs/current-handoff.md` で確認。次の作業は下記P3/P7の5万件限定native caseの具体化・実行前質問のまま。残枠約4%で終了準備、shutdownしない。

## 今回の継続作業・終了checkpoint（以下より優先）

- **現行アプリsource `2cf99b2`**、既存`feat/winui3-production-mvp-20261011`/PR #5を継続。今回`cc6f7e8`から引継ぎ。最後は文書だけのcommitを追加するため、最新HEADは`git log -1`で確認する。新branch/PR/main merge/Actionsなし。PR metadata connectorはTransport closedだったが、GitでPR #5 head refとremote branchの一致を確認する。
- **利用者向け改善**：`7aa2162`の原本検査4並行、`b8b41a4`の作成中件数表示、`e965455`の原寸animation、`9968eac`のbounded HTTP再利用、`2cf99b2`のpage/thread内root解決再利用。生成小CBZの割当約27–35ms、生成実PNG5万件のsnapshot45.219→35.116s（単回）・全payload一致。大規模準備の約35秒待ちは残る。[一覧の証拠](result-sessions.md)/[viewerの証拠](viewer-performance.md)。
- **最終基本ZIP06**：`dist/portable-basic-20261026-06/Aredoko` と adjacent `Aredoko-windows-x64.zip`、source **`2cf99b2`**、**800 files / 661,032,596bytes**。Core/Portable/起動画面CPU自己検査/同梱runtime/全inventory/ZIP照合、同梱Pythonの基本CPU23 PASS・owned EOF exit0。既存SDKキャッシュ用targetsは開発用で未同梱。06のGUIは未実施（WinUI変更のないflowを反復していない）。04では通常EXE再起動とviewer実入力を個別回答後に受入済み。
- **installed Alphaは更新していない**：前日の`e52c8ec`のまま。普段のDB/設定/shortcut/旧release不変。新機能を試す候補は上記06であり、installed Alphaと同一版ではない。配布先clean Windowsは未受入。
- **音声の到達点**：`ba6e3e7`の安全なPCM切り出し、`a59245b`のtext/audio専用profile/namespaceとprivate worker、`a33077f`の完全ゼロskipを実装。CPU45＋最終worker12（開発/基本Python、実CPU pipe含む）確認。`17b3265`の限定GPU予備評価では4合成発話×日英query8、合成音3、相互類似2が全Top1。**通常の音声自動索引/検索GUIへはまだ未接続**。[予備評価](audio-input-evaluation.md)/[契約](audio-content-design.md)。既存text/cover/512D保存は維持。
- **P6の進捗**：`c6d8602`でONNX Runtimeの333KB ThirdPartyNotices収集漏れ修正・CPU19 PASS、新NOTICE束05は52 distributions/92 entries/1,456,448bytes。`750b116`でnative325の対応表（owner対応285/未対応40）・CPU7 PASS。旧sealed runtime/archiveは保持、新NOTICEでの再封印/個別native公開review/不変host/registry（0）は未完。[詳細](runtime-notice-inventory.md)。公開承認と混同しない。
- **今回の制約/実施済み許可**：PC使用中のためGUI/GPUは各質問への回答後だけ実施。今回の各限定GUI、tone GPU1回、生成8本のGPU評価1バッチの許可は全て実施済みで、次回へ拡張しない。新モデル/依存取得0、私物scan/通常DB変更0。所有試験は終了。**shutdownしない**。終了準備開始時の5時間残枠は約10%、reset credit操作なし。
- **次の1件（P3/P7）**：新候補06と既存`real-source-50k01`の生成実ファイルを使い、5万件の初回準備/取消/末尾移動・可視thumbnailだけを一つの限定native caseへ具体化し、GUI実行前にユーザーへ問い合わせる。生成ファイルは再作成せず、成功済みの取得/復元/棚/起動flowは反復しない。35秒待ちをさらに変える場合もsource identity/祖先guard/順位を維持する。
- **別の次単位**：R07の長時間producer・atomic保存/backup fence・namespace/検索への接続は[一点レビュー用メモ](audio-producer-review.md)で**Astraクラス推奨**。全計画の再作成は不要。M1残受入のHC/物理DPI/clean Windows/長時間FPS-RSS、実録音/曲/ASR比較、M2と製品全体は未完。未受入を発生中の致命的不具合と混同しない。

生証拠は `data/ai-ui/snapshot-review-20261026/`（Git対象外）。途中のharness失敗（撮影tooltip見出し、provider60件の期待等）と診断・修正は各技術文書/ログに保持する。06内docsはbuild時点のsnapshotであり、このリポジトリの最新引き継ぎを再開の正本とする。

## Sol再開checkpoint（2026-10-26、以下より優先）
- `cc6f7e8`からclean/remote/PR #5 ref一致で再開。**`7aa2162`**：snapshotの既存原本guardを最大4件で並行化、120件以内/順位/世代/取消を保全。生成5万metadata＋実PNG80枚の旧44.590s→20.772s（各1回、他PC負荷非固定）、全payload SHA一致。CPU31 PASS、許可済みnative1試行15 checks/4PNG目視/exit0。[証拠](result-sessions.md)。属性API試作は効果がなく撤去済み。API/GUIの全性能合格ではない。
- **`87fbf51`**：一覧の初回表記も表示範囲に統一。Portable/frontend06 build成功（既存warnings維持）、後続の原寸nativeで初回`1–3 / 3`も確認。[キャッシュ済みSDKビルドの一時指定と失敗ログ](p3-continuous-browse.md)。installed Alpha/基本ZIP03は前日の`e52c8ec`のままで、今回のsourceはまだ反映していない。
- **P1原寸streamも実装/限定確認済み**：任意boolの明示要求で原寸APNG/WebP、旧APIの2048互換/16MP入力/4frame・128MiBを維持。Python17（開発/基本Python）/Core/Portable frontend07 PASS、許可済みnative23 checks/4PNG目視/exit0。[契約と限界](animation-streaming.md)。この変更のcommitは`git log -1 -- app/animation_sessions.py`。
- **今回の制約**：ユーザーはPC使用中。GUI/GPUは都度回答後。5万件の限定native1回と原寸アニメーションnative1回は別々の回答を得て実施済みで、他のテストへ拡張しない。GPU推論0、新規取得0、通常DB/私物/installed Alpha変更0、shutdownしない。利用枠が少なくなったらcommit/push/最新handoffを完了して終了する。
- P3の全件結果作成は文字検索でも専用15分transportへ分離。range/neighbor/close等は通常transport・明示取消を維持。Coreでliteral作成/通常range・close/取消ID cleanupを確認、WinUI最小build PASS（GUI再実施なし）。commitは`git log -1 -- src/Aredoko.Core/ResultSessionClient.cs`。
- P3の作成中件数表示も実装/限定確認済み。building statusはcommit済み件数だけでpartial rowsを公開せず、Coreの任意observer/終了joinとUI versionで旧応答を抑止。Python33/Core/Portable frontend08 PASS、許可済み生成1,201件native1試行5 checks/4PNG目視/exit0。[仕様](result-sessions.md)。このunitのcommitは`git log -1 -- src/Aredoko.Core/ResultBuildProgress.cs`。前記2許可に加え進捗GUI1回も回答を得て実施済み。
- **P1/P3 HTTP待ちの局所改善**：認証と原本guardを毎回維持したまま、boundedな画像/結果取得と読書位置保存へ接続再利用を導入。所有socket終了、framing/解除/認証を含む接続7・既存HTTP8・animation17・結果33 PASS。実.NET生成CPUでwarm info約10/8ms・1.18MB原本約30ms（旧約200ms台）、冷間接続は残る。[範囲と証拠](viewer-performance.md)。commitは`git log -1 -- app/owned_http_server.py`。
- **最新基本ZIP04完成/限定受入**：`dist/portable-basic-20261026-04/Aredoko`、source **`9968eac`**、796 files / 660,993,785 bytes。Core/Portable/起動画面CPU自己検査/同梱runtime/全inventory/ZIP照合、同梱Pythonの基本CPU23 PASS。SDKキャッシュ指定は`--msbuild-targets`の開発用targetsだけ（ZIPへ同梱しない）。
- **ZIP04の許可済みGUI各1試行**：`transport-native01` 29 checks/6PNG目視/frontend exit0/decoder2close。原寸アニメーションの同一接続再利用と最終frame、生成小CBZ往復/304再利用を確認。[数値と限界](viewer-performance.md)。通常入口 `Aredoko.exe` も `basic-native04` で専用DB/生成1画像の起動→正常終了→1回再起動、11 checks/所有4exit0/2PNG目視/inventory不変。GPU0、普段のDB/installed Alpha/shortcut更新0。GUI許可はすべて実施済みで、新しい範囲には回答が必要。
- **P7 viewer実入力も限定受入**：`tools/test_native_viewer_input.py`、ZIP04の生成静止画2枚/5ページCBZだけ。各回答後01/02を実施、01はtooltip混在撮影によるharness FAILを保持。viewport撮影＋寸法検証へ修正後02は9 checks/4PNG目視/所有exit0。中心zoomの目印座標不変、左dragは正確に(-80,-50)、実wheel画像前後/循環ONの本1→5→1、bar hide/hotzone/専用設定保持が通った。[証拠と未受入](viewer-performance.md)。製品のzoom修正は行っていない。
- **R06/R07共通PCM入力境界**：`app/audio_input.py` と内部 `PreviewReader.audio_pcm_window` を追加。最大30秒/16kHz mono f32le、所有FFmpegのfd/pipe限定・取消/回収、返却前の登録/除外/原本再確認。実生成WAVの位置/末尾/振幅・無音、変更/取消等の新規13、関連video21（PATHの独立試験1件はharness修正後に対象再確認）、基本Python3.11の新規13、追加lookup前取消1がPASS。[契約と限界](audio-content-design.md)。認識モデル選定/推論/通常AI索引へは未接続。基本ZIP04/installed Alphaへ未収録。
- **R06既存モデル入力の限定実測**：CPUの生成WAV→PCM→AutoProcessorがPASS。個別回答後のGPU smoke1回も、既存固定モデルの実験用audio ON/vision OFFで768D/finite/norm1.00023、単回encode1.81s/PyTorch peak約1.09GiB。process exit0・追加取得0・本番profile/通常DB変更0。[契約・範囲](audio-content-design.md)。登録音声8形式の基本切り出しも生成CPUで確認。speech/music品質やモデル方式選定の完了ではない。
- **R06生成8本の予備評価**：個別回答後GPU1バッチ。4日本語合成発話は日本語query4/英語query4ともTop1=4/4、合成音3問と相互類似2問も全Top1。入力は数字名の波形のみ、正解文/名前を埋め込みへ入れていない。元SHA不変/process exit0。実録音/実曲/ASR比較・長時間は未評価でR06/M2未完。[条件・生証拠・限界](audio-input-evaluation.md)。fixture01のPowerShell policy失敗は保持し、既存Python COMへ変更して生成。OS設定変更なし。
- **R06/R07音声worker契約もsource実装**：明示text/audio profile・別contract/key、型付きPCM private IPC、両側strict検証、default audio無効/legacy key保全。新worker/関連profile/release/PCMのCPU45 PASS、基本Pythonのworker9 PASS。[仕様](audio-content-design.md)。実モデルAPIの前記GPU評価とは区別し、新private IPCの実GPUは未実施。通常索引/UIや512D空間へは未接続、基本ZIP04/Alpha未収録。
- **P6既知NOTICE漏れを修正**：ONNX Runtime付属`ThirdPartyNotices.txt`約333KBをcollectorが認識せず旧束へ未収録だった。名前判定を補強、CPU19 PASS。新規NOTICE束`runtime-notices05`（証拠root内）は52 distributions/92 entries/1,456,448bytes、不足distribution0。[詳細](runtime-notice-inventory.md)。旧sealed pack/約3GB archiveは変更せず、新封印待ち。公開承認や全native reviewを完了扱いにしない。
- **P6 native対応表も作成**：`inspect_runtime_native.py`と生成CPU7 PASS。`runtime-native-review02.json` はdeclared native325（RECORD owner対応285/未対応40/重複0/不明PE0）、METADATA/RECORD SHA照合済み。未対応はCPython標準拡張/本体/同梱DLL等。[範囲・残review](runtime-notice-inventory.md)。payload全hash/依存graph/公開承認とは区別し、旧pack/archive不変。ctimeのpath/handle差による初回停止と修正も記録。
- **R07デジタル無音保護も実装**：正/負の完全ゼロPCMはparentのモデル起動前にskip。低音量の非ゼロは通す。child側もstrict skip理由を維持。開発/基本Pythonでworker12 PASS、最大30秒PCMの実所有CPU subprocess/pipe往復・handshake・正規化・終了も確認。[仕様とVADとの区別](audio-content-design.md)。通常索引/空結果の永続化は未接続。
- **P3実ファイル5万件を測定/改善**：全件180×240の生成PNGでsnapshot45.219s→35.116s（単回・非固定負荷）。各page/threadのroot解決だけ既存cacheへ再利用し、全祖先/leaf guardは各itemで維持。全5万payload SHA/順序一致・全source取得・原本不変・先頭/末尾present。[証拠・初回fixture期待FAILと修正・残待ち](result-sessions.md)。基本Pythonの関連4件もPASS。以前の一部実ファイル20.8sと混同しない。
- **基本ZIP05**：source`a33077f`、799 files/661,026,006bytes。Core/Portable/起動画面自己検査/全inventory/ZIP、同梱Python基本CPU23 PASS。05のGUI追加なし。上記P3の最後のroot解決改善はまだ未収録なので、新規ZIP06へまとめてから終了する。installed Alpha/shortcutは前日のまま。
- **現在の次の1件**：最終P3変更をcommitし基本ZIP06のbuild/基本CPUを確認、その後引き継ぎ・remote一致で終了へ。残枠約16%（確認時点）から新しい大作業へは入らない。R07は[一点レビュー用メモ](audio-producer-review.md)を用意（Astraクラス推奨、全計画再作成は不要）。GPU/GUIの許可は全て実施済み、新範囲には新回答が必要。M1残受入・native公開review/host・R06最終方式選定/M2は未完、shutdownなし。

## Sol終了checkpoint（2026-10-26、以下の過去記録より優先）
- **基点** `49ca8c8`（Antigravity/remote/Draft PR #5一致、clean）。既存ブランチを継続。最新アプリsource **`e52c8ec`**、この引継ぎのcommitは`git log -1 -- docs/current-handoff.md`。ロードマップ全体は未完。Actions/新PR/main merge/追加取得なし。
- **今回の利用者向け変更**：`38c63f6`で所有背景照合の取消/終了と通信上限を整理し、**設定→高度な設定→AI実行環境の全ファイルを照合する**を追加（既定オン、オフ保存は次回起動から）。基本ZIP・取得時検証まで一括で無効にする設定ではない。[仕様・結果](ai-runtime-setup.md)。`a216fd0`で詳細を閉じた一括保存にも進捗/完了を表示し、保存中の競合操作を抑止。`cca0984`でgrid/list切替の可視アンカーを修正。`22e481c`でviewerの読み上げ名を更新。`42c0743`で中断したAI待機が自動再実行される不具合、`e52c8ec`でページ移動取消時に有効sessionを破棄/詳細を無効化する不具合を修正。
- **確認済み**：runtime33/WD11/設定job15、関連CoreとPortable build。生成nativeでLightの一括整理/600件外選択/起動時更新中止/draft保持/最終refresh、Darkの実Ctrl複数選択/right-click一括保存/表示切替アンカー、高度設定の保存/再起動保持を確認。[選択と取消](library-selection.md)。大容量実フレームGIF約82.55MiB、高解像度APNG/CBZと304 bitmap再利用・正常session解放を限定確認。[測定範囲・限界](viewer-performance.md)。失敗試行も証拠として保持し、製品不具合とharness問題を区別した。
- **AIの実機確認**：既存pack/モデル＋生成2枚だけでCUDA索引/日本語検索/再読込、通常`Aredoko.exe`から照合待ち取消→高度設定オフ保存→照合中正常終了→再起動→モデル読込表示→日本語CUDA検索2件までPASS（`basic-native-ai03`、所有4exit0、4PNG目視）。全照合対象は23,903 files / **4,947,898,990 bytes**であり、旧記録の約8.5GBとは区別する。詳細の単回時間は一般性能保証ではない。
- **最終候補・installed Alpha更新済み**：`dist/portable-basic-20261026-03/Aredoko`、source `e52c8ec`、795 files / 660,950,883 bytes。準備時Core/build/自己検査/全payload/ZIP照合、同梱Pythonで基本CPU23 PASS。デスクトップ「Aredoko Alpha」は新しい`%LOCALAPPDATA%/Programs/Aredoko/releases/20261026-e52c8ec/Aredoko.exe`へ更新。旧releaseと旧shortcutは`updates/20261026-e52c8ec/`等に保持。通常DBのsize/mtimeとlaunch設定SHA不変、通常DBでの起動は行っていない。旧MSIX/Startメニュー登録は別物で更新していない。
- **installedコピーの受入**：`installed-native01`で新releaseの通常入口から専用LOCALAPPDATA/生成DBの起動→正常終了→1回再起動を確認。frontend/launcher計4exit0、2PNG目視、release全inventory不変。証拠は`data/ai-ui/startup-review-20261026/`（Git対象外）、`alpha-update-final.json`を参照。同じGPU試験を最終のrange-only修正後に繰り返してはいない。
- **未完/未検証**：長時間RSS/FPS、複雑な透過/disposalの追加実素材、streamアニメーションの原寸（現行2048px縮小を維持）、HC/物理マルチモニターDPI、clean Windows、全検索条件のnative受入、runtime公開権利/native依存review/host（registry 0）、M1判定後のR06–R09実音声/音楽。これらを今回完了扱いにしない。
- **翌日の次の1件**：P3の既知の**5万件metadata初回snapshot待ち**（既存単回約24.5s）の局所削減。既存の結果session/順位/guard/600件windowを維持し、不要な全件処理の削減を一つ実装→関連CPU/buildまで。上記の今回PASS済みflowを無変更で再試行しない。runtime公開情報待ちで独立開発を止めず、P7残受入/M1→R06–R09の順序も維持する。
- **終了条件**：保存・commit/push・clean/remote一致・所有試験終了を最終確認してから、今回ユーザーが明示した`Stop-Computer`（**Forceなし**）を実行する。通常AGENTSのshutdown禁止を恒久変更しない。他アプリの強制終了や権限回避は禁止。起動しっぱなしだった通常版はユーザーが閉じたと回答済み。

## Sol中間checkpoint（2026-10-26、当時の記録）
- Antigravity `49ca8c8` までをclean/remote/PR #5一致で引継ぎ。UTF-8/Portable初期化は採用。**38c63f6**：背景照合の所有停止・取消/待機、通常通信の応答上限を分離、設定→高度な設定からAI runtime全照合を既定オン/任意オフ（次回起動）にした。[仕様/CPU/生成GPU](ai-runtime-setup.md)。
- **a216fd0**：詳細を閉じた一括操作にも保存/一覧更新/完了を表示、処理中のメニュー等を無効化。**cca0984**：grid/list切替のアンカーを可視位置順へ修正。[U5受入と残件](library-selection.md)。生成nativeでLightの最終refresh含む一括整理/起動queue/draft保持、Darkの実Ctrl＋クリック/right-click一括整理/先頭保持まで確認。
- 証拠 `data/ai-ui/startup-review-20261026/`。runtime32/設定job15/Core/Portable PASS、生成画像2枚のCUDA索引・日本語cold/warm検索・再読込もPASS（追加取得なし）。高度な設定はDarkで既定/オフ保存/再起動保持を確認。現在のinstalled Alpha/shortcut/普段の設定は更新していない。
- **現在の次の1件：生成大容量GIF・高解像度APNG/CBZの限定nativeケース**。コード再実装ではなく既存U3b経路の受入をまとめる。試験ハーネスの古いUI契約は現在の明示詳細/動的window title/通常window closeに合わせる。UI/GPUは今回ユーザー許可済み。今回のみ、終了前の保存/commit/push/引継ぎ後に `Stop-Computer`（Forceなし）を依頼されている。旧shutdown指示の再利用ではない。

## バックグラウンドAI整合性検証・プログレスバーUI・タイムアウト抑止（2026-10-26、以下より優先）
- **利用者にできるようになったこと**:
  1. **起動直後の自動バックグラウンド検証**: AIモデルおよび実行環境（ランタイムパック ~8.5GB/23,903ファイル）が導入されているAredoko環境において、初回AI検索を待つことなく、起動直後に裏で整合性チェック（SHA-256照合）を自動開始。
  2. **右下の常駐プログレスバーと進捗表示**: メイン画面右下に非侵入型のカード（`RuntimeVerifyCard`）を新設。検証中はプログレスバーとともにパーセントおよび進捗バイト数（例: `45% (3.8 / 8.5 GB)`）をリアルタイムに表示。
  3. **照合中のタイムアウト抑止**: 検証完了前にユーザーがAI検索を実行した場合、従来のタイムアウトエラー（40秒/120秒）を出さずに照合完了を待機し、完了次第自動で検索を開始（検索中断ボタンはいつでも利用可能）。
  4. **5分経過時の長時間照合案内**: 照合開始から5分（300秒）以上経過した場合は、右下カードとステータスに **「照合に時間がかかっています」** と明確に表示。
  5. **初回AIモデル読み込み中の表示**: 照合完了後の初回コールドモデルロード（EmbeddingGemma 2の重み読み込み約15秒）中も右下に「AIモデルを読み込み中…」を継続表示。
- **実装内容**:
  - `app/runtime_paths.py`: 軽量な `_state_lock` を用いたスレッドセーフな進捗追跡（`files_done`, `files_total`, `bytes_done`, `bytes_total`, `elapsed_seconds`, `slow`）、バックグラウンド起動 `start_runtime_verification`、ワーカー起動時の照合重複抑止 `verify_runtime_pack`。
  - `app/ai_search.py` / `app/production_server.py`: `AISearch.status()` / `DisabledAI.status()` に `runtime_verification` を追加し、`_serve` 起動時に自動でバックグラウンド照合をキック。
  - `src/Aredoko.WinUI/MainPage.xaml` / `MainPage.xaml.cs`: 右下オーバーレイ `RuntimeVerifyCard`、1秒間隔のステータスポーリング、5分超過検出、進捗反映。
  - `src/Aredoko.WinUI/MainPage.ResultSessions.cs`: AI検索開始前の照合完了待機 `WaitForRuntimeVerificationBeforeSearchAsync`、初回ロード表示 `SetAiSearchModelLoading`。
  - `src/Aredoko.Core/LibraryApi.cs` / `TagReviewClient.cs`: `HttpClient.Timeout` を15分（900秒）へ拡大。
- **実証済み・検証結果**:
  - Python単体テスト: `tests/test_ai_runtime.py`, `tests/test_runtime_paths.py`, `tests/test_ai_status_clarity.py`, `tests/test_winui_compile_stub.py`（全38件 PASS）。
  - C#単体テスト: `dotnet run --project tests/Aredoko.Core.Tests -c Release`（全PASS）。
  - WinUI ポータブルビルド: `dotnet publish src/Aredoko.WinUI -c Portable -p:Platform=x64 -p:AredokoPackageChannel=Portable`（0 errors, 正常完了）。
  - インストール済み Alpha リリース同期: `%LOCALAPPDATA%/Programs/Aredoko/releases/20261025-2811863/` の `bin/`（373項目）および `backend/app/` を完全同期。`bin/portable-build.json`（373項目）、`manifest.json`（794項目）、`sha256sums.txt`（794項目）を更新し、`inspect_portable` PASS、`verify_release` PASS（`794 files, 660,908,161 bytes`）。
- **次の1件**:
  - デスクトップの「Aredoko Alpha」ショートカットからアプリを起動し、起動直後に右下に「AI環境の整合性を検証中…」プログレスバーが表示されること、およびAI検索（両方で探す／画像の見た目）を実行してタイムアウトエラーにならず正常に候補が表示されることを確認する。

## AI推論パイプライン・初回検証タイムアウト・WinUI起動クラッシュ修正完了（2026-10-26、以下より優先）
- **確認された事象と根本原因**:
  1. **初回40秒タイムアウト**: 起動後初回AI推論時、8.5GB・23,903ファイルのSHA-256整合性チェック（約30秒）＋EmbeddingGemma 2重みロード（約15秒）が重なり、フロントエンド `LibraryApi.cs` の `HttpClient.Timeout` および `SearchRequestClient.RunAsync` の deadline（従来40秒）を超過してキャンセルされていた。
  2. **Worker Stopped (TypeError)**: Windows環境でisolated mode (`-I`) 起動されたPython子プロセスは環境変数 `PYTHONIOENCODING` を無視してWindows ANSI (CP932) にフォールバックするため、標準入力に渡された「りんご」等のUTF-8日本語文字列が文字化けし、SentenceTransformers tokenizerが `TypeError: TextEncodeInput must be Union[...]` を送出していた。
  3. **整合性検証の設計仕様**: 実行時検証 (`verify=True`) はバックエンドプロセスの生存期間中、初回worker起動時の1回のみインメモリで実行される（`_verified_packs`）。常駐したworkerプロセスにより、**2回目以降の検索はファイル検証もモデル再ロードも一切走らず、約100msで完了する**（実測 `104.5ms` を確認）。
  4. **WinUI起動クラッシュ (`Application exited before ready` / `FileNotFoundException: Microsoft.Windows.ApplicationModel.WindowsAppRuntime.Projection`)**:
     - ポータブル自己完結配備（`WindowsPackageType=None`, `WindowsAppSDKSelfContained=true`）において、Windows App SDK Build Tools がデフォルトでフレームワーク配布用デプロイ初期化子 (`DeploymentManagerAutoInitializer`) を挿入していた。
     - 自己完結配備では Projection DLL がトリミング・除外されるため、モジュール初期化子（`.cctor()`）で `FileNotFoundException` が発生し、ウィンドウ生成前に即座に落ちていた。
- **実施した修正**:
  - `src/Aredoko.WinUI/Aredoko.WinUI.csproj`: Portableプロファイルに `<WindowsAppSdkDeploymentManagerInitialize>false</WindowsAppSdkDeploymentManagerInitialize>` を追加し、自己完結不要なデプロイメントマネージャーの自動初期化を無効化。
  - `src/Aredoko.Core/LibraryApi.cs`: `HttpClient` のタイムアウトを40秒から120秒（`TimeSpan.FromSeconds(120)`）へ延長。
  - `src/Aredoko.Core/SearchRequestClient.cs`: `RunAsync` の既定タイムアウト引数を40秒から120秒（`int seconds=120`）へ統一。
  - `app/runtime_paths.py`: worker起動引数に `-X utf8` を追加し、`-I` 下でも全ワーカー（`ai_worker`, `laya_worker`, `tagger_worker`）の標準入出力を強制的にUTF-8モード化。
  - `app/ai_worker.py` / `app/laya_worker.py` / `app/tagger_worker.py`: `sys.stdin`/`sys.stdout`/`sys.stderr` の `reconfigure(encoding='utf-8')` を明示。
  - `app/ai_runtime.py`: Pythonが自動生成する `__pycache__` を整合性検査から除外。
  - `app/ai_process.py` / `app/laya_process.py` / `app/wd_tagger.py`: `PYTHONDONTWRITEBYTECODE='1'` を設定。
- **実機リリース適用・検証結果**:
  - `dotnet publish src/Aredoko.WinUI -c Portable -p:Platform=x64 -p:AredokoPackageChannel=Portable` を実行し、完全な自己完結ポータブルフロントエンドバイナリを生成。
  - デスクトップ版実行先 `%LOCALAPPDATA%/Programs/Aredoko/releases/20261025-2811863/` の `bin/` および `backend/app/` を同期。
  - `bin/portable-build.json`（全373項目）を再生成し、`inspect_portable` PASS。
  - `manifest.json` および `sha256sums.txt`（全794項目）を更新し、`verify_release` PASS。
  - `Aredoko.exe --self-test` PASS、`launch_release.py --check` PASS。
  - `Aredoko.WinUI.exe` 単体直接起動テストにより、クラッシュせず正常にイベントループへ突入することを確認。
- **次の1件**:
  - デスクトップの「Aredoko Alpha」ショートカットからアプリを起動し、検索バーで「両方で探す（AI）」または「画像の見た目（AI）」を実行して、初回ロード成功（約40秒）および2回目以降の高速応答（約0.1秒）を確認する。

## 最終終了・Alpha更新結果（2026-10-25、以下より優先）
- 実装source **2811863**、事前引継ぎ **ebe3122** までPush後、ユーザーの追加依頼により**デスクトップ「Aredoko Alpha」の実用起動先を最新Portableへ更新済み**。実配置は `%LOCALAPPDATA%/Programs/Aredoko/releases/20261025-2811863/Aredoko.exe`。旧MSIX登録は削除・更新しておらず、Startメニューの旧MSIX入口とは別。ユーザーへデスクトップ入口を案内する。
- 最新基本ZIP09のCPU21項目・全payload/ZIP照合PASS、配置後も同一payloadを確認。通常DBは開かず、size/mtime不変。モデル保存先は保持し、以前のAlphaが暗黙に使っていた旧同梱AI interpreterを `launch-settings.json` の明示 `ai_python` として継承（新しい基本版へPyTorchをコピーしない）。設定/旧shortcutを `%LOCALAPPDATA%/Programs/Aredoko/updates/20261025-2811863/` へバックアップ。ignored証拠は `data/ai-ui/continuation-20261025b/alpha-update.json`。
- 更新時にGUI/GPUは起動していない。実推論と更新版の通常起動は未検証。U4b/U5限定GUI18項目と最後のrefresh待機FAILの記録は前節を維持し、09/実配置のGUI PASSにしない。残存Aredokoプロセスなし。**新しいGUI/GPUはユーザーの回答後のみ**。
- 残り枠約3%で終了。新機能へ着手しない。**次の1件は最新実配置またはZIP09の通常入口について許可を得て、最終refresh＋Ctrl/右クリック/gridを短く確認すること**。許可待ちには独立したR06–R09/runtime公開権利・hostを進めてよい。source完成分を再実装せず、M1/ロードマップ全完了とはしない。shutdownなし。

## 終了引継ぎ（2026-10-25、以下より優先）
- 今日の実装はPush済み：**8972be3** 引継ぎ補強 → **51491a6/428af7f** U4b → **454dba0/d97c780** U5 → **1adb694** U6 → **2811863** 起動queue停止確認/復元proof保護。[U4](scan-startup.md)/[U5](library-selection.md)/[U6](compressed-filter.md)。U1–U6の完成実装を繰り返さない。
- **最新実物は基本ZIP09/source2811863**。[入口・SHA・正確な受入](portable-polish-20261025.md)。Portable/bootstrap/runtime/ZIP全照合と、実同梱PythonのCPU21項目/正常EOF/DB integrity/原本保全/実行後inventory確認PASS。794 files、ZIP約348MB。モデル/PyTorchを同梱しない。通常起動のGUI・clean Windowsは未受入。
- GUIは許可された範囲だけ実行：旧U4 2回＋追加1回、新U5 2回＋追加1回の生ログを保持。frontend06/native-selection03は18項目PASS/全体FAIL（最後のrefreshはタグ保存後の再検索完了待ち不足）。設定保存/再起動queue/所有取消/draft保持、複数選択/一括棚・favorite/600件外保持/filtered除去と2frontend通常終了、6PNG目視済み。harnessの待機/進捗を修正後の再GUIはしていない。
- **次の1件**：ユーザーから09候補の通常入口GUI確認の回答を得て、修正済み待機で最終refreshとCtrl+マウス/右クリック/gridを一つの短い受入へまとめる。許可待ちなら独立したR06–R09またはruntime公開権利/hostの残件へ進む。Light/HC/DPI/clean Windows、大画像FPS/RSS/CBZ cold-warmは残す。ロードマップ全体完了ではない。
- 追加指示：**この引継ぎ保存後、デスクトップ「Aredoko Alpha」を最新版へ更新**。旧起動先は旧MSIXを呼ぶPythonw launcher。新規ユーザー用アプリ領域へ09を配置し、DB・モデル保存先と旧AI interpreterの継承を確認して既存shortcutを更新する。元設定/shortcutをバックアップ、旧MSIX登録は削除せず、GUIは新しい回答なしに起動しない。実施結果を後続で記録する。
- PR #5 open/Draft/未merge、既存branchを継続。GPU/新モデル取得/私物走査/Actions/main mergeなし。shutdownしない。

## 配布候補更新・終了所有確認（2026-10-25、以下より優先）
- U6 **1adb694** を新規基本ZIP08へ封印。prepare/runtime/ZIP全照合PASS、同梱Pythonの基本＋U4–U6 CPU21項目PASS。旧07/Alpha/shortcutは未変更。08に未収録だった終了所有の補強を次の単位へ入れたため、**次は補強を含む新規ZIP09の作成/CPU確認**。
- 起動queue.closeの時間切れを成功とみなさず、既存owned job closerを使ってrestore正常終了proofをブロック。生成workerの停止境界を含むstartup16 PASS。[根拠](scan-startup.md)。`check_basic_release.py --polish`で同梱Pythonのstartup設定・ZIP/CBZ・一括favorite/棚・欠落metadata保全をCPU確認可能。GUI/実モデル/GPUを起動しない。
- GUIの最新実測はfrontend06/native-selection03（18項目PASS、最終refresh待機失敗を保持）。07/08/09のGUI受入へ流用しない。新GUI/GPUはユーザーへ質問し回答を得る。追加大機能へは進まず、候補/commit/未受入を引継いで終了する。

## U6 filter・現在の再開位置（2026-10-25、以下より優先）
- 今日のsource：引継ぎ補強 **8972be3**、U4b **51491a6**/GUI callback改善 **428af7f**、U5基盤 **454dba0**/WinUI **d97c780**。U6 filterは `git log -1 -- app/media_filters.py`。[U4](scan-startup.md) / [U5とGUI受入](library-selection.md) / [U6](compressed-filter.md)。
- U6の種類を「圧縮ファイル（ZIP・CBZ）」へ統合（hint含む）。保存済みbook/archive・旧query・reader導線を維持し、通常/AI/scope/本文/候補/結果sessionで共通predicateを使用。本文/未承認候補に残っていたmissing混入も修正。DB/vectors移行不要。
- CPU compressed7/AI scope12/production8/Core1132 PASS、正しいPortable frontend07 publish成功。U6 GUIは未実施。U4b/U5のfrontend06/native-selection03は18項目PASS/全体FAIL保持（最後のrefresh待機だけ未完）、所有frontend2回通常終了・6PNG目視済み。GPUなし。
- **次の1件：最新基本ZIP候補を別出力へ作りCPU確認**。旧ZIP07/Alpha/shortcutは上書きしない。新候補でもGUI/GPUはユーザーへ質問し回答後に行う。Ctrl+マウス/右クリック/grid/範囲取消/Light/HC/DPI、最終refresh、大画像FPS/RSSとCBZ、runtime公開権利/host、R06–R09を残す。source完成をロードマップ全完了と扱わない。shutdownしない。

## U5 WinUI接続・現在の次（2026-10-25、以下の過去checkpointより優先）
- 基盤 **454dba0** の上にExtended複数選択/明示summary/一括favorite・棚追加解除、600件外stable選択、編集後のwindow/可視anchor保持、literal favoriteのcard差分更新を接続。[正本・未受入](library-selection.md)。この単位commitは `git log -1 -- src/Aredoko.WinUI/MainPage.Selection.cs`。
- CPU基盤9/Core1124 PASSに続き、Portable publish成功（既知警告維持）。ユーザー許可のU5 GUI 2回＋追加1回、frontend06/native-selection03は**18項目PASS・全体FAIL**。複数選択/一括棚/favorite/600件外保持/filtered除去、U4b設定保存/再起動/所有取消/draft保持/明示保存/通常終了を確認。6PNG目視。[各失敗と修正](library-selection.md)。
- 最終refreshはタグ保存の再検索完了前に押されたため未確認。harnessの待機条件と保存中表示を修正し、追加GUIなし。Ctrl+マウス/右クリック/grid/範囲取消/Light/HC/DPIも未受入。GPUなし。**新しいGUI/GPUはユーザー回答後のみ**、今はCPU/buildの独立作業を続ける。通常DB/元メディア/旧Alpha/Actionsを触らずshutdownしない。
- **次の1件：U6** ZIP/CBZをまとめる圧縮ファイルfilter（保存済み分類・旧APIは維持）。U4b/U5のsource完了分を繰り返さない。

## U5基盤・現在の再開位置（2026-10-25、以下より優先）
- U4b本体 **51491a6**、選択callback改善/GUI診断 **428af7f** はPush済み。U4b再起動/中止/draftのGUI受入は未完。[正確な経緯](scan-startup.md)。許可試行2回＋追加1回は終了、以後GUI/GPUを行う場合は新たな回答を得る。frontend04は修正前候補、同期disable撤去はbuildのみ。
- **U5のAPI/Core基盤**を追加：[仕様](library-selection.md)。検索sessionに束縛した256件までのatomic favorite/棚追加・解除、全件scope/原本検証、locateによる選択再配置。Coreはstable ID/ordinalで600件外保持、120件ずつの範囲選択、取消/世代/上限を扱う。利用者向けUIはまだ未接続。
- CPU selection API9、Core既存＋新規選択契約PASS。通常DB/元メディア/モデル/GPU/Actions/旧Alphaは未使用・未変更。**次の1件はU5 UI接続**（Extended選択/一括右クリック/summary）、その後600件windowと絞込結果の差分更新。U4の完成実装を繰り返さない。

## U4b実装・次の1件（2026-10-25、以下の過去checkpointより優先）
- Antigravity開始51b4302から、引継ぎ補強 **8972be3** はPush済み。続いて **U4b** を実装：フォルダごとの起動時更新OFF/一覧/一覧＋AI、初画面後のbackend所有queue、進捗/中止、欠落原本の通常一覧除外と再出現時metadata復帰。[仕様・証拠](scan-startup.md)。U4bのcommitは `git log -1 -- app/startup_scans.py`。
- catalog v3へ移行（既存rootの自動更新はOFF）、v0–v3のバックアップ復元・同居vector互換を保持。設定の保存は即時/次回起動適用、未保存の棚・タグ・除外draftは維持。
- CPU startup15/root prefs6/live backup12/storage backup29/missing結果session1、Core契約・専用Portable publish PASS。実物モデル/GPUなし。`data/ai-ui/continuation-20261025b/` にログ。frontend01は補強のみ、frontend03はU4b候補。通常DB/元メディア/旧Alpha/Actionsは未変更。
- **GUI/GPUは今回のユーザー回答後のみ**。U4bは2回＋追加1回の明示許可で実行。frontend03はビルドチャネル漏れで起動失敗、正しいfrontend04は正常起動/終了。native-startup02はUIA selector曖昧、03は同期disableによるSelectionItem COMエラー（設定の実保存はDB/PNGで確認）。callback中のdisable撤去を修正、再GUIはしていない。再起動queue/中止/タグdraft保全の実機受入は残す。[失敗・診断](scan-startup.md)。GPUなし。新しいGUIは回答を得る。
- **次の1件：U5残**（Ctrl/Shift複数選択・一括お気に入り/棚、絞込時の差分、600件window保持）。U4a/U4bの完成分を再実装しない。続いてU6圧縮ファイルfilter。未検証GUIを全完成と扱わず、独立したCPU/実装を進める。shutdownしない。

## Codex引き継ぎレビュー（2026-10-25、上の優先度）
- 開始51b4302、remote/既存Draft PR #5一致・clean。AntigravityのAPNG修正とU4aを維持し、AIの選択root範囲・所有worker/取消・複数rootの部分成功公開・AI設定dialog遷移を補強。[正本](scan-startup.md)。この節のcommitは `git log -1 -- docs/scan-startup.md`。
- CPU follow-up9/production8/AI search13/animation14 PASS、専用frontend01 publish成功。**今回のユーザーはGUI/GPUテストを事前回答後に限定**。まだGUI/GPUは実行しておらず、過去の自動許可を今回へ適用しない。通常DB/元メディア/旧Alpha/Actionsは未変更、shutdownしない。
- 次はU4b：folder別の起動時更新・成功再走査後のmissing除外。U4aの完了分を再実装しない。

## 今回の完了・次の1件（2026-10-25、以下の過去checkpointより優先）
- **開始 d448b1e（remote/Draft PR #5一致）から2単位を実装・実機検証完了**：
  1. **指定パレットAPNGのループ2周目黒化修正（cdf7a35）**：app/animation_sessions.py の Decoder.pull で EOFError 到達時に、既に検証・保持済みのオープンストリーム self.file を seek(0) して Image.open(self.file) を再構築する _reopen_loop を実装（パスの再オープンなし、既存 source_guard 保全）。単体テスト tests/test_animation_sessions.py（20 PASS）および実機 data/ai-ui/attached-apng-20261025/native02（5 checks PASS・exit0・所有残存0、animation_samples: [1, 4, 7, 10, 13, 16, 1]）の5 PNG直接目視で2周目以降も有色・透過を維持することを確認。証拠は[animation-streaming.md](animation-streaming.md)。
  2. **U4a：登録後のスキャン選択・一覧とAI索引の分離・3段階初回ガイド（本commit）**：
     - バックエンド（app/production.py / app/production_server.py）：POST /api/library/scan に明示的 mode（'list' 既定 / 'list_and_ai'）と複数 root_ids 対応を追加。catalog.sqlite の scan_jobs スキーマ（storage_schema_v1.json）を変更せず、一覧走査の完了（state='complete' コミット＋sync_index()）後にのみ ai_scan_hook を起動することで、AI未準備・失敗・取消でも取得済みアイテム一覧を絶対に巻き戻さない構造を実装。POST /api/library/cancel は stage=='ai' 時に ai.cancel_build() も呼ぶ。
     - フロントエンド（MainPage.GettingStarted.cs / MainPage.xaml / MainPage.xaml.cs / MainPage.FileActions.cs）：フォルダ登録成功直後に1回だけ「登録したフォルダをスキャンしますか？」ダイアログ（PostRegistrationScanDialog：「アイテム一覧だけ取得（推奨）」「一覧取得＋AI索引を作成」「後で」、AI未準備時の理由と「AI検索の準備を開く」導線）を表示。初回ライブラリ画面（GettingStarted）を3ステップ（1. フォルダを追加 → 2. 一覧を読み込む → 3. 必要ならAIを準備（任意））の進捗カード＋次の主ボタン1つ＋「あとで閉じる」に整理し、800px高ウィンドウでもスクロールなしで下部ボタンまで完全表示されるよう余白とマスコット高を調整。使い方ダイアログ内の小画像拡大設定の案内もビューア内設定メニューへ更新。右ペインのフォルダ設定に ScanModeChoice と1行ヘッダーの RootExcludes（「スキャン対象から除外（例: cache, *.tmp）」）および段階別 ScanStatus を追加。
     - 検証：tests/test_production.py（12 PASS）、Aredoko.Core.Tests（全PASS）、専用Portable data/ai-ui/usability-u4a-20261025/frontend02 による実機 run02（**35 checks PASS・exit0・残存0**、spyで一覧のみスキャンのAI呼出し0回、7 PNG全目視＋UIA座標検証）を確認。先行 run01 で見つけた GettingStarted 下部見切れと RootExcludes 2行ヘッダー重なりを修正して run02 で解消を確認済み（詳細は[usability-followup-20261025.md](usability-followup-20261025.md)）。
- **次の1件はU4b（[usability-followup-20261025.md](usability-followup-20261025.md)）**：
  - 登録フォルダ設定へ「起動時：しない（既定）／一覧のみ更新／一覧＋AI索引」を追加（既存rootはOFF移行、選択rootだけ初画面表示後の所有queueで処理、手動scanと二重実行しない、backup/restoreにも含める）。
  - 成功した全走査で missing と確定したitemを通常一覧/検索/棚/お気に入りの表示対象および開いている結果セッション・AI検索scopeから除外（元ファイル削除やタグ・棚・履歴の物理消去ではなく、再出現で復帰、切断/権限拒否/途中取消は missing 確定しない）。
  - 続いて **U5残（複数選択・一括棚/お気に入り・favorites絞込からの部分削除・600件保持）→ U6（圧縮ファイル ZIP・CBZ 種類フィルター）**。
- **守るべき制約**：通常DB/私物/旧Alpha/ZIP07は未変更。data/ai-ui/ は .gitignore のままコミットしない。GitHub Actionsは起動しない（[skip ci]）。**shutdownしない**。

## 指定APNG黒化の再現・診断のみ（2026-10-25、上記 cdf7a35 で修正完了）
- ユーザーは添付APNGの再現/原因調査だけを指示し、**修正は次回**と指定。アプリコード/依存/通常DBは変更していない。専用コピー原本SHA/mtime不変。診断のcommitは本節と同じ（git log -1 -- docs/current-handoff.md）。
- **現象再現、原因切分け済み**：palette APNG 320×320/17frames/1.7秒loop。1周目は有色、保持Pillowオブジェクトを先頭へseekすると2周目からRGB全0・alpha保持。Image.openし直すと正常。実backend40framesと最新frontend08の4PNGで確認。GUI入力/FPSの問題とは別の、decoder巻き戻し/パレット状態の問題へ絞った。[診断正本](animation-streaming.md)。UIA進行チェックPASSでもvisualはFAILとしてsidecarに明記、exit0/所有残存0。
- **次回の1件をU4aより優先**：AnimationSessionsのpalette APNG loop再初期化/パレット復元を限定修正し、2〜3周のpixel一致と既存形式・取消/原本guardを確認。その後U4aへ戻る。今回その修正へ着手しない。元画像や私物の絶対pathはGitへ含めず、証拠はignored data/ai-ui/attached-apng-20261025に保管。shutdownしない。


## 今回の終了・次の1件（2026-10-25、以下の過去checkpointより優先）
- 開始c18c5ef・remote一致/clean。既存branch/Draft PR #5を継続。**U1=64034ba、U2=389ad76、U3局所改善=f2fd7eb**。U5aのお気に入りcard保持は本checkpointと同じcommit（`git log -1 -- docs/current-handoff.md`）。[U1–U6進捗・正確な残件](usability-followup-20261025.md)。ロードマップ全完了ではない。
- **利用者向け変化**：単クリックは選択だけ、明示詳細とdraft保持、長名省略/選択枠/ナビ名/検索hint。viewerはOSタイトルに名前/位置、独自headerなし、固定toolbar/独立notice、下端表示/1秒hide、viewer内小画像拡大/常時bar/本の循環、中心zoom/左drag。animation clockの累積遅れ削減、64MiB超GIFを所有streamへ。通常ライブラリのお気に入りは同一結果のcardを保持。
- **確認**：最新専用frontend `data/ai-ui/usability-20261025/frontend08`、Portable publish成功（既知WUI1001×3/SDK IL2104×2）。Core対象97、animation13/image-format6、backup28＋不正boolean1 PASS。U1 Dark/Light各9、U2 10、U3 6、favorite10の生成native UIAは各exit0/残存0、変更状態PNGを目視。source・assembly・script SHA等は各report。通常DB/私物/旧Alpha/shortcut/モデル/GPU/Actionsは変更・使用していない。
- **候補を混同しない**：frontend08は専用試験frontendで、通常EXE入り新ZIPは今回未作成。ZIP07/source e197723と旧Alphaは新素材/U1–U3/U5aを含まない。配布候補を更新する際は最新sourceから新出力へ作り、bootstrapの新ICOと設定互換も反映する。
- **残る受入**：Windowsの前面化拒否によりphysical hover/hotzone/drag/wheel/keyboard/context-menuは未確認（u1-dark01..04 raw保持、回避操作なし）。High Contrast/DPI/clean Windows、元報告APNGの黒化、実大容量素材のFPS/RSS、CBZ cold/warmは未確認。73MiB GIFはcomment padding/小画素の生成testで容量経路だけを確認。これを速度同等/全ちらつき修正の証拠にしない。
- **次の1件はU4a**：folder登録直後の「一覧のみ／一覧＋AI索引／後で」、一覧取得とAI jobの明示的分離、初回3段階案内。現在の基本scanに直接AI呼出しはないので、ユーザー報告と実候補のjob連携を区別する。`MainPage.GettingStarted.cs`の小画像拡大設定案内もviewer内へ直す。U3の原本再現待ちで独立U4開発を止めない。
- U4b=folder別起動scan/成功走査後の欠落除外、U5残=複数選択/一括棚・favorite/filtered差分/600件保持、U6=ZIP+CBZ種類filterは未着手。旧viewer入力試験のheader/Close/page label参照、単クリックdetail前提は新導線へ更新する。runtime公開監査/hostとR06–R09も既存残件。**shutdownしない**。

## U2ビューア改善（2026-10-25、現在の再開位置）
- U1 **64034ba**をPush後、U2a/bを実装。OSタイトルへ名前/位置、独自header撤去、固定toolbar/独立notice、下端32DIP/約1秒hide、viewer内の小画像拡大/常時bar/本循環、中心zoomと左dragを追加。[進捗と限界](usability-followup-20261025.md)。この節のcommitは `git log -1 -- docs/current-handoff.md`。
- 専用候補 `data/ai-ui/usability-20261025/frontend06`、publish成功。Core対象79 / backup28+1 PASS、U2生成native UIA10checks/exit0/残存0。144生成PNG/CBZ不変、OSタイトル・固定bar・設定保存・単ページ/奇数RTL双方向循環・bar消去を確認。既知WUI1001/SDK IL2104は維持。
- **未検証**：物理hover/hotzone/左drag/wheel/tooltip、HC/DPI。前面化拒否はU1のrawを参照し、制限回避や同じ試行の反復はしない。旧入力依存viewerテストは新しいOSタイトル/closeへ更新が必要。通常DB/旧Alpha/ZIP07/shortcutは未変更。
- **次の1件：U3aのWebP/APNG再生clock・frame合成の局所改善**。原本がない報告は生成fixtureで対象を絞り、未再現を解消済みにしない。独立したU3b/U4aへ進めてよい。全ロードマップ完了とはしない。

## U1実装（2026-10-25、実装再開済み）
- 開始c18c5ef・origin一致/clean。ユーザーが枠の残りまで継続を指示。U1のtooltip/ナビ見出し/長名/選択枠/明示詳細/検索方式hintを実装。[計画と証拠](usability-followup-20261025.md)。この文書のcommitは `git log -1 -- docs/current-handoff.md`。
- 候補 `data/ai-ui/usability-20261025/frontend04`、Portable publish成功。Dark `u1-uia02`・Light `u1-light01`各9checks/exit0/残存0、各3PNG目視。145生成PNG不変、応答前の見出し更新・旧一覧操作停止、選択時pane閉、draft保持を限定確認。選択枠と長名省略を両テーマで確認。
- **物理hover/keyboard/context-menu/60%サイズの受入は未検証**。前面化拒否で失敗したu1-dark01..04のrawを保持し、UIAで可能な範囲へ切替。OS制限回避はしていない。High Contrast/物理DPIも未確認。旧GUI試験が単クリックで詳細表示を前提にする箇所は、新しい明示詳細導線へ更新すること。
- **次：U2a（ビューワーの固定toolbar・下端表示・OSタイトル・ビューア内設定）**。U1の残入力受入は入力可能時に対象だけ実施。旧Alpha/ZIP07/shortcutは更新していない。通常DB/私物/モデル/GPU/Actions操作なし、shutdownしない。

## 実機フィードバックの計画化（2026-10-25、現在の再開位置）
- **今回は計画のみ。コード・依存・設定・DBは変更せず、build/GUI/GPU/scanは実行していない。** ユーザーの次の実装開始指示を待つ。起動中の試験GUIには触れていない。
- 基点 **9c69ea1**、origin一致・開始clean、既存PR #5 open/Draft/同HEADを確認。[改善計画 U1–U6](usability-followup-20261025.md)に今回の全指摘、ソース根拠、優先順、変更候補、完了条件、Sol/Antigravity共通の再開指示を収録。文書コミットは `git log -1 -- docs/usability-followup-20261025.md` で取得する。
- **次の1件：実装再開を指示されたらU1a（Ctrl+Home tooltipの表示範囲と、ナビ見出しの即時/正確な更新）。** 続いてU1b→U2a/b→U3a/b→U4a/b→U5→U6。既存高解像度APNG/CBZの性能残件はU3bへ統合する。以前の「まず性能測定」より本節を優先する。
- 原因確定：favorites見出し分岐の欠落、選択時の詳細自動展開、toolbar内status、64MiB画像拒否経路。WebP/APNGの症状・AI導入後scanのAI実行はユーザー報告で、今回の実機再現/原因確定ではない。キャッシュ/tooltip/逐次再生は既にあり、効果不足を修正する。
- 新素材のsource試験候補frontend02と、素材未収録のZIP07/旧Alphaを区別する。今回新しい配布候補は作らない。全P7/clean Windows/runtime公開監査/実音声等は既存残件を維持。過去のshutdown指示は再適用しない。

以下は先行作業の記録。過去の「次」「最優先」「現在地」は上の再開位置より優先しない。

## ビジュアル素材v1導入（2026-10-25、直近の変更）
- 実装 **787614a**。開始b8147fa、remote/既存Draft PR #5一致・clean、確認できる他の進行中repo作業なし。ユーザー指定ZIPを導入。[適用素材・変更ファイル・保留理由・証拠](visual-assets-v1.md)。
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
