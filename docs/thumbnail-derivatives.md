# P3 派生サムネイル基盤（PARTIAL）

> 続き: [120×5結果window・可視優先・DPI/復号予約](p3-result-window.md)。以下の未完欄は前の段階の記録で、最新状態はリンク先とhandoffを優先。

2026-10-22。P2 native source接続 `9fd565c01d269450c538fa8a47a0f3210575364a` の後に追加。既存原本・AI代表frame・DB schema・旧preview APIは維持する。完成形UI/仮想化全体の完了ではない。

## 実装

- 認証済みGET `/api/library/thumbnail/<id>?edge=128|256|512|1024`。画像・ZIP/CBZ表紙・明示登録したフォルダ本の先頭pageを、既存guard付きhandle/page取得からPNGへ生成する。EXIF方向を適用、APNG posterを飛ばし最初の表示frameを使う。GIFのn_frames/is_animatedや全frame走査は呼ばない。縮小のみ、拡大なし。新依存なし、Pillowは遅延importする。
- 原本版・item/kind・page0・edge・方式版をkeyとし、同一keyの進行中作業を共有。生成は最大2、待機を含む別key作業は最大32。HTTP切断でその要求を取消す。leaderが切断しても共有相手が残れば生成を継続し、最後のwaiterが去った作業は次の安全点で停止する。close後の遅延cache公開を拒否する。codec中のOS/Pillow処理を強制終了するものではなく、hard cancellation期限は未実装。
- PNG byte RAM cacheは64MiB/256entryのLRU。**decoded RAM64MiBの目標とは別**。生成の原本は既存64MiB/16Mpixel以内、並列2だが、Pillowの原寸decoder/EXIF/変換copy・入力byte・Windows BitmapImageの実heapは別に消費する。総RAM64MiB達成とは主張しない。
- 所有backendごとの一時SQLite cacheを遅延作成。512MiBのpage-count hard capとpayload予約・4096entry/LRUで制限、normal closeで所有directoryだけ削除する。停止/再起動をまたぐ永続cacheは未実装。ディスクhash/PNG header/長さを確認し、破損・SQLite異常・容量不足はtierを無効化またはmissへ変え、基本閲覧は継続する。原本/model/ユーザーcatalogへ書込まない。
- RAM/disk hitも現在のroot登録/除外/祖先/原本版を再検証。本はrevisionとpage ETagの304経路でZIP/folder pageの検証を行い、hit時に画像を再展開しない。途中変更を正常な別画像やEOFとして返さない。HTTPはno-store。
- WinUI ThumbnailServiceは画像/本を新APIへ接続し、WindowsでのPNG再変換を省く。ローカルrow-key cacheによるguard省略を撤去。動画は既存guard付きpreview API（既に256px PNG）を使い、同じく再PNG変換せず表示する。旧APIは互換維持。
- Coreはedge/ID・最大8MiB・Content-Lengthと実長・派生MIME/PNG signatureを検査する。取消tokenを保持し、404等はplaceholder、5xxは次のrealizationで再試行する。

## 確認と限界

Linuxで生成PNG/JPEG/GIF/APNG/CBZ/folderだけ使用。原本SHA/mtime不変、4size、EXIF、poster、全GIF走査なし、同時要求共有と双方の取消、2生成上限、待機取消、途中close、scope変更/未接続/同size+mtime置換、RAM/disk eviction、破損・SQLITE_FULL fallback、所有cleanup、token/厳密routeを確認。

- 初期25 PASS/1.439sはHTTP subclassが同じ12 testを再実行していた。失敗はないが重複を修正し、25件をunique coverageとして数えない。
- RAM段階の関連41 PASS/4.446s（画像形式/原本/guard/stub生成含む）。
- ディスク/動画/folder追加後の関連**56 PASS/9.627s**。raw: `docs/validation/20261022-thumbnails/`。重複したtest群の件数を加算しない。
- 最後のcodec/cache境界修正3 PASS/0.122s。Pillowのbomb/codec例外を404相当へ正規化し、壊れた本cache ETagは再生成へ戻す。APNG/GIF経路も局所確認。上の56件を再加算しない。
- Core ThumbnailTests追加はsourceのみ。**.NET SDKなし、Core実行/WinUI・Portable build/native PNG表示/速度/メモリ測定はUNRUN**。stub生成の合格はC# compileではない。既存Alpha/basic03等を更新した結果ではない。

## 2026-10-24 永続サムネイルディスクキャッシュ（`<db>.thumbs.sqlite`）

- `app/thumbnail_disk.py` の `ThumbnailDisk` に明示 `path`（永続モード）を追加し、`app/production_server.py`（`_serve` および `production_handler`）から `catalog.path.parent / (catalog.path.name + '.thumbs.sqlite')` を渡して再起動をまたぐ派生サムネイルキャッシュを有効化した。省略時（`path=None`）は従来通り一時ディレクトリを作成し `close()` で削除する。
- 永続ファイルは `plain_path` / `storage_parent` で検証し、`storage_lease(path)` により単一プロセス所有を強制（ロック競合時はキャッシュ層のみ fail-open で無効化し、原本から通常生成を継続）。
- 接続前に残存 `-wal` / `-shm` / `-journal` を `plain_path` 検査のうえ掃除し、`PRAGMA trusted_schema=OFF`、`PRAGMA quick_check`、`PRAGMA user_version`（`0` または `1`）、`sqlite_master` の厳密構成（`thumbs` テーブルのみ、trigger/view/未知objectなし）を検証。不一致や破損時はキャッシュファイルを張り直して fail-open で復旧し、起動を止めない。
- 再起動後のLRU順序維持のため `COALESCE(MAX(touched), 0)` で `tick` を初期化し、起動時にも件数/容量上限の `_evict()` を適用。永続モードの `close()` はDB接続とleaseのみを閉じ、`<db>.thumbs.sqlite` を保持する。
- `app/storage_backup.py` の対象store正規表現（`<catalog>.ai...`）および `live_backup.py` は `<db>.thumbs.sqlite` と `.owner.lock` をバックアップに含めない。
- 確認：`CUDA_VISIBLE_DEVICES=-1 python -m unittest tests/test_thumbnail_cache.py tests/test_thumbnail_priority.py tests/test_storage_backup.py tests/test_live_backup.py` **73 PASS / 43.510s**（再起動をまたぐ永続hit、原本変更時の失効、破損/不正schema/未知user_versionからの自動再初期化、lease競合時のfail-open、バックアップ非収録、`production_handler` 配線を含む）。
- **実機 `Aredoko.exe` 再起動横断ヒット・100%→180%サイズ/DPIバケット昇格・棚一覧再取得・メモリ境界確認（2026-10-24）**：`tools/test_native_persistent_thumbnails.py` を追加し、生成24 PNG＋2 CBZ（540〜640px、計26件＋初期棚 `テスト棚`）・独立 `LOCALAPPDATA`・ステージング `data/ai-ui/p3-persistent-thumbs-20261024/staged-release{,-02}/Aredoko` で検証。
  - `run01`（FAIL、生ログ・PNG1枚保全）：Phase 0 のグリッド表示と終了 `0` までPASS後、`.owner.lock` のファイル非存在検査で停止（`storage_lease` はinode競合防止のため `.owner.lock` ファイルを残しカーネルロックのみ解放する契約）。`with storage_lease(thumbs_db_path):` に修正。
  - `run02`（**PASS**、25 checks PASS、2 PNG全目視）：100%固定でのList→Grid→終了 `0`（`rows=30, max_touched=30, bytes=18,779`）→再起動→List→Grid→終了 `0`（`rows=30, max_touched=60, bytes=18,779`、100%キャッシュヒット）を確認。
  - さらに `UpdateItemSizes()`（`containerRefresh`・`ShowDetailPreviewAsync(preserveExisting: true)`・`UpdateShelfItemSizes()` の `shelfRefresh`）を実機GUI操作でも通すため、詳細プレビュー表示＋100%→180%サイズ変更＋棚一覧（`NavShelf`）140%→180%サイズ変更を追加して `staged-release-02` を検証（途中 `run03` の `send-input` 拒否、`run04` の `1024` 元寸上限 `560..640` 含有、`run05` の遷移直後UIA `stale_element` を生ログ・PNGとともに保全しリトライ修正）。
  - `run06`（**PASS**、28 checks PASS、4 PNG全目視）：
    - Phase 0：List（`128`）→Grid 100%（`256`）→詳細ペイン（`DetailPreview`）→180%拡大（`UpdateItemSizes()` から `containerRefresh` と既存画像を消さない `ShowDetailPreviewAsync(preserveExisting: true)` を実行し `512` 派生取得）→棚一覧 `NavShelf` で140%→180%変更（`shelfRefresh` 実行、`01-phase0-shelf-180pct.png`）→`NavAll` 180%グリッド復帰（`1024` バケット＝元寸上限 `560..640` 取得、`02-phase0-grid-180pct.png`、`WorkingSet64=218,091,520 B` / `PrivateMemorySize64=172,597,248 B`）→通常終了（WinUI PID `32424` / bootstrap PID `38368` とも exit `0`）。終了後 `catalog.sqlite.thumbs.sqlite` に `rows=49`・`max_touched=49`・`bytes=102,469`・`edges=[128, 256, 512, 560, 580, 600, 620, 640]`・`user_version=1`・`quick_check=ok`・`storage_lease` 解放を確認。
    - Phase 1（再起動）：同一 `LOCALAPPDATA` / `catalog.sqlite` で `Aredoko.exe` を再起動し、保存された180%スケールでList→Grid→詳細ペイン（`03-phase1-restarted-thumbs.png`）→棚一覧 `NavShelf`（`04-phase1-restarted-shelf.png`、`WorkingSet64=205,168,640 B` / `PrivateMemorySize64=159,002,624 B`）→通常終了（WinUI PID `47120` / bootstrap PID `48176` とも exit `0`、残存 `0`）。終了後 `rows=49`・`bytes=102,469` 不変のまま `max_touched=75` へ進行し、再起動後の全表示要求が100%永続ディスクキャッシュから提供されたこと・生成26原本のSHA256/mtime完全不変を実証。
- 実機での数万件スクロール時の体感速度・decoded RAM全体目標は引き続き別検証。

## 次の作業

P3 PARTIAL。可視優先scheduler/近傍先読み/画面外取消の一覧接続、DPI/tile実寸に合わせたedge選択、decoded全体のRAM budgetは未完。現在の一覧は従来page UIのままで、120件block/最大5blockのdata virtualization/標準container再利用と完成形主画面を実装する。Windowsでは既存依存のみでCore→Portable buildを各1回、生成媒体で全size・再利用cell・画像混入・除外/解除後のcache・取消/close・Light/Dark/狭幅を確認する。既存GUI回数capを新名称でresetしない。

大規模UI/実機待ちで独立backendを停止しない。P4複数棚/履歴/root favorites、P5起動中backup/restore、P6 setup/配布、P7は引き続き未完。
