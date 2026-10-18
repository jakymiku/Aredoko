# R02-C — 検索専用の受付ID・中断

2026-10-18。R02-Bの全件候補検索に、request所有の取消と切断検出を接続する。モデル・永続DB schema・検索順位式・索引jobの停止APIは変更しない。

## HTTP契約

すべて既存loopbackのHost/Origin/X-Aredoko-Token認証を必須とする。

1. `POST /api/library/ai/searches/prepare`、body `{}`。推論せず、サーバー発行128bit乱数の小文字hex32桁 `request_id` と `expires_in_seconds:60` を返す。未使用予約の保持は最大32、60秒期限。上限時は409、次のprepareで期限切れの未使用予約だけを回収する。実行中の受付は時間で失効させない。
2. 通常の `ai/search`、`ai/similar`、または `tag-suggestions/search` の `semantic:true` にそのIDを追加する。同じIDは1回だけclaimでき、成功応答は同じIDをechoする。終了/失敗時に削除する。重複実行・期限切れ・未登録IDは409 `search_request_unavailable`。形式不正/nullは400。
3. `POST /api/library/ai/searches/cancel`、bodyは `{"request_id":"..."}` のみ。IDとbooleanの `cancel_requested` を返す。実行中はそのEventだけを立てる。未開始の場合は予約を削除し、遅れて届く検索POSTを拒否する。古い/未知/完了済みIDはfalse、別の実行中検索には影響しない。これは中断受付で、worker終了の確認応答ではない。
4. 中断を検出した検索は409 `search_cancelled`、部分結果なし。完了判定と中断は競合し得るため、最終チェックを通った直後の取消では完了結果が先に確定する場合がある。クライアントもcancel tokenとrequest IDで古い結果を捨てる。

既存のID省略検索HTTPは引き続き使用でき、接続切断を確認する。文字だけの未承認候補検索にrequest IDを渡すと400。索引作成の `/ai/cancel`、タグ生成/本文生成/page jobの取消とは別で、検索中断で索引jobのEventを立てない。IDは一時メモリだけに持ち、履歴・catalog・vectorへ保存しない。

## 中断点・後片付け

- メタデータ256行batch間、score追加/最終融合・ページングの既存SQLite progress handler、保存ページvector256行ごとと本の物理確認前、公開前で中断を確認する。
- HTTP bodyを消費した検索接続をselect/MSG_PEEKで非ブロック確認する。EOF/resetで中断し、読めるデータ自体を切断と誤認しない。socketモードやタイムアウトを変更しない。サーバーは1要求でConnection:closeとする既存仕様。
- `AISearch.close()`は受付を閉じ、全予約/実行中Eventへ通知してから既存worker/inferenceを待つ。CPU検索は一時DB/接続を閉じて所有temp folderを削除し、inference lockを返す。通常検索が再び動くこと、元生成素材bytes/mtimeとpending候補が不変なことをテストする。
- **実行中のencode、OSファイルI/O、外部worker待ちは強制killしない。** 戻った直後に中断を確認する。取消受付の速さとworker解放までの時間を混同せず、常に即停止/1秒以内停止とは主張しない。サービス停止は現在のclose呼び出しに接続し、ThreadingHTTPServer.shutdown単体をAI所有者のclose代替にはしない。

## CoreとGUIの境界

`SearchRequestClient`が受付→検索→ID照合を共通化し、JSONのMIME/宣言長/実長をbounded確認。通常AI、画像類似、タグ候補意味へ接続する。失敗/timeout/caller cancellation時は、元のcancel済みtokenとは独立した3秒以内の取消HTTPをawaitする。取消自体の通信失敗は元エラーを隠さず、再試行しない。完了検索には不要な取消を送らない。通常40秒/類似10秒/タグ意味180秒のdeadlineと、HttpClient自身のtimeoutの早い方が有効。

ID発行APIのない旧バックエンドへ新版Coreを接続するfallbackは行わない。既存の検索応答パーサーの旧shape互換は保持する。通常AIのAPIメソッドへoptional CancellationTokenを追加し、既存呼び出しは維持。既存の類似UIは既存token経由で新経路を使う。**通常検索のcancelボタン/選択変更時のtoken配線などUI全体の整理はR10**。新しいボタンや画面は追加しない。GUI実動作の合格はCPU/Core/ビルドから推定しない。

## 検証記録

開始HEAD `3f29893483660f10280dddcff5a5f8dab8a670ef`、実装 `b6731565e185101d58a56de9c2e144d7ebf6df53`。ログ/環境/source SHAは `data/large-library/r02c-checks-20261018-01/` に新規保存し、以前のR02-B記録は上書きしない。

- 初回対象CPU66件PASS（62.258436秒）、Core527 checks PASS。その後shutdown競合とpending HTTP取消を補強し、最終全体/Core/Releaseを検証する。
- 最終Core **528 checks PASS /2.3576823秒**、x64 SelfContained Release **0警告/0エラー /13.49秒**。新しいWinUI/XAML APIなし。WinUI Code Reviewでasync/using/失敗保存/認証/応答上限を確認、WinUIAnalyzer未導入/未実行。既存code-behindの日本語全面resw化は対象外。
- **全Python546件：543 PASS /3 Windows platform SKIP /428.427327秒**（full-python.log/json、source SHA不変）。専用Python3.11.9の関連対象は **67 PASS /66.011661秒**（python311-targeted.log/json）。全体を再実行するのは今回の1回で、GPU/GUIは含めない。
- R02はA/B/C実装・CPU検証済みの **CPU_DONE**。必要実機受入はR14、UI全体の取消配線はR10、資源/性能受入はR12へ残し、全媒体製品の完成と混同しない。

生成素材/固定vector/mock queryのみ、GPU/GUI・実モデルload/新download/依存追加/私物走査/原本変更/Actions/main mergeなし。実品質・native操作/High Contrast/Narrator/DPI/AOT・RSS/1TB性能・R12のp95/資源予算は今回未検証。P0累積2/2閉鎖、専用OCR保留と旧book-batch取消PNGの未完は維持する。

次はR03の複数DBバックアップ/復旧契約と生成DBでの検証、続いてR04の明示的な索引継続。必要な実機受入はR14へ送る。
