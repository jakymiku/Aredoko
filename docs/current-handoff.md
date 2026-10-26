# Aredoko — 現行の単一引き継ぎ（2026-10-26）

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
- **現在の次の1件**：R06/R07の明示的text/audio profile＋bounded PCM worker契約を実装。通常text/cover profile・legacy namespace・既存512D音響空間を維持し、自動索引/UIへ一括接続しない。直前のGPU許可は実施済みで、新GPU/GUIには新回答が必要。M1残受入（HC/物理DPI/clean Windows・長時間FPS/RSS）・公開runtime権利/host（registry0）・R06最終方式選定/M2は未完。既存成功flowを無変更反復しない。shutdownなし。

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
