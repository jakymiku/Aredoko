# Aredoko — ChatGPT引き継ぎ

## 最初に貼る依頼
Aredokoの開発を引き継いでください。添付ZIPまたはアクセス可能な https://github.com/jakymiku/Aredoko を読み、実装済みと未実装を区別してください。最初の作業は、現行Web試作のUI監査と、コンパクトな検索バー・広い一覧・右側の詳細/タグ編集パネルを持つ操作試作への改善です。既存の検索・編集・保存機能を維持し、必要なテストと画面確認を行ってください。編集できる環境なら変更ファイルを作成し、実行環境がなければ適用可能な差分または変更ファイルを返してください。実行していないテストを成功と報告しないでください。スキルが利用可能なら目的に合うものを読み、利用不能なら下記の開発ルールに従ってください。

## アクセスに関する前提
- リポジトリは非公開。URLだけでは読めない場合、添付のコードZIPを使う。
- 元のPCの C:\AI\Aredoko や http://127.0.0.1:8765 は別環境から自動的にアクセスできない。
- PCのスキルはチャットへ自動転送される前提にしない。
- この資料は開始時点のスナップショット。以降は実際のコードと最新docsを優先する。
- Windows GUI/GPUの実測には対応する実行環境が必要。環境がなければその部分は未検証と記載する。

## ユーザーの目的・決定事項
複数フォルダの画像・動画・音楽・素材・購入同人誌を、曖昧検索・関連表示・仮想棚で探し直せるWindowsアプリ。
数万ファイル・1TB以上。Core i7-13700K / RAM32GB / RTX4070Ti 12GB。
本は画像フォルダ・ZIP・CBZが混在し、PDFは少数。Komgaは読む時だけ起動する。
元ファイルの移動を強制しない。元データを変更せず、タグや棚をアプリ側で持つ。
移動/変換後も整理情報を引き継ぐ設計。実ファイルの対象フォルダは未指定。
ローカル処理が基本。ツール/OSS検索は別企画。
GUIはTauriとWinUI 3を比較予定で未決定。Pythonを共通バックエンドとする。

## 実装済みと未実装
Python標準ライブラリ+SQLite+HTML/CSS/JavaScriptのWeb試作あり。2026-10-10の改修で、左ナビ/中央のコンパクトな検索と広い一覧/右詳細タグ編集パネルを実装。画面の空状態・エラー状態・未保存確認も追加。
架空データ5万件、60件ずつ一覧、タイトル/タグの文字検索、種類別表示、タグ/単一棚/お気に入り/確認済みの単体・一括編集、保存。
AI検索、実ファイル走査、読書ビューア、Komga接続、移動検出、複数棚、解析キューは未実装。
React/Tauri/WinUI本体も未実装。HallmarkとWeb Interface Guidelinesを参照したWeb UIソース監査は `docs/ui-audit.md` に記録。WinUI正式監査は未完了。

## スキルの扱い
このPCには以下を導入済み。ただし添付ZIPにスキル本体は含めていない。
- Hallmark: https://github.com/Nutlope/hallmark （見た目・構造の監査と改善）
- Web Design Guidelines: https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines （Webの操作性・アクセシビリティ）
- WinUI: https://github.com/microsoft/winappCli/tree/main/plugins/winui/agent-plugin/skills （setup/design/dev-workflow/code-review/ui-testing/packaging）
利用可能ならSKILL.mdと必要な参照ファイルを読む。WinUIスキルはWinUI実装時に適用する。
以下はAredoko向けの引き継ぎルールであり、スキル全文や正式監査の代わりではない。

## 環境に依存しない開発ルール
- 一覧・検索・連続整理を優先。大きな宣伝見出しや意味のない英語装飾を減らす。
- 既存機能とデータを保持し、実装範囲を小さく区切る。
- 色・文字・余白を一貫させる。日本語を読みやすく、Windows拡大表示でも操作できる設計にする。
- キーボード操作、明確なラベル、フォーカス、読み込み中、空結果、エラー、未保存編集の扱いを確認する。
- 画面に必要な件数と縮小画像だけを読み込み、キャッシュと先読みに上限を持たせる。
- ファイルや購入作品をGitや外部サービスに送らない。試作は架空データを使用する。
- DB・モデル・キャッシュ・認証情報はGit対象外にする。
- AI類似度を正解率と呼ばない。文字検索を意味検索として見せない。
- GUI性能は同一データ/画像/先読み条件で比較し、関連プロセス全体を測る。推測値を実測として報告しない。

## 実行・検証
起動: python app/server.py --open
Windows: start-demo.cmd
テスト: python -m unittest discover -s tests -v
JS構文: node --check web/app.js
UIテスト: デモ起動中、PlaywrightとEdgeが使える環境で node tools/check-ui.cjs
改修後はバックエンド4件・JS構文・Chromiumでの操作検証（ローカルAPIへの橋渡し）が成功。Edge/Node Playwrightの実HTTP E2Eはこの環境では未検証。`docs/ui-audit.md` を参照。

## 資料の順番
README.md → docs/spec.md → docs/status.md → docs/gui-comparison.md → docs/api.md → docs/development-skills.md

## 次の作業
1. 改修後のWeb UIをWindows/Edgeで直接起動して検証・微調整する。
2. WinUI/Tauriの開発環境を整え、共通APIで比較試作。
3. 使用許可された少量の実データで閲覧と検索精度を検証。
4. GUI方式を決めて段階的なインデックスとAI検索を実装。
