# 基本ZIP09・U4–U6反映候補

2026-10-25。source **281186398614151a23bdc6a77598d5e4c9d1deaf**。

- 通常入口：`dist/portable-basic-20261025-09/Aredoko/Aredoko.exe`。ZIP：同親の `Aredoko-windows-x64.zip`。新規出力先で作成、旧08/07を上書きしない。
- 794 files / 660,875,459 bytes、ZIP 347,983,136 bytes。SHA256 `b8cee0ded7dfd9170f705b04d1aeb9c433f1cc10a3fe7254c6f9c878b976c2c7`。
- U4aの補強、folder別起動時更新/catalog v3/欠落除外、U5複数選択/一括favorite・棚/600件保持/差分、U6 ZIP・CBZ共通filter、終了所有proof補強を収録。現行アイコン/状態素材と初回案内も維持。基本Python/メディア処理は同梱、PyTorch/モデルは含めない。
- prepareのPortable実評価receipt、bootstrap self-test、同梱runtime check、全ZIP照合PASS。同梱Pythonで基本＋U4–U6の**21項目PASS**、生成DB integrity=ok、所有backend EOF exit0、元生成PNG SHA/mtime保全。実行後の全payload inventory/hashも再照合。証拠：`data/ai-ui/continuation-20261025b/{prepare09.log,basic09/report.json,release09-proof.json}`。
- **staging-only**。09の通常EXE/GUI・clean Windowsは未受入。frontend06/native-selection03の18項目確認を09全体PASSへ流用しない。新GUI/GPUには現ユーザーの事前回答が必要。GPU/実モデル/新download/Actions/merge/通常DB変更なし。
- ユーザーは引継ぎ保存後のデスクトップAlpha更新を追加指示。既存の通常DB/モデル保存先/旧AI interpreterを保持する更新を行い、実施結果はcurrent-handoffへ追記する。旧MSIX登録の削除はしない。

## 実用入口の更新完了
- 事前引継ぎebe3122のPush後、ユーザー用アプリ領域 `Programs/Aredoko/releases/20261025-2811863` へ09と同一payloadを配置し、既存デスクトップAlpha shortcutを新しい `Aredoko.exe` へ更新。通常DBは未オープン・size/mtime不変、モデル保存先と旧AI interpreterを継承。旧設定/shortcutのバックアップをupdatesへ保存した。
- MSIX登録そのものは旧1.0.0.1のまま保全。今後の実用入口はデスクトップAlpha。更新後のGUI/実推論は未実施であり、次の確認にはユーザー回答を得る。確認結果の正本はcurrent-handoff。
