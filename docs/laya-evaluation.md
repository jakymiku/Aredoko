# Laya evaluation before integration

Status: offline runtime, suggestion-only API and two rounds of actual GPU evaluation implemented (2026-10-12). Latest question/order experiments are recorded at the end; earlier sections describe the first round. The GUI integration gate is not met; automatic routing/filtering remains disabled. EmbeddingGemma 2 is already the retrieval engine. Laya would suggest which existing retrieval mode fits a query. Do not equate package documentation or confidence with validated Japanese accuracy.

## Runtime candidate

Use upstream PyTorch Laya, initially release 0.4.2 plus a pinned `convaiinnovations/laya-multilingual` checkpoint. The original laya-mlx targets Apple Silicon. Verify local-path loading/offline behavior before any GUI integration. Never use an unrestricted lazy Router that may fetch other checkpoints.

The current package metadata declares torch >=2.0 and transformers >=4.48, so the existing project environment is a candidate, not a tested compatibility guarantee. Freeze existing dependencies and reject a setup that would replace them. Reuse the shared 6,000,000 bytes/s HTTPS proxy for any explicitly approved package/model setup. Pin model revision and inventory exact download size first; local files stay ignored. The user explicitly authorized setup for this experiment; setup and the measured results are recorded below.

## Bounded questions and fallback

- Retrieval intent: `cover` for appearance/color/cover descriptions; `text` for filename/creator/tag recall; `mixed` for semantic content or uncertain requests.
- Suggested kind: `book`, `image`, `audio`, `video`, `archive` or `any`. Keep this as a visible suggestion initially. An incorrect guess must not hide the only relevant hit.
- Explicit user mode/kind wins. Empty query uses normal browsing. Missing model, timeout, malformed response or ambiguous decision returns the existing EmbeddingGemma behavior.
- Keep scores as experimental evidence. The model card describes overconfidence and uncalibrated probabilities; do not apply an arbitrary threshold and call it reliable.

## Evaluation set

Prepare at least 30 synthetic Japanese requests with expected intent/kind, including paraphrases, mixed requests and ambiguous examples. Examples for the fixture and later expanded synthetic set:

| Request | Expected intent | Expected kind |
| --- | --- | --- |
| 青い画像 | cover | image |
| 赤い表紙の本 | cover | book |
| タイトルに雨が入っていた音楽 | text | audio |
| 作者名で探したい同人誌 | text | book |
| 傘が必要な暗い都会の景色 | mixed | any |
| 夜っぽいやつ | mixed | any |
| 青い表紙の本か、青い写真 | cover | any |

Measure classification confusion, warm/cold latency and memory on this PC. Compare actual retrieval top hits with fixed manual modes and EmbeddingGemma mixed mode. Include a held-out subset before choosing any confidence policy. Typed intent accuracy and retrieval ranking improvement are separate results; neither is a substitute for evaluation on explicitly selected personal samples.

## Integration gate

Only expose an optional “おすすめの検索方法” after local offline inference and fallback tests pass, Japanese suggestions improve the benchmark, and errors leave manual search usable. Do not auto-filter user results in the first integration. Model downloads need explicit setup authorization under AGENTS.md; existing permission covered EmbeddingGemma 2 only.

## Primary references

- [Upstream README](https://github.com/NandhaKishorM/laya): typed decisions, Windows setup and lazy Router behavior.
- [Package metadata](https://github.com/NandhaKishorM/laya/blob/main/pyproject.toml): declared dependency floor and release version; documentation prose mentions newer torch while the package floor is lower.
- [Multilingual model card](https://huggingface.co/convaiinnovations/laya-multilingual): language support and calibration limits.
- [Agent implementation](https://github.com/NandhaKishorM/laya/blob/main/laya/agent.py): inspect local model construction and tokenizer fixup before implementation; fixup can alter model cache files, never media sources.


## Implemented runtime and explicit setup

Embedding providers still produce vectors. The independent SearchIntent provider returns two typed decisions and never edits a search request. app/search_intent.py defines the bounded questions, answer contract and fallback; app/laya_process.py owns a private inference child, and app/laya_worker.py loads only a validated local checkpoint. No Router or automatic checkpoint selection is used.

- Package: laya 0.4.2, wheel 380,522 bytes, fixed SHA256.
- Model: convaiinnovations/laya-multilingual, revision 1720e3e3357cfe1e281542e223f8273b0890ca34. Five runtime files total 678,201,614 bytes; every original artifact has a pinned size/digest.
- Existing torch 2.9.1+cu128 / transformers 5.19.0 / other packages remained unchanged. Install uses --no-deps, fixed wheel hash, inventory comparison and pip check. No system or driver changes.
- tools/setup-laya.ps1 without switches prints the plan and performs no install/download. With -InstallAndDownload it reuses the aggregate 6,000,000 bytes/s proxy and verifies provenance, checkpoint integrity and interrupted-download resume. Source/revision markers stay under ignored models.
- Measured authorized setup: 679,568,032 TLS bytes, 180.14 seconds (includes package installation/verification), aggregate cap enabled. Only Laya was added; pip check passed.
- Upstream converts tokenizer extra_special_tokens from a list into a mapping in the local model cache. Validation permits this exact compatibility change only when the entire reconstructed original config matches its pinned digest. The first restart test exposed this and the validator was corrected. No source media are touched.
- Worker has offline HF/transformers settings plus a Python socket connection guard. Observed blocked connection attempts were zero. This is application enforcement, not an OS firewall or network trace; no OS settings changed.
- Query max 300 characters, JSON response max 32,768 characters, one active decision, no queued work, cold startup timeout 60s / warm inference timeout 5s, failure cooldown 30s. Unexpected labels/probabilities/non-finite values/truncated input yield no suggestion. Scores are explicitly uncalibrated.
- On Windows a venv redirector can own a separate real interpreter. The worker monitors both its immediate OS parent and the API owner; timeout kills the owned redirector and ends the real worker. Its own PID is used for memory measurement. Owner-exit/timeout checks passed.

Run from the repository:

    pwsh -File tools/setup-laya.ps1
    pwsh -File tools/setup-laya.ps1 -InstallAndDownload
    .\.venv-ai\Scripts\python.exe tools/evaluate_laya.py --output data/laya-evaluation/new-run
    python tools/test_laya_api.py --output data/laya-evaluation/new-api-run

Output directories must be new and contain generated evidence only. The benchmark creates its own 17 fictional files and compares source hashes; it does not discover personal folders. Setup and evaluation are separate explicit commands. Evaluation does not download a missing model.

## Experimental API

Enable with backend --laya-intent, or tools/start-winui.ps1 -LayaIntent. Normal launch leaves this provider disabled. Even when enabled, it loads lazily on an explicit suggestion request, not while searching or listing. The GUI currently has no suggestion control; existing manual modes remain unchanged.

- GET /api/library/intent/status requires the session token, starts no worker, and reports enabled/available/device/experimental/applies_automatically.
- POST /api/library/intent/suggest requires the existing session token and exact loopback Origin. Body: query, source (all/text/cover), kind (empty or any existing catalog kind, including material). The current classifier has no material output label; that does not limit or change an explicit material filter. Invalid query/settings return 400.
- Response always preserves requested source/kind. It separately returns an experimental suggestion (intent/source/kind/uncalibrated scores) or null with state empty/disabled/unavailable. It never calls retrieval, overrides the explicit source or applies a guessed kind filter.
- A missing/failed/busy model does not cause a 503 search failure; the suggestion endpoint returns null, while normal literal/EmbeddingGemma endpoints continue unchanged. A cold suggestion can take about 13 seconds; callers must show cancellable progress before any future GUI integration.

## First actual Japanese results

Frozen fixture: tests/fixtures/laya-ja-queries.json, 36 synthetic requests (24 development + 12 held-out). Question definitions and expected labels were fixed before evaluation; no prompt or threshold tuning was performed using these results. Repeated executions checked runtime fixes only, and returned the same classifications. These hand-authored requests are not a representative accuracy estimate for the user's media library.

| Split | Intent correct | Kind correct | Both correct | Runtime unavailable |
| --- | --- | --- | --- | --- |
| Development | 16/24 | 16/24 | 9/24 | 0/24 |
| Held-out | 10/12 | 6/12 | 5/12 | 0/12 |
| Total | 26/36 | 22/36 | 14/36 | 0/36 |

The model sometimes guesses archive for manga or unspecified files, and cover for filename/tag/audio-mood requests. An ambiguous request being assigned a high score does not make that guess reliable. Kinds must stay suggestions; this experiment does not justify automatic filters.

On this RTX4070Ti: cold first request 13,133ms, warm median 40.65ms / p95 43.78ms across the remaining 35 requests. First inference includes additional GPU initialization. PyTorch peak allocated GPU memory 1,501MiB is not total GPU/driver usage. The real interpreter used 1,965MiB Working Set, 2,707MiB peak Working Set and 5,766MiB Private Bytes (committed private memory, not all resident RAM). An earlier measurement accidentally sampled the small venv redirector; that 3MiB result is invalid and superseded. CPU, quantization and idle unload are untested.

Retrieval comparison used 17 generated records and six fixed queries, with explicit kind unchanged. Laya's source suggestion was applied only inside this benchmark. Mixed, manually chosen source and suggested source were each evaluated separately:

| Query | Expected first hit | Mixed rank | Suggested-source rank |
| --- | --- | --- | --- |
| 青い画像 | image-01.png | 1 | 1 |
| 赤い表紙の本 | book-03.cbz | 2 | 1 |
| 青い表紙の本 | book-01.cbz | 1 | 2 |
| 傘が必要な暗い都会の景色 | generated rainy-city filename | 1 | 1 |
| 雨の夜の街並みという名前の音源 | generated rainy-city filename | 1 | 1 |
| 晴れた昼の海辺という名前の音源 | generated sunny-shore filename | 1 | 1 |

One case improved and one regressed: top-1 success stayed 5/6. This does not demonstrate overall retrieval improvement and does not meet the GUI gate. Generated files' hashes stayed unchanged; no private media were scanned. Current text-only handling of audio/video contents is unchanged.

Evidence stays local/ignored: data/laya-setup/result.json, data/laya-evaluation/first-03/result.json, data/laya-evaluation/api-01/result.json. first-01 records the initial tokenizer-validator failure; first-02 predates the real-interpreter memory fix.

Actual HTTP/lifecycle check passed: literal request during cold Laya startup 12.78ms, concurrent suggestion fallback 5.76ms, exact manual settings preserved, forced inference timeout left literal catalog usable and stopped the real interpreter, and abrupt owner exit also stopped it. No model worker remained afterward. GUI was not changed or operated for this backend-only experiment.

## Next decision

Keep the experimental provider opt-in. Improve question/option wording on development examples, add option-order/abstention checks and a fresh held-out set before choosing a policy. Compare against an EmbeddingGemma-only baseline and simple explicit cues as well. Require measured retrieval benefit before adding a user-confirmed GUI suggestion; improve retrieval scoring separately because choosing cover alone can also worsen a color query. Never reuse this evaluated held-out set as an unseen accuracy claim after tuning.

## 日本語質問・順序棄権の第2回評価（2026-10-12）

既存24文＋新8文をdevelopment32、過去held-out12をlegacy-regressionに改称、新しい24文をheld-out-v2として候補比較前に固定した。fixtureは `tests/fixtures/laya-ja-v2.json`。過去の12文も今回の24文も今後「未見」として再利用しない。

`app/intent_questions.py` にv1/短い英語v2-en/短い日本語v2-ja/旧intent＋日本語kindのv2-hybridを登録。kindに素材のmaterialを追加した候補を比較。質問文・選択肢順序のSHA256とorder-check設定をworker handshakeへ含める。v2判断契約は旧workerを誤接続しない。各質問を通常順／逆順で推論し、不一致のheadだけintent=mixed / kind=anyへ棄権する。確率は未校正のままで閾値を設定しない。同順で一致しても正解保証ではない。

さらにモデルがcoverを提案しながらaudio/video/materialと判断した場合は、その種類に現在cover vectorがないためintentのみmixedへ棄権する。モデル自身の提案の整合性確認であり、ユーザーの手動source/kindは変更しない。名前やタグの内容に対する拒否ではない。

developmentでは英語/日本語へ質問全体を置き換えるとintentが悪化したため、v2-hybrid＋上記棄権を選んだ。raw/effectiveの違いは、effectiveが棄権後の値を含むこと。棄権が期待mixed/anyと一致しただけの正解を、モデルの確信した正解と混同しない。

| development32（順序確認あり） | intent raw/effective | kind raw/effective |
| --- | --- | --- |
| v1（種類矛盾guard追加前） | 21 / 22 | 20 / 21 |
| v2-en（同上） | 17 / 14 | 15 / 19 |
| v2-ja（同上） | 16 / 14 | 21 / 24 |
| 選定hybrid＋種類矛盾guard | 21 / 24 | 21 / 24 |

選定後に新24文へv1とhybridを適用し、以後質問/棄権規則を調整していない。比較v1にも同じ順序・種類矛盾guardを適用した。

| 新held-out24 | intent raw/effective | kind raw/effective | intent 提示数/提示正解 | kind 提示数/提示正解 |
| --- | --- | --- | --- | --- |
| v1 | 17 / 17 | 11 / 12 | 18 / 14 | 21 / 11 |
| v2-hybrid | 17 / 17 | 13 / 15 | 18 / 14 | 18 / 12 |

hybridではintent6・kind6件を棄権。kindは modest improvement、intentは改善せず、棄権後でも15/24・17/24でGUI採用条件未達。新しいGUI提案・自動モード変更・種類の自動絞込みは追加しない。

既存の明示 `--laya-intent` / launcher `-LayaIntent` で有効にした実験用APIは、選定hybrid＋順序確認を既定にする。Laya自体の既定起動は無効のまま。再現用に `--intent-questions v1` と `--intent-no-order-check` を用意し、statusで設定を返す。`LayaProcess` 直接構築の既定v1/no-checkは旧開発ツール互換用。`tools/evaluate_intent_v2.py --phase development --output <new-dir>`、次に選定を固定し `--phase held-out --selected v2-hybrid --output <new-dir>`。今回のfresh集合はもう評価済みなので、次回調整後の検証には別集合を作る。

実CUDA hybrid held-out: 冷間12,937ms、warm中央値81.53ms、PyTorch peak allocated GPU 1,506.02MiB、Pythonネット接続試行0。順序確認で2回推論するので旧1回の約40msより増える。全24推論成功。モデル重み/依存関係は変更せず、追加取得なし。

実HTTP新契約PASS: cold中の文字検索10.42ms、競合fallback5.98ms、手動条件保持、order evidence、強制timeoutでreal worker停止・通常検索継続、owner突然終了でもreal worker停止。APIとworker終了をCIMで確認。

混合順位はLayaから独立して改善し既定GUIへ適用した。[ai-ranking.md](ai-ranking.md) に23素材/28条件・下着テンプレート例・実native GUI検証を記録。これはLayaの分類精度が上がった証拠ではない。

証拠（Git対象外）: `data/laya-evaluation/v2-dev-01/result.json`, `v2-hybrid-dev-01`, `v2-hybrid-guard-dev-01`, `v2-heldout-01`, `api-v2-01`。Python90/C#13/Release PASS、旧SDK IL2104警告2件。CPU/量子化/idle unloadは未検証。次は別の未見集合を用意した精度検証と、ユーザーが選んだ実サンプルでの検索順位測定を行う。
