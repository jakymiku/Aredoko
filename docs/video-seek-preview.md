# シークバーと時刻付きサムネイル（2026-10-15）

## 操作

動画の下部シークバーをクリック/ドラッグすると、その位置へ移動する。フォーカスしたバーから左右キーで1秒移動できる。現在位置は再生中にも更新する。バーにマウスを置くと指した時刻とそのフレームを表示し、hoverだけでは再生位置を変えない。hover終了/閉じる/再試行で画像を隠す。取得不可では「サムネイルなし」と表示し、再生/シークを続けられる。下部帯はStretch・margin0・左右border0・corner0でウィンドウのコンテンツ端まで揃える。

## 取得と制限

- `GET /api/library/video/{id}/frame?revision=<64hex>&at_ms=<integer>`、Host/token必須、追加/重複queryやpathを拒否。時刻0〜86,400,000ms（24時間）。stale409、busy503、取得不可404、不正400、成功PNG200/no-store。
- range再生と同じpresent/active root/除外/リンク/reparse/索引stat/open handle/revision・取得後変更チェックを通す。クライアントの指定pathや外部URLを開かない。
- 既存FFmpeg/FFprobeを使い、検査済みの読み取りハンドルをstdinへ継承する。時間指定だけseek可能な`fd:`入力を使い、通常先頭thumbnailは既存`pipe:0`を維持する。[FFmpeg公式fd仕様](https://ffmpeg.org/ffmpeg-protocols.html#fd)。子へ渡す前にPythonの先読みbufferを無効化してOSのoffsetを0へ合わせる。
- input2TiB、16M画素、最大辺256px・PNG512KiB、1decoder thread、合計10秒、共通preview2枠、revision＋時刻LRU32枚（先頭thumbnailと共有、最大16MiB出力）。fdがない旧FFmpegや非対応codecは画像なしへ戻る。全codec heapの固定上限ではない。
- UIは320ms debounce、1要求のみ進行、秒単位で最寄りの時刻へ丸め（終端より前）、同じ時刻の再取得を省略。変更中の古いframeを表示せず、閉じる/再試行でtokenを取消。PNG受信512KiB/12秒、Bitmap decodeも取消・view/version照合。サムネイル用元動画copy/cacheファイルを作らない。
- HTTP取消はバックエンド子の即時killを意味しない。サーバー側10秒deadlineで回収する。長編/高bitrate/同時取得負荷、多DPI/Narrator/High Contrast、24時間を超すhover時刻は未検証。24時間超はUI上のpreview時刻も上限に留まる。

## 検証

Python全279 PASS/132.626秒/skip0。新frame3件では認証/strictquery/revision/解除・除外・busyと、実FFmpegの赤→青2秒生成動画から0秒赤/1秒青、cache、source hash/mtime不変を確認。初回はprefix読込でPython先読みbufferにより子のOS offsetがずれた問題を検出・修正。Core213 PASS（frame固定route・時刻検証・PNG/MIME/長さ制限を含む）。最終x64 self-contained Release27.97秒、0error/既存IL2104 2warning非抑制。

`video-seek-native-03` PASS88 checks/40keys/skip0/18PNG全目視/graceful close2/cleanup失敗なし。Light/Dark・1200×820と700×620、slider/keyboard、再生位置0秒のままhover1秒の青い実frame、503previewなしでもseek可能、遅延frameの閉じる/別動画open後の排除、MP4/WMV、unsupported/corrupt、再生/停止/前後移動/音量/消音、503manualretry/409、auto-hide/F10/Esc、未保存draft/focus復元を完走。source/settings不変、AI0。

native01は中心のpointerが1秒の直前へ丸められる境界で期待1秒との差が発生。秒切捨てを最寄り秒へ修正、標準数値tooltipを無効化。02はhover後のauto-hideにより閉じるbuttonをfocusする旧テスト前提が失敗。常在viewportへのEscapeへ修正。2修正cycleで03が完走し、失敗PNGも確認済み。専用WinUI analyzer/Native AOTは未実施。range再生の生成70MiB実測は[別checkpoint](video-streaming.md)であり、今回長編動画を再実測した結果ではない。
