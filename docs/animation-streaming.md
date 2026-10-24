# P1B 所有セッションによる逐次アニメーション

2026-10-22。基点 `1969ab4`。GIFは引き続きWindows標準の再生を優先し、失敗時とAPNG/WebPは新しい逐次経路を使う。旧manifest/frame API・AI代表frame規則・静止画原寸・本のcache/読書位置は維持する。

## 実装

- `animation_sessions.py`は検証済みhandleを一度だけPillowで開く。GIFの`n_frames`/`is_animated`を参照せず、先頭1枚を先に返す。EOFまで逐次seekし64枚で切り捨てない。
- Pillowの合成済みRGBAをpremultiplied BGRA8へ変換。APNG posterは除外しblend/disposal/透明度/durationを維持。GIFのloopは追加反復数、APNG/WebPは総再生数として扱い、loopなしは1回、0は無限。AI用の旧64枚契約は変更しない。
- token/Origin/Host認証付きPOST `/api/library/animation/open`（item_id/revision/session_id）、`next`（session_id/count 1–4）、`close`（session_id）。新APIは未知field・重複JSON・過大bodyを拒否する。
- nextはlittle-endian uint32 JSON長＋UTF-8 metadata＋各frameのpixel。metadataはitem/revision/session、width/height/stride/format/alpha、sequence/index/cycle/duration/length/done。Coreは順序・同じsession/版・寸法・payload長を検査し、frame単位で読む。
- 保持handleと現在の登録・除外・祖先・物理identity/版をpull前後に再検証。再生中に原本を開き直さない。closeはactive decoderを並行破棄せず取消flagを立て、処理のfinallyで解放。開くHTTP応答が失われてもclient側で先に決めたIDをcloseでき、close先行時の遅延openも拒否する。
- WinUIは先頭表示後に最大4枚を先読み、1つのWriteableBitmapを再利用。全frame PNG/HTTP取得待ちとBitmapImage全配列を撤去。version/session/cancellationで古い応答を拒否し、遅延・有限loop終了・失敗時も最後の正常画像を保持する。

## 資源と限界

3sessionまで、idle300秒で所有reaperが解放、backend終了時close。batchは4枚/128MiB以内、表示用edge2048以内なので現状pixel payloadは最大64MiB。decode元は64MiB/16Mpixel以内。先読みとは別に、Pillowの圧縮入力・合成canvas/変換・HTTP送信buffer・描画bufferが必要で、128MiBをアプリ全体RSS上限とはしない。clientは消費済みbatch全体を保持せずframeごとの配列を解放する。

OS I/O/Pillowの1回のdecodeを強制中断する期限は保証しない。close済みIDは5分/最大4096程度の短命tombstoneで遅延openを拒否する。接続喪失時はidle cleanupがfallback。現時点でnative GIFの内部bufferや全体RSS/速度の実測はない。

## 検証とWindows手順

生成GIF/APNG/WebP70枚×2周、先頭取得時の非列挙/decoder1回/原本再openなし、poster/透過/blend/disposal/duration、有限/無限loop、中止/同時pull/close先行/idle/容量、原本不変、除外/解除/更新、実loopback HTTP/認証/JSON/binary順序をPythonで確認。

初回17 PASSにはimportされた既存6件を含む（新規11件）。関連runnerは不存在`test_original_pages`指定で42 PASS/1 runner ERROR。修正した関連48 PASS/4.693s。その後の原本再open除去の新規11件は11 PASS/1.093s（`python-guard-final.log`）を記録し、合算しない。raw logはignored `data/ai-ui/animation-stream-20261022/`に保持。

Core通信の回帰テストを追加したが、このLinux環境には.NET SDK/Windowsがない。**Core実行/WinUI build/native表示/実loop/速度/Honeyview比較は未実行**。P1Bはsource接続とPython確認までで、完成・実機受入済みとはしない。配布/旧Alpha/basic03/shortcutは更新していない。

Windowsでは既存依存で `dotnet run --project tests/Aredoko.Core.Tests -c Release`、続けて既存Portable build手順を1回実行。生成した70枚以上のAPNG/WebP・poster/透明画像・有限2loop・真GIF/native失敗fallbackを開き、先頭の早期表示→64枚以降→loop→高速切替/close→古い画像の混入なしを確認。追加native自動操作は過去のGUI capをresetせず別途扱う。build/API代入を実描画・速度合格としない。

次はP2結果session/60件境界。Windows待ちだけで独立backend開発を止めない。R13 DOING/R14 PARTIAL/M1/M2未完、OCR保留・全機能・過去失敗を保持する。

今回のraw log（失敗・途中版も保持）は [永続検証記録](validation/20261022-work/) を参照。


## 2026-10-24 Windows限定native確認
- source `54feb46`＋reportの差分SHA、候補 `data/ai-ui/animation-stream-native-20261024/frontend01`。専用DB・生成素材のみ、70frame APNG＋poster/有限2loop、真GIF、`.gif`名のWebPを確認。新ハーネス `tools/test_native_animation_stream.py`、run01はPASS/owned app exit0/残存PID0。4 PNG全目視。
- APNGは最初のbatch1枚、posterを除く70枚×2cycleが正順に配信され、UIAで70枚目を確認。有限終了後も最後の正常画像を保持。真GIFはnative経路、偽拡張子WebPは逐次経路で表示・終了。2所有sessionとも解放し、元PNG/GIFのSHA・mtimeは不変。実モデル/GPU/私物scan0。
- XAML source割当までの単回stage値：APNG656.54ms、真GIF460.92ms（復号ready458.46ms）、偽拡張子WebP648.73ms。物理表示時刻・FPS・HoneyView同等速度・全RSS・大画像・高速取消の受入ではない。
- ViewerLoadTraceだけに残っていたGetFolderPathをAppLogと同じ明示LOCALAPPDATAへ揃え、専用directoryに実ログを確認。情報は固定stage/経過msのみ。Portable publish成功、既知WUI1001/SDK IL2104を抑制していない。
- 独立診断 `transport-baseline.json`（生成warm image/CBZ、各3sample）はHTTP本体/304中央値約11–30ms。別の小さいinfo測定では約217ms、直接preview profileは約4ms。TCP_NODELAYや一括writeの仮説は改善せず、アプリへのその変更は行わない。環境/ハーネス差のある測定を同一条件の性能改善値として扱わない。詳細はignored `tiny-info-*`/`http-profile.txt`/`constant-http-diagnostic.json`。
- 次の局所改善は逐次開始時の`open`→`next(1)`を一つの所有APIへまとめること。既存API互換・取消ID・原本guardを維持し、同じ素材の限定nativeで初回割当と正常終了を比較する。全回帰やHoneyView反復には戻らない。


## 先頭取得を1要求へ統合
- 新規owned `POST /api/library/animation/open-first` は既存open＋pull(1)を同じ応答へまとめる。clientで先に決めたsession ID、close先行tombstone、重複IDで既存sessionを破棄しない動作、原本の前後guard、失敗時解放を共有する。旧open/next APIはそのまま互換維持。
- Core/WinUIは先頭1枚を同じbinary検証で受け、次のsequence1から最大4枚を先読みする。未知source/stride/順序/サイズは拒否し、壊れた先頭応答でも既知IDをcloseする。現在の有限loop・最終frame保持・native GIFは変更しない。
- 関連Python12件/3.504s、追加認証HTTP1件/0.783s、Core1019 assertions、Portable publishは各PASS。新しい大規模回帰は実施していない。
- frontend02＋run02はnative全19チェックPASS、4 PNG目視、app0、session残存0、原本不変。先頭応答のaction=open-first、APNG70frame×2cycleの順序、native GIFと偽拡張子WebPを確認。provenanceと正確なfront/source/test SHAはreport。
- 同じ生成条件の限定単回比較：APNG割当656.54→442.89ms、WebP648.73→442.76ms。未変更GIFは460.92→468.80ms。1通信の削減に対応する改善であり、平均/p95/物理表示/FPS/HoneyView同等速度の宣言ではない。大画像/RSS/高速切替・全P7受入は未完。
