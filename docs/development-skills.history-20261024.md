# 開発スキルと引き継ぎ

2026-10-10、以下をこのPCのCodexスキルフォルダに導入済み。
- Hallmark: Nutlope/hallmark / skills/hallmark
- Web Design Guidelines: vercel-labs/agent-skills / skills/web-design-guidelines
- Microsoft WinUI: microsoft/winappCli / plugins/winui/agent-plugin/skills/ 配下の winui-setup, winui-design, winui-dev-workflow, winui-code-review, winui-ui-testing, winui-packaging

MicrosoftのWinUIスキルはwin-dev-skillsからwinappCliへ移転しているため、現行パスから導入した。
React Best PracticesはReact採用段階で検討。ImpeccableはHallmarkと役割が重なるため未導入。
これはPCへのスキル導入であり、アプリ依存ライブラリや.NET/Rust SDKの導入ではない。
他環境では同じスキルを別途導入する必要がある。

## 次の試作
- 現状はPython + 素のHTML/CSS/JS。Tauri/React/WinUI本体は未実装。
- 大きな導入見出しを縮小して、検索・一覧・右側の詳細編集を中心にする。
- キーボード操作、フォーカス表示、読み込み中、空結果、入力エラー、未保存編集の扱いを点検する。
- Web Design GuidelinesとHallmarkの監査を行い、実装に反映する。正式な監査報告とUI改修は未完了。
- 管理アプリとしての一覧密度と操作性を優先する。マーケティングページ向け装飾は適用しない。
- WinUIとTauriで共通API・同じデータ・同じ画像条件を用意して実測する。

## 引き継ぎ時に読む順番
README.md → docs/spec.md → docs/status.md → docs/gui-comparison.md → docs/api.md。
起動: python app/server.py --open
テスト: python -m unittest discover -s tests -v
実データの対象フォルダは未指定。素材を勝手に収集しない。
