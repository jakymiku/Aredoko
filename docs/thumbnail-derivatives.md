# P3 派生サムネイル基盤（PARTIAL）

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
- Core ThumbnailTests追加はsourceのみ。**.NET SDKなし、Core実行/WinUI・Portable build/native PNG表示/速度/メモリ測定はUNRUN**。stub生成の合格はC# compileではない。既存Alpha/basic03等を更新した結果ではない。

## 次の作業

P3 PARTIAL。可視優先scheduler/近傍先読み/画面外取消の一覧接続、DPI/tile実寸に合わせたedge選択、decoded全体のRAM budgetは未完。現在の一覧は従来page UIのままで、120件block/最大5blockのdata virtualization/標準container再利用と完成形主画面を実装する。Windowsでは既存依存のみでCore→Portable buildを各1回、生成媒体で全size・再利用cell・画像混入・除外/解除後のcache・取消/close・Light/Dark/狭幅を確認する。既存GUI回数capを新名称でresetしない。

大規模UI/実機待ちで独立backendを停止しない。P4複数棚/履歴/root favorites、P5起動中backup/restore、P6 setup/配布、P7は引き続き未完。
