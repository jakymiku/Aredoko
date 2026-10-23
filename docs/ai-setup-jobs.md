# 配置済みAI環境のバックグラウンド検査（LD4a）

## 2026-10-24 Core・配置済み環境のGUI接続（最新）

既存の「AI検索の準備」→「AI環境を追加・配置する」から、runtime/modelsのフォルダ選択、標準設定への復帰、背景検査、実進捗、中止、再表示をsource接続。`AIEnvironmentClient`は未指定と明示nullを区別し、保存済みと推論準備完了を混同しない。保存先をGET診断へ追加し、GUIの非同期応答はrevision/lifetimeで保護。操作エラーは最終Render後も保持する。画面を閉じても背景検査は続く。正常モデル・索引をhot swapしない。

Core947 assertions PASS、既存setup jobs15 PASS/3.067s。Portable build0errors/既知WUI1001×3 (28.77s)、候補 `data/ai-ui/ai-environment-20261024/frontend01` publish成功/既存SDK IL2104×2。GUI受入はこの時点で未実施。新しい具体範囲で生成データのみ最大2回の許可を質問済み、回答前には起動しない。復元3/3等の既存capとは別の実体の作業だが、旧flowを再試行しない。実モデル・GPU・新規取得0。

利用者向け配置ガイドは[AI環境の追加と配置](ai-environment-guide.md)。アプリ取得は[LD4b](ai-acquisition.md)の製品catalog未登録のため利用可能と表示しない。手動選択は一般のvenv任意実行ではなく、既存LD3の検証済みAredoko pack契約を使用する。旧CLI復旧手順は通常説明から折りたたみへ整理し、アプリ内復元の案内を最新化した。

次：許可があれば上記候補の独立GUIフローを確認し、製品catalogのprovenance/配布元準備と取得Core/UIを続ける。P5/LD4b/LD5/LD6の全完了とはしない。Goal active、no shutdown。

2026-10-22。前回のLD3は5d7984fでcommit/push/文書/PR本文更新まで完了していた。停止点はPR head確認中のusageによる自動承認review不能であり、実装の未保存ではない。再開時にfetch/status/log、remote branch/refs/pull/5/head/APIのhead一致、Draft/open/unmerged、Actions/checks0を確認した。作業treeもcleanで、他AIの未取得変更はなかった。

## 今回の実装

`app/ai_setup_jobs.py`が、明示した既存runtime/models rootの検査・設定保存を1つの所有threadで実行する。新たなdownload/model load/pip/driver操作をしない。LD3の選択サービスを再利用し、通常のHTTP handlerを全pack SHA計算で占有しない。基本一覧/検索は継続できる。

- 開始時はconsent=trueとruntime_rootまたはmodels_rootを要求。指定なしは保持、nullは既定へ戻す。未知field/相対path/制御文字/不正type/4096文字超は拒否。対応pack/モデルの意味は[LD3契約](ai-runtime-setup.md)のまま。
- job IDはサーバーが生成する32桁hex。現在の1件だけを保持し、同時開始は409。古いIDで現在の処理を中止できない。IDは認証情報ではなく、同じ有効session tokenとOrigin/Host検査も必要。開始応答を失った場合はGET jobで現在の状態を確認し、無条件再開始しない。
- 段階はvalidating/checking_runtime/saving/complete、終了分岐はcancelled/failed。manifest全entryのfile数/bytes総量が確定した後だけ実際のhash済み件数/bytesを公開する。未知総量はnull。先行するinventory/core検査と最後のmanifest再確認/設定保存は総hash bytesに混ぜない。全bytes100%でも保存完了やAI推論の準備完了とは表示しない。
- hashは1MiB境界で取消を確認。取消とatomic replaceを同じlockで順序付け、中止が受理された場合は設定を後からpublishしない。既に保存済みならcancel_accepted=false。保存後の診断だけが失敗した場合はsaved=true/complete/diagnostics_failedとして、取消・rollback済みと偽らない。
- settings lease/最新設定の再読込/既存field保持/fresh temp/flush/fsync/atomic replaceを維持。破損・検査失敗・取消・lease競合では旧設定を保持。実行中encoder/モデル/index identityは変更しない。
- production serverのExitStackにownerを登録し、通常終了/owner EOF/起動bind失敗のcleanupで閉じる。close後は新jobと遅れて来たcommitを禁止。開始に失敗して未開始のthreadも安全に閉じられる。
- 通常closeは取消後joinの待ち予算10秒。OSのfile readやatomic replace自体が停止した場合の硬い終了期限を保証するものではない。中断不能なreadではdaemon threadを保持し、close済みのpublish gateで遅延保存を拒否する。実際の保存が先に始まった場合は保存済みとして扱う。プロセス名/PID列挙で他のアプリをkillしない。

## API

| 操作 | route | 内容 |
| --- | --- | --- |
| POST | /api/library/ai/setup/select | consentと明示folder。202でjob状態を返し、検査は背景で続く |
| GET | /api/library/ai/setup/job | 現在のjob/実進捗/保存済みflag/結果。full SHAをやり直さない |
| POST | /api/library/ai/setup/cancel | job_id必須。中止を受理できたかを明示 |
| GET | /api/library/ai/setup | 従来のruntime/model別診断にjobを追加。selection API対応、download未対応を区別 |

POSTは既存のHost/Origin/session token/32KiB制限を保持し、新しい2routeでは重複JSON keyも拒否する。GETは既存認証を保持。エラーは限定code/日本語の案内にし、例外の生文字列や任意のpathをmessageへ流さない。静的result.readyは従来通りfile状態で、GPU/inference_verifiedではない。

## 検証

- 初期36 PASS/8.744s（job11件＋従来runtime25件、後のstart/close/commit境界追加前）。
- 影響回帰01は104件中103 PASS/1 runner ERROR。存在しないtest_storage_leaseを指定したためで、製品failureではない。77.501s。失敗logを保存し全体成功とは記載しない。
- module名を修正し、未開始threadのclose境界も追加した回帰02は81 PASS/73.195s。runtime/jobs/起動所有権/配布staging/relocation/HTTP拒否/production/paths。最後の新API重複JSON拒否・commit直前取消test前。
- 最終の関連42 PASS/12.074s（新job14件＋runtime25件＋HTTP拒否3件）。同じテストを足して総成功数にしない。開始不可の案内をworker開始失敗でも正しく読める文に整理し、関連2 PASS/1.157s（ai-setup-jobs-start-message-20261022-01.log）。
- 生成pack/専用settings/専用DB/loopback serverのみ。検査中のGET一覧応答、認証/Origin不足拒否、重複JSON拒否、同時開始、古いID、中止受理、hash進捗、検査中/保存直前の取消、commit後の取消不受理、save後診断失敗、未開始workerのclose、遅延readとclose、lease競合、設定/source SHA+mtime不変、tmp cleanupを確認。

証拠はignored data/ai-ui/ai-setup-jobs-20261022-01.log、ai-setup-jobs-regression-20261022-0{1,2}.log、ai-setup-jobs-final-20261022-01.log。GUI/GPU/実model/新download/私物scan/通常DB・個人設定変更0。XAML/C#未変更で、Core/native build/GUI受入を今回実行したとはしない。旧GUI固定3/3上限と全失敗を保持。

## 未完と次

**LD4はPARTIAL。** 今回は既存folderの検査job/APIまでで、製品GUI、信頼済み取得catalog、download/stage/publish/resumeは未実装。検査jobはbackend session限りで保持し、再起動後は明示して全検査をやり直す。download途中fileの永続再開を実装済みとしない。

次はLD4b：配布元/固定revision/サイズ/SHA/roleを明示するtrusted catalogと、生成HTTPからの取得stage→検証→新version公開。破損・通信切断・同一revision再開・取消・容量不足をCPU fixtureで受入する。正常pack/models/indexは上書きしない。外部モデルや依存を実取得する前には具体物の許可が必要。製品downloadは既定無制限/任意合計cap。

その後LD5の既存「AI検索の準備」へ簡潔なfolder選択/進捗/中止/再試行/公式案内を接続し、LD6の具体buildによる通常restart/ZIP移動/clean Windows/実AIへ進む。GUIは新たな具体範囲の許可なしに過去capを別名resetしない。

新規配布は作成しておらず、basic03/Alpha/shortcut/旧artifactは今回変更なし。basic03は今回のjobを含まない。現行sourceと配布内snapshotを混同しない。R13 DOING/ALPHA未完/R14 PARTIAL。全機能/専用OCR保留/U09/U11/U13/U14/ALPHA後実音声音楽を維持。Actions/main merge/旧shutdownなし。
