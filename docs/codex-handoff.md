# Aredoko — Codex向け開発引継ぎ（2026-10-11）

> **最初に読む文書。** 2026-10-10時点の旧 `docs/status.md` / README には「GUI未決定」「ネイティブGUI未実装」という古い記述が残っている。現在の方針・分岐状況はこのファイルと [Issue #4](https://github.com/jakymiku/Aredoko/issues/4) を優先する。ファイル上の実装が異なるときは実際のコードを調査してから更新する。

## 今、何をしているのか
- 目的: **Aredoko**（Windows用のローカルメディアライブラリ検索・整理アプリ）の**製品版MVPをWinUI 3 + C#で新規実装する**。以前はGUI方式としてTauri + Reactも評価したが、2026-10-11にユーザー判断で**WinUI 3を先行採用**した。Tauriの比較コードは削除しない。
- 理由: Tauri/WinUI双方の実機GUI基本操作が完走し、WinUIのPrivate Bytes（アプリ本体関連プロセス）が一貫して小さかった。CPUは操作回数の差や負荷条件が統一できておらず優劣は未確定。安定性に関しては**WinUIだから無条件に安全と証明されたわけではない**。過去にWinUI試作固有のクラッシュも修正済み。
- GUI: Fluent 2 / Windows 11らしいモダンで密度の高いUI。左ナビ・上部検索・中央の大きい作品一覧・右の詳細/タグ編集。狭い画面は詳細をドロワーに。Mica等の見栄えは安定性・操作性を損なわない範囲。
- 開発実務: **製品用の最初の縦切り実装と実機GUI検証まで完了**。登録・走査・文字検索・整理・再起動保持に加え、画像/CBZ/ZIPのプレビューが動く。EmbeddingGemma2の最初のAI索引/検索APIとGUI接続も追加。GUIのAI検索通しテストは未完了。Issue #4全体の完成宣言ではない。最新結果と残課題は末尾、起動手順は [winui-mvp.md](winui-mvp.md)。

## GitHub上の資産と現在位置
| 作業 | 場所 | 状態・意味 |
| --- | --- | --- |
| 公式デフォルト | `main` | 既存デモの安定基点。直接改変しない |
| UI設計/試作 | [PR #1](https://github.com/jakymiku/Aredoko/pull/1) · `feat/compact-library-ui-20261010` | **Draft / 未マージ**。Web試作のモダンUIや未保存確認、エラー・ドロワーUXの参考 |
| フォルダ索引 | [PR #2](https://github.com/jakymiku/Aredoko/pull/2) · `feat/library-index-foundation-20261010` | **Draft / 未マージ**。読み取り専用の `app/library_index.py`, `tools/index_library.py` とテスト・ドキュメント。製品版で必要なら**差分を調べて安全に取り込む** |
| GUIフレームワーク比較 | [PR #3](https://github.com/jakymiku/Aredoko/pull/3) · `feat/gui-framework-comparison-20261010` | **Draft / 未マージ**。WinUI 3 / Tauri + Reactの試作、Windowsテスト用BAT、自動操作ドライバー、CSV/HTML計測 |
| **製品版MVP** | **`feat/winui3-production-mvp-20261011`** | **現在作成済みの作業ブランチ**。PR #3のHEADから分岐し、比較試作を参照できる。**このブランチに新規ソースを追加して進める** |
| 実装タスク | [Issue #4](https://github.com/jakymiku/Aredoko/issues/4) | Codexへ渡す実装目標、スコープ、禁止事項、合格基準 |

**注意:** PR #3 → PR #1 → mainという祖先関係に対し、PR #2はmainをベースとする独立ブランチ。製品版ブランチからPRを作る際は差分に比較用コードが含まれる。適切なPRベースを選び、旧PRの無断マージ・履歴書き換え・強制pushを避ける。

## 引継ぎ受領時点の既存資産（2026-10-11実装開始前）
- **Python標準ライブラリ＋SQLite / localhost API**: `app/catalog.py`, `app/server.py` など。50,000件の架空レコード、60件ページ、タイトル/タグ検索、種類フィルタ、詳細、タグ・棚・お気に入り・確認済みの単体/一括保存。セッショントークン付きのlocalhost API。Webデモとテストあり。**これはAI意味検索ではない**。
- **比較用 WinUI 3**: `experiments/gui-compare/winui3/overrides/` が元となるC#/XAML。`winui3/generated/` はユーザーWindows上で公式CLIにより作成された**ローカル生成物**。再生成・削除禁止。
- **比較用 Tauri**: `experiments/gui-compare/tauri-react/`。製品版採用ではない。比較用コードや測定履歴は残す。
- **実機テスト（ユーザー報告と提出ZIPによる）**: **Tauri・WinUI双方とも**GUI自動操作の事前チェック（検索/スクロール/詳細/タグ保存）と5種類の計測を完走した。CIのビルド・ヘッドレステスト成功だけでなくWindows GUI基本操作の通過実績がある。ただしこれは**比較試作**であり、サムネイル/読書ビューア/実ファイル索引の製品版動作を保証しない。
- **比較の暫定傾向**: WinUIのPrivate BytesがTauriより小さい傾向。CPU測定は操作回数差や検索/描画負荷の差があるため最終的な順位を確定していない。GPU/FPS/起動時間は測定していない。最適化競争は一旦打ち切る。
- **別PRに安全な索引エンジン**: PR #2はフォルダ/サブフォルダの読み取り専用走査、除外、リパースポイント回避、追加/変更/消失検知、一時DBテストなど。現在のGUI側とは**未統合**。
- **Windows実機で発見した重要な落とし穴**: WinUI ReleaseではJSONのリフレクション型シリアライザが無効な構成があり、比較試作は`BenchJson.cs`のJSON-DOMで回避。WinUIの管理`ObservableCollection<MediaRow>`を`ListView.ItemsSource`へ割当てた版で0x80004003系クラッシュ（`WinRT.ComWrappersSupport`）を確認し、`ListViewItem`ネイティブ行作成で回避。作品切替時の誤dirty判定、Tauriのスクロール位置/ページ遷移、テスト用UIA入力とデバウンスも修正した。**これらを製品版で無検証のまま再発させない。**
- **ユーザー側ツール**: Windows 11、Python 3.14系/.NET SDK 10/WinApp CLI/PowerShell 7、Node/Rustも比較キット用に確認済み。環境差は必ず自分で確認。旧作業フォルダ例`C:\AI\Aredoko`、比較用`C:\AI\Aredoko-gui-compare`。

## 実装開始前の未完成項目（最新状況は末尾）
- 製品版`WinUI 3`アプリ（製品用起動、見た目・画面遷移、ルート登録GUI、個人ライブラリの表示）は**未実装**。
- PR #2の実ファイル索引とPythonカタログ、WinUIの作品一覧は**未接続**。5万件のダミーGUIが動くことと、本物のフォルダが取り込めることは別。
- 実際の画像/動画/本のサムネイル、読書（画像フォルダ/ZIP/CBZ/PDF）、Komga、AI意味検索/タグ推定/OCR、オフラインドライブ追跡は**これから**。`EmbeddingGemma 2`は候補であり採用・モデル自動DLは未承認。
- セットアップ型配布、署名、インストーラー、動作確認済みのWinUI製品版Releaseは**未達**。
- 新しい実装をしないまま、旧`README.md`や`docs/status.md`を書き換えただけで「MVP完成」と報告しない。

## Codexが実際に取る次の手順
1. `git status`、現在branch/HEAD、`git log`、既存の未コミットファイルを調べる。意図しない上書き厳禁。ブランチは上記製品版ブランチを使用。
2. [Issue #4](https://github.com/jakymiku/Aredoko/issues/4)、`docs/spec.md`、`docs/api.md`、`docs/ui-audit.md`、比較用WinUIのXAML/C#、PR #2の索引実装を把握する。
3. 最初のコミットは**比較用とは別フォルダに、起動できるWinUI 3製品版の骨格＋ローカルAPI接続＋ログ/エラー表示**。Windows環境がなければ検証不能を明記し、実行環境に依存しないテストは先に作る。
4. 次に、**許可されたテスト用フォルダだけ**登録→PR #2の読み取り専用索引でスキャン→作品一覧/検索へ表示。スキャン進捗とキャンセルの実装は実測・設計に応じた範囲で。
5. その次に、作品の詳細/タグ/お気に入り/未確認の編集・保存・再起動後保持。旧APIの機能を退行させず、実ファイルを移動・削除・リネーム・変換しない。
6. Fluent UIを磨く。コンパクト検索/広い一覧/詳細編集/レスポンシブドロワーの一貫性、仮想化・アクセシビリティ・キーボード操作を見直す。
7. 各段階でテスト、コミット、残タスクを記録。製品版ブランチから**Draft PR**を作り、実機確認済み/未確認を分けて書く。**ユーザーの指示なくmainや既存PRをマージしない。**

## セキュリティ・データの境界
- 元メディアを**書換え・リネーム・削除・移動しない**。実ファイル走査はユーザーがGUIで指定した範囲のみ。キャッシュ/サムネイル/DBは別保存先へ。
- 購入作品、私物ファイル、個人パス、ローカルDB、アクセストークン、AIモデルをGitにコミットしない。ネット送信・モデルダウンロードなし。localhost外にサーバーを公開しない。
- Git管理下の比較試作や`generated`ディレクトリを壊さない。SDKやOS設定を勝手に変えたり、管理者権限の変更・常駐処理を無断導入しない。
- 不確実なAPI・WinUIの仕様は実コード/テスト・公式ドキュメントで確かめる。修正作業は**実装と検証**まで。曖昧な成功報告をしない。

## 参照先
[PR #1 UI試作](https://github.com/jakymiku/Aredoko/pull/1) · [PR #2 索引](https://github.com/jakymiku/Aredoko/pull/2) · [PR #3 GUI比較](https://github.com/jakymiku/Aredoko/pull/3) · [Issue #4 MVP実装指示](https://github.com/jakymiku/Aredoko/issues/4)

> Codexが作業を終える都度、この文書の「今どこまで進んだか」を更新する。単発チャットを唯一の作業記録にしない。

## 実装進捗 2026-10-11（Codex）
- 開始HEAD: `9c1b2aa` の製品版ブランチを確認。既存PRは未マージ。
- 公式インストール済みテンプレートから src/Aredoko.WinUI を新規作成。比較用generatedには触れていない。
- 最初の起動骨格にAPI接続と再試行/失敗表示を追加。テンプレートのNuGet参照を復元済みバージョンに固定。
- dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 --no-restore -v:q: 成功、警告0/エラー0。
- この時点ではGUI操作未検証。続いて読み取り専用索引との統合を実装中。

### 製品版の縦切り実装（実機検証済み）
- 起動骨格コミット: `acfb0c2`。以後、独立した製品DB/API、PR #2から必要な索引ファイルだけを移植、WinUI一覧/タイル/検索/詳細保存/フォルダ登録を追加。
- Python 28テスト成功。再起動時のSQLite接続リークをテストで検出して修正。元ファイル不変、永続化、消失/未接続、キャンセルのロールバック、再起動復旧、同意・トークンを検証。
- .NET Releaseの8チェック成功（リフレクションJSON無効、Unicode、dirty、古い検索応答）。WinUI Releaseビルド成功、SDK由来IL2104警告2件が残る。
- 開発用起動スクリプトと制約は docs/winui-mvp.md。Sandbox実行ファイルなしのためローカルWindowsで実機GUIテスト実施。検証用75ファイルの登録・同意・走査・一覧・検索・タグ/お気に入り保存・タイル切替・ページ移動・未保存の継続/破棄に成功。実スクリーンショットを確認。ランチャー経由の終了/再起動後にWinUI上で保存タグを確認。
- 起動骨格 `acfb0c2` に続く実装コミットはこの節を含むコミット（`git log -1`で確認）。PRは比較ブランチをbaseとする積み重ね方式。既存PRをマージせず、元デモ/API/比較generatedを保持。
- 手動コードレビュー実施: 再起動時のDB接続リーク、選択解除後の古い編集表示、ナビの二重破棄確認を修正。JSON/編集状態/API通信は純粋C#層に分離。画面調停はcode-behind、MVVM Toolkit未導入。
- 未検証/制約: 高DPI・ライトテーマ・狭幅の実機操作、フォルダピッカー自体の操作、スクリーンリーダー、1TB/数万件の実ファイル負荷、Native AOT、配布インストーラー。WinUI analyzer未導入なので解析未実施（無断依存追加なし）。SDK IL2104警告2件を抑制せず残している。日本語文言のリソース化は後続。
- 機能上の残り: フォルダを本単位にまとめる機能、サムネイル/読書、AI/OCR/Komga、ネイティブ一括編集、移動同定、複数棚の詳細仕様。現状はファイル単位。スキャン再開は最初からの原子的再走査。長時間走査中のメタデータ保存はSQLiteロックで失敗し得るので編集内容を保持して再試行する。
- 次の3手: (1) Draft PRをレビューしてこの基盤を固める、(2) 高DPI/狭幅/ピッカー/アクセシビリティと大規模スキャン中の応答性を検証・改善、(3) 画像フォルダ/ZIPを作品として扱う仕様とサムネイル縦切りを実装。

### 今回の提出
- 実装HEAD: `eb461f0`（起動骨格 `acfb0c2`）。この追記のみの後続コミットを最終HEADとしてpush。
- [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) 作成済み。base: `feat/gui-framework-comparison-20261010`。未マージ。
- テスト用GUIとバックエンドは検証終了後に停止。通常起動は `pwsh -File tools/start-winui.ps1`。

### 次の段階（開始）
- 開始HEAD `4de6c67`、作業ツリーcleanを確認。既存Draft PR #5の製品ブランチで続行。
- 画像/CBZ/ZIPのサムネイル縦切りと基盤の競合修正を実装中。追加依存なし。元素材は読み取りのみ、ZIP展開保存なし。私物スキャンなし。
- スキャン中の保存は即座に409を返して編集を保持する方針。サムネイルは読み取り8MiB、デコード16MP、同時2、256px、メモリキャッシュ64件を上限とする。

### 画像/CBZ/ZIPプレビューと競合修正（完了）
- バックエンド実装コミット: b71c30b。UI実装HEADは後続の提出記録に記載。既存Draft PR #5を更新し、base/Draftを維持。
- 登録済み画像とCBZ/ZIPの自然順先頭画像を一覧/タイル/詳細へ表示。源8MiB・16MP・同時2・256px・派生PNGのLRU64件。アーカイブ512MiB/中央ディレクトリ4MiB/1万エントリ/圧縮比200の境界。元メディア不変、展開保存なし。選択/キャンセルで古い応答を捨てる。
- スキャン中の更新/登録/除外変更は即409。GUIは編集を保持して終了後に再保存可能。検索/種類の最終条件再適用、ナビ/保存/未保存確認の調停、除外設定の既存値読込を修正。
- Python python -m unittest discover -s tests -q: **40テスト成功**。源不変・自然順・破損/過大/圧縮境界・差分再走査・リパース置換・同時上限・実スキャン中の拒否/再試行・HTTP保護を検証。
- C# dotnet run --project tests/Aredoko.Core.Tests -c Release: **13チェック成功**。LRUと画素上限/整数オーバーフローも追加。WinUI Releaseビルド成功、SDK IL2104警告2件は未解消で抑制なし。
- ローカルWindows実機: tools/test-preview-ui-local.ps1 成功。画像/CBZ表紙、タイル/詳細、破損代替、連続検索の最終条件、タグ保存、700pxの詳細開閉、元ファイルの全ハッシュ不変。初回は縮幅後に詳細へ戻れず失敗、詳細ボタンと常時見える閉じるボタンを追加して再実行成功。スクリーンショットも目視確認済み。
- 元の tools/test-winui-local.ps1 も新規DBで再実行成功（登録/走査/選択clean/タグ・お気に入り/検索/タイル/ページ/未保存の継続と破棄）。Sandbox実行ファイルなしのためローカル実機。私物スキャンなし。
- WinUIコードレビュー実施。Windows標準コーデックと純粋C#方針層を利用。WinUI analyzer未導入なので解析未実施。文言リソース化/MVVM拡張/高DPI/ライトテーマ/スクリーンリーダー/ピッカー本体/1TB実負荷/Native AOTは未検証。700pxドロワーは確認済み。
- 残り: ファイル単位の索引。画像フォルダの作品化、PDF/動画/音楽プレビュー、読書/OCR/Komga/AI、永続サムネイルキャッシュ、移動同定、配布は未実装。以前の節の「サムネイル未実装」「狭幅未検証」「保存タイムアウト」はこの追記で更新。
- AI検索時期の質問を受け、次はAI試作を優先する案: [ai-search-plan.md](ai-search-plan.md)。EmbeddingGemma 2は検索、Layaは意図/種類の補助。laya-mlxはMac向けなのでWindowsでは本家Layaを検証。依存/モデルはまだ導入していない。
- **次の3手:** (1) 分離AI環境・依存・モデルの具体的導入案を提示、明示承認後にGPU動作/VRAMを測る、(2) 数百〜数千件の名前/タグ/画像/表紙をEmbeddingGemma 2で索引化してWinUI意味検索と日本語評価を実装、(3) Laya多言語の意図/種類補助を比較評価し、数万件向け差分索引・中断再開を固める。

### プレビュー段階の提出
- 実装HEAD: 86eed50（バックエンド b71c30b）。この提出記録のみの後続コミットをpush。
- Draft PR #5: https://github.com/jakymiku/Aredoko/pull/5 。比較ブランチbaseを維持、未マージ。
- 検証用アプリを閉じ、ランチャー終了コード0と専用バックエンド停止を確認。AI環境/モデルは未導入。


### AI検索段階（2026-10-12開始）
- 開始HEAD 701730d、製品ブランチclean。Issue #4/AGENTS確認済み。
- ユーザーが専用AI環境・EmbeddingGemma2取得・生成素材GPU検証を明示承認。追加条件: 回線85Mbpsのため合計約6MB/s以下。ローカルCONNECTプロキシで全依存/モデルTLS受信を共通制限し、Xet/transfer高速経路を無効にして実行中。システムPython/ドライバーは変更しない。
- Python3.11既存、RTX4070Ti12GBを実機確認。固定CUDA版torch2.9.1、sentence-transformers6.1.0、transformers5.19.0、EmbeddingGemma2固定revisionで分離。AI索引/API/GUIを実装中、意味検索成功はまだ未確認。

### EmbeddingGemma2初回実装・実測（2026-10-12）
- 専用.venv-ai、固定モデルを承認済み手順で導入。依存/モデルのTLS受信は合計6,000,000bytes/sの共通上限。初回取得4,482,870,732TLS bytes/968.3秒（インストール時間含む）、追加torchvisionも同じ上限。システムPython/SDK/GPUドライバー変更なし。Layaは導入していない。
- stdlibカタログから分離Pythonプロセスでオフライン推論。SentenceTransformer text+vision、audio encoder無効、bf16 CUDA（CPUはfloat32）。入力は名前/タグ/相対名と、既存安全リーダーの画像/CBZ/ZIP先頭画像。PDF/動画/音楽の中身や本の本文は未解析。
- sibling AI SQLiteに768次元の正規化float32、text/cover別、固定モデルprofileとsource/metadata指紋を保存。初版は登録済みpresent対象の先頭最大2,000件。途中キャンセル/再起動中断状態/保存済み分再利用、更新済みタグや源の旧vector除外、現在の除外/お気に入り等フィルタを実装。AIキャッシュ破損時も通常検索は起動可能。
- GET /api/library/ai/status、POST index/cancel/search追加、既存token/Origin保護。実推論中の競合を拒否。WinUIにAI索引の進捗/作成/中断画面、AI意味検索とAI画像・表紙の切替を追加。空検索は通常一覧を表示。通常検索/API/Web比較は維持。
- 実モデルの生成17件検証成功: 日本語言い換え「傘が必要な暗い都会の景色」→雨の夜の街並み.wav（名前だけの入力）、cover専用で「青い画像」→image-01.png、「赤い表紙の本」→book-03.cbzが各1位。破損源はテキストのみ、元ファイル全ハッシュ不変。最終warm検索104–106ms、PyTorch peak allocated 931.8MiB（OS/プロセス全GPU消費ではない）。初回全検証40秒、warmファイルキャッシュの回では約12–16秒。個人ライブラリ/数千件への速度や精度は未実測。
- textとcoverのcosine最大値で混ぜた初回は色順位が名前側に偏った。coverのみの明示モードで上記色条件が改善。複合検索の順位補正・意図判定は未完成。意味検索は全候補を類似順で返し、適合閾値はまだ校正していない。
- Python **51テスト成功**、C# **13チェック成功**。新テストの既知vectorはAPI/永続化の検証であり精度証拠ではない。別途tools/test_ai_model.pyで実CUDAモデルを検証。Releaseビルド成功、SDK IL2104警告2件は引き続き未解消。analyzer追加なし。
- 元のnativeメタデータ回帰テストは新しい検索切替を加えた版でも成功。**AI GUI通しテストはFAIL/未完了**: 初回は非同期登録待ち不足、1回目再実行はフォルダ画面終了直後の待ち不足を修正。2回目再実行でGUIから17件の実CUDA索引作成が成功したが、テストCLIがAI意味検索という同じ表示名のListItem/Textを重複検出し停止。選択肢にModeLiteral/ModeSemantic/ModeVisualの専用AutomationIdを追加しビルド済みだが、その修正後のGUI再実行は未実施。winui-ui-testingスキルの最大2 fix-and-rerun cyclesに従い、再試行を打ち切って失敗を残す。検索画面のタグ保存/dirty keep/文字モード戻しについて新AI通しテスト成功は主張しない。
- AI GUI失敗時スクリーンショットとJSON結果を保存して目視確認（generated test artifacts、Git対象外）。源カバーと一覧/詳細/検索切替のUIを確認。Sandbox不在でローカルWindows。アプリ終了時に所有AIプロセス2つとAPIポートが消えることを確認済み（親終了監視）。
- **次の3手:** (1) 専用IDを使うAI GUI通しテストを次回再実行し、選択/保存/未保存保持/モード切替を完走、(2) 明示選択した小規模サンプルで日本語・同人誌表紙の精度と混合順位、2,000件の初回速度を評価、(3) Laya multilingualの具体的導入案を作り検索意図/種類補助を比較し、索引上限拡大/大規模応答性へ進む。今後のダウンロードも6MB/s上限を維持。

### AI初回実装の提出
- 実装HEAD: 8dd25ff。後続はこの提出記録のみ。Draft PR #5の同じbaseへpush、未マージ。
- 実CUDA検索・51 Pythonテスト・13 C#チェック・Releaseビルド成功。AI GUI通しテストは選択肢専用ID追加後の再実行待ち。
- 検証用GUI/API/所有AIワーカー停止確認。導入済みモデル/環境はローカルのみ、Git対象外。


### AI GUI通し検証の続行 2026-10-12（完了）
- 開始HEAD: `28c5923`、作業ツリーclean。Issue #4とAGENTSを再確認、既存Draft PR #5のブランチで続行。
- 検索メニューがmain/PopupHost双方から同じUIA peerを露出するためAutomationIdだけでも2件に一致。テストを実際のPopupHost HWNDに限定し、非同期出現と選択値を待つ方式に修正。アプリ本体の追加変更なし。
- 新しい生成素材用DBでnative AI通しテスト **PASS**。GUIから17件CUDA索引、日本語言い換え検索、結果選択/タグ保存、AI画面を開く際の未保存確認で「編集を続ける」が内容を保持、名前・タグ検索への復帰、画像・表紙の色検索/タイル表示まで完走。生成素材の全ハッシュ不変。3枚の実スクリーンショットを目視確認。
- Python51テスト、C#13チェック成功。Windows Release成功。初回buildのSDK IL2104警告2件は未解消、incremental build警告0を修正の証拠としない。analyzer未導入。
- アプリ終了後に所有モデルワーカー2つ/APIポートが停止、ランチャー終了0を確認。同じ検証DBを再起動してタグ/AIベクトル保持も **PASS**。GUI編集欄に保存タグを読戻し、再索引なしの表紙検索がCUDAで青い先頭候補を返した。再起動用2枚も実画像を目視確認。

- 再起動検証で待機ヘルパーのIsEnabledがCLIの文字列Falseをtruthyと扱う問題を検出してTrueとの比較に修正。初回モデル読込中の検証API競合はテスト側の待機不備。修正後の冷間起動で検証完走。tools/test-ai-ui-local.ps1 -RestartOnlyを追加。
- WinUIコードレビュー: 今回アプリのXAML/C#追加変更なし。既存AIダイアログの非同期調停/未保存保持とテストのwindow scope/value waitを手動確認。以前のcode-behind/リソース化/analyzer/AOT制約は残る。
- Layaの具体的な実験設計を docs/laya-evaluation.md に追加。Windows向けupstream PyTorch/multilingualを候補に、日本語意図判定と検索順位改善を別々に評価。confidence未校正のため閾値だけで自動フィルタしない。既存依存を固定し共有6MB/sを再利用。Layaの実インストール/ダウンロード/推論はまだ行っていない。
- **次の3手:** (1) Layaのモデルrevision/正確な容量と依存差分を確定して明示セットアップを用意、ローカル日本語分類/フォールバックを比較、(2) 明示選択したサンプルで意味/画像検索の順位・混合方式と最大2,000件の初回速度を評価、(3) 測定に基づき上限拡大/大規模索引の応答性、作品フォルダ単位/本文OCRを順に進める。現状は最大2,000件の開発プレビュー、数万件/1TB規模や実作品精度は未検証。

### AI GUI検証の提出
- 検証実装HEAD: `5d0f46a`（AI本体: `8dd25ff`）。後続はこの提出記録のみ。既存Draft PR #5の同じbaseへpush、未マージ。
- 実CUDAのGUI通し/再起動保持PASS、Python51テスト/C#13チェック成功、Windows Release成功。スクリーンショット5枚を目視確認。生成素材は全ハッシュ不変。Layaは評価設計のみ。
- 最終の検証アプリ/API/所有モデルワーカー停止、ランチャー終了0を確認。作業内容をPR説明へ反映。

### モデル交換対応（2026-10-12完了）
- 開始HEAD fa30b9c、clean/Issue #4/AGENTS確認。ユーザー要望によりEmbeddingGemma 2固定設定をモデルprofileへ分離。
- 起動時の設定ファイル選択、adapter/次元/入力能力/immutable revision/promptを検証し、異なるprofileの索引を別DBへ保存。既存標準profileは既存AI DBを再利用する設計。新しいモデルやLayaのダウンロードは行っていない。

- app/ai_profiles.py に検証済みJSON profile、app/ai_adapters.py に登録式loader、app/ai_vectors.py にモデル非依存vector契約を追加。EmbeddingGemma2 text/coverと汎用Sentence Transformers text-onlyを分離。既存標準profileはlegacyキー/DBを維持。他profileはID/revision/adapter/次元/入力/prompt/precision/前処理契約の識別で別DB。label/同一重みの配置変更のみは再利用。workerの実次元/完全profile照合、返却vector検証で混在を拒否。
- tools/start-winui.ps1 -AIProfile <JSON> / backend --ai-profileで再起動時に選択。切替時に新索引を作成、戻すと元の索引を再利用。GUI AI索引画面に選択モデルと対応入力を表示。text-onlyの画像モードは説明付きで失敗し、通常検索を維持。GUIモデルピッカー/稼働中切替は未実装。
- 明示setupにも-AIProfileを追加、既存pin/合計6MB/s制限を再利用。download途中の再開用source記録と別revisionの上書き防止。今回追加download/installなし。互換派生モデルは設定交換、異なる構造はadapter追加が必要。どんな非検閲モデルでも自動互換とは主張しない。
- Python **61テストPASS**、C# **13チェックPASS**、Windows Release PASS（既存SDK IL2104 2件）。不同次元/同次元別revisionの分離、旧profileへの復帰、prompt/能力/誤handshake/不正設定/取得中断を検証。汎用adapterはモック契約のみで別実モデル未検証。
- 既存ローカル重みを用いた実CUDA検証PASS: 標準text+vision → text-only/float32 → 標準へ戻し、索引分離と再構築なし再利用、2件の生成名前で日本語top hit/源hash不変を確認。これは2つの設定の試験であり、別重みや将来の派生モデルの精度証明ではない。
- native GUI PASS: explicit profileで生成17素材の新規索引/意味検索/表紙検索/保存/dirty keep/文字モード復帰。native legacy互換 PASS: 変更前の17件AI DBをそのまま開き、保存タグとCUDA表紙検索を再索引なしで使用。モデル表示を含む6枚の実スクリーンショットを目視確認。私物フォルダ未走査。
- WinUIコードレビュー: 新規XAML/API追加なし、TextBlockのモデル表示と非同期dialog調停を確認。JSON DOM/既存テーマ/AutomationId維持。WinUI analyzerなし、AOT/高DPI等の旧未検証項目は継続。
- 開発手順 docs/model-profiles.md、default sample config/ai-profiles/embeddinggemma-2.json。model/revision/次元/prompt変更が再索引条件、既存タグ/棚とは別管理。モデルmarkerは由来の宣言で全重みの暗号学的検証ではない。
- **次の3手:** (1) Layaもembeddingとは別の判断用interfaceに分離してoffline評価セット/明示setupを実装、(2) GUIのモデルprofile選択/不足モデル案内を追加、(3) 実サンプルで順位/索引速度を評価し2,000件を超える索引へ拡張。Laya実導入/別checkpoint取得はまだなし。モデル交換の基盤は完了。

- 最終互換性レビューでlegacy条件を現在のDEFAULT_PROFILEから切り離して歴史的設定へ固定。将来defaultモデル/前処理契約を変えても旧DBを誤再利用しない回帰テストを追加。前処理変更はVECTOR_CONTRACT更新が必要。

### モデル交換対応の提出
- 実装HEAD: `64b0af9`（本体 `6fa3e69`＋将来default変更の互換性固定）。後続はこの記録のみ。既存Draft PR #5へpush、未マージ。
- 61 Pythonテスト、13 C#チェック、WinUI Release、実GPU profile切替、新規GUI通し/旧索引GUI互換の検証成功。所有AIワーカー/API/GUIの終了確認、ランチャー終了0。追加モデル取得なし。
- 最新仕様/制約/次の3手は上記と docs/model-profiles.md。別実モデルや将来checkpointは未検証、Layaは次段階。


### Laya判断実験（2026-10-12開始）
- 開始HEAD 2ea24f0、clean/Issue #4/AGENTS確認、Draft PR #5継続。EmbeddingGemma 2公式カードはpost-training alignment/safety tuning/output moderationなし、学習データのフィルタありと明記。Aredokoの検索に内容拒否処理なし。
- 固定Laya 0.4.2/多言語revision 1720e3e3357cfe1e281542e223f8273b0890ca34、モデル678,201,614bytes+wheel380,522bytes。既存依存は条件を満たしpip check成功。ユーザーが新しいLaya取得/GPU検証を明示承認、共有6MB/s制限で取得中。
- 計画モード/既存依存不変更/--no-deps/固定hash/モデル整合性/中断再開/別revision拒否を実装、setup4テストPASS。embedding profileとは別の判断interface/owned offline worker/提案専用APIを実装中。現時点で実モデル精度・GUI提案は未検証。


### Laya独立判断provider・実GPU評価（2026-10-12完了）
- 実装HEADはこの節を含むコミットを後続の提出記録で確定する。製品ブランチ/既存Draft PR #5/baseを維持。既存WinUI/Web/embedding profile/旧索引/タグ・棚・手動検索を保持。
- app/search_intent.py にベクトル検索とは別の判断interface、app/laya_process.py / laya_worker.py にowned stdin/stdout worker、app/laya_config.py に固定ID/revision/package/全artifact SHA256。300文字・応答32,768文字・同時1・冷間60s/推論5s・失敗cooldown30s。推論はローカルのみ、HF offline+Python socket接続遮断、ネットワーク接続試行0。Laya 0.4.2 +固定多言語重みを明示承認後に取得。共有6,000,000bytes/s、679,568,032TLS bytes/180.14s。既存依存バージョン全不変/pip check成功、system/driver変更なし。
- tools/setup-laya.ps1 は無指定planのみ。-InstallAndDownloadで--no-deps/固定wheel hash/取得中断再開/別revision上書き拒否/モデル全hash検証。upstream tokenizerのリスト→mapping互換修正を許す場合も全original configを復元して固定hashと照合。最初の再起動実験first-01でその差を検知、修正してfirst-02/03成功。
- GET /api/library/intent/status、POST /api/library/intent/suggestに既存token/Origin保護。既定は無効、--laya-intent / tools/start-winui.ps1 -LayaIntentで開発者が明示起動。結果はexperimental提案のみ、手動source/kindをrequestedとして保持、検索本体は呼ばず種類で絞らない。missing/busy/timeout/malformedはnull提案で通常検索維持。GUI提案control・自動切替/フィルタは追加していない。
- 固定36件の架空日本語fixtureを追加（development24/held-out12）。実CUDA: 意図16/24+10/12=26/36、種類16/24+6/12=22/36、両方14/36。全36推論成功。プロンプト/閾値を結果に合わせて調整していない。漫画→archive、種類不明→archive等の誤分類を記録。held-outは評価済みであり、以後の調整で未見検証と再主張しない。
- 生成17素材/6検索の実EmbeddingGemma比較: Laya source提案を実験内だけで適用。赤表紙は期待順位2→1、青表紙は1→2、残り4は同順位。top1はmixedもLayaも5/6、全体改善を確認できずGUI採用条件未達。sourcehash不変、私物未走査。本文/OCR/音声動画内容は依然未解析。
- 実測first-03: 冷間first query13,133ms、残り35の中央値40.65ms/p95 43.78ms、PyTorch GPU peak allocated1,501MiB（driver全使用量ではない）。実interpreter Working Set1,965MiB/peak2,707MiB、Private Bytes5,766MiB（commitでresident RAMとは異なる）。first-02の3MiBはvenv redirector誤計測で無効。CPU/量子化/idle unload未検証。
- Windows venv redirector/実interpreterの2プロセスを区別し、workerでAPI親と直接OS親の両方を監視。tools/test_laya_api.py 実CUDA/HTTP PASS: cold読込中literal12.78ms、競合fallback5.76ms、異なる手動条件を保持、強制timeoutでrealworker終了/文字検索継続、os._exitによるowner突然終了でもrealworker終了。終了後CIMで全所有laya/embedding workerなしを確認。
- Python **76 tests PASS**（新setup4/intent11、既存61を保持）、C# **13 checks PASS**、WinUI Release PASS（旧SDK IL2104警告2件を抑制せず維持）。launcher構文PASS。コードレビュー: XAML/C#変更なし、JSON/非同期GUI/テーマ/AutomationIdの既存コードを維持。stdlib APIにtorch等をimportせず、全外部推論依存をworkerへ分離、有限probability/label/truncation/worker identity/provenance/busy/閉鎖・再起動境界を手動確認。analyzerなし、今回native GUI操作なし。既存GUI実機成功は前節の証拠を参照。
- ローカルignored evidence: data/laya-setup/result.json、data/laya-evaluation/first-03/result.json、api-01/result.json。docs/laya-evaluation.mdに手順・全結果・不採用理由と次の評価条件を記録。モデル/venv/DB/スクリーンショット/私物はcommit対象外。
- **次の3手:** (1) Laya質問/選択肢をdevelopment文で改善、選択肢順序/棄権と新しいheld-out集合を用意し、種類の推測は当面提案のみ、(2) text/cover混合順位を別途改善して実検索の総合利益を再測定、(3) GUIモデルprofile選択と明示サンプル/2,000件超の索引規模を進める。精度・順位・初回待ち・メモリを満たしてからGUI提案を追加する。
- 最終レビューで既存material条件を提案APIが拒否する不整合を修正。手動kindは既存TYPESを正として素材も保持し、判断ラベルの種類数で制限しない。質問/fixture/実測分類には変更なし。intent11テスト再実行PASS。


### Laya実験の提出
- 実装HEAD: 1e49592。後続はこの提出記録のみ。同じ製品ブランチとDraft PR #5へpush、base維持/未マージ。
- GPU推論・独立API/競合/timeout/親終了の検証PASS。Layaの日本語精度・検索順位の改善はGUI採用条件未達、提案APIは開発者の明示起動のみ。通常検索/GUIを保持。
- Python76/C#13/WinUI Release PASS、SDK IL2104 2件は既存のまま。質問/fixture変更なく最終manual material条件だけ修正・intent11再検証PASS。
- 検証用APIと所有Laya/EmbeddingGemmaプロセスは停止済み。モデルとvenvはローカルに保持、private/generatedデータはGit対象外。


### 日本語判定・混合順位改善（2026-10-12開始）
- 開始HEAD d7d7fb9/clean、Issue #4/AGENTS/PR #5 base確認。既存ローカル重みのみ使用、追加取得や私物走査なし。下着デザイン等の非露骨な架空素材検索を評価へ追加。内容による拒否処理は追加しない。
- v1質問を保ち、英語/短い日本語のv2候補と順序一致確認を実装中。判断契約hashに質問文と選択肢順序を含め、workerと照合。kind material候補を追加。旧24+新8のdevelopment32で候補を選び、旧held-out12はregressionに改称、新held-out24を選定後の検証に限定する。現時点で候補改善は未確認。

### 日本語判定・混合順位改善の完了（2026-10-12）
- 実装HEADは後続提出記録で確定。同じ製品feature/Draft PR #5/base維持。追加download/installなし、導入済み固定GPUモデルのみ、私物走査なし。内容拒否処理なし。
- AI意味検索の既定をmean-rrf（k60・cosine同点は平均順位・利用可能modalityで平均）へ変更。旧maxと明示text/cover cosineを維持し、launcher -AIRanking max/API rankingで復帰可能。候補filter/fingerprint/negative score維持。vector schema/profile/namespaceは変更せず再索引不要。応答ranking/score_kind追加、semantic_scoreは尺度が方式で異なりconfidenceではない。docs/ai-ranking.md。
- 実EmbeddingGemma CUDA/生成23素材14文×kind有無28条件: top1 max25→fusion27（旧6文12条件10→12、新8文16条件15→15）、悪化0。赤表紙期待CBZ2→1、青表紙1維持。「下着のデザインテンプレート」架空PSD名前・タグで両kind条件1位。ランジェリーひな形の未指定条件はPSD2位/関連PDF1位のまま。音声動画/PSD/PDF内部は依然読まず、個人ライブラリ精度/1TB速度未検証。sourcehash不変。
- Laya registry候補/質問・順序hash/判断契約v2、二順序推論とhead別棄権、cover＋未対応kind(audio/video/material)矛盾時intent棄権を実装。手動source/kind保持、確率閾値/自動検索なし。旧intent＋新日本語kindのhybridをdevelopment32で選定してから、新24を検証。旧held12はlegacy-regression、新24も以後未見扱い不可。
- 実Laya fresh24: v1 intent raw/effective17/17、kind11/12 → hybrid intent17/17、kind13/15。hybrid intent提示18/正解14、kind提示18/正解12、各6件棄権。warm81.53ms/cold12,937ms/PyTorch GPU peak1,506.02MiB/networkcalls0。種類は小幅改善、GUI gate未達。既定無効の-LayaIntent実験APIだけhybrid/order-checkを採用、GUI control/自動mode/filter追加なし。docs/laya-evaluation.md。
- 実HTTP新契約PASS: cold中literal10.42ms、競合5.98ms、manual保持/order証拠/timeout realworker停止/literal継続/os._exit親終了停止。モデル/依存変更なし。
- Python **90 tests PASS**、C# **13 checks PASS**、WinUI Release PASS（旧SDK IL2104 2件、抑制なし）、launcher/native-test構文PASS。新規native GUI実機PASS: generated17登録/索引CUDA/意味検索/保存/dirty keep/文字復帰/赤表紙fusion第一候補/max復帰/青coverタイル/sourcehash。4枚実スクリーンショット目視確認。Sandboxなしでlocal、今回再起動GUIは未実行（過去結果は前節）。検証用API/GUI/worker終了済み。
- WinUIコードレビュー: XAML/C#変更なし。既存async検索・stale判定・native ListView/60paging・JSON DOM・token/Origin・ThemeResource/AutomationIdを確認。追加計算は既存2,000上限内、Laya/torchは隔離workerのみ。WinUI analyzerなし、高DPI/Light/HighContrast/reader/ピッカー全体/AOT/配布は継続未検証。
- ignored証拠: data/ai-smoke/ranking-01、data/ai-ui/ranking-01/full、data/laya-evaluation/v2-dev-01/v2-hybrid-guard-dev-01/v2-heldout-01/api-v2-01。fake fixtureだけGit管理し、models/venv/DB/個人paths/PNG証拠はcommit対象外。
- **次の3手:** (1) GUIでモデルprofile選択と不足時案内を追加（既存旧索引互換/手動mode維持）、(2) ユーザー選択の実サンプルで混合順位と追加の未見日本語判定セットを評価（Layaは精度を満たすまでGUI提案保留）、(3) 2,000件超の索引を段階的checkpoint/増分・resource上限で拡張。本文/OCR/音声動画内容は別段階。

### 混合順位・Laya v2の提出
- 実装HEAD: e21c7aa。この後続コミットは提出記録のみ。同じfeatureブランチ/Draft PR #5へpushし、stacked base維持・未マージ。
- Python90/C#13/WinUI Release/実CUDA評価/実HTTP lifecycle/WinUI local生成17素材フローPASS、4枚目視確認。旧SDK IL2104 2件は継続。所有API/GUI/embedding/Laya worker停止を確認。
- mean-rrfはGUI意味検索の既定、maxへ復帰可・旧vector再利用。Layaは新未見24の精度不足でGUI採用保留、明示実験APIのみ。最新仕様と次の3手は直前節・docs/ai-ranking.md・docs/laya-evaluation.md。

### GPTチャットへの引継ぎ（2026-10-12）
- ユーザーがCodex残量節約のためGitHub Markdownへ進捗と再開手順を残すよう依頼。開始HEAD afb189c/clean、機能実装HEAD e21c7aa。今回は文書のみで新規機能/テスト再実行なし。
- docs/chat-handoff.mdをWinUI/AI実装済みの最新状態へ更新。古い「GUI未決定/AI未実装/Web監査が次」を置換。完了機能・90Python/13C#/Release/実GPU/native結果・Laya精度制約・未検証・主要ファイル・コマンド・そのまま貼れる依頼文を収録。
- 次の3手はGUI profile選択/不足案内、選択された実サンプルと新しい未見集合、2,000超の索引。チャットにPC/モデル/venv/スキルが転送されるとは扱わず、private repoアクセス不可時は実ソース共有が必要と明記。
- 同じfeature/Draft PR #5へ文書更新をpush。base/既存PR/未マージを維持。文書差分チェックのみ実行、前回の機能検証結果は再実行結果ではない。

### 2026-10-12: WinUIのモデルprofile選択（GPT引継ぎ作業）
- 開始HEAD `9190114`。変更は同じ `feat/winui3-production-mvp-20261011` と既存Draft PR #5に追加。従来のモデルprofile、旧default index、mean-rrf、Laya experimental API、個人データ不変更。
- `app/ai_settings.py`でGUI用ローカルprofile選択を検証・atomic保存し、起動時引数 `-AIProfile` を優先する。無効profileやモデル重み不足を表示し、**実行中のworker切替とモデルDLはしない**。選択肢は既定とignored `data/ai-profiles/*.json`。settingはユーザーの `%LOCALAPPDATA%/Aredoko/settings.json`（テスト時 `--ai-settings`）。
- `app/production_server.py` の認証済みprofile GET/POST経路と `src/Aredoko.WinUI/MainPage.xaml.cs` の「AI索引」ダイアログにprofileセレクタ、再起動案内、不足・無効モデルの警告を追加。既存のAPIと編集ロック・dirty制御は変更せず、AI使用不能でもliteral文字検索可能。
- `tests/test_ai_settings.py`と `.github/workflows/ai-profile-checks.yml`、`docs/model-profiles.md`を追加/更新。テストは一時フォルダ・架空DB、no download/ no user media。
- テスト状況: Windows CIによるPython AI単体テストとC# Releaseチェックを実施。WinUI Releaseでは.NET linkerの `NETSDK1102`（SelfContained未指定）が初回CIで出たため、CIビルド引数を `-p:SelfContained=true` に修正。**最終CI結果は対応するGitHub Actionsで確認**。GUI画面の実機操作・再起動後の実モデルロードは未検証。成功と混同しない。
- 次の3手: ①JakyのWindows実機で `tools/start-winui.ps1` からAI索引→候補を設定→終了/再起動してactive表示と旧索引復帰、text-only cover拒否、missing/invalidからliteral復帰を検証、②UIの説明文/高DPI・ライトテーマ・アクセシビリティを確認、③新しい実サンプル/未見データで順位を確認し2,000件上限拡張の設計を進める。

### チャット実装を実機へ戻す検証（2026-10-12開始）
- ローカル9190114/cleanからGitHubのf4273ffへfast-forwardし、チャット側のGUI profile選択/API設定/CI修正を全保持。Issue #4/AGENTS/PR #5を確認、base/Draft維持。
- 取り込んだ状態でPython96/C#13/WinUI Release（SelfContained=true）PASS、旧IL2104 2件。native確認は別作業。私物未走査・追加取得なし。
- 最初の画面probeはno-buildのPlatform指定がなく旧bin/Releaseを起動したためモデル欄がなく失敗。実機対象をPlatform=x64/SelfContained=trueへ揃えて最新dialogの表示・目視確認に成功。旧出力の結果を新コードの不具合・成功としない。
- launcherもCIと同じx64/self-contained指定へ揃え、テスト用-AISettingsを公開し個人AppDataを変更しない。profile候補のAutomationIdと人向けactiveモデル名、保存中の重複操作防止を追加中。実CUDA再起動/旧索引復帰/不足・破損のnative検証はこれから。

### GUI profile実装の実機確認・残件（2026-10-12）
- 実装HEADは後続提出記録で確定。f4273ffのチャット側実装を維持。launcher x64/SelfContainedをCI/実機と統一、-AISettingsで専用保存先を指定可能にした。候補AutomationId、人向けactiveラベル、保存中重複操作防止を追加。新規download/installなし、私物未走査。
- Python96/C#13/WinUI Release PASS、既存SDK IL2104 2件、launcher parse/diffチェックPASS。変更後ReleaseもPASS、初回フルと増分0警告は別で、IL2104解消とは主張しない。
- native baseline probeは古いbin出力のためモデル欄なしでFAIL。Platform指定して最新dialog表示を確認。新native harnessは01ウィンドウ生成待ちでFAIL→02はGUI17件CUDA索引/profile保存/no hot swap後に検索方法PopupHost検出FAIL→03も同じpopup問題でFAIL。window/popupの2回修正再実行後はwinui-ui-testing skillの上限により同じ通し再試行を止め、未達を報告した。GUI selector保存は確認、text-only/missing/invalid再起動画面と最新dirty通しは未完。probe旧/最新、02保存後/失敗、03失敗の計5枚を目視確認。成功/失敗の両証拠を含み、通し成功と誤称しない。
- 新 tools/test_profile_preference_gpu.py の独立実HTTP/CUDAはPASS。03でGUI保存したtest preference/生成17DBのコピーを使用してtext-only次回適用/別索引17/日本語hit/cover非対応、設定保存hot swapなし、default復帰の旧17vector＋cover再利用（再構築なし）、不足/invalidでAI unavailable/literal17、corrupt保存に対しexplicit -AIProfile優先、sourcehash不変。GUIの通し成功ではなくAPI/GPUの証拠。同じ既存EG2重みの2profileで、別checkpoint未検証。
- ignored証拠 data/ai-ui/profile-probe-01/dialog-latest.png、profile-picker-01/02/03（全FAIL/部分到達）とdata/ai-smoke/profile-preference-01/result.json（PASS）。生成profileは厳密に作成したファイルだけcleanup。個人AppData設定未変更、検証用GUI/API/worker終了確認。
- コードレビュー: JSON DOM/async・native ListView・dirty guard/Origin-token/immutable index keyを維持。新C# APIは既存ComboBoxItem/AutomationPropertiesのみ、テーマstyleは既存platform。analyzer/Sandboxなし、高DPI/Light/HC/reader/AOT/配布未検証。ScrollViewer APIを調べたが現サイズのdialogは表示できたため不要なレイアウト変更なし。表示リソース化は将来課題。
- **次の3手:** (1) 保存済みfailure-tree.jsonからPopupHostの公開境界を診断し、新ターンでnative全profile再起動/不足/破損/dirty回帰、(2) 小さいwindow/DPI/themeの警告表示を検証、(3) 明示選択の実サンプル・新未見分類集合と2,000超の索引へ。Layaは依然実験APIだけ。
