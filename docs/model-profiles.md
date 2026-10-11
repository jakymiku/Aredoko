# Swappable embedding models

Aredoko chooses a validated local embedding profile at startup. The default remains EmbeddingGemma 2. A compatible derivative can be selected without rewriting catalog, API, GUI or ranking code. A model with a different architecture needs a registered adapter; arbitrary models are not guaranteed to load.

## Selecting a profile

Copy config/ai-profiles/embeddinggemma-2.json into an ignored local directory such as data/ai-profiles/custom.json. Edit the model ID, immutable revision (40-character commit SHA or 64-character content hash), model directory, label, dimension and supported inputs to match the actual model. directory is relative to models and cannot escape that directory. Use a different directory for different weights/revisions.

Stop Aredoko and launch:

    pwsh -File tools/start-winui.ps1 -AIProfile data/ai-profiles/custom.json

Omit -AIProfile to return to the original model. Selection takes effect on restart; no hot swap can race an in-flight index job. The AI索引 dialog shows the active model, input capabilities and its own progress. For a new profile, click 索引を作成・更新. Existing tags, shelves, favorites and file catalog remain shared.

The backend also supports --ai-profile. Invalid settings disable optional AI while literal search remains available.

## WinUI 3での選択（2026-10-12追加）

**「AI索引」→「次回起動で使用するAIモデル」** からモデルprofileを選べます。通常の文字検索はいつでも利用可能です。

- 選択肢は既定のEmbeddingGemma 2と、`data/ai-profiles/*.json`（ignoredのローカルJSON）のみ。既存の`config/ai-profiles/embeddinggemma-2.json`を複製したファイルをローカルフォルダへ置き、モデルの情報を編集します。**GUIはモデル自体をダウンロードしません。**
- 対応adapter・identity等のスキーマは `app/ai_profiles.py` が一元検証します。無効なJSON・不明なadapter・逃避パス・リンク先のモデルprofileは選択禁止。重みフォルダ、`.venv-ai/Scripts/python.exe`、`aredoko-revision.txt`の不足やリビジョン不一致は、モデル選択画面に警告を表示。検出できた場合でも実モデルのロード成功までは保証しません。
- モデルを選び「次回起動に設定」を押すと、`%LOCALAPPDATA%/Aredoko/settings.json`（デフォルト）へ**原子的に保存**します。現在のworkerとベクトル索引は**そのまま**。**Aredokoを閉じて起動し直す**と新しいprofileが有効になります。既定モデルへ戻す場合は同じ欄で既定を選び直してください。
- **優先順位は明示 `-AIProfile <JSONパス>` ＞ GUIの保存済み選択 ＞ 既定profile**。毎回 `-AIProfile` を付けて起動した場合、GUIの選択は保存されても優先されません。引数を外して再起動すると反映します。
- 起動時に保存profileが消失・JSONが無効なら、そのAI機能を無効にして**文字検索を維持**。GUIのモデル選択画面で修正方法を案内します。既定へ戻すと設定を復旧できます。起動引数で有効なprofileを明示した場合は破損した保存済み選択より優先されます。
- 既存のvector identityとprofile別SQLite索引は変えません。新profileへ切り替えたら必要に応じ「索引を作成・更新」。旧profileへ戻れば以前の対応する索引を再利用できます。text-onlyモデルは画像/表紙の入力に非対応なので、AI画像・表紙では既存の非対応メッセージが表示されます。
- profile選択APIは `GET /api/library/ai/profiles` / `POST /api/library/ai/profile`（body `{"id":"default"}` または `{"id":"local:custom.json"}`）。既存のlocalhost／トークン／Origin境界を維持し、POSTは候補IDしか受け取りません。任意ファイルパスやPythonモジュールをPOSTさせず、remote codeも読みません。
- テスト専用の設定パスはサーバー `--ai-settings <path>` で指定可能。デフォルトの個人用設定をテストで汚さないためのものです。自動ダウンロード・hot swap・LayaのGUI統合は実装しません。

## Supported adapters

- embeddinggemma2: compatible EmbeddingGemma 2 Sentence Transformers exports; text and optional image/cover inputs. Audio is unloaded; a text-only profile also unloads vision. Named task prompts default to SearchQuery and Document.
- sentence-transformers: conventional text-only Sentence Transformer exports, with their actual vector dimension and prompt names or explicit prefixes. Set modalities to ["text"]. This is a generic loading contract; no additional model has been downloaded or validated on this PC.
- Other architectures: add a registered class in app/ai_adapters.py exposing dimension, encode_text and encode_image, then extend profile validation and tests. Neither arbitrary Python module paths nor remote model code are accepted. Laya will have a separate decision interface; its decisions are not embedding vectors.

Prompt names and explicit prefixes are mutually exclusive. To use a prefix, set the corresponding prompt name to null. Empty explicit prefixes intentionally disable model-default text prompts. Precision supports auto-bf16 (CUDA bfloat16 when available, float32 otherwise) and float32. Float16 is not supported.

## Index compatibility and rollback

Vector-space identity includes model ID, immutable revision, adapter, dimension, modalities, query/document prompt settings, precision and the preprocessing contract. Changing any of these selects a separate sibling AI SQLite database. Same dimension alone never makes two models compatible. Worker startup must echo the exact identity and actual dimension, and all returned vectors are validated.

Cosmetic labels and relocating the same weights do not change identity. The exact default profile retains the original <catalog>.ai.sqlite and its legacy identity: no initial rebuild required after this application upgrade. Other profiles use <catalog>.ai.<identity hash>.sqlite. Their stored full identity is also checked. Legacy recognition is frozen to the historical settings, independent of future default changes. Changing preprocessing requires bumping VECTOR_CONTRACT and then selects a new store even for the original model.

Switching back reuses the previous index; source/title/tag revision checks still exclude stale records. Old indexes are preserved for rollback and consume disk until explicitly managed. Raw cosine scores from different profiles are not mixed or compared as calibrated probabilities.

## Preparing local weights

Runtime is offline, local-files-only, with remote code and telemetry disabled. Switching does not download or install anything. For an explicitly approved new model setup:

    pwsh -File tools/setup-ai.ps1 -AIProfile data/ai-profiles/custom.json

Inspect the profile/model size first. The next command opts into installation/download:

    pwsh -File tools/setup-ai.ps1 -AIProfile data/ai-profiles/custom.json -InstallAndDownload

The existing project-local dependency pins and shared aggregate 6,000,000 bytes/s proxy also apply to custom downloads. No new setup/download was performed for this feature. The downloader records model ID/revision before retrieval to allow interrupted setup to resume, and rejects overwriting another revision in the same directory.

Already installed exports need an aredoko-revision.txt marker containing the declared immutable revision. A manually altered checkpoint must use a new revision/content hash and a separate directory/profile. The marker is a user-managed provenance declaration, not a cryptographic verification of all local weights.

## Validation

Known-vector tests cover different dimensions and same-dimension revisions, identity changes, wrong worker handshake, source capabilities, malformed/oversized settings, prompt routing and interrupted-download guards. They are protocol evidence, not model quality evidence.

The actual local-model test tools/test_ai_profile_switch.py uses existing weights in default text+vision and text-only float32 profiles, then switches back without rebuilding. This validates loader/config/cache switching on CUDA, not an unreleased derivative or a second independent model. Generated filenames only; source hashes unchanged.

[Sentence Transformers API](https://sbert.net/docs/package_reference/sentence_transformer/model.html) documents local loading and prompt options.
