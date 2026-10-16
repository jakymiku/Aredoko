# 2026-10-16 実利用フィードバックと対応表

ユーザーが通常ライブラリで試した22件を保持する。これは受け入れ条件を含む計画であり、コード/検証結果の記録なしに完了へ変更しない。簡潔なWinUI 3・全機能保持・元メディア不変を守る。新モデル/依存/私物scanを無断追加しない。

| ID | 要求 | 受け入れ条件 | 状態 |
|---|---|---|---|
| F01 | wheelページ送り・方向設定 | 原寸fitで画像/本の前後送り、上下の進行方向を保存。zoom中のスクロールを妨げない | 実装・画像実入力PASS／reader・反転適用未検証 |
| F02 | 検索方法の名称 | 文字一致・見た目・名前/タグの意味・両方が区別でき、「豆」の例と本文/動画未解析が必要時に分かる | 実装・native検索63 PASS |
| F03 | 登録の追加同意checkbox | フォルダ選択＋登録を明示同意とし、重複checkboxをなくす。HTTP consent検査は保持 | 実装・HTTP PASS／GUI登録未検証 |
| F04 | サブフォルダを含める選択 | 既存rootは従来通り含む。直下のみのscan/再登録/除外/本の根拠も検証 | 実装・backend9件内でPASS／GUI未検証 |
| F05 | フォルダsingle/double click | 行clickで設定、doubleでAredoko内のフォルダを開く。checkbox/ボタン操作を誤解釈しない | 実装・native未検証 |
| F06 | 閲覧履歴と未確認 | ユーザー確定：左ナビを履歴へ。未確認は検索条件へ残す。閲覧成功を記録しrestart後も保持 | 実装・backend/Core・画像実履歴PASS |
| F07 | GIF/WebP/APNGアニメ表示 | 実フレーム/時間/ループを再生し、終了時に資源を解放。単一静止画をアニメ成功と呼ばない | 未実装 |
| F08 | アニメ画像のAI索引 | 表示と別に代表フレーム入力・版/前処理を保存、生成アニメで索引と検索を確認 | 未実装 |
| F09 | Explorer/既定アプリ | 右clickした正確な登録アイテムを開く。任意外部path/URLを実行しない | 実装・Coreパス境界PASS／shell実起動未検証 |
| F10 | 詳細にproperties | 種類・容量・更新日時・登録先/相対path。folder tokenを日時と誤表示しない | 実装・Core PASS／native未検証 |
| F11 | 54,802KB級APNG | 一律8MiB capの単純解除を避け、bounded frame decode/転送・取消で生成大画像を確認 | 未実装 |
| F12 | 動画の内容AI索引 | 時刻付き代表frame→embedding→動画集約→該当時刻へ。名前/タグ検索と区別 | 未実装 |
| F13 | 左下の設定 | ツールを「設定」へ。AI準備/関連語/ビューワー設定等をここから利用 | 実装・Light設定保存PASS／管理遷移未検証 |
| F14 | mouse進む/戻る | ユーザー確定：ビューワー内の画像/ページ送り。メイン画面の履歴移動ではない | 実装・画像X1/X2 PASS／reader未検証 |
| F15 | 動画double click | list/gridの動画thumbnailからnative playerへ。元の検索/編集を保持 | 実装・native入口未検証 |
| F16 | 動画canvas click | 映像clickで再生/一時停止、seek/音量/操作ボタンに干渉しない | 実装・動画native PASS |
| F17 | seek thumbnail点滅 | 同じ時刻を再要求せず、次frame準備中も前frameを消して点滅しない | 実装・動画native PASS／高速連続移動の追加確認は残る |
| F18 | 右側の音量slider | pointer/keyboardで0〜100、mute/既存±操作と同期、狭幅で重ならない | 実装・動画native PASS |
| F19 | 動画右click | 全種類に共通open menu、画像類似と動画未索引を混同しない | 実装・native未検証 |
| F20 | 分かる再登録 | 元の設定を維持して登録を復元、成功/失敗を表示、自動scanはしない | 実装・backend保持PASS／GUI未検証 |
| F21 | 解除済みrootのDB完全削除 | 元ファイルを残し、確認の上で関連metadata/履歴/索引を削除。ID再利用で古いscopeが別rootへ向かない | 未実装 |
| F22 | folder drag/drop | 明示したfolderだけを登録候補へ。dropだけで無断scanや複数root登録を開始しない | 実装・native drop未検証 |

## 確定した意味

- wheelは既定で下＝次、設定で反転可能。zoom中/修飾キー押下中は既存の拡大・scrollを優先する。
- 「未確認」はreviewed=falseの整理用filterとして維持。閲覧履歴は読書位置とは別に画像/本/動画を実際に開けた時点で保存する。
- 「フォルダを開く」はAredoko内の内容一覧。「エクスプローラーで表示」はWindowsの元ファイル位置を開く別の操作。
- 現行の画像AIは画像/表紙の見た目、文章AIは名前/タグの意味。映像・音声本文/本の本文の理解を実装済みと見せない。

最新の実装/検証は[codex-handoff.md](codex-handoff.md)と[chat-handoff.md](chat-handoff.md)。現段階では上表の未実装を実装済みと扱わない。

## 検証の区切り

実装とnative受け入れを分けた。Python393件実行（390 PASS/3 platform SKIP）、Core350 PASS、Release0警告/0error。独立native動画92/検索mode63/画像実wheel・X1/X2・閲覧履歴16 PASS、計28 PNG全目視。フォルダ統合バッチは設定/未確認まで部分確認後、harnessのcollapse/gone待機でFAILED。修正は保存、スキルの2 fix/rerun上限により再実行せず次回へ。全22件完了とはしない。コマンド・証拠と未検証一覧は最新handoff。

## コミット前コードレビュー

WinUI design/code-reviewの観点で、入力のzoom/操作部優先、async eventと取消、source_id捕捉、テーマ/AutomationId、bounded thumbnail cache、reflection-free JSON、root外path/URI/ADS/リンク拒否を点検。ドライブ直下rootの包含判定と履歴の現在除外ルールを補正しテスト済み。新規MVVM/ObservableCollection移行やAOT対応を今回の達成として扱わない。未導入WinUIAnalyzerは未実行。既存日本語文字列のresw化は別作業とし、今回の機能を削って整形しない。
