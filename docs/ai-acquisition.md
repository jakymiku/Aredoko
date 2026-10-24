# LD4b：任意AI環境の取得基盤（2026-10-24）


旧2/2・3/3等は当時の履歴。新機能/有意味な修正の通常検証は[現行テスト方針](local-test-policy.md)に従う。現在の次の1件は[current-handoff](current-handoff.md)を優先する。

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
