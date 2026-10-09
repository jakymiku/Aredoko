# Aredoko
画像・本・動画・音楽を、あいまいな記憶から探す。

Windows向けローカルライブラリ。現在は仕様策定・GUI比較準備段階です。アプリ本体は未実装です。

- [仕様](docs/spec.md)
- [GUI比較計画](docs/gui-comparison.md)
- [作業状況](docs/status.md)

実ファイル、購入作品、AIモデル、個人設定、検索DBはGit管理しません。
比較用の架空メタデータ: `python tools/generate_fixture.py --count 50000`
GUIはTauri + ReactとWinUI 3 + C#を比較して決定します。AI解析は共通Pythonプロセスです。
