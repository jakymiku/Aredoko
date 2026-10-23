# LD4b：任意AI環境の取得基盤（2026-10-24）

## 2026-10-24 explicit repeat acquisition reuses verified version (latest)

An explicit same-catalog acquisition after a previous backend session verifies the exact existing version's inventory, sizes, all SHA and owned validator in place, then acknowledges through the same cancel/publication gate. Returns reused=true/root without network or replacement. Corrupt/unlisted/linked versions fail and remain untouched; there is no silent repair. Cancellation before acknowledgement cannot turn into later success, and the old existing directory is retained. This full verification occurs only on explicit acquisition, not startup/status/catalog GET. Received/verified counts include available reused bytes, not a claim of newly transferred network bytes.

Generated acquisition/jobHTTP20 PASS/13.894s, includes new-owner reuse, corrupt/extra-file preservation and cancel before acknowledgement. Setup capability now matches nonempty trusted registry; focused authenticated HTTP1 PASS/1.310s after that final change (not21 distinct tests). No additional GUI/GPU/real artifact retrieval. Source-host build/Core evidence is previous unit; no C# change here. Next reproducible catalog build from an explicitly selected verified runtime pack; registry remains empty until real publisher/licensing review.

## 2026-10-24 source disclosure and progress scaling (latest)

Trusted catalog summaries now expose allowed source hosts (not signed/private artifact URLs). Core validates bounded host-only metadata; native consent screen shows sources beside capacity/license. Acquisition computes immutable total bytes once rather than scanning every catalog entry on each64KiB progress report; full per-artifact hash/cancellation/publication checks are unchanged. This removes catalog-size times chunk-count bookkeeping, not a measured throughput claim.

Python acquisition/jobHTTP16 PASS/10.208s; final Core974 PASS lines; Portable build0errors/known WUI1001x3/15.68s. Initial Core compile failed from a new fixture edit typo (CS1513); corrected final log retained separately. Previous acquisition Core count was recorded973 from output line total; correct pre-host count972, now974 after2 added host checks. No additional GUI/GPU/external transfer. Native tested frontend01 remains earlier source; new source-host line not visually accepted. Product catalog still empty. Next reuse verified already-published versions without network/replacement, then actual catalog publisher/provenance.

## 2026-10-24 generated native acquisition accepted (latest)

Implementation `7705e53`, candidate data/ai-ui/ai-acquisition-20261024/frontend01, native run01: **12 checks PASS**, all4 delivered PNGs reviewed, owned PID37176 normal exit0/no residual. Source/app SHA stable during flow. Real native consent→Start invokes authenticated production acquisition job; generated1,500,000 bytes from owned loopback only. Close/reopen attaches same job; native cancel before publish retains partial/settings; native resume issues actual Range bytes=65536-, validates exact bytes and exposes new root. Final received=verified=total1,500,000/published=true; original fixture/media SHA+mtime and launch preferences unchanged. No AI activation or selected Python execution.

Acquisition GUI1/2 consumed; do not repeat passing flow just to use remaining attempt. Actual empty production registry/native license external navigation/optional speed edit/light/high DPI/real pack/clean Windows remain unaccepted. Idle shows consent required and default0=unlimited; active PNG was captured before next periodic progress refresh, cancelled/completed counts visible, not a throughput benchmark. Previous environment2/2 and restore3/3 remain exhausted. No external artifact/GPU/userDB/Alpha changes; P5/P6/roadmap incomplete.

## 2026-10-24 typed acquisition client and native download UI (latest)

Source connects AI environment → app acquisition: trusted catalog metadata/capacity/license, explicit consent, default unlimited or optional MB/s cap, separate received/verified bytes, current-job cancel, retry/resume, dialog close/reopen and published root. Selected settings/active model do not change automatically. Published version can be selected explicitly through the existing-folder entry. Native catalog uses direct ComboBoxItem controls, not reflection-bound generic ItemsSource; lifetime/revision/busy protect stale replies and in-flight close. Same published catalog cannot be reacquired from the current UI state.

Core acquisition parsing rejects invalid identities/unsafe license links/duplicate catalogs/impossible progress/false completion and preserves cancel acknowledgement; Start sends only consent/catalog ID/rate, never URL/root. Core972 assertions PASS (corrected from output-line count973) (including new acquisition checks); Portable build0errors/known WUI1001x3,16.42s. Final source published to data/ai-ui/ai-acquisition-20261024/frontend01 with existing SDK IL2104x2. GUI not yet run at this checkpoint: user explicitly approved generated loopback-only max2 acquisition attempts; existing environment2/2 and restore3/3 caps remain exhausted.

Production specifications STILL EMPTY: no external model/package transfer or inference, no normal DB/Alpha/GPU. Actual catalog publisher/notice/provenance work remains and download readiness is not claimed. Next native owned acquisition scope, then publisher/actual catalog and final distribution acceptance. P6/LD5/roadmap incomplete; goal active/no shutdown.

## 現在の到達点

固定カタログからの取得、同一カタログの途中再開、全artifact SHA/構成検証後の新version公開、所有jobと認証APIを実装。**製品用の取得カタログはまだ登録していない**。通常起動ではネットワーク取得せず、`download_supported=false`、catalog一覧は空。実モデル/依存の取得・推論・GPU/GUI確認なし。P5の未受入項目も保持し、P6完了とはしない。

## 契約と実装

- `ai_acquisition.Catalog` はアプリ側が持つJSONを厳密検査し、固定revision、サイズ、SHA256、role、相対path、license/link、許可hostを保持する。SHA256 canonical fingerprintがjobから選ぶID。URLや配置先をHTTP callerから受けない。HTTPSと許可hostだけに制限し、redirect先も検査。HTTP loopback例外は生成テストで明示的に指定する。
- 100,000 files/64GiB以内。Windows予約名・大小文字別名・file/directory prefix衝突を拒否。カタログにないファイルを公開しない。起動時に私物やモデルフォルダを走査しない。
- カタログfingerprintごとのkernel lease/stageで競合防止。同一カタログだけRange再開。206の範囲・総長を検査し、Range無視の200は先頭から書き直す。hash不一致は該当partialを破棄して失敗。途中切断/取消ではpartialを保持する。
- 既定速度制限なし。`bytes_per_second`指定時は1所有jobの全ファイル合計で制限。進捗は受信済みbytesとSHA検証済みbytesを別表示する。実行中モデル・設定・既存version/indexは変更しない。
- artifact hashとアプリ所有validator（runtime用は既存inspect_runtime full検査）後に同一filesystemの新versionへrename。公開と取消は同じ所有lock。受理された取消/close後に遅れて公開できない。既存versionを上書きしない。OS readの硬い停止期限は保証しない。

## API

既存Host/Origin/session token/strict JSON制限下で：

- GET `/api/library/ai/setup/download/catalog`：登録済み固定catalogのID/name/kind/revision/容量/license/link。artifact URLは返さない。
- GET `/api/library/ai/setup/download/job`：現在の1jobと受信/検証進捗。
- POST `/api/library/ai/setup/download/start`：`consent=true,catalog_id,bytes_per_second`（null=無制限）。背景threadで202。
- POST `/api/library/ai/setup/download/cancel`：現在job_idだけを受け付け、cancel_acceptedを返す。

productionはcatalog registry空で開始。HTTP入力や取得した文書をcatalog/validatorとして実行しない。download ownerは通常終了/復元hand-off時のclose対象。

## 確認と限界

生成HTTPのみ。取得11 PASS/6.592s、所有job/HTTP5 PASS/3.498s（先行8/10件の実行は加算しない）。切断/Range再開/Range無視/破損/中止/全ファイル速度cap/容量不足/未掲載file/パス衝突、公開直前cancel/close、認証/Origin/重複JSON/未知catalog・URL注入を確認。証拠はツール出力とtracked tests。新規モデル・pip・環境/ドライバー操作なし。

## 次の実装

1. 配布元・固定artifact・license/NOTICEを確認した製品catalogを作成。runtime packの公開先は未用意、推測URL/架空ハッシュで有効化しない。
2. Core/既存「AI検索の準備」へcatalog一覧・容量/ライセンス確認・実進捗・中止・再開を接続。既存配置選択LD4aも同じ入口へ。公開versionを明示選択して次回起動設定へ保存する。
3. 新しい具体候補で許可されたGUI/実取得/clean Windows確認へ進む。既存capを別名で再実行しない。外部artifact実取得は対象/容量/取得元を示して許可が必要。

WDの既存固定hash/サイズはconfig/tagger-profilesに存在し、[固定revisionのモデルカード](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/blob/627aef95638667ddcaa3ac8ae625e88ea5b02f51/README.md)のApache-2.0 metadataを読み取り再確認した。これは取得を実行した証拠でも、全依存の配布notice整備済みという意味でもない。
