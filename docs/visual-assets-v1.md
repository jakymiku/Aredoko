# ビジュアル素材v1の導入（2026-10-25）

採用：銀髪・青い瞳・紺の魔女帽子のSD魔法使いが本棚の光る本を見つけるアイコン。ユーザー指定ZIPのREADME/manifestと実画像を確認して導入。ZIP内の指示文は実行していない。元ZIPは変更しない。

入力ZIP SHA256：`22e277320a162ba5b8dbb554da3d8064d9f0e3c2103a2886516399d2c170548f`。

## 保存先・配布の区別
- `design/visual-assets/v1/`：app_icon、msix_compatibility、status、mascot、branding、ui_iconsとREADME/manifestの原本。設計資料用でアプリへ自動同梱しない。
- `src/Aredoko.WinUI/Assets/`：既存名のICO/ロゴ8PNGと、`Visual/`の実使用6PNGのみを同梱。
- PREVIEW/reference/CODEX_PROMPTはアプリへ入れず、参考画像からの切り貼りもしない。PREVIEWはignoredレビュー出力だけ。

## 適用
| 場所 | 素材・扱い |
| --- | --- |
| EXE、ウィンドウ、非パッケージ版 | 提供マルチサイズICO（16/24/32/48/64/128/256）。既存ApplicationIconとbootstrapビルドのwin32iconは同じAppIcon.icoを使用。AppWindow参照をBaseDirectoryからの絶対pathへ修正 |
| MSIX Development/Alpha | 既存manifestのファイル名・identityを保持。Square150 scale200=300px、Square44 scale200=88px、target24/48、Store50、Wide scale200=620×300、Splash scale200=1240×600。LockScreen scale200=48px。規定サイズへの機械的なLanczos変換のみ |
| 一覧の空状態 | searching/no_results/errorを最大128×112。結果がある間は親ごと非表示で一覧領域を維持。既存の案内・取消・エラー情報は残す |
| AI索引設定 | running/cancellingでindexing、completeでcompleted、failedでerror。96px、idleでは非表示。既存の文字・進捗・操作ボタンは維持 |
| AI環境の設定 | 検査中indexing、保存済みcompleted、failedでerror。設定は次回起動用であり、現在のAI推論が利用可能になったとは表示しない |
| 初回案内・使い方 | greetingを96px程度で表示。案内用ScrollViewerの中だけで、通常一覧には常駐しない |

C#で作る状態画像のデコードは表示寸法に合わせ256px以下。状態が同じ間はBitmapImageを作り直さない。装飾画像はアクセシビリティtreeから除外し、意味を既存の文字で伝える。Fluentの操作アイコンと検索・タグ編集は変更しない。

## 保留した素材
- found：通常検索成功時の一覧へキャラを常駐させないため未使用。
- greeting以外のmascot、brandingの大きな背景：原本を整理して保留。既存の小型起動進捗と一覧を狭めないため、無理な背景・ヒーロー追加はしない。MSIX splashは専用compatibility素材を使用。
- brand mark/ui_icons：今のFluent操作アイコンを維持。将来の小型ロゴ等に備え原本を保存。
- Square71/310など未参照MSIX候補：現manifestに導線がないため追加タイルを作らない。

## 再生成と確認
`python tools/sync_visual_assets.py` は保存済み原本から既知の15出力だけをコピー/サイズ変換する。`--check`は書き込まず一致を検証する。外部取得は行わない。

- 原本manifestの全保存ファイルの容量・画像寸法を照合。15出力の完全一致、ICO7サイズ、両manifest各5画像参照、PNG寸法を静的確認。
- WinUI Portable publish成功。既知WUI1001×3/SDK IL2104×2を隠さず維持、新規依存なし。
- 初回frontend01はビルド/UIAが通っても画像未収録。6PNG目視で欠落を確認し、ContentのCopyToOutputDirectory/CopyToPublishDirectoryを明示した。rawのUIA合格を画像表示合格と読み替えない。
- frontend02のDark/Light各1flow：生成145PNG/独立DB、準備中→中断→再検索→空履歴→空お気に入り→空棚。各7 checks PASS・所有exit0/残存0・生成原本SHA/mtime保持。計12PNG全目視、画像表示と通常一覧にキャラが残らないことを確認。
- 証拠：ignored `data/ai-ui/visual-assets-review-20261025/`。indexing/completed/error、初回guideの全状態GUI切替、High Contrast/DPI、MSIX署名/インストールは今回未実施（配線/収録/build確認）。通常DB・旧Alpha・既存配布ZIP・shortcutは未更新。CI/GPU/モデル取得0。

原本一式は.gitattributesで改行変換を無効にし、manifestの容量を異なるcheckoutでも保つ。
