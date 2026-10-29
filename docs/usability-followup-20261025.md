# 実機フィードバック改善計画（2026-10-25）

**状態：実装進行中。U1/U2のsource実装・Portable build・限定UIA確認済み。物理入力の受入は未完。U3以降は下記進捗を参照。**
Codex GPT-6.1 Sol / Antigravity共通の実装手順。既存P0–P7を置き換えず、P1/P3/UI/P4/P6の具体的な改善キューとして統合する。2026-10-25にユーザーが実装再開を指示した。

## 実装進捗（2026-10-25）
- **U6 filter source/CPU/build完了**：ZIP/CBZを共通predicateでまとめ、旧book/archiveを維持。本文/未承認候補のmissing除外も補強。[仕様・確認](compressed-filter.md)。U1–U6のsource完成分を再実装せず、最新基本ZIP候補へ反映して未受入だけを確認する。
- **U5 WinUI接続済み・実機は限定**：複数選択/一括整理/600件window・選択保持/literal favorite差分を接続。frontend06/native-selection03で18項目確認、全体は最後のrefresh待機不足でFAIL保持。[正確な未受入](library-selection.md)。次の実装はU6。
- **U5基盤（UI未接続）**：検索sessionのscope/原本版を全件検証する一括favorite/棚追加・解除API、locate、Coreのstable ID選択/range/取消/上限を実装。[仕様・残件](library-selection.md)。次はU5のnative UI接続。
- **U4b source実装・CPU確認済み、GUI受入待ち**：folder別起動時更新（旧root OFF）・一覧/AIの選択・初画面後queue・所有取消・進捗と明示一覧更新、成功scan後のmissing除外/metadata復帰を追加。catalog v3移行とv0–v3復旧互換。[仕様/確認](scan-startup.md)。次の実装はU5残、GUI/GPUは今回ユーザーの事前回答後に限る。
- **U1**：Page acceleratorの自動tooltipをHidden（キー自体は維持）、検索開始時の正しいナビ見出し、1行の長名省略と全文tooltip、テーマ対応の選択枠、単クリックでは詳細を開かずボタン/右クリックから明示表示、未保存draft保持、検索方式のtooltip/HelpTextを実装。
- 専用候補 `data/ai-ui/usability-20261025/frontend04`。Portable publish成功、既知WUI1001×3/SDK IL2104×2は残存。生成145PNG/専用DBのUIAで、結果providerを停止したままの3ナビ見出し更新・旧結果操作禁止、選択でpane非表示、明示詳細のdraft保持・原本不変を確認。証拠は `u1-uia02/report.json`。Light側/最終visual reviewの結果はcurrent-handoffを参照。
- `u1-dark01..04`は前面化/入力ハーネス・環境失敗としてrawを保持。screenshot --focus、focusコマンド、所有HWNDへの通常SetForegroundWindowも前面確認を満たさなかった。別アプリ入力やOS制限回避は行っていない。`--uia-only`でpointer/keyboard/context menu/小サイズsliderを**未検証として明示**する。これらをPASSへ数えず、入力可能時に対象だけ受け入れる。
- 先行 `u1-uia01`の画面レビューで選択枠の弱さとuniform tileのcaption領域不足を見つけ、選択styleとcaption最小高を修正。UIA PASSだけで見た目の合格にはしない。次の実装はU2a。
- **U2a/b**：画像/本の独自header/×を撤去しOSタイトルへ名前・位置を反映。noticeをtoolbarから独立overlayへ、下端32DIP/約1秒hideの共通制御、keyboard/menu/hover中の保持と常時表示設定。小画像拡大をviewer設定へ移動し、中心zoom/左drag、設定OFF既定の本の双方向循環を追加。保存/backup契約は旧形式を読み新boolean2値を保全。
- **U3 部分実装**：再生clockを処理時間の累積しない絶対deadlineへ変更。starvation/長い停止では再同期し、無条件frame skipをしない。同じWriteableBitmapのSourceを毎frame再設定しない。APNG黒化の原因確定/修正とは扱わない。
- U3bの容量経路：metadata/所有handleのstreamのみ256MiBまで、丸ごと原寸取得は64MiB、AI/旧APIの制限は維持。大容量GIFはnative全量転送を避けstreamへ。既存の画素数/4frame/128MiB制約・登録/版guardを保持。73MiBの生成GIFで、全frame数を走査せずprobe/先頭thumbnail/先頭stream成功、元mtime不変、原寸byte-array拒否、256MiB超拒否を確認。コメントpaddingで容量を増やした小画像fixtureであり、実72MB高解像度GIFのFPS/RSS受入ではない。
- U3候補 `frontend07` publish成功、Core対象97・Python animation13/format6 PASS。`u3-uia02`は6checks/exit0/残存0、生成WebP12frame/APNG72frameの連続割当とloopを確認、3PNG目視。先行u3-uia01は同件数検索の待ち条件が古い結果を通したハーネスFAILで、対象ID待ちへ修正して再確認。**報告原本APNGの黒化、物理FPS/Honeyview同等、大画像/RSS、CBZのcold/warm性能は残件。**
- **U5aの小区分**：空query/通常文字方式のライブラリで、お気に入り保存後にサーバーが同一順序/metadataを確認したときだけnative cardを保持し、対象の星とmenuを更新。結果session自体は作り直して世代/guardを保全。AI・順位/範囲変更・異なる行は既存再描画へfallback。`frontend08` publishと `favorite-uia01` 10checks/exit0/4PNG目視、登録→解除/タグdraft非保存を確認。複数選択、一括棚、favorites絞込からの部分削除、600件window保持は未実装でU5全体の完了ではない。
- U2候補 `frontend06` Portable publish成功、新規CS8602は初期化順を直して解消（既知WUI1001×3/SDK IL2104×2は残存）。Core対象79 checks、backup既存28＋不正boolean拒否1 PASS。生成144PNG/5ページCBZの `u2-uia01` は10checks/exit0/残存0、4PNG（主画面含む）を確認対象とした。OSタイトル更新、header非表示、toolbar位置固定、表示設定、単ページ/奇数RTLの双方向循環、bar非表示と設定ファイル保持を確認。ホイール/物理drag/hotzone/tooltip/HC/DPIは未受入。旧viewer試験のImageClose/ReaderClose/ReaderPageNumber等はOSタイトル/正常WM_CLOSEへ移行する必要がある。
- **U3a 添付パレットAPNGのループ2周目黒化修正（`cdf7a35`）**：`app/animation_sessions.py` の `Decoder.pull` で `EOFError` 到達時に保持済み `self.file` を `seek(0)` して `Image.open(self.file)` を再構築する `_reopen_loop` を追加し、Pillow `PngImagePlugin` のインプレース `seek(0)` で `PLTE`/`tRNS` が再読込されず2周目以降RGB全0になる不具合を修正。単体テスト `tests/test_animation_sessions.py`（20 PASS）および実機 `data/ai-ui/attached-apng-20261025/native02`（5 checks PASS・exit0・残存0、`animation_samples: [1, 4, 7, 10, 13, 16, 1]`）の5 PNG目視で2周目以降も有色・透過を維持することを確認（詳細は[animation-streaming.md](animation-streaming.md)）。
- **U4a 登録後のスキャン選択・一覧とAI索引の分離・3段階初回ガイド**：`app/production.py` と `app/production_server.py` に明示的スキャン `mode`（`'list'` 既定 / `'list_and_ai'`）および複数 `root_ids` 対応を追加し、一覧登録完了（`scan_jobs.state='complete'` コミット）後にのみ `ai_scan_hook` を接続することでAI失敗・取消でも取得済み一覧を絶対巻き戻さない構造を実装。`MainPage.GettingStarted.cs` / `MainPage.xaml` / `MainPage.xaml.cs` / `MainPage.FileActions.cs` でフォルダ登録直後の選択ダイアログ（「アイテム一覧だけ取得（推奨）」「一覧取得＋AI索引を作成」「後で」、AI未準備理由と準備導線、複数フォルダ一括1回確認）、3段階初回ガイドカード（`1. フォルダを追加` → `2. 一覧を読み込む` → `3. 必要ならAIを準備（任意）`）と「あとで閉じる」、使い方ダイアログ内の小画像拡大設定案内（ビューア内設定メニューへの誘導）、登録フォルダ設定の `ScanModeChoice` と段階別 `ScanStatus` / キャンセル、および `GettingStarted` の縦幅調整・`RootExcludes` 1行ヘッダー調整を実装。単体テスト `tests/test_production.py`（12 PASS）・Coreテスト全PASS・Portable `data/ai-ui/usability-u4a-20261025/frontend02` による実機 `run02`（35 checks PASS・exit0・残存0、spyで一覧のみスキャンのAI呼出し0回、7 PNG全目視）を確認。次は **U4b**。

## 1. 基準と確認範囲

- 読み取り基点：`9c69ea112d271ac005dee318473d1a2c490b2671`、`feat/winui3-production-mvp-20261011`、origin一致、作業開始時clean。PR #5はopen / Draft / 同HEAD。新規PR・ブランチ不要。
- 新素材を含む試験GUIは `data/ai-ui/visual-assets-review-20261025/frontend02`。既存ZIP07/source e197723、インストール済みAlphaと区別する。今回の報告すべてがこの候補だけで起きたとは断定しない。
- 今回はソースと既存記録の確認のみ。報告されたWebPのカクつき、APNGの黒化等を新たに実機再現したとは扱わない。以前の小さい生成素材や10.gifの成功も反証に使わない。
- 現在の登録→一覧→AI準備・索引、結果セッション、仮想化、複数棚、バックアップ、素材導入は既存資産。再実装せず、各項目の差分だけを仕上げる。
- 新しい色・キャラクターを増やす作業ではない。広い一覧、コンパクトな検索、明示的に開く右詳細を優先する。

### ソースで確認したこと（原因確定と仮説を区別）

| 対象 | 現行の根拠と解釈 |
| --- | --- |
| Ctrl+Homeの吹き出し | `MainPage.xaml`のPage直下にHome/End等のKeyboardAccelerator。自動tooltipの表示範囲が原因候補。ショートカット自体は残す |
| ナビの名称 | `MainPage.xaml.cs:LoadAsync`の見出し分岐にfavoritesがなく「ライブラリ」へ落ちる。見出し更新も結果処理側にある |
| 選択と詳細 | `Items_Changed`周辺で`Details.IsPaneOpen=true`。選択と詳細を開く操作が結合している |
| お気に入り | `SetFavoriteAsync`はフラグのみ保存するが`RefreshResultRowsAfterEditAsync`を呼ぶ。未保存タグを巻き込まない既存仕様を保全して更新範囲を狭める |
| 長い名前 | `TextTrimming=CharacterEllipsis`は既にある。追加するだけでは直らず、カード/テキストの測定幅・親の制約を確認する |
| ビューワー | `ImageViewerView`/`ArchiveReaderView`に下部StackPanel内のstatus、全域PointerMovedによるバー表示、2.5秒timer、zoomの`ChangeView(null,null,...)`がある。表示の上下動/再表示/中心ずれを対象にする |
| ヒント・キャッシュ | 画像ビューアには既存tooltip、静止画3件/96MiB cache、本はpage cache/先読みがある。全ボタン未実装・キャッシュ不存在とはしない。媒体間の不足とhit経路を調べる |
| アニメーション | `animation_sessions.py`はPillow逐次復号、最大4frame/128MiB batch、premultiplied BGRA。全frame待ちの旧方式へ戻さない。duration・合成・表示スケジュール・buffer更新を切り分ける |
| 大容量 | `previews.py`の画像分岐は`MAX_LARGE_IMAGE_BYTES=64MiB`でimage_info/animation_source等へ入る前に拒否。72MB級の拒否原因になり得る。圧縮容量と復号メモリは別 |
| スキャン | `ProductionCatalog._scan`は`index.scan`→`sync_index`。この関数内にAI推論はない。「AI導入後は必ずAIまで走る」は今回未確認で、launcher/ジョブ/現候補の接続を確認する |
| 実ファイル欠落 | `library_index.py`は完全に成功した走査後だけmissingへ変更する既存保全あり。これを維持し、一覧/検索での表示方針を整える |
| ZIP/CBZ | `library_index.py:TYPES`ではCBZ=book、ZIP=archive。ラベルZIPの単純改名だけでは両方を検索できない |

## 2. 実行順・完了ゲート

| 順序 | 単位 | 目的 / 既存計画との関係 |
| --- | --- | --- |
| U1 | ナビ・ヒント・名前・単一選択 | すぐ目に付く不具合と一覧の位置ずれを解消。P3/UI-2 |
| U2a | ビューワーのバー・設定・タイトル | 画像面を動かさず、迷わず操作できる。P1/UI |
| U2b | ズーム・ドラッグ・本の循環 | 基本閲覧操作を揃える。P1/P2 |
| U3a | WebP/APNG再生の安定化 | カクつき・黒化を対象限定で修正。P1/P7 |
| U3b | 大容量画像・キャッシュの仕上げ | 72MB超と既存高解像度APNG/CBZ残件を同じ限定確認に統合。P1/P3/P7 |
| U4a | 登録後の選択・初回ガイド・scan種別 | 一覧取得とAI索引を明確に分離。P6/UI-3 |
| U4b | 起動時scan・欠落の反映 | 許可されたフォルダだけ自動更新し安全に整理。P3/P4 |
| U5 | お気に入り差分更新・複数選択 | 選択位置を保った一括整理。P3/P4 |
| U6 | 種類フィルター・統合確認・新候補 | ZIP/CBZの見つけやすさと配布物への反映。P3/P6/P7 |

U1の後、独立したU4aを先行してもよい。U3で素材再現待ちとなったら原因未確定を記録しU4/U5へ進む。数値だけの性能調査で他の改善を止めない。基本ZIPの公開runtime権利/host、HC/DPI/clean Windows、R06–R09音声・音楽は既存の残件として保持し、今回消さない。

## 3. 各実装単位

### U1：一覧の操作と説明

**実装**
- Page全体の自動ショートカットtooltipを局所化/抑止。実装前に復元済みWinUI参照で対応プロパティを確認。Ctrl+Home/End/F/S、入力欄内のキー処理は維持する。
- ナビ遷移が許可された時点（未保存変更の確認後、ネットワーク応答前）で「ライブラリ／お気に入り／閲覧履歴」を更新。新範囲の準備中であることを示し、古い結果を新範囲の結果のように操作させない。取消/失敗/連打で見出し・選択・結果が混在しない。
- 名前はカード幅内で1行省略（`Test11451…`）、全文はtooltip/読み上げ/詳細へ。日本語・絵文字・拡張子付き・長い半角文字、小/中/大、list/gridで確認する。
- 単クリックは選択のみ。選択枠＋背景とfocusの区別、High Contrast用の枠を保つ。詳細が閉じていれば勝手に開かない。「詳細」ボタンと右クリック「詳細」で開く。既に開いている場合だけ単一選択に追従し、dirtyなら既存保存/破棄/取消を使う。複数選択時はU5へ。
- 検索方式の各選択肢と選択済み欄に短い説明。hoverだけでなくkeyboard focus/読み上げからも到達させる。
  - ファイル名・タグ：入力した文字でファイル名やタグを探します。
  - ファイル名・タグの意味：言い換えや関連する意味から探します（AI索引が必要）。
  - 画像の見た目：画像・本文ページの見た目や画像内の文字を手掛かりに探します（認識精度の保証ではない）。
  - 両方で探す（AI）：画像の見た目とファイル名・タグなどの意味検索を組み合わせます。
  実際の検索対象/方式と照合して文言を確定する。未実装の音声理解等を説明に含めない。

**箇所**：`MainPage.xaml/.xaml.cs`、一覧・ナビ・詳細の関連partial、既存style。
**完了/最小確認**：関連build＋1つの生成GUI flowで、window空白hover、キー、nav連打/失敗、長名、小tile、選択→右クリック詳細→戻る、dirty保持。詳細を閉じた状態で選択しても一覧が再配置されない。通ればU2へ。

### U2a：画像中心のビューワーと設定

**実装**
- 下部バーは高さを固定し、読込/失敗文言を独立overlayへ。文言が出てもバーと画像の配置を動かさない。読込中は前の正常画像を保持し、取得失敗と終了境界を区別する。
- 提案する既定：通常はバー非表示、下端32DIP程度の領域へpointerを動かすと表示、領域/バーから離れて約1秒で非表示。単にウィンドウ内で動いたことでは表示しない。値は最初の限定実機確認で調整し、恒常的な設定項目を増やさない。
- バー上hover・tooltip・開いているmenu・keyboard focus中は隠さない。Tab/F10で表示・操作可能、EscとAlt+F4で閉じられる。「常に操作バーを表示」をビューア設定に置き、誤操作を避けたい人の選択肢とする。
- 上部の独自ファイル名/重複×バーは撤去する案を採用。OSタイトルバー/ウィンドウ閉じるは維持。`Aredoko — 画像ビューア　Test01.png [50/100]`、本は本名とページ番号/見開き範囲をWindow.Titleに反映。非同期移動成功時だけ更新し、検索結果の総数と画像のみの順番を混同しない。確定できない総数は推測しない。
- 「小さい画像を画面に合わせて拡大」を画像/本の設定メニューへ移す。既存保存値を引き継ぎ即反映し、共通設定には必要なら同じ画面へのリンクだけ残す。設定を二重管理しない。
- 前後、zoom、fit、原寸、再試行、見開き、設定等の全ボタンに用途・有効なshortcutを表示。既存tooltipが出ない条件も確認する。

**箇所**：`ImageViewerView.cs`、`ArchiveReaderView.cs`、`ViewerWindow.cs`、`ViewerNotice.cs`、`ViewerInputSettings.cs`と既存保存契約。
**完了/最小確認**：読込/エラーでtoolbar座標が変わらず、下端/画像中央/keyboard/menuの状態遷移とOS×のclose/読書位置flushが通る。画像と本で1flowずつ。fullscreenが存在する場合も閉じる操作へ到達可能にする。通ればU2bへ。

### U2b：ズーム・パン・本の循環

- ボタンzoomは表示領域の中心にある画像座標を固定して拡縮し、offsetを境界へclamp。ホイールzoom等を既に提供している場合はpointer位置基準との役割を区別する。原寸/fit切替・DPI・見開きで余白を含め正しく計算する。
- 拡大時は左ドラッグでpan。pointer captureとcancel/lost captureを扱い、ボタン操作・double click・ページ送りと競合させない。画像が収まる軸では不要な移動をしない。
- 本の設定に「最後まで進んだら先頭に戻る」を追加。既定OFF（既存の末尾停止を維持）、ONは末尾→先頭/先頭→末尾で双方向循環。キー/ホイール/前後ボタンで同じルール。単ページ・RTL/LTR・奇数見開き・表紙単独・連続入力を扱う。
- 循環はその本（CBZ/画像ZIP/フォルダ本）のページ内に限定。ライブラリ全体の結果セッションを勝手に循環しない。取得失敗や取消を末尾とみなして先頭へ飛ばさない。

**箇所**：上記ビューア、`ViewerInputGestures.cs`、Coreのページ移動/入力設定。
**完了/最小確認**：中心座標の計算テスト、パン境界、単/奇/偶ページの循環・方向、再起動後の設定保持、1回のnative操作。通ればU3へ。

### U3a：WebP/APNGの安定化

- 最初の関連caseでdecode→転送→queue待ち→frame割当の時刻とduration/sequenceを記録。形式だけを理由に推測修正しない。GUIのframe割当成功は見た目の滑らかさ/物理FPSの証明と分ける。
- WebPはdeadline基準の再生clockと現行timerを比較し、処理時間を毎frameの待ちに上乗せするドリフト、先読み補充の空白、UI threadのcopyを診断。遅い場合もframe順・有限loopを壊す無条件skipはしない。
- APNGはposter、alpha、blend/disposal、差分矩形、ループ境界、半透明frameを生成fixtureで比較。黒化がデコード結果かbufferのclear/再利用/再描画かを特定し、正常frameを保持する。黒を透明と見なす応急処理は禁止。
- queue4frame/128MiB、worker所有/原本再検証、取消時の解放を維持。CPUが原因と確認されないままWin2D/別OSSへ全面置換しない。

**箇所**：`app/animation_sessions.py`、`image_animations.py`、`previews.py`、Core animation契約、`ViewerImageCodec.cs`、`ImageViewerView.cs`。
**完了/最小確認**：異なるdurationのWebP、透過/差分/有限loop APNG、GIF、64超frame、切替取消を関連CPUと限定nativeで確認し、再現したカクつき/意図しない黒frameが解消。未提供の問題原本は未確認と記録。必要な素材は実装段階で限定的に依頼し、私物フォルダ全体を探さない。

### U3b：大容量と既存キャッシュ

- 64MiBのファイル容量チェックを用途別に見直す。metadata probe/先頭thumbnail/逐次再生/原寸bytes送信/AI入力/圧縮内ページの上限を一括撤去しない。基本表示は全ファイルをHTTP byte配列へ載せず、検証済みhandleと逐次decoderを再利用する。
- 小解像度で長時間の72MB超GIFも対象。native GIF経路が全量転送/復号で不利なら既存逐次経路へ限定fallback。先頭thumbnailは全frame走査せず得る。画素数・展開寸法・同時decoder・合計buffer・取消/時間予算で保護する。
- cacheを静止画decoded / 本page / manifest / thumbnail disk別に測る。同一item/版/寸法の重複取得、表示前に待つ不要なpreload、先読みとの競合、版key不一致を優先して直す。原本版/登録状態/範囲の検証を速さのために省かない。
- 「初回」と「往復/再表示」の時間を分ける。既存高解像度APNG/CBZ残件をここで1つの小規模caseに統合。全アニメを無制限キャッシュする案は採用しない。

**完了/最小確認**：生成72MB超GIFのthumbnailと先頭再生、生成大APNG/CBZのcold/warm切替、cancel/close後のworkerとRSSを確認。一般素材で開始概ね1秒/キャッシュ切替250ms以内という既存目標は保持するが、大容量素材まで無測定で保証しない。上限拒否は具体的な理由と既定ソフトで開く導線を示す。

### U4a：登録後のスキャン選択と初回ガイド

- 「フォルダ登録済み」と「アイテム一覧取得済み」と「AI索引準備済み」を別状態として扱う。初回画面は **フォルダを追加 → 一覧を読み込む → 必要ならAIを準備** の3段階、現在の完了状態と次のボタン1つを中心にする。長文説明は使い方へ。後で閉じても設定から再開できる。
- フォルダ登録成功後に1つのdialog：「登録したフォルダをスキャンしますか？」
  - 「アイテム一覧だけ取得」：推奨の初期選択。ファイル名検索・閲覧ができる。AI workerを起動しない。
  - 「一覧取得＋AI索引を作成」：一覧取得の成功後、新規/変更分に既存profile・範囲・候補タグ方針に従いAIジョブを接続する。WD候補の自動承認はしない。
  - 「後で」：登録だけ保持。「登録フォルダ → 対象フォルダの設定 → スキャン」から実行可能、と明示。
- AI未準備なら2番目は理由と「AI検索の準備」導線を提示。選んだだけでモデル取得/実行環境導入を始めない。複数folder追加時は対象をまとめ1回だけ聞く。登録取消/失敗では成功dialogを出さない。
- 既存scan APIへ明示mode契約を追加/接続する。旧clientの省略値は一覧のみとし互換影響を確認。「一覧の登録」と「AI索引」の段階別進捗/取消を表示。AI失敗でも取得済み一覧を巻き戻さない。
- 今回の「AIまで自動実行される」報告は起動対象とログを確認して原因を記録。現ソースの基本scan関数にAI呼出しがないため、見た目の文言だけの問題か別ジョブ連携かを区別する。

**箇所**：`MainPage.GettingStarted.cs`、folder登録/設定、`production.py`/`production_server.py`、既存AI job/scan状態、Core API、利用ガイド。
**完了/最小確認**：AI有無×各選択、後で→設定から実行、登録失敗、一覧取消、AI失敗での一覧保持。spyで一覧のみのAI呼出し0を確認、生成DBのnative導線1回。通ればU4bへ。

### U4b：起動時の自動更新と削除反映

- 登録folder設定へ「起動時：しない（既定）／一覧のみ更新／一覧＋AI索引」を追加。既存rootはOFFで移行。ユーザーが選んだrootだけ、初画面表示後の所有queueで処理する。重複起動/手動scanと二重実行しない。
- AI未準備なら一覧を取得し、AIは未実行理由を通知。未接続rootは失敗/保留で表示して無限retryや全消去をしない。バックアップ/復元のwriter fence・cancel・再起動境界と共存する。設定のbackup/restoreにも追加値を含める。
- 成功した全走査でmissingと確定したitemは通常一覧/検索/棚/お気に入りの表示対象から除外し、開いている結果セッションも適切に無効化/再取得する。これは**元ファイル削除やメタデータの物理消去ではない**。タグ・棚・履歴を内部保持し、同一locationの再出現で復帰できる。
- 切断/権限拒否/途中取消/不完全走査はmissingへ確定しない。既存の完全走査後commitを維持。古いAI vector/cacheが欠落itemを検索へ戻さないよう共通scopeで除外する。

**箇所**：`root_preferences.py`、`library_index.py`、`production.py`、共通query/scope・job・backup形式、folder設定。
**完了/最小確認**：実削除/再出現、root切断/権限失敗/取消で誤消失0、再起動で指定rootだけ動く、AI mode保持、restore旧形式互換。データ保全テストは省略しない。

### U5：差分更新と複数選択

- お気に入り登録は対象itemだけpending表示→応答後に星/メニュー/詳細を更新。既存のタグ/shelf draftは保存しない。失敗時は元へ戻し原因を示す。
- お気に入り表示から解除する場合はその行だけ除去し件数とanchorを維持。検索条件/順位に影響する編集は無条件local patchせず、backendのresult generation/範囲を照合して該当windowを再取得する。古いsessionが通るよう安全検査を無効化しない。
- Ctrlで追加/解除、Shiftで現在の検索順の範囲選択。単一クリックは単一選択。選択枠と「N件選択」を表示。選択内の右クリックは複数選択を保持し、非選択の右クリックは対象を単一選択する。
- 複数メニューは「お気に入りに登録／解除」「棚に追加／棚から外す」。混在をtoggle1個で曖昧にしない。棚追加は既存所属を上書きしない。画像や本を開く等は単一選択時だけ提供。
- 選択はセルではなくstable item IDで保持。600件cacheから外れても選択が消えず、未ロード範囲のShiftは結果sessionの順序とrangeで取得。大範囲は件数・準備/取消を表示し、全画像や全UIを生成しない。条件変更時は旧selectionを混ぜない。
- 一括APIは認証/範囲/版を全IDで検証して1単位transaction、上限が必要なら明示して拒否し黙って途中切断しない。長い操作をchunk化する場合は部分成功/取消の契約を先に定め、成功分を表示する。
- 詳細が開いている場合、複数選択では「N件選択」のsummaryへ。単一itemのdraftを別itemへ転用しない。U1の明示詳細導線を維持。

**箇所**：MainPage一覧/選択/context menu、結果session更新、`api/items/update`、既存shelf bulk契約。
**完了/最小確認**：scroll/layout/600件eviction中のCtrl/Shift、favorites絞込から解除、応答競合/保存失敗、棚複数所属保全、dirty保持、key選択。全一覧の点滅・先頭への飛び・毎回のthumbnail再取得がない。

### U6：圧縮ファイルの種類と受入

- UIの「ZIP」を「圧縮ファイル（ZIP・CBZ）」へ。保存済みbook/archiveのkindを一括書換えず、検索条件にcontainer形式の共通predicateを追加してZIP/CBZを対象とする。「本」は従来のCBZ/フォルダ本等を維持し、CBZは両方の入口で見つかってよい。PDF/EPUB/フォルダ本を圧縮ファイルフィルターへ誤混入させない。RAR/7z対応を暗示しない。
- 通常/AI/類似/棚/結果session/ビューワーの範囲へ同じpredicateを適用。UIだけで後filterせず、旧kind指定の互換を維持する。DB移行が不要なら追加しない。
- 各単位の関連確認を使い回し、最後に登録→scan→検索→選択/一括整理→閲覧→設定保持の短い統合確認を行う。新候補は新出力先へ作成し、source/commit/起動入口を明記。ユーザーが古いAlphaで確認し続ける状態を避けるが、黙って上書きしない。

**完了**：ZIP/CBZの両方が該当filterで出て同順に閲覧可能、PDF等と分離、旧API保持。変更箇所build/関連テスト、Light/Dark通常幅とkeyboardをまとめて確認。HC/DPI等の既存未受入は別途記録し、今回の部分成功をM1全完了と呼ばない。

### U7：ダブルクリック時のビューワー選択（2026-10-27 source実装・限定確認待ち）

設定「ダブルクリックで開くアプリ」へ内蔵（既定）／Windows既定アプリを追加。既存の原本パス検査・右クリックshell経路を共用し、外部起動失敗時は内蔵で開くか閉じるかを選べる。詳細の明示表示ボタンは内蔵を維持。検索順が外部へ渡らない説明、既存設定の保持、backup/restore互換を追加。Core設定・重複起動防止、生成backup復元3件とPortable/frontend02は確認済み（Automation名前空間不足の初回build失敗を保持）。**設定のnative操作と実際の外部関連付け起動はまだ未検証**。実行時はユーザーへ確認し、外部アプリや通常データを勝手に操作しない。

個別許可のu7-native01/02はどちらもWindows前面化を取得できず、操作入力前に停止・所有exit0。02では初期一覧準備待ちを加えたが前面化は許可されず、同じ試行を追加反復しない。設定操作/外部起動/内蔵fallbackをPASSにせず、今回の生成画像削除も実行されていない。PC操作に干渉しないCPU作業へ進む。証拠`data/ai-ui/continuation-20261027b/u7-native01`/`u7-native02`。

**2026-10-28設定保存の限定受入**：ZIP10/source0138a58を専用DB/生成素材でUIAのみ操作。`u7-settings-native02`は既定アプリへ変更→保存/再表示→内蔵へ変更→保存/再表示、8checks/3PNG全目視/exit0。実ダブルクリック/外部アプリ/fallbackは実行しておらず未検証。初期Lightだが試験seedの必須version/wheel欠落により設定はsystemへ戻り、保存後Darkになった。Lightだけの全面受入とはしない。seedを今後用に補強し、同じGUIを再実行しない。01はitemと子textの同名誤選択で保存前FAIL、raw保全・所有modalをlive UIAで閉じ通常exit0。両方とも物理入力/前面化/ファイル削除/GPU/通常DB/Alphaなし。証拠`data/ai-ui/continuation-20261028/u7-settings-native01/02`。上の27日時点のnative未確認を、この保存範囲だけ更新する。

**利用者の意図**：Aredoko内蔵ビューワーの機能に物足りなさを感じる人が、毎回右クリックしなくても普段使いの外部ビューワーで開けるようにする。Aredokoを主に検索・整理へ使い、閲覧体験は好みのアプリへ委ねられるようにする。

- **実装済みとの区別**：アイテムの**右クリックから外部ビューワーで開く機能は既に存在する**。新規実装対象は**ダブルクリック時の起動先を設定で切り替えること**であり、右クリック機能の再実装ではない。
- **既定値**：従来どおり、ダブルクリック→Aredoko内蔵ビューワー。既存ユーザーの操作を突然変えない。
- **追加設定**：「ダブルクリックで開くビューワー：内蔵（既定）／外部」を用意。外部の場合は既存の外部起動経路を再利用し、Windowsの既定アプリを基本とする。既存実装でアプリ指定を扱える場合はその設定も再利用し、不要な別実装を増やさない。
- **重要な制約**：外部ビューワーへはAredokoの検索結果・ライブラリアイテムの並び順、連続閲覧順、結果セッションを引き継がない。設定欄にその旨を明記し、外部アプリ内での次/前アイテムがAredokoの順位と一致するとは案内しない。**内蔵ビューワー選択時の既存の閲覧順・読書位置・ページ移動は維持**する。
- **安全と互換性**：単クリック選択・右クリックメニュー・本/画像/動画等の既存挙動を壊さない。対象形式の外部関連付けや起動に失敗した場合は理由と内蔵で開く導線を示す。勝手な既定アプリ変更・追加インストール・元ファイルの改変はしない。既存の設定保存/復元経路を使う。
- **最小確認**：既定値の後方互換、設定切替→再起動保持、内蔵/外部のダブルクリック各1件、右クリック経路の維持、関連付け不可の案内、外部でAredoko順序が継承されない表示を確認。Windows実機がない場合は未検証と明記する。

**優先順位**：将来の閲覧/操作性改善としてバックログへ追加。現行current-handoffの「次の1件」や動画内容索引、P6等の優先順をこの追加要望だけで置き換えない。着手時はコードで現在の右クリック外部起動経路を先に確認する。

## 4. 要望の対応表（取りこぼし防止）

| ユーザー指摘 | 対応 |
| --- | --- |
| ウィンドウhoverでCtrl+Home | U1 |
| 初回セットアップが難しい | U4a |
| 登録後scan選択、一覧/AI、後での導線 | U4a |
| 読込文言で下部バー上下動 | U2a |
| 本の末尾⇔先頭、設定 | U2b |
| 閲覧速度/キャッシュ | U3b |
| zoom右下ずれ/左ドラッグ不可 | U2b |
| 下部ボタンのhint | U2a |
| pointer在窓中に隠れない/もっと短く/下端だけ表示 | U2a |
| 小画像拡大の設定をビューワーへ | U2a |
| 独自上部/×撤去、OS titleに名前と番号 | U2a |
| お気に入り/履歴の名前と遷移遅延 | U1 |
| お気に入り保存で全体更新/遅い | U5 |
| WebPのカクつき/APNGの黒化 | U3a |
| 検索方式ごとの説明 | U1 |
| 長いファイル名が見切れる | U1 |
| 72MB級GIFのthumbnail/再生 | U3b |
| 単クリックの詳細自動表示停止/選択枠/右クリック詳細 | U1・U5 |
| Ctrl/Shift複数選択、一括お気に入り/棚 | U5 |
| folder別の起動時scan、一覧/AI | U4b |
| 削除原本の再scan後の一覧除外 | U4b |
| CBZを含む圧縮ファイル種別 | U6 |
| ダブルクリックの起動先を内蔵／外部で選択（右クリック外部起動は維持） | U7（source実装、設定保存/再表示UIA確認済み、実ダブルクリック/外部起動は未確認） |

## 5. Codex 6.1 Sol / Antigravityへの引き継ぎ

1. AGENTS → current-handoff → 本書の未完単位だけ読む。fetch/status/HEAD/既存PRと他agent差分を確認。今回のplan以後の実装があれば同じ項目を重複実装しない。
2. **最初はU1**。1単位に全部詰めず、U1a=Ctrl+Home tooltip＋nav見出し、U1b=長名＋明示詳細＋検索hint、の2コミット程度で進める。その後U2aへ。
3. 通常はSolまたはAntigravityで実装できる。モデル名による全体再設計は不要。結果session世代と差分更新、跨window複数選択、scan/backup競合で安全性を両立できない場合のみ設計レビューを切り出す。Astra級レビューはその局所判断の候補で、全作業の前提ではない。
4. 単位ごとに実装→関連build/テスト→次へ。修正なしで全回帰/同一native試験を反復しない。取消/原本保全/範囲漏れ/移行の確認は省略しない。今回は計画のみなのでbuild/GUI/GPU/scanも実行しない。
5. コードを触る際は該当WinUI skillと現行テスト方針に従う。未導入のskill/特定CLIを必須にせず、Antigravityでも同じ受入条件と既存repoツールを使えるようにする。新依存・新モデル・私物全体スキャンはこの計画で許可されたものではない。
6. current-handoffに「単位ID/利用者向け変化/commit/確認/未確認/次の1件」を短く記録。実装済み・確認待ち・素材待ちを区別。既存文書を消さず本書の状態を更新する。
7. 既存branch/PRを使い、関連分だけcommit/push。Actions/新PR/main merge/force pushなし。起動中のユーザーGUIや通常DBを勝手に閉じたり差し替えたりしない。shutdownしない。

再開用の指示例：

> 最新開発ブランチとAGENTS.md/current-handoff.mdを確認し、docs/usability-followup-20261025.mdの未完先頭から実装してください。まずU1a（Ctrl+Homeの吹き出しとナビ見出し）を仕上げ、関連確認後にU1bへ進んでください。既存の結果セッション・選択・未保存編集を維持し、ロードマップの再作成は不要です。

## 6. 追加提案と見送り

- 採用：scan後に「一覧に追加N件／更新N件／見つからないN件、AI索引は未作成/進行中」を短く表示。利用者が検索可能範囲を理解できるようにする。意味のない進捗%は作らない。
- 採用：設定・helpから起動候補の版/commitを確認しやすくし、報告時にsourceと旧配布物を混同しない。既存診断表示を活用する。
- 採用：設定値の移動は既存値を引き継ぐ。新しい「設定画面を探す」作業を増やさず、ビューア内に関連項目をまとめる。
- 見送り：大規模UI全面再設計、常駐キャラクター拡大、全frameの永続キャッシュ、無根拠なcodec交換、別frontend、専用OCR。今回の症状に必要な局所改善を優先する。


## 2026-10-29c：ネイティブ操作部のキーを優先する局所改善

プレイヤーのpreview shortcutがSliderの左右キーとButtonのSpaceも先に処理する経路をsourceで確認。frontend内のvisual ancestry判定で、音量/シークの矢印やbuttonのSpace/Enter、文字入力/選択controlの操作をcontrol側へ返す。画像は設定menu表示中のMoveAsyncを止め、画像/本ともmenuのnative key操作を通す。viewport上の既存shortcut・クリック・wheel・拡大/読書位置/設定値は保持。

既存Portable候補16で実キーのreproを試みたが、最初は前面化不可、次はwinappがWindowsのlocked/secure desktopを明示して**入力前停止/正常exit0**。ユーザーのGUI許可不足ではなくdesktop readiness不足であり、repro済み/実キー合格とは記録しない。UIA-only専用modeでは、無音WAV/専用DBで音量75/消音とpauseの独立、元media不変を確認。初回getterのRangeValue想定違いは表示Textの読取に修正済み。codeのPortable buildは0 errors/既存WUI1001×3。新sourceのpublishとUIA-only確認を行い、解除後に `tools/test_native_viewer_input.py --keyboard-controls` の一括3ケースを確認する。`--inspect-controls` は実キーを検証しない。

### 2026-10-29c：動画・音声の表示整理

- 画像・本と同様、ファイル名をOSタイトルへ表示し、動画・音声の重複した上部バーを廃止。シーク位置は下部の再生／音量操作の間へ配置した。閉じる操作はOSの×／Alt+F4／既存Escを使用する。
- 読込・失敗の通知は操作バーと独立したoverlayへ移し、通知の出入りで操作バーの高さが変わらない。字幕や再生画像の変換・新decoderは追加しない。
- Portable build成功、既存picker analyzer警告3件を保持。関連UIA／通常入口は最終候補で確認する。locked desktopの実キー未受入は継続し、UIA成功をキーボード成功に置き換えない。
