# Aredoko — Codex向け開発引継ぎ（2026-10-11）

> **最初に読む文書。** 2026-10-10時点の旧 `docs/status.md` / README には「GUI未決定」「ネイティブGUI未実装」という古い記述が残っている。現在の方針・分岐状況はこのファイルと [Issue #4](https://github.com/jakymiku/Aredoko/issues/4) を優先する。ファイル上の実装が異なるときは実際のコードを調査してから更新する。

## 今、何をしているのか
- 目的: **Aredoko**（Windows用のローカルメディアライブラリ検索・整理アプリ）の**製品版MVPをWinUI 3 + C#で新規実装する**。以前はGUI方式としてTauri + Reactも評価したが、2026-10-11にユーザー判断で**WinUI 3を先行採用**した。Tauriの比較コードは削除しない。
- 理由: Tauri/WinUI双方の実機GUI基本操作が完走し、WinUIのPrivate Bytes（アプリ本体関連プロセス）が一貫して小さかった。CPUは操作回数の差や負荷条件が統一できておらず優劣は未確定。安定性に関しては**WinUIだから無条件に安全と証明されたわけではない**。過去にWinUI試作固有のクラッシュも修正済み。
- GUI: Fluent 2 / Windows 11らしいモダンで密度の高いUI。左ナビ・上部検索・中央の大きい作品一覧・右の詳細/タグ編集。狭い画面は詳細をドロワーに。Mica等の見栄えは安定性・操作性を損なわない範囲。
- 開発実務: **製品用の最初の縦切り実装と実機GUI検証まで完了**。登録・走査・検索・整理・再起動保持が動く。Issue #4全体の完成宣言ではない。最新結果と残課題は末尾、起動手順は [winui-mvp.md](winui-mvp.md)。

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
