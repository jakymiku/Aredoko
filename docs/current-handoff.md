# Aredoko — 現行の単一引き継ぎ（2026-11-11）

旧checkpointより本書を優先。過去の全文・判断は本書のGit履歴と[履歴目録](history-index.md)から辿る。

## 2026-11-11 候補05とPython未導入Windowsの配布試験

- 開始時のローカル・remote・Draft PR #5のHEADは `63b0c13`。製品source `f487f1d` で動画・音声の操作バーに「再生を閉じて詳細で整理」を追加。同じ作品の詳細を開き、タグ欄へフォーカスする。既存のお気に入り保存待ちを通り、タグと棚の下書きを保持する。最新branch HEADは本書のGit履歴を参照。
- **候補05のホストGUI**。通常EXEと専用設定・DB、生成MP4/WAVで、操作バーのボタンから同じ詳細に戻ることを確認。WAVのタグ下書きは画面に残りDBは未更新。専用SQLiteの書き込みを一時保留した試験では、保存完了までプレイヤーが残り、解除後に星を保存して詳細にも反映した。通常終了0、所有プロセス残存なし、専用DB整合と生成原本のSHA一致。前面化できなかったため、詳細を閉じた一覧からの物理ダブルクリックと復帰時のキーボードフォーカスは未確認。証拠は `data/gui-player-details01/run-01`。
- **候補05の配布物**。 `dist/portable-managed-20261111-05/Aredoko/Aredoko.exe`、Python非同梱663 payload、manifest込み665 files / 500,167,539 bytes。Portable build/publish、全payloadとZIPのSHA照合済み。ZIP 214,938,155 bytes、SHA256 `af65bd2d0b62e04f16055e86c91068ad38c8ed6d70136099090e433c5ff1130a`。frontendは `data/development-tools/frontend-player-details01`。候補04を受入済み予備として保持。installed Alpha・通常DB・shortcutは未変更。
- **P6試験準備**。`prepare_windows_sandbox.py --managed-python-download` を追加。既定ではオフライン、指定時はPython非同梱のmanaged候補でゲスト通信を有効化。候補と生成kitのSHAを照合し、読み取り専用で共有する。vGPU・クリップボード等は無効。Sandbox設定8件、Portable startup 18件PASS。後者はCodexの制限内ではハードリンク拒否とloopback timeoutがあり、専用一時領域・通常権限で確認した。
- **候補05のゲスト受入はBLOCKED**。再開用の手動設定は `data/ai-ui/managed-candidate05-clean-manual/Aredoko.wsb`。GUIと基本環境取得の許可後、以前のWinSxSパス（9278）は非PEで起動拒否。拡張子の関連付け・System32入口が見つからず、署名が有効な9818コンポーネントからの起動も、Windows Sandbox自身のイベント1000／`0xc0000409` で即時終了。ホスト証拠は `data/ai-ui/managed-candidate05-clean`。ゲスト内の新規公式取得・通常EXE起動・一覧表示は未実施。OS設定の変更、AI取得・GPU推論は未実施。

## 2026-11-11 候補04のGUI受入

- 開始時のローカル、remote、Draft PR #5のHEADは `4d521e7`。候補04（製品source `2748640`）の通常 `Aredoko.exe` をホストWindowsで起動。今回のGUI・GPU許可を取得後、専用設定・DBと生成素材で操作した。製品コードは候補と同じ。今回の引き継ぎHEADは本書のGit履歴を参照。
- **P0-1〜5、A1〜6、B1〜4、C1〜9の24件PASS**。AI準備の同意・容量・提供元・ライセンス、速度既定と5MB/秒、実進捗と再表示を確認。既存runtime/modelをCUDAで再利用し、未選択プロファイル・別配置・別索引を保持。別試行の全照合フェーズ中止は設定SHA一致。空キャッシュの表示・案内・Explorerでの保存先確認・削除無効を確認。通常再起動後の日本語GUI検索で `blue.png` が先頭。保存済みベクトルの内容も一致。
- 生成MP4/WAVで再生中の星の登録・解除、一覧と詳細への同期、タグと棚の下書き保持を確認。専用SQLiteの書き込みを一時保留し、閉じる要求後も保存待ちでプレイヤーが残り、解除後に保存・終了することを確認。通常再起動後も星が保持され、お気に入り一覧から開くWAVの操作バーでは星が非表示。
- D06と別経路のWinApp UI Automationで受入完了。画面遷移直後の古いUIA要素や隠れたプレイヤー操作バーは、遷移完了の確認や所有ウィンドウでのF10表示で切り分けた。Computer Use自体の復旧は未確認。WinApp初回のテレメトリ案内が出た時点で送信の有無は未計測。以後はプロセス環境で無効化。
- 3起動とも通常終了0、所有プロセス残存なし。生成原本・基本artifactのSHA/mtime、専用DB整合、配布物663件の照合に成功。結果表・画像・ログはignoredの `data/gui-acceptance04/session-result.md` と同階層。製品不具合として起票する再現はなかった。新規ネットワーク取得の全一連、実ファイル入りキャッシュのGUI削除、完全Python未導入Windows・Sandbox guestでの今回の候補04は別途受入。

## 候補04までの実装記録

- **branch / PR**：`feat/winui3-production-mvp-20261011` / Draft PR #5を継続。候補04までの実装は **815f0d1 → d7dc9a6 → 5b9f1d1 → 2748640459f3c63e0dc994532d158c31a3d124d0**、push済み。Actions/新branch/新PR/main merge/force pushなし。未追跡`Aredoko-test/`はuser作業として不干渉。
- **user指示**：クォータ残10%前後まで継続し引き継ぐ。今回はGUI/GPU許可済み、実行前に通知。通常DB/私物/installed Alpha/shortcut/OS設定/driverは変更なし、shutdownなし。C drive復旧後のAlphaは再導入していない。

## 利用者にできること

- **公式AI環境の自動構築**：設定「AI環境を自動構築」、または初回AI案内「EmbeddingGemma 2を自動構築」へ接続。容量/提供元/licenseと同意→固定公式44wheel/model取得→基本Pythonからpipなし専用venv→公式payload/base/全file検証→生成text/image実推論→既存atomic settings保存。既存正常runtime/modelは再利用し、他profile/配置/索引namespaceを保持。失敗/取消は旧設定を保つ。GPU一時probeは既存inference groupの排他内、CPU fallbackあり。既定無制限・任意MB/秒の取得上限も接続。
- **キャッシュ管理**：設定「ストレージとキャッシュ」で専用wheel cacheの容量/path/開く/削除・手動削除案内。選択済み環境を全照合してから固定recipeのwheelだけを削除。取得/構築/選択と共有leaseで排他。モデル/venv/DB/原本は対象外。元wheel由来receipt SHAを設定へ固定した後は、cacheなしでも完全照合・実行できる。小さい基本Python/Pillow検証artifactは保持。未完incoming/過去retained folderは現行削除ボタンの対象外。
- **動画・音声のお気に入り**：画像/本と共通のViewerFavoriteActionを接続。通常文字検索/allの有効なresult sessionから、再生を継続したままflag-only保存、一覧/詳細同期、close時に保存完了を待つ。タグ/棚draftは保存しない。AI/類似/お気に入り/履歴scopeは新action非表示を維持。

## 今回のGUI受入より前の実証記録

- **AI新規構築 PASS（ホスト）**：専用data/auto-ai01へ保持済み公式base/wheelを独立コピーし、製品AIEnvironmentJobsを実行。新venv22,652file/4,861,676,424bytes→固定モデル全照合→CUDA text/image probe（観測peak931.8MiB）→receipt/設定公開まで465.895秒。取得原本と既存model/venvは変更なし。新方式の初期登録では元wheel provenanceも必須、任意folderの自己申告inventoryだけを信用しない。最終reviewで既存basic verifierと同じpyvenv.cfgの既知5keyに限定し、大文字alias等によるCPythonとの解釈差を対象CPU6件と実venv設定で確認。最後の差分は検証条件のみ、GPU試験を無意味に反復していない。
- **cache削除後の実検索 PASS（ホスト）**：44file/2,972,088,117bytesを製品serviceで削除。保存済みroot/hashを使う新production backendで全file照合32.01秒→生成青赤PNG2件GPU索引→「青色の四角い画像」で2結果/先頭blue.png→EOF正常終了0。原本SHA/mtime不変、catalog/vector DB integrity ok。さらに実build/start APIでcacheなし既存環境を再利用し、resident検索workerを解放→一時probe→設定内容不変→検索継続を確認（再取得/新venv/再索引なし）。
- **梱包payload PASS（ホスト/API、最終cfg制限追加前の候補03）**：候補03に梱包されたbackendを、独立設定/生成DB・索引コピーと公式basic Pythonから起動。cacheなし全22,652file照合36.17秒→GPU日本語検索2結果/先頭blue.png→自動構築capability確認→EOF正常終了0、原本/DB整合維持。source repo内backendを使った結果ではない。GUI/guest起動とは区別。data/release-ai-api01/result.json。
- **関連CPU/build**：managed runtime6、cache/API7、setup job15（HTTP1はOS sandbox10013後に通常権限PASS）、factory8、ownership11、audio worker14、runtime paths6（symlink作成権限1skip）。保持原本/wheelを使う既存関連確認は再利用し全回帰を反復していない。最終Portable publish成功、既存WUI1001×3/IL2104×2のみ。
- **GUIは未受入（D06）**：6.1 TerraのComputer Useが専用cache02 window列挙後、画面取得で応答せず操作前に中断。通常close操作も応答せず結果不明。node_repl reset済み。正確なPID/path/parentを照合してfixtureのみ終了、owner/backend回収・今回の所有プロセス残存なし。これは正常終了の合格ではなく、製品の画面停止とも断定しない。同じtool経路を変更なしで反復しない。新cache/自動構築/速度制限/動画音声starの実GUI操作は未検証。
- **限界**：製品の自動構築から新規network取得を含む全一連、完全Python未導入Windows/Sandbox guest、実GUI AI検索、動画/音声の新star保存中close、HC/DPI、全依存license/NOTICE/署名・正式公開は未受入。今回のhost/API結果をSandbox成功として報告しない。過去のguest/GUI成功は当時のsourceの範囲だけ。

## 候補・容量・証拠

- 予備の候補04は **dist/portable-managed-20261111-04/Aredoko/Aredoko.exe**、source **2748640**（frontendのC#は5b9f1d1から不変）。Python非同梱663payload/499,984,667bytes、manifest込み665files/500,167,921bytes、ZIP214,938,342bytes。最後のcfg境界修正を含む実venv通常設定のCPU確認もPASS。全payload/公式basic artifacts/venv/import/media/ZIPを検証、正確なfiles/bytes/SHAは同directoryのpreflight.jsonと[配布記録](portable-refresh-20261024.md)末尾。候補04のfrontendはdata/development-tools/frontend-product04。
- cache削除後の構成相当は **6,968,324,482bytes（約6.97GB）**：app全manifest込み500,167,921、base39,588,189、basic venv15,301,385、AI venv receipt込み4,865,379,772、model1,525,821,059、必要artifact22,066,156。最終候補04への差分も反映した論理file容量。ZIP/SDK/開発コピー/通常DB/原本は別。15GBは構築時空き目安。保持開発原本1組はdata/ai-lock01/wheels、通常cacheと混同しない。
- 不要な中間publish/frontend-auto01と再生成可能bin、計412,721,466bytesを絶対path/Git非追跡/link/process非参照確認・ignored記録後に削除。後続buildのbinと置換済み候補02/frontend-product03も同じ安全確認で整理し、合計2,255,663,289bytesを削除。中間03も退役、最新04/予備01・現行frontend04/失敗再現cache02は保持。モデル/venv/DB/log/SDKはゴミ扱いしない。
- 証拠：data/auto-ai01/{result,cache-clear-result}.json、data/auto-ai-api01/{result,reuse-job,reuse-result,fixture-first-failure}.json、data/ai-gpu01/result.json、data/managed-cache01/evidence、data/gui-cache02/{cleanup,session-result}.json、data/capacity-20261111。初回API fixtureのready/verified誤期待は失敗記録を保持し、契約修正後に索引/検索部分だけ再確認。詳細は[配布設計](lightweight-distribution.md)最上段と[UI記録](p3-continuous-browse.md)末尾。

## 次の1件

1. **P6**：標準入口から起動できるSandboxか別のPython未導入Windowsで、候補05の通常EXEから公式基本環境を取得・照合し、生成素材3件の一覧表示まで確認する。WinSxS直接起動の同じ失敗を繰り返さない。新規取得とGUI・GPUの実行は対象を具体化して事前確認する。
2. **UI**：候補05の一覧ダブルクリックから詳細への復帰とタグ欄のフォーカスを、前面操作できる専用環境で限定確認する。実装は検索・一覧から閲覧と整理への往復を続ける。保存・原本・起動に影響する再現を優先し、非致命的なものは[対応待ち](deferred-issues.md)に記録する。
