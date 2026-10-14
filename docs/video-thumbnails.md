# 動画の先頭フレーム・プレビュー（2026-10-14）

明示登録・索引済みの動画を、画像・本と同じプレビューAPIで扱う小さな実装。
動画の内容検索、代表シーン選択、再生UIはまだ実装していない。

## 使い方と境界

- backendを起動する環境のPATHに**既存のffmpegとffprobe**がある場合のみ動作する。自動導入・ダウンロードはしない。Windowsの`.bat`/`.cmd`ラッパーは実行しない。
- `GET /api/library/preview/<id>`から`image/png`を返す。登録中のroot・除外・presence・リンク/リパース・索引size/mtime検査を通したファイルだけが対象。認証・no-store・404 fallback・503 busyは従来と同じ。
- WinUIのlist/grid/詳細プレビューに接続し、成功した行は「動画の先頭フレーム」と表示するソースを追加。**この接続はWindowsビルド/実GUI未検証**。画像/本のdouble-click入口やreader対象を動画へ広げていない。
- ツール不在・破損・非対応・上限超過では「プレビューなし」。最初のデコード可能な映像フレームなので、暗い冒頭や無地のフレームもあり得る。代表場面や内容の判定ではない。
- 対象拡張子：MP4/M4V/MOV、MKV/WebM、AVI、WMV、TS。拡張子は対応保証ではない。入力をseek不可の`pipe:0`で渡すため、末尾moovなど後方seekが必要なMP4/MOVは取得に失敗し得る。512 MiB超の動画もこの段階では対象外。

## 資源と元ファイルの保全

| 項目 | 上限・方式 |
| --- | --- |
| 入力動画 | 512 MiB、映像16百万画素、最大16 stream |
| 探索 | probe 1 MiB、analyzeduration 1秒、probe packet 128 |
| 処理時間 | probe＋frame取得で合計10秒、timeoutで子processを停止・回収 |
| 並列 | 画像・CBZ/ZIP readerと共通の2枠、満杯なら即503 |
| decode/filter/encode | 各1 thread、FFmpegの単一allocation上限64 MiB |
| 出力 | 長辺256px以下、拡大なし、PNG最大512 KiB |
| probe本文 | 最大16 KiB |
| backend cache | revisionキーのLRU 32枚、PNG合計最大16 MiB、memoryのみ |
| WinUI cache | 既存64枚LRU・取消・stale応答排除を再利用 |

検査済みの**開いた読み取りハンドル**を子processのstdinへ渡し、元ファイルのパスをコマンドに含めない。shellを使わず、pipeのみのprotocol allowlistと限定demuxerでplaylistや外部参照を拒否。継承した`FFREPORT`を除去し、ツールのlogファイル出力を抑える。元動画・展開ファイル・PNGのdisk cacheを作らない。

cache hitもroot/path/statを再検査し、取得後にもhandleのsize/mtime/ctimeとパスのidentityを確認する。revisionは既存のfile identity/metadataであり、全内容hashやimmutable snapshotではない。処理中に取得された古い結果は、検知した変更/差し替え時に返さない。元ファイルを保持するhandleは読み取り専用。

これらはapplication側の出力・並列・処理時間の制限。FFmpegの総heap/CPU/読み込み帯域の厳密な上限やsecurity sandboxを保証しない。HTTPクライアントが閉じてもbackendは処理を完了またはtimeoutまで継続する。native codecの導入・更新はこの実装に含めない。

## 検証

```
NO_PROXY=127.0.0.1,localhost python -m unittest discover -s tests -p test_video_previews.py -v
```

Linux／既存FFmpeg 6.1.1で**19 PASS、skip0**。生成MP4（MPEG-4／faststart）・MKV（FFV1）・WebM（VP8）の先頭赤frameをPNGから確認し、256×144、元bytes/mtimeとファイル一覧不変を確認。playlistを偽装した入力に対してloopback sentinelへのHTTP要求0を確認。

既存preview **12 PASS**、reader **16 PASS**。新しい回帰は認証、fallback/busy、除外/解除/欠損/stale/link、処理中の変更/差し替え、cache上限と再検査、dimension/output/deadline制限、子process回収、ツール不在、FFREPORT非継承を含む。timeout/outputテストでは実際の小さなPython子processを停止している。

**未検証**：Windowsのstdin handle／ffmpeg buildと各codec、WinUI Release/XAML/native表示、実素材・大規模負荷、動画再生。生成3形式の合格を全codecや一般ライブラリの成功率へ流用しない。

次のgate：Windows Release→生成動画のlist/grid/詳細・fallback・取消・Light/Dark・元bytes/mtime不変→必要に応じてseek可能な安全入力/大動画対応を設計。サムネイルdouble-click実機確認は[前回の残課題](viewer-reader-validation.md)のまま。

実装で参照した公式資料：[protocol/pipe](https://ffmpeg.org/ffmpeg-protocols.html)、[ffprobe options](https://ffmpeg.org/ffprobe.html)。
