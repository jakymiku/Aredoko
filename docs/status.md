> **最新（2026-10-14、追加確認は一部残る）**：フォルダ/棚/解除・再登録/AI候補のLight/Dark GUIは新batch46checks PASS。初期棚の表示・再登録の除外・一括適用checkbox状態を修正。追加batchは補助HWND参照で停止し、初期棚の修正後表示まで確認。Python14/Core107/Release PASS。右クリック設定と追加復元条件は実機未完了。自動区切りは正解率ではありません。[使い方と検証](folder-search-and-ai-candidates.md)。

> **最新（2026-10-13、Windows部分確認）**：Hark追加分を維持し、拒否POST応答/非object JSONエラー/辞書busyと狭幅/検索理由row表示/古いAppX deps再使用を修正。全Python211/Core97/Release/windowless dependency probe PASS。native03は全体FAIL26checks/5PNG全目視、Lightの辞書・理由・partialまで。読書/Dark/pickerは未確認。[Windows確認](windows-hark-followup.md)/[引継ぎ](codex-handoff.md)。CI起動0回・Draft未マージ。以下は履歴。

---

> **最新の状況（2026-10-13）**：詳細パネルを利用可能な高さへ拡張、保存/状態を固定。成功/失敗後の編集focus復帰・retryと保存中に選んだQuery focus維持を確認。editor-native-03 93 checks/実入力50/skip0/12PNG全目視・正常close2、Core35/Python6/最終Release PASS。resize時の自動open保持、高DPI/Contrast/読み上げは残作業。詳細は[詳細とfocus](editor-layout.md)/[引継ぎ](codex-handoff.md)。CI manual-only・Draft未マージ。以下は履歴。

---

> **最新の状況（2026-10-13、一部確認）**：詳細内Esc/未保存確認と一覧focus復帰、編集欄の明示Nameを追加。Core35/Python6/最終Release PASS。native03は全体FAIL、50 recorded checks/26実入力/4PNG全目視/正常close2。Light操作は完走、DarkはUIA peer失効で未到達が残る。高DPI/Contrast/読み上げは未確認。詳細は[キーボード検証](keyboard-accessibility.md)/[引継ぎ](codex-handoff.md)。CI manual-only・Draft未マージ。以下は履歴。

---

> **最新の状況（2026-10-13）**：検索方法を実CUDAで検証。画像対応 75 checks・要求19件・document/image/query=2/2/15 / 文章専用 75 checks・要求19件・document/image/query=2/0/13。各6PNG全目視・正常close2・所有handles6全終了。文章専用profileのcover非対応案内をAI文章へ訂正し、保存索引再利用も確認。Core35・Python23・Release PASS。生成3PNGでの接続検証で検索精度の評価ではない。詳細は[実GPU検索方法](search-methods-gpu.md)/[引継ぎ](codex-handoff.md)。CI manual-only・Draft未マージ。以下は履歴。

---

> **最新の状況（2026-10-13）**：GUIに「AI文章」単独検索を追加し混合/画像と根拠説明で選択。Core35・Python scope12/retrieval13・Release PASS。native03 65 checks/6 PNG全目視/正常close2、生成素材とCPU契約encoderで要求・条件・dirty rollbackを確認（実GPU/品質は前回v2の別証拠）。詳細は[検索方法](search-methods.md)/[引継ぎ](codex-handoff.md)。CI manual-only・Draft未マージ。以下は履歴。

---

> **最新の状況（2026-10-13）**：前回の検索可能なroot pickerに続き、新規30素材/30問を推論前に固定してtext/pixel根拠別に評価。実CUDA runtime258checks PASS、155Python/Core29/Release PASS。metadata text12/12・混合10/12、pixel cover6/6・混合0/6（種類なし）。これは生成入力の観測で製品quality gateではない。モデル/順位/GUIは今回未変更。次はtext-onlyの明示GUI選択。詳細は[新規固定評価](search-quality-holdout.md) / [引継ぎ](codex-handoff.md)。CI manual-only・Draft未マージ。以下は履歴。

---

# 作業状況 — 2026-10-10

## 完了
- Web試作のUIを「左ナビ/中央一覧/右詳細タグ編集」へ変更。検索バー・カード密度・狭幅パネル・未保存確認・エラー/空状態を改善。
- HallmarkおよびWeb Interface Guidelinesを参照したソース監査結果を `docs/ui-audit.md` に記録。
- 名称・仕様・GUI比較条件を文書化。
- 非公開GitHubリポジトリ jakymiku/Aredoko に接続・pushを確認。
- Python標準ライブラリでSQLiteカタログとローカルHTTP APIを実装。
- 5万件の架空データ、60件単位のページ表示、文字検索、種別フィルタ。
- 単体・一括のタグ/棚/お気に入り/確認済み編集と永続化。
- Webの操作試作を作成。HTML/CSS/JavaScriptによる試作でありReact/Tauriは未導入。

## 検証済み
- **今回の改修後:** Pythonバックエンド6件、JS構文検査、Chromiumによる描画・操作検証（ローカルAPIへの橋渡し利用）が成功。詳細は `docs/ui-audit.md`。
- **今回の環境では未検証:** Edgeからの実HTTP画面遷移/Node Playwright E2E、WinUI/Tauri/Windows実機。

### 前回の検証履歴（改修前）
- バックエンド4テスト: ページ分割と検索、再起動後の保持、不正な一括変更の原子性、HTTP更新のセッション検証。
- JavaScript構文検査。
- Edgeヘッドレスで一覧・本フィルタ・文字検索・タグ編集・再読込後の保持・ページ送り・60件選択を確認。
- 1440x1050と540x900のスクリーンショットを生成、狭幅で横はみ出しがないことを検証。
- UI操作中にJavaScriptエラーなし。

## 追加修正
- 通信失敗時に古いカードを操作できないよう、一覧と選択をクリアし再試行を表示。
- 更新APIが成功した場合は、その後の一覧再取得失敗を「保存失敗」と誤表示しない。
- 検索条件・値検証の回帰テスト2件を追加（計6件成功）。
- ChromiumでローカルAPIに橋渡しした保存・再読込・狭幅パネルの検証を再実施。
- GitHub側は `feat/compact-library-ui-20261010` ブランチでレビュー待ち。`main` には未反映。

## 追加のUI自動検証（PR #1 更新）
- `node tools/run-ui-check.cjs` を追加。OS一時ディレクトリに検証用SQLiteを生成し、`--db` 指定・ポート自動割り当てでサーバーを起動してEdgeのE2Eを実施する。終了時は一時DBを破棄する。
- CIにWindows Edgeでの実HTTP画面操作ジョブを追加。検索、単体保存、再読込、一括編集警告、未保存確認、画面幅と通信エラーの復帰を自動確認する。
- ローカルPython6件とJS構文検査が成功。GitHub Actions run #28（Windows）の `tests` および `browser-smoke` 両ジョブが成功した。

## 未完了
AI検索、実ファイル登録、ZIP/CBZ読書、Komga連携、移動検出、複数棚、解析キュー。
WinUI 3とTauriのネイティブアプリ試作・性能比較は未実施。
.NET SDKは一覧に出ず、cargoはPATH上に見つからない。Visual Studio 2022 Communityは存在するが必要なワークロードは未確認。

## 次に進める順番
1. 更新したUIをWindows上のEdgeで `node tools/check-ui.cjs` により再検証し、画面の方向性を確認する。実データの読み取り対象フォルダはユーザーの許可を得て指定する。
2. 比較用SDK/ビルド環境を準備し、同じAPIを使う両GUIを作る。
3. 共通サムネイルと読書データを追加してGUI性能を比較する。
4. 採用GUIにフォルダ登録と段階的インデックスを接続する。
5. 少量の実データでEmbeddingGemma 2の精度/速度を確認してAI検索を接続する。

## 制約
今の検索は部分文字列検索。タグで一致するため、意味検索と誤解しない表示を設けた。
5万件を表示できることは、数万の実ファイルや百万ページの解析性能を保証しない。
生成SVGは操作確認用で、実画像の展開負荷と同等ではない。
