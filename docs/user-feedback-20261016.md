# 2026-10-16 実利用フィードバックと対応表

ユーザーが通常ライブラリで試した22件を保持する。これは受け入れ条件を含む計画であり、コード/検証結果の記録なしに完了へ変更しない。簡潔なWinUI 3・全機能保持・元メディア不変を守る。新モデル/依存/私物scanを無断追加しない。

| ID | 要求 | 受け入れ条件 | 状態 |
|---|---|---|---|
| F01 | wheelページ送り・方向設定 | 原寸fitで画像/本の前後送り、上下の進行方向を保存。zoom中のスクロールを妨げない | 完了（画像・reader実wheel・Light/Dark反転設定適用PASS） |
| F02 | 検索方法の名称 | 文字一致・見た目・名前/タグの意味・両方が区別でき、「豆」の例と本文/動画未解析が必要時に分かる | 完了（native検索63 PASS） |
| F03 | 登録の追加同意checkbox | フォルダ選択＋登録を明示同意とし、重複checkboxをなくす。HTTP consent検査は保持 | 完了（HTTP・GUI登録PASS） |
| F04 | サブフォルダを含める選択 | 既存rootは従来通り含む。直下のみのscan/再登録/除外/本の根拠も検証 | 完了（backend9件＋GUI `RootRecursive`表示/登録PASS） |
| F05 | フォルダsingle/double click | 行clickで設定、doubleでAredoko内のフォルダを開く。checkbox/ボタン操作を誤解釈しない | 完了（native single/double click PASS） |
| F06 | 閲覧履歴と未確認 | ユーザー確定：左ナビを履歴へ。未確認は検索条件へ残す。閲覧成功を記録しrestart後も保持 | 完了（backend/Core・画像/reader実履歴・未確認切替PASS） |
| F07 | GIF/WebP/APNGアニメ表示 | 実フレーム/時間/ループを再生し、終了時に資源を解放。単一静止画をアニメ成功と呼ばない | 完了（`app/image_animations.py`・`ImageViewerView`・native `feedback-animation-20261016-01` 16 checks PASS） |
| F08 | アニメ画像のAI索引 | 表示と別に代表フレーム入力・版/前処理を保存、生成アニメで索引と検索を確認 | 完了（`representative_frame_index`・`read_cover`/`tag_input`・PythonテストPASS） |
| F09 | Explorer/既定アプリ | 右clickした正確な登録アイテムを開く。任意外部path/URLを実行しない | 実装・Coreパス境界＋nativeメニュー項目確認PASS（外部Explorer/既定アプリの自動起動は安全上未実行） |
| F10 | 詳細にproperties | 種類・容量・更新日時・登録先/相対path。folder tokenを日時と誤表示しない | 完了（Core・native Light/Dark `FileProperties` PASS） |
| F11 | 54,802KB級APNG | 一律8MiB capの単純解除を避け、bounded frame decode/転送・取消で生成大画像を確認 | 完了（元64MiB/16MP/64frame・転送8MiB上限で54,802KB APNGのサムネイル/アニメーション再生PASS） |
| F12 | 動画の内容AI索引 | 時刻付き代表frame→embedding→動画集約→該当時刻へ。名前/タグ検索と区別 | 未実装 |
| F13 | 左下の設定 | ツールを「設定」へ。AI準備/関連語/ビューワー設定等をここから利用 | 完了（native Light/Dark 設定保存・AI準備・関連語遷移PASS） |
| F14 | mouse進む/戻る | ユーザー確定：ビューワー内の画像/ページ送り。メイン画面の履歴移動ではない | 完了（画像・reader実X1/X2 Light/Dark PASS） |
| F15 | 動画double click | list/gridの動画thumbnailからnative playerへ。元の検索/編集を保持 | 完了（native list/detail double-click・未保存draft保持PASS） |
| F16 | 動画canvas click | 映像clickで再生/一時停止、seek/音量/操作ボタンに干渉しない | 完了（動画native PASS） |
| F17 | seek thumbnail点滅 | 同じ時刻を再要求せず、次frame準備中も前frameを消して点滅しない | 完了（動画native PASS／高速連続移動の追加確認は残る） |
| F18 | 右側の音量slider | pointer/keyboardで0〜100、mute/既存±操作と同期、狭幅で重ならない | 完了（動画native PASS） |
| F19 | 動画右click | 全種類に共通open menu、画像類似と動画未索引を混同しない | 完了（動画native右clickメニュー表示・`FindSimilar`非表示PASS） |
| F20 | 分かる再登録 | 元の設定を維持して登録を復元、成功/失敗を表示、自動scanはしない | 完了（backend保持・native `RestoreFolder`ワンクリック復元PASS） |
| F21 | 解除済みrootのDB完全削除 | 元ファイルを残し、確認の上で関連metadata/履歴/索引を削除。ID再利用で古いscopeが別rootへ向かない | 完了（`POST /api/library/roots/purge`・`library_root_seq`・Python/Core・native確認ダイアログ取消/実行PASS） |
| F22 | folder drag/drop | 明示したfolderだけを登録候補へ。dropだけで無断scanや複数root登録を開始しない | 実装済み（OSファイルドラッグ合成は自動化対象外のためnative dropは未検証） |

## 確定した意味

- wheelは既定で下＝次、設定で反転可能。zoom中/修飾キー押下中は既存の拡大・scrollを優先する。
- 「未確認」はreviewed=falseの整理用filterとして維持。閲覧履歴は読書位置とは別に画像/本/動画を実際に開けた時点で保存する。
- 「フォルダを開く」はAredoko内の内容一覧。「エクスプローラーで表示」はWindowsの元ファイル位置を開く別の操作。
- 現行の画像AIは画像/表紙の見た目、文章AIは名前/タグの意味。映像・音声本文/本の本文の理解を実装済みと見せない。

最新の実装/検証は[codex-handoff.md](codex-handoff.md)と[chat-handoff.md](chat-handoff.md)。現段階では上表の未実装を実装済みと扱わない。

## 検証の区切り

実装とnative受け入れを分けた。Python **395件実行（392 PASS / 3 platform SKIP、185.899秒）**、Core **351 PASS**、Release **0警告 / 0 error**。
- フォルダ・読書・設定・DB完全削除の統合バッチ（`data/ai-ui/feedback-antigravity-20261016-13`）：**98 checks PASS / PNG 19枚全目視PASS / graceful close 2**（Light/Dark 設定保存・反転wheel適用・reader X1/X2・閲覧履歴記録・`FileProperties`・タグレビュー・旧token GUI rescan・フォルダsingle/double click・直接再登録・解除済みrootのDB完全削除の確認ダイアログ取消/実行を確認）。
- 動画再生・double-click入口・共通右クリックメニューの統合バッチ（`data/ai-ui/feedback-video-20261016-04`）：**102 checks PASS / keys 52 / PNG 22枚目視PASS**（一覧/詳細サムネイルdouble-clickからの動画起動と未保存draft保持、動画右クリックの「エクスプローラーで表示」「既定のアプリで開く」表示と画像類似項目の非表示を確認）。
- アニメーション画像（GIF/WebP/APNG）・54,802KB級APNGのネイティブ再生バッチ（`data/ai-ui/feedback-animation-20261016-01`）：**16 checks PASS / keys 4 / PNG 4枚全目視PASS**（一覧サムネイル表示、画像ビューアでの複数フレーム実再生・54,802KB APNGのbounded転送再生・Light/Dark・通常/狭幅・閉じた際のタイマー/フレーム解放を確認）。
- 既存の検索モード63 checks、画像実wheel/X1/X2＋閲覧履歴16 checksも維持。
- F12（動画内容の時間付きAI索引）は未実装。F09の外部プロセス（Explorer/既定アプリ）実起動とF22のOSドラッグ＆ドロップ注入は自動テストの安全境界により未実行。コマンド・証拠と残作業は最新handoff。

## コミット前コードレビュー

WinUI design/code-reviewの観点で、入力のzoom/操作部優先、async eventと取消、source_id捕捉、テーマ/AutomationId、bounded thumbnail cache、reflection-free JSON、root外path/URI/ADS/リンク拒否を点検。ドライブ直下rootの包含判定と履歴の現在除外ルールを補正しテスト済み。新規MVVM/ObservableCollection移行やAOT対応を今回の達成として扱わない。未導入WinUIAnalyzerは未実行。既存日本語文字列のresw化は別作業とし、今回の機能を削って整形しない。
