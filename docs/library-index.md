# ローカルインデックス基盤（v0.1）

## 目的・安全境界

`app/library_index.py` は**実ファイルを開かず**、ディレクトリエントリの名前・種類・サイズ・変更時刻だけをローカルSQLiteに保存する独立した試作です。ユーザーが明示登録したルート以外は走査しません。プログラムにはファイルの移動、削除、変換、アーカイブ展開、内容アップロードの機能がありません。

既存のデモDB `data/demo.sqlite` と `items` テーブルは使用しません。新規DBは初期設定で `data/library-index.sqlite` です。実データの索引DBとダンプ、個人フォルダの位置情報を Git にコミットしないでください（既存の `.gitignore` 対象）。

## コマンドライン（自分で指定したフォルダのみ）

```powershell
# 初回：登録だけ。ファイルはまだ走査しない
python tools/index_library.py add "D:\Media" --exclude "cache" --exclude "*.tmp"

# 登録先とオンライン状態、ルートIDを表示
python tools/index_library.py roots

# 除外ルールの入れ替え（既定の除外名は維持）
python tools/index_library.py rules 1 --exclude "cache" --exclude "*.tmp"

# まずファイル走査の差分を確認（SQLiteには反映しない）
python tools/index_library.py scan 1 --dry-run

# 承認した場合にだけメタデータを索引DBへ記録
python tools/index_library.py scan 1

# 登録結果を一部表示（最大500件ずつ）
python tools/index_library.py locations 1 --status present --limit 50 --offset 0
```

対象フォルダは各自のPCで明示指定してください。未指定の状態で実ファイル走査は起こりません。Python標準ライブラリだけで実行できます。`--db` はサブコマンドの**前**に付けて試験用DBに変更できます（例: `python tools/index_library.py --db data/my-test.sqlite roots`）。

## 現段階でのデータモデル

- `library_roots`: 登録ルート（実際の場所）、相対パスの除外パターン、最終走査日時。
- `library_locations`: 1つの物理ファイルにつき、`id`、`root_id`、ルート相対パス、仮の種別、サイズ、mtime（ナノ秒）、`present / missing / excluded` 状態、初回検出日時、最終検出日時。`root_id + relative_path` は一意です。
- 2回目以降は同じ相対パスのIDを維持し、サイズやmtimeが変わった場合のみ「changed」と集計します。内容ハッシュやリネーム自動推定は**していません**。
- 削除・移動された場所の記録は削除せず `missing` にします。除外対象へ切り替わった既存レコードは `excluded` とし、メタデータを保持します。
- ルートにアクセスできない場合、または走査途中で権限エラー等が発生した場合は**失敗を返し**、走査全体のDB更新をロールバックします。全件を `missing` にしません。
- 登録ルートの重複・入れ子登録は拒否します。シンボリックリンクとWindowsリパースポイントは走査対象外です。
- 既定の除外名: `.git`, `.svn`, `__pycache__`, `node_modules`, `Thumbs.db`, `desktop.ini`。`--exclude` は名前かルート相対パス（`/` 区切り、fnmatchスタイル）を追加します。

## ファイル種別（現段階の仮分類）

`book`: cbz/pdf/epub。`archive`: zip（本か素材か未判定）。`image`: jpg/jpeg/png/webp/gif/bmp/tif/tiff/avif/heic/heif。`video`: mp4/mkv/webm/avi/mov/wmv/m4v/ts。`audio`: mp3/flac/wav/ogg/opus/m4a/aac/wma。`material`: psd/clip/kra/ora/blend/svg/ase/aseprite。

対象拡張子は今後設定可能にします。拡張子による仮分類は内容の正当性や安全性を保証しません。画像フォルダを1冊として扱う規則・ZIP内を列挙する処理・Komga接続・サムネイル/AI解析は未実装です。

## 現状の制約と次の設計課題

1. **論理作品IDはまだない**: 同じ作品の複数保存場所、移動・リネーム検出、フォルダ⇔CBZ変換の突合は未実装。`library_locations.id` は作品IDとして使わないでください。
2. **DBは一走査一トランザクション**: 中断時に元に戻る一方、50,000ファイル以上の実運用を保証していません。次段階でバッチ処理・永続キュー・再開機能、アプリと同時実行時の読み取り競合を設計します。
3. **オフライン判定は到達可否による**: 空のディレクトリとして誤マウントされた場合などは `missing` と判断され得ます。自動削除は行わず、記録は残します。
4. **複数ファイルのハードリンク・重複内容は未判定**: サイズとmtimeが同じでも内容が異なる場合があります。
5. **プロダクションUI/APIとは未接続**: デモ一覧には実データを一切混ぜません。GUI方式決定前にバックエンドを独立して検証する段階です。
6. **ファイルアクセス制御ではない**: シンボリックリンクやリパースポイントを可能な範囲で除外しますが、悪意ある別プロセスが走査中にパス構成を入れ替える場合の完全なサンドボックスではありません。

## 検証

`python -m unittest discover -s tests -v`。`tests/test_library_index.py` は `tempfile.TemporaryDirectory` に架空の拡張子だけを作り、登録/除外/差分/復活/オフライン/途中エラー時のロールバック/シンボリックリンク/重複ルートを検証します。実ファイルにはアクセスしません。
