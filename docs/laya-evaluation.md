# Laya evaluation before integration

Status: planned experiment, not implemented inference (2026-10-12). EmbeddingGemma 2 is already the retrieval engine. Laya would suggest which existing retrieval mode fits a query. Do not equate package documentation or confidence with validated Japanese accuracy.

## Runtime candidate

Use upstream PyTorch Laya, initially release 0.4.2 plus a pinned `convaiinnovations/laya-multilingual` checkpoint. The original laya-mlx targets Apple Silicon. Verify local-path loading/offline behavior before any GUI integration. Never use an unrestricted lazy Router that may fetch other checkpoints.

The current package metadata declares torch >=2.0 and transformers >=4.48, so the existing project environment is a candidate, not a tested compatibility guarantee. Freeze existing dependencies and reject a setup that would replace them. Reuse the shared 6,000,000 bytes/s HTTPS proxy for any explicitly approved package/model setup. Pin model revision and inventory exact download size first; local files stay ignored. No model or package download was performed in this investigation.

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
