# 帰宅後の起動チェック

## このPCの最新修正版（2026-10-21）

**`dist/portable-startup-diagnostic-20261021-02/Aredoko/Check-Startup.cmd`** を開いてください。専用の空ライブラリで、本体表示・通常終了・起動取消まで実機確認済みです。Prepare-Portable.cmdをやり直す必要はありません。

旧`dist/portable-wincheck-20261021-02`は起動通知の依存欠落でタイムアウトするため使わず、失敗記録として保持しています。[原因・修正と検証範囲](docs/portable-startup-console-fix.md)。全件チェックにはまだ数十秒かかります。通常データの再起動保持/clean Windows/ZIPは未受入です。以下は別途新規ビルドを準備するときの手順です。

## 最初に開くファイル

開発ブランチ`feat/winui3-production-mvp-20261011`の最新変更を実機へ取り込んでから、リポジトリ直下の **Prepare-Portable.cmd** をダブルクリックしてください。

これは開発段階の準備用です。既存のruntime入り配布と.NETのキャッシュを再利用して、Coreテスト→Portable本体publish→小型起動EXE→実行環境のコピー→import/動画tool検査を一回ずつ実行します。アプリ本体は自動起動しません。

- 既存の`dist/alpha-0-msix-20261021-02`をruntime素材として読み取り、書き換えません。見つからなければ、runtimeを同梱した既存配布フォルダを選択します。
- 新しい依存・モデルをダウンロードしません。足りないキャッシュやWindows標準のコンパイラがあれば停止し、ログを残します。失敗時に自動再試行しません。
- コピー先は毎回新しい`dist/portable-日時-識別子`。旧配布/登録/証明書/モデル/既存DBは変更しません。runtimeをコピーする分の空き容量が必要です。
- 最初の確認を早く始めるため、大きなZIPの作成は省略します。成功後、生成された **Aredokoフォルダ** が開きます。

## 画面で確認すること

生成フォルダ内の **Check-Startup.cmd** をダブルクリックしてください。

1. 小さな「Aredoko 起動チェック」画面が先に現れ、ファイル確認の件数や処理段階が変わる。
2. 本体の初期一覧が準備できると、起動画面が消えてAredoko本体が現れる。起動チェックでは空のライブラリが正常です。
3. 本体を普通に閉じる。起動用プロセスと今回のバックエンドも終了する。
4. もう一度Check-Startup.cmdを開き、起動画面の「キャンセル」で終了できるか確認する。

起動チェックは毎回`%LOCALAPPDATA%/Aredoko/startup-check/識別子`に**新しい専用DB/設定**を作ります。既存の登録フォルダ・タグ・お気に入りを使わず、モデルも取得・推論しません。各回が新規DBのため、このモードだけでは再起動後のタグ保持を検証できません。

通常利用の入口は、同じ生成フォルダ内の **Aredoko.exe** です。こちらは従来どおりのユーザーデータと明示設定を使います。Check-Startupと通常起動を同時に開くと、既存のport/lease保護で後の起動が拒否されます。

## 止まった場合

準備段階で止まった場合は、生成した`dist/portable-...`内の`core-tests.log`/`frontend-build.log`/`bootstrap-build.log`/`bootstrap-cpu.log`/`runtime-check.log`を確認します。存在するログだけで構いません。起動段階ではエラーを表示したままにし、「ログを開く」で今回のstartupログを開けます。詳しいlauncher/backendログの場所もそこへ記録します。内容にはローカルpathが含まれ得るため、そのままGitへ追加しません。

このチェックは画面の起動・取消・終了の確認です。検索品質、実画像の描画速度、HoneyView比較、clean Windows、全機能の受入完了にはしません。自動GUIテストの過去3/3上限もリセットしません。

## ZIPを作成する場合（開発担当者向け）

`tools/prepare_portable.py --runtime-release <既存配布> --output <新規先>`で準備すると、ZIPも作成します。元のPrepare-Portable.cmdは`--no-zip`を指定しています。すでに確認用フォルダがある場合は、同toolの`zip_release`で新しいZIP先へ書き出せます。ZIPは全entryのSHAとCRC、stageの全inventoryを照合し、既存ZIPを上書きしません。

[実装・検証境界](docs/portable-startup-check.md)
