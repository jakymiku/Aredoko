# LD4b：任意AI環境の取得基盤（2026-10-24）


旧2/2・3/3等は当時の履歴。新機能/有意味な修正の通常検証は[現行テスト方針](local-test-policy.md)に従う。現在の次の1件は[current-handoff](current-handoff.md)を優先する。

## 現行：最初の実モデルカタログ（2026-10-25）

製品registryは**EmbeddingGemma 2＋WDのモデル2件、runtime0件**へ更新。以下の古い「empty/0件」は当時の履歴。`config/acquisition/wd-swinv2-v3.json` は既存 `wd-swinv2-v3` profileとraw SHAを固定し、上流revision `627aef95638667ddcaa3ac8ae625e88ea5b02f51` の `model.onnx`/`selected_tags.csv` を変更せず取得する。ネットワーク対象467,769,446 bytes、inline出所/NOTICE込み467,783,838 bytes・6 files。カタログfingerprint `a03b0332560b8e852354b31bf39465d9f068ae7b93099a2be8141ca7ff597b13`。

- 公式固定[モデルカード](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/blob/627aef95638667ddcaa3ac8ae625e88ea5b02f51/README.md)のApache-2.0宣言、固定treeのONNX LFS SHA、HEAD-onlyの両artifact容量/最終host（huggingface.co/us.aws.cdn.hf.co）を確認。CSVは既存ローカル308,468 bytesを読み取り、SHA256のprofile一致と固定tree Git blob SHA1の一致を確認した。重み・CSVの外部取得や実行はしていない。
- [Apache公式ライセンス全文](https://www.apache.org/licenses/LICENSE-2.0.txt)、上流カード全文、著者/固定出所/未変更artifact/独立runtimeのNOTICE、Aredoko出所sidecarをbounded inlineで同梱。上流treeに独立NOTICE/LICENSEはないことも確認。モデルpackにPython/ONNX Runtime/PyTorch等は含めず、それらのruntime packの完全NOTICE・公開先は依然未完。
- 登録自体は通信・実行・設定保存を開始しない。明示consent後だけ既存の再開/容量/hash/validator/検証後公開を使い、取得完了後も対象モデルrootの明示保存と次回起動が必要。既定帯域は無制限、任意cap。画面ではモデルの用途と「対応する実行環境が必要」を表示する。
- CPU：registry7/model-pack10/owned-download6/inline7/staging19 PASS（各別実行）。公式metadata/HEAD証拠はignored `data/ai-ui/wd-catalog-review-20261025`。認証カタログ表示と新基本ZIPの確認は次工程。実467MB転送/推論/clean Windowsは未検証。新しい実取得やGUI/GPUは今回のユーザー指示どおり確認後に実行する。
- 基本版checkerは「常にcatalog0」を合格条件にせず、同梱Pythonで読み取った**その候補の固定registry**とAPIの完全一致を検査する。旧候補のempty registryも正確に検査でき、未導入AIと取得可能モデルを混同しない。

### EmbeddingGemma 2も登録（2026-10-25）

現在使用中の `google/embeddinggemma-2` / revision `914f7f89142e33e77833254d9c9b90c3cef7303b` を最初の選択肢として登録。公式固定モデルカードとAPIはApache-2.0・gated=false。旧THIRD_PARTY_NOTICESの `google/embeddinggemma-2-2b` / 汎用Gemma利用条件という記載は、実profileの出所に合わせて訂正した。他モデル/他revisionのライセンスへ一般化しない。

- 13個の未変更upstreamファイル（safetensors、両tokenizer、processor/config、chat template、pooling/normalize等）＋4個のinline LICENSE/NOTICE/上流カード/固定revision marker。ネットワーク1,525,787,092 bytes、全pack1,525,821,059 bytes。fingerprint `8ee756badd8a85a24d1dbf80103be005b2b9c21b3e91d009a8568704d634406e`。
- 大きい3artifactは固定treeのLFS SHA256とHEAD容量/hostを確認。小さい設定ファイルは既存ローカルのbytes/SHA256と上流Git blobを照合。重み・tokenizer本体の外部取得、依存取得、推論は0。公式metadata/HEADのrawはignored `data/ai-ui/embedding-catalog-review-20261025`。
- 実行時のprofile/768D/namespace・既存索引は変更しない。配布取得の固定profile SHAをcheckoutの改行変換で壊さないよう、該当profileとカタログ/NOTICEは `.gitattributes` でLF固定。
- 登録2件のCPU8 tests PASS。新基本ZIP02/source13778adの同梱Python11項目でregistry/API完全一致を確認。許可済みの表示のみnative＋1再起動もPASS（[候補記録](portable-refresh-20261024.md)）。既存runtimeの明示配置は利用可能だが、**実行環境の自動取得はまだ公開していない**。モデル取得だけで未導入runtimeまで揃ったとは表示しない。

### 実モデル転送とタイムアウト回復（2026-10-25）

ユーザー明示許可（合計約2GB・専用先・CPUのみ）で両モデルの実転送を実施。`data/ai-ui/real-model-download-20261025-01` 内のみへ保存し、既存models/設定を適用・変更していない。推論/GUI/GPU/依存取得は0。

- 最初の `report.json` はEG2の8MiB取消→206再開後、612,237,312 bytesで通信停止（failed/非公開）。旧ログ/partialを保全。`resume-report-02.json` では同partialから再開しEG2 **1,525,821,059 bytes/17 filesを全検証・公開完了**。同runのWDは8MiB取消→206再開後、188,219,392 bytesでread TimeoutErrorとなり非公開。このrun全体をPASSへ書き換えない。
- 実TimeoutErrorに対して、一時的なread timeout/reset/disconnectに限る**最大2回のRange再接続**を追加。閉じたpartialの実サイズから再開し、取消は即中止。認証/host/range/size/hash/容量/保存の失敗を再試行で覆さない。上限時はpartialを残して通常の「取得・再開」へ。既定速度無制限・任意の合計capと全SHA/validator/所有公開gateを維持。
- 局所修正後の `resume-report-03.json` はWDの保持済み188MBから206再開→ **467,783,838 bytes/6 filesを全検証・公開完了**、owner close成功。downloader SHA256 `20c4493f40951fe4ee009baaf0487f61f3a5a4ced79670394e4a0503f2420f31`。この最終runには新たなtimeoutがなく、内部自動retryの発火は生成CPUテストで確認した。EG2/WDの成功範囲はそれぞれ別runで、全体の無故障1回完走や推論品質と同一視しない。
- 新retry CPU5、従来取得14、owned job6 PASS（各別実行）。実HTTPのRange/206・最終hostだけを記録し、signed query URL/認証情報は保存しない。通常DB/旧Alpha/shortcutは未変更。

### 初回導線の短縮

「AI検索の準備」に `AIModelDownloadOpen`（モデルをダウンロード）と既存 `AIEnvironmentOpen`（配置済みを指定）を並べる。取得だけのために配置画面を経由する操作を減らす。旧配置経由の取得導線は維持し、scope保存中は両方の画面遷移を止める。未配置時の「自動ダウンロードは行いません」という旧説明も、取得/既存配置を選べる案内へ更新した。関連ai_settings13 PASS/Portable publish成功。新しい直接入口のnativeはまだ未実施（GUIは今回のユーザー指定で確認後に行う）。

## 2026-10-24 role-root backend contract (latest)

Source backend/owned launcher now accept optional absolute `embedding_models_root`, `tagger_models_root`, `intent_models_root` (matching hyphenated CLI flags). Each role uses its specific root before shared `models_root`, retaining shared/repository fallback when unspecified. Embedding settings/worker, WD and optional intent factories receive their own roots; model profile and vector namespace identity are unchanged. No file movement/copy, model execution or hot swap is added.

Preferences validate these paths and report pending effective `model_roots` plus the effective embedding `models_root`. Any role change requires restart. The existing shared-folder picker/select/reset is deliberately a common selection: on successful atomic save it clears all per-role overrides. Cancellation preserves every old field. Explicit role-specific CLI choices remain more specific than a generic fallback root. P5 ready cleanup preserves these machine-local preferences without incorporating foreign runtime paths from a backup.

Generated role/launcher/dispatcher/validation/cancel/P5-preservation9 PASS/0.887s; existing setup jobs/HTTP plus normal real owned-backend lifecycle16 PASS/5.141s; existing runtime preference11 PASS/1.238s separately. Dispatcher paths are checked with non-executing factory spies; normal lifecycle is a real missing-AI backend. No GUI/GPU/model inference. Evidence `role-roots-*.log` under the current active-selection evidence directory.

This is the backend/advanced launch-settings unit, **not finished model acquisition selection UI**. Next: expose the registry profile role to Core/catalog summaries, save one selected role through the owned setup job without clearing the others, and show that role's current/pending location in native setup. The common reset behavior above stays explicit. Basic ZIP02/sourcef508b82 does not contain these fields: do not add them to its settings or treat this as installed Alpha support. Actual product catalog stays empty.

## 2026-10-24 bounded app-owned metadata (latest)

Acquisition catalog version2 allows an entry to carry `inline_utf8` instead of `url`. Its exact UTF-8 bytes/size/SHA and text are covered by the catalog fingerprint; no URL/body ambiguity or executable/weights role is allowed. Only configuration/inventory JSON/TXT and license/NOTICE text:64KiB per entry,256KiB total. The ordinary partial-file/hash/inventory/validator/cancellation/publication checks are shared with remote files. Sidecars are not executed or interpreted as a new catalog. Progress includes available payload bytes; bandwidth accounting still covers actual network bytes only. Version1 remains supported and rejects inline fields; older applications reject version2.

`build_ai_model_catalog.py --embed-metadata` optionally embeds the already reviewed provenance marker and license/NOTICE text while leaving model artifacts at explicit HTTPS sources. CRLF/UTF-8 bytes are preserved, not normalized. No source writes, actual model download or registry activation. A source LICENSE/NOTICE and separate redistribution review are still required. License links now reject control characters and password-only userinfo consistently with Core.

Generated7 PASS/3.275s; old/new format rejection, mixed-source rejection, hash/size/role/extension/byte budgets, exact UTF-8, inline-only no network/execution, corruption/reuse, cancel and model-builder source preservation. Related existing acquisition/job/model/runtime-builder/registry plus future-format case41 PASS/16.916s separately. The final link-validation cases1 PASS/0.518s. No full GUI/Core repetition for this Python-only change. Evidence `inline-*.log` in the active-selection evidence directory; module discovery remains7 tests (imported fixture classes do not add duplicate runs).

### Fixed WD source review (metadata only)

The [pinned upstream card](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/blob/627aef95638667ddcaa3ac8ae625e88ea5b02f51/README.md) declares Apache-2.0. The [fixed tree metadata](https://huggingface.co/api/models/SmilingWolf/wd-swinv2-tagger-v3/tree/627aef95638667ddcaa3ac8ae625e88ea5b02f51) and HEAD-only requests confirm model.onnx467,460,978 bytes and selected_tags.csv308,468 bytes. The ONNX LFS SHA matches the existing profile; the CSV tree does not supply SHA256, so its downloaded bytes were not reverified here. HEAD stayed HEAD across redirects, recording only final hosts (`us.aws.cdn.hf.co`, `huggingface.co`), never signed URL query strings. The fixed tree has no Aredoko provenance marker or standalone LICENSE payload, which is the reason for bounded app-owned sidecars. No weights/dependencies were downloaded or executed. Ignored evidence: `data/ai-ui/acquisition-source-review-20261024-01/{official-tree.json,report.json}`. This metadata check is not full dependency NOTICE/redistribution/inference acceptance.

Before enabling separately downloaded models, retain the current common `models_root` compatibility and design role/model-specific placement: a single-model version root cannot silently replace a root that currently provides both embedding and WD models. The runtime selection tested above is independent; it does not prove multi-model placement. Real registry remains empty until that selection contract and reviewed source/NOTICE are ready.

## 2026-10-24 explicit-use native acceptance (latest)

The new published-root handoff (not a repeat of the old cancel/resume workflow) was exercised on Windows with a generated valid runtime inventory and loopback artifacts. `tools/test_native_ai_acquisition.py --published-selection --theme light` publishes the fixture, passes its exact root into setup, verifies that navigation alone does not save, then invokes the explicit use button and checks the pinned next-restart settings. Unrelated model-root/theme fields and generated sources/media remain unchanged. A Popen allowlist blocks selected/generated Python or other unexpected process execution; attempted unexpected launches0. The test intentionally does not restart into the generated non-executable runtime.

11 checks PASS, owned frontend exit0/no live process,4 PNGs all viewed, no external transfer/GPU/normal DB/installed Alpha. Publish succeeded with known WUI1001×3/SDK IL2104×2. AppLog now uses the same explicit LOCALAPPDATA as owner/Python; the real frontend startup stages were written inside the dedicated user directory. Evidence: ignored `data/ai-ui/ai-acquired-selection-20261024/run01/{report.json,visual-review.json,commands.log}` and PNGs. Frontend/source/diff/test-script SHA are recorded because the candidate was built with the pending AppLog change on94c9816. The product registry remains empty, and this is not real-runtime inference/clean Windows/model-kind native acceptance.

The current [local test policy](local-test-policy.md) supersedes inherited lifetime caps: retain old raw failures/attempt records, diagnose before rerunning, and test meaningful fixes/features in isolated fixtures. The separately user-scoped basic02 first launch+one restart has ended; it is not relabelled as this feature test. No old raw FAIL was overwritten.

## 2026-10-24 application-owned registry boundary (latest)

Production now obtains acquisition specifications from `ai_acquisition_registry.TRUSTED_CATALOGS`, a source-owned tuple of reviewed registrations. Each registration pins a catalog path below `config/acquisition` and its canonical fingerprint; model registrations additionally pin the exact profile path/SHA/kind. Runtime uses the existing full runtime validator, model uses its bound layout validator. No runtime HTTP path, preferences/environment override, directory scan or downloaded document can add a registration. Missing/changed/unsupported metadata disables optional downloads and records a sanitized error class in the backend log; basic library startup continues. `config/acquisition` is copied into release inventory when present.

The tuple intentionally remains empty. To publish a real environment: audit publisher/artifacts/complete NOTICE, build a fixed draft with the appropriate builder, review the exact files/URLs/hosts/license/bytes and profile, place the reviewed JSON below config/acquisition, then add a source registration with that exact fingerprint/profile SHA. A catalog's fingerprint is integrity binding, not independent publisher authentication. No made-up product URLs/hashes or automatic registration from builder output.

Generated registry6 PASS and real owned-backend startup/EOF1 PASS in the initial8-test run; that run had1 staging-fixture ERROR (wrong expected manifest filename, raw retained). Corrected staging assertion1 PASS/0.779s confirms the config is copied and SHA-covered. Registry tests cover empty/no discovery, unlisted files, catalog/profile changes, validators, duplicate/unsafe path/HTTP refusal. No external transfer, GUI/GPU, installed Alpha or normal DB changes.

## 2026-10-24 published version → explicit setup (latest)

The download dialog now carries the completed version's root and catalog kind into the existing environment dialog. A read-only acquired location and explicit use button avoid copying the path or opening a folder picker again. No setting is saved on navigation; the use button starts the same owned setup validation/save job and applies only at next restart. Runtime packs and parent models folders stay separate. The shortcut is offered only for complete/published/all-bytes-verified jobs whose ID/capacity still match the catalog, independent of the current ComboBox choice. Failed/cancelled/unverified jobs and removed catalogs provide no shortcut. Existing manual pick/reset/cancel paths remain.

Core985 assertions PASS; Portable build0 errors/3 existing WUI1001 warnings,23.82s. WinUI code review: existing standard controls/theme/spacing, named automation targets, lifetime/revision cancellation and background owner job retained; no model loading/CPU hashing on UI thread and no new reflection bindings. Existing Japanese string convention retained; app-wide resource localization is not added. No native GUI invocation/acceptance and no cap consumed. Raw logs: `acquired-selection-core.log` / `acquired-selection-build.log` under the current generated evidence folder.

## 2026-10-24 model catalog/layout preparation (latest)

`tools/build_ai_model_catalog.py` now prepares a draft from one explicitly selected model directory and an app-owned embedding/WD profile. It preserves the directory below the published models root, so the existing-folder setup can select the returned root without moving/renaming files. It hashes files once, checks source identities/inventory again, requires included license/NOTICE payloads and explicit HTTPS source/hosts/license metadata, and creates a new output only. It never changes source profiles/models/settings, runs a selected interpreter, downloads, or registers a product catalog.

`app/ai_model_pack.py:model_validator(profile,catalog)` binds a fixed profile/revision/layout to an app-owned acquisition specification. Existing acquisition verifies all file sizes/SHA/inventory first; the validator checks bounded metadata, provenance/revision marker, configuration/tokenizer and single/sharded weights before publication. WD's two artifact sizes/SHA must match its existing fixed profile; a catalog cannot silently replace them. No remote code or pickle/ONNX/model execution. Structural validity is not inference quality, publisher authentication or license approval. A supplied LICENSE file is required but does not by itself prove redistribution rights.

Developer syntax:
`python tools/build_ai_model_catalog.py --model-directory <one-model-folder> --profile <reviewed-profile.json> --profile-kind <embedding|wd> --output <new-catalog.json> --id <model-pack-id> --base-url <immutable-HTTPS-model-directory> --license <reviewed-license-summary> --license-url <official-NOTICE-URL> --allow-host <publisher-host>`

The source folder must already contain the exact existing provenance marker (`aredoko-revision.txt` or WD `aredoko-source.json`) and LICENSE/NOTICE; the tool does not invent missing provenance or fetch it. Profile revision supplies catalog revision. Publisher URLs/NOTICE and complete adapter-specific assets still require operator review before source registry registration. The production registry remains empty: no real model or runtime download is enabled by this change.

Generated CPU9 PASS/1.066s: single/sharded layout, WD exact definition/provenance, metadata duplicates/unsafe shard/missing tokenizer/revision/license, source hardlink/change/cancel, host boundaries, non-overwriting output, loopback acquisition → validation/publication → explicit models-root selection while preserving settings/source. Repeat acquisition rejects corrupted published weights without network/replacement. Existing acquisition/job/runtime-catalog25 PASS/13.708s separately; no GUI/GPU/model execution. Evidence: ignored `data/ai-ui/active-selection-20261024-01/model-pack-*.log` and tracked tests.

## 2026-10-24 reproducible runtime catalog preparation (latest)

Developer-only tools/build_ai_runtime_catalog.py prepares a draft catalog from one explicitly selected sealed pack. Full existing LD3 validation is reused; entries and hashes come from the verified inventory, including its marker, rather than hashing all PyTorch files again. Explicit HTTPS base/immutable revision/license/NOTICE link/allowed hosts are required, paths URL-escaped, exact inventory and normal-path rules retained. New output only, outside source pack, exclusive creation; no download/upload/selected interpreter execution/source edit/automatic product registry insertion. A failed output may remain as evidence and is not registered.

Generated pack tests5 PASS/0.888s: all files/marker/checksums/source SHA+mtime, corrupt/unlisted rejection, URL escaping/host boundary, existing-output preservation/pack overlap and cancellation. No actual5GB pack read or licensing approval claimed. Source configuration and distribution provenance still require operator review; checksum inventory does not authenticate publisher or establish rights to all bundled dependencies. Runtime catalog can be hosted only after actual pack/NOTICE/public URL are ready, then its fingerprint plus app-owned validate_runtime must be registered in source.

Preparation syntax (developer build, not user setup UI):
`python tools/build_ai_runtime_catalog.py --runtime-root <sealed-pack> --output <new-catalog.json> --id <pack-id> --revision <40-or-64-hex> --base-url <fixed-HTTPS-directory> --license <audited-license-summary> --license-url <official-NOTICE-URL> --allow-host <publisher-host>`
Additional redirect/CDN hosts must be explicitly listed with repeated --allow-host. Do not add guessed endpoints or bypass source checks to make a transfer pass. Model catalogs use the separate model-layout tool above; the runtime tool intentionally does not infer one.

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

Source connects AI environment → app acquisition: trusted catalog metadata/capacity/license, explicit consent, default unlimited or optional MB/s cap, separate received/verified bytes, current-job cancel, retry/resume, dialog close/reopen and published root. Selected settings/active model do not change automatically. Published version can now be passed explicitly to the existing-folder entry as described above. Native catalog uses direct ComboBoxItem controls, not reflection-bound generic ItemsSource; lifetime/revision/busy protect stale replies and in-flight close. Same published catalog cannot be reacquired from the current UI state.

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

## 当初の残件（履歴：現在の再開位置はcurrent-handoff）

1. 配布元・固定artifact・license/NOTICEを確認した製品catalogを作成。runtime packの公開先は未用意、推測URL/架空ハッシュで有効化しない。
2. Core/既存「AI検索の準備」へcatalog一覧・容量/ライセンス確認・実進捗・中止・再開を接続。既存配置選択LD4aも同じ入口へ。公開versionを明示選択して次回起動設定へ保存する。
3. 新しい具体候補で許可されたGUI/実取得/clean Windows確認へ進む。既存capを別名で再実行しない。外部artifact実取得は対象/容量/取得元を示して許可が必要。

WDの既存固定hash/サイズはconfig/tagger-profilesに存在し、[固定revisionのモデルカード](https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3/blob/627aef95638667ddcaa3ac8ae625e88ea5b02f51/README.md)のApache-2.0 metadataを読み取り再確認した。これは取得を実行した証拠でも、全依存の配布notice整備済みという意味でもない。


## モデル別保存先・固定catalogとの接続（2026-10-24、P6）
- `model_locations` は最大32個の `(role, model_id, revision, directory, root)`。物理配置をベクトルnamespaceから分離し、同じ重みのprompt違いで索引を混同しない。解決順は完全一致→役割root→共通root→従来default。現在workerを変更せず次回起動で反映。
- 所有setup APIへ `model_target`（固定4項目）または `model_role`＋`models_root` を明示送信する。完全一致指定/resetはそのモデルだけ、役割指定/resetは当該役割内の個別指定だけ、従来の共通指定/resetは全個別・役割指定を解除する。取消/失敗は旧設定を保全。
- catalog summaryはsource所有の`ModelPackValidator`からのみ`model_target`/正規化定義SHA256を返す。kind/nameから役割を推測しない。validatorと別catalogの組合せは拒否。raw profile SHAのregistry pinと定義SHAは用途が異なる。製品registryは引き続き0件、実取得なし。
- CPU証拠：`data/ai-ui/active-selection-20261024-01/model-placements-initial.log` 34件PASS、`model-binding-related.log` 38件PASS（別実行）。生成fixtureのみ、非実行dispatcher spy、P5復元ready後の一時override解除でもmodel_locationsを保全。Core/native接続は別の後続単位で記録する。


### Core／nativeの役割・モデル選択（同日）
- Coreはmodel_target/定義SHA/役割/revision/安全な相対directoryを検証する。旧unbound model catalogは取得表示を維持するが適用shortcutを出さず、役割を推測しない。runtime経路は従来通り。
- 配置画面は手動選択の対象（共通・検索・WD・意図）を明示し、共通/resetの影響を説明する。取得完了ボタンはsource-boundの完全一致モデルだけへ適用。開いただけ・対象変更だけでは保存しない。現在のprofile/namespaceを勝手に切り替えない。
- Core `1003` assertions PASS、Portable build errors0（既知WUI1001×3）/publish成功（既知SDK IL2104×2）。`model-binding-core.log`/`model-roles-winui-build.log`/`model-roles-publish.log`（同じactive-selection証拠directory）。
- native候補 `data/ai-ui/ai-model-selection-20261024/frontend01`。source `8db7c2f`＋reportの正確なdiff SHA、frontend SHA/source一覧を保存。生成WD422 bytesのみloopback配信、実モデル/GPU/新依存0。旧Alpha/通常DB/shortcut変更0。
- `data/ai-ui/ai-model-selection-tagger-20261024/run01/report.json` はFAILのまま保全。モデル保存・他役割保全は成功したが、画面再表示ハーネスがライブラリへ戻った後に存在しないBtnAIIndexを直接探した。6 PNG目視・所有app正常終了0。Settingsを開き直す実修正後run02は全チェックPASS、5 PNG全目視、app0/所有process残存なし・検査用runtime実行0。対象dropdownのpopupをEscで閉じる観測手順も明示。
- 手動role/common resetと取消の保存保全はCPU/Coreで確認。nativeはWDの明示適用・モデル2個を含む他設定保全・対象切替・再表示に限定。実推論/完全配布受入は未実施。


### 次回モデル候補の配置判定
- AIProfileSettingsは次回候補ごとに`model_locations`を解決する。起動中の実保存先と候補のfallback rootを混同せず、保存先追加後にプロフィール一覧を開き直しても別モデルの準備状態を正しく表示する。起動時active定義・namespaceは不変。
- `pending-model-locations.log`44件PASS（モデル配置・profile設定・P5 active/pending復元）。2種類の検索モデルを別rootへ置き、片方をresetしてももう片方の準備状態を保全。通常起動dispatcherと復元readyの既存関連確認を含む。全回帰ではない。
- 同じnative候補frontend01＋backendは後続差分の状態で、生成embeddingモデルのLight経路も`ai-model-selection-embedding-20261024/run01`で全チェック・終了0。他の2モデルとWD等の設定保全、個別適用・scope切替・再表示を確認。source一覧/差分SHAはreportに記録し、WD時点と混同しない。実推論/起動後workerへの反映はこのGUIテスト範囲外。


### 個別モデルの配置選択（2026-10-24）
- 配置先対象に保存済みの個別モデルと取得対象も追加し、そのモデルだけの指定/解除が可能。acquiredの保存後は同じモデルのpending rootを表示し、共通rootと混同しない。選択肢は設定の最大32件＋取得対象まで、ファイル走査なし。Tagへはstring keyだけを渡し、Core定義はmanaged dictionaryで保持。
- frontend02/embedding run02は追加UIのrefreshで選択中項目をremove/recreateし共通選択へ戻るFAIL。初期のTag ABI仮説だけを直したfrontend03/run03でも同FAILであり、確定原因と混同しない。両raw/reportを保全（run03 failure PNGは小さく視覚証拠にならず、他4 PNGとUIAを使用）。モデル保存自体は両方成功。
- 診断後はnative項目を置換せず、足りないbounded選択肢だけ追加する方式へ修正。frontend04/embedding run04で全チェックPASS、5 PNG全目視、保存後の正確なroot表示/他役割保持/再表示/終了0を確認。手順上限を無変更で抜け直した再実行ではなく、追加した選択UIの回帰・実修正の履歴としてrun01〜04を保持する。既存WD役割UIのrun02 PASSは別時点の結果。


### 直接取得入口の限定native受入（2026-10-25）

基本ZIP03/source5ddd97aの通常EXEから、新しい `AIModelDownloadOpen` を明示操作して取得画面へ直接遷移できた。生成DB/画像だけで容量・ライセンス・runtime別途必要表示、未同意では開始不可、転送owner idle、正常終了/予定内1再起動、設定と全payload保全を確認。11 checks PASS / 4所有exit0 / 2 PNG目視。旧環境配置経由とWD切替の反復ではない。新しい実転送/モデル実行/GPUはなし。[候補と証拠](portable-refresh-20261024.md)。

任意runtimeの通知原文収集・source binding・pack同梱は `5ddd97a`。[不足と確認範囲](runtime-notice-inventory.md)を参照。runtimeを自動取得できる状態にはまだしていない。


### 宣言サイズ前のEOFも限定再接続（2026-10-25）

peerが例外なしで短いbodyを閉じた場合も `IncompleteRead` として既存の最大2回再接続へ接続する。ディスク等の一般OSErrorは対象に広げない。実loopback HTTPの70,000 bytesでの切断→Range `bytes=70000-`→全hash一致を新規確認。継続切断は上限後に未公開の部分を保持、次の明示再開/Range無視の再取得も保持する。通信関連6・既存取得14 tests PASS（別実行）。実2GB転送の反復はしていない。基本ZIP03/source5ddd97aにはこの最終EOF補強は未収録。
