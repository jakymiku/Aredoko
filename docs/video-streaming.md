# 動画の範囲取得再生（2026-10-15）

専用WinUIプレーヤーは認証付きmanifestと明示Rangeを使う。動画全体のメモリコピーは行わない。Windows標準codecの制限は残る。

- `GET /api/library/video/{id}/manifest`：item_id / size_bytes / mime / revision。サイズ1〜2TiB。
- `GET /api/library/video/{id}/range?revision=<64hex>`：単一の`Range: bytes=start-end`、1要求1MiB以下。成功206、Content-Length/Content-Range/ETagをCoreが検査。範囲外416、更新409、共通preview2枠使用中503、不正形式400。suffix/open-ended/multiple rangeは扱わない。
- active root、present、除外、リンク/reparse、索引stat、open handleの同一性、取得前後の変更を各要求で再検査。revisionはファイル同一性/メタデータのトークンで、内容hashではない。
- manifest受信4KiB/5秒、range受信1MiB/40秒。Coreは同時2取得、WinRTカーソルは独立したPositionとClone/InputStreamを持つ。native1読込は最大8MiB（内部を1MiBへ分割）。codec側のメモリ使用量まで固定する保証はない。
- 閉じる/再試行時は共有sourceを先に取消し、nativeのクローン破棄だけでは他のカーソルを停止しない。UI更新はview/version境界で保護。HTTPリダイレクト無効。元ファイル、モデル、設定を変更しない。
- 旧`GET /api/library/video/{id}`とCore.VideoAsyncは互換用に64MiB上限で残す。通常の先頭サムネイルは512MiB/10秒の既存境界を維持。先頭プレビュー不可でも動画再生を開ける。

## 実測

生成MP4に70MiBの有効なfree atomをmdat後/moov前へ追加し、末尾metadataへのnativeランダムアクセスを要求。`video-range-native-03`は73 checks / keys30 / skipped0 / PNG12全目視PASS。MP4/WMV再生・停止・前後移動・音量/消音、非対応FFV1/破損、503手動retry、409、auto-hide/F10/Esc、狭い/広い幅、Light/Dark、未保存draftとフォーカス復元。全要求はmanifest/rangeで旧全体取得0。source bytes/mtime・設定不変、AI0、owned windowのみclose、cleanup失敗なし。

初回01は末尾free atomだけではcodecがprefixに収まるため「非zero offset必須」の証拠条件に失敗（再生操作自体は完走）。02は末尾moovが既存非seek thumbnailで不可になるのにDetailPreview必須だったテスト前提に失敗。2回修正して03で完走。失敗証拠もignored dataに保存・全PNG確認。

全Python276 PASS（138.384秒・skip0）、Core208 PASS、x64 self-contained Release32.19秒・0error/既存IL2104 2warning（非抑制）。専用WinUI analyzer、Native AOT、Narrator/High Contrast/多DPI、2TiBや長編高bitrateの実動画、再生中の実更新・切断によるcodec側の回復は未検証。実測は生成70MiB/2秒動画であり、上限全域の保証ではない。
