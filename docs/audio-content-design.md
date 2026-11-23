# 音声・音楽内容検索の方式設計と契約 (R06)

2026-10-19 凍結。M2マイルストーン（全媒体の製品版候補）における音声・音楽機能の基本設計書。
本設計は [completion-roadmap.md](completion-roadmap.md) の R06完了条件および [product-vision.md](product-vision.md) に基づき、音声・音楽の入力能力、候補アーキテクチャの比較評価、ベクトル空間の厳格な分離、および時間区間根拠の契約を固定する。

---

## 1. 背景と目的

Aredokoは画像・本・動画に続き、音声・音楽メディア（`.mp3`, `.flac`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.wma`）の内容検索と類似検索をM2で実現する。
音声・音楽の検索要求は本質的に異なる2つの次元から構成される：
1. **言語的・意味的内容（発話・会話・歌詞・ナレーション）**：ユーザーが日本語テキストクエリ（例：「おはよう」「会議の報告」「事件の真相」）で検索し、該当する音声ファイル内の発話箇所（秒単位の時刻）へ直接シークして再生する。
2. **音響的・音楽的特徴（効果音・環境音・音楽の雰囲気・楽器・音同士の類似）**：発話を含まない雨音、爆発音、ジャズピアノ、アコースティックギター、BGMの雰囲気検索、および「この曲に似た曲」「この効果音に似た素材」というアイテム起点類似検索。

これらを混同して単一の空間で扱おうとすると、無音やノイズがテキストクエリに誤ヒットする「意味の捏造（Hallucination）」や、逆に発話の文字情報が音楽類似を狂わせる問題が発生する。本設計書ではこの分離契約を工学的に確定する。

---

## 2. 実入力の方式選定は未完（2026-10-20訂正）

以前の構造調査ではローカルconfig/重みに音声関連部分があり、現在のアダプターでは音声towerを無効化していると記録されている。これは入力能力や品質、実VRAMを測った証拠ではない。構造から「環境音や音楽の能力なし」「追加1.5〜2.0GB必須」「別方式は完全/追加VRAM0」と断定した旧比較は撤回する。

候補Aは既存EmbeddingGemma 2への直接音声入力、候補Bは発話抽出→既存テキスト埋め込み＋別の音響特徴抽出。まず既存環境でAPI/波形入力/出力空間/時間根拠を確認し、生成または許可済み音声で発話・環境音・音楽・類似の4軸を比較する。新モデル/依存の取得は明示許可後。R06/R08方式選定はAstra推奨だが、自動切替/別agent起動の指示ではない。

## 3. 実装済みの保存・検索契約

768Dの発話テキスト意味空間（`audio-speech-segment:v1`）と512Dの音響特徴空間（`audio-acoustic-feature:v1`）を分離した保存/比較APIは実装済み。異なる空間を混ぜずに保持する。512Dは現在のadapter契約であり、今後採用するモデルを無条件でこの空間へ押し込まない。実producerのモデル版/前処理/次元/由来と既存profile・鮮度・バックアップ互換を確認する。

## 4. R07/R08/R09の現在地

- R07：供給済み発話/区間/ベクトルの保存と意味検索・時刻/スニペット表示は実装。録音→PCM→発話抽出→通常索引のproducerは未実装。
- R08：供給済み音響ベクトルの類似計算と保存記述子の文字照合は実装。元音声/曲からの特徴・記述子自動生成は未実装。
- R09：名前/タグ検索、音声プレイヤー、保存済み特徴への類似検索/時刻接続を維持。実音声内容からの検索→再生受入はR07/R08待ち。
- 旧GPU13/GUI5 PASSは硬コード発話を実EG2で埋め込み、人工512D特徴を注入した接続試験。音声理解/無音判定/音楽検索の精度結果ではない。詳細は[監査](polish-audit-20261020.md)。

## 5. 発話区間データ契約とスキーマ設計 (R07仕様)

### 5.1 SQLiteスキーマ (`ai_audio_segments`)

```sql
CREATE TABLE IF NOT EXISTS ai_audio_segments(
    item_id INTEGER NOT NULL,
    source_revision TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL CHECK(start_ms >= 0 AND start_ms <= 86400000),
    end_ms INTEGER NOT NULL CHECK(end_ms >= start_ms AND end_ms <= 86400000),
    snippet TEXT NOT NULL,
    vector BLOB NOT NULL,
    contract TEXT NOT NULL,
    PRIMARY KEY(item_id, segment_id)
);
```

### 5.2 境界値と制約
- **最大継続時間**: 86,400,000 ms（24時間）。これを超える値はスキーマおよびバリデータで拒絶。
- **セグメント長**: 推奨3秒〜30秒（最大60秒）。過度に短い無音（<500ms）は破棄。
- **スニペット長**: 1文字〜1,024文字。空文字や空白のみのスニペットは登録しない。
- **ベクトル形式**: 768次元 float32（リトルエンディアン、3,072バイト）、$L_2$ 正規化済み（$\|v\|_2 = 1.0 \pm 10^{-4}$）。非有限値（NaN, $\pm\infty$）は除外。
- **最大ファイルサイズ**: 512 MiB（`MAX_AUDIO_BYTES = 512 * 1024 * 1024`）。

### 5.3 将来の音声入力仕様（producer未実装）
- サンプリングレート: 16,000 Hz
- チャンネル: 1 (Mono) float32
- 入力パイプライン: FFmpeg/fd 経由で安全にPCM抽出（一時ファイルへのパス出力や外部プロトコル読み込みを完全排除）。

**2026-10-26：共通入力境界を実装**。`PreviewReader.audio_pcm_window(item_id,start_ms,duration_ms,revision,cancel)` は登録済み音声の検証済みhandleから最大30秒/1,920,000bytesの16kHz・mono・float32 little-endianを返す。内部producer用でHTTP routeは追加しない。開始位置/長さは厳密な整数、入力512MiB/24時間以内、FFmpegは既存実行物・fd/pipe・demuxer allowlist・10秒deadline・既存preview2slot。取消時は所有childを終了/回収し、返却前にも取消・登録/除外・原本の版/祖先を再確認する。元音声/出力ファイル/DBへ書き込まない。上限は出力と所有時間の制限であり、native heap全体の保証ではない。

生成WAVで500msから750msの12,000samples、1,750msから末尾まで4,000samples、区間の振幅と無音保持、EOF拒否を実FFmpegで確認。原本変更/解除/除外/取消ではPCMを返さずworkerを解放。開発Python3.14で新規13＋関連video21のうち、PATH指定試験1件はbundled-tool環境を除外するharness修正後に対象再確認PASS。基本Python3.11で新規13 PASS、追加したlookup前取消1件は開発PythonでPASS。証拠 `data/ai-ui/snapshot-review-20261026/audio-*.log`（Git対象外）。基本Python初回のtests import失敗はisolated `_pth` がPYTHONPATHを無視する起動指定の問題で、明示sys.path指定後に確認した。

認識/特徴抽出モデルの選定・実推論・通常索引へのproducer接続は引き続き未完。今回のwave切り出しをR06/R07/R08の内容認識合格へ数えない。基本ZIP04/source`9968eac`とinstalled Alphaへは未収録。

### 5.3a 既存モデルのCPU前処理契約（2026-10-26）

`tools/inspect_audio_input_contract.py` を既存 `.venv-ai` で実行した `audio-contract01/report.json` はPASS。GPUを不可視にし、offline/local-only、model load/inferenceなし。固定版`914f7f8…`のlocal configは`gemma4_audio`、feature extractorは16kHz/128band。bounded safetensors headerに音声関連752tensors/611,223,040bytesを確認した。これは重みpayloadの構造情報であり、実VRAM/品質/他重み不要の一般保証ではない。

登録生成WAV→検証済みPCM境界→ローカルAutoProcessorが接続し、1秒/16,000samplesから`input_features [1,99,128]`/float32とmask`[1,99]`、input_ids`[1,29]`を生成。全音声特徴はfinite、生成音声とモデル重みsize/mtime不変。既存sentence-transformers6.1.0/transformers5.19.0/numpy2.4.6を利用し、追加取得なし。本番profileはtext/cover、adapterの`audio_config=None`は維持する。

次の限定API確認は `tools/probe_audio_embedding.py --gpu`（別途ユーザー回答後）。生成1秒のtone・実験用audio ON/vision OFFのみ、768D/finiteness/normと資源を確認し、通常DB・profile・索引を書き換えない。CPU前処理合格やtoneのAPI合格を、発話・環境音・音楽・類似の品質合格へ数えない。

**上記GPU smokeは個別回答後1回実施済み**：`audio-gpu-smoke01/report.json` PASS/所有process exit0。audio ON/vision OFFの実験用modelで768D・全finite・norm1.00023、load6.58s/encode1.81s（生成tone1秒・単回）。PyTorch peak allocated1,167,375,360bytes / reserved1,176,502,272bytesであり、driver/nativeを含む総VRAMではない。新規取得0、通常DB/profile/本番adapter変更0、原本不変。発話内容や音楽の品質・ASRとの比較は未評価。

追加の生成format試験は、既存同梱FFmpegでmp3/flac/ogg/opus/aac/m4a/wmaへ変換した2秒音声から各500ms/8,000samplesを取得してPASS。WAVと合わせ登録済み8形式の基本入力経路を確認したが、実私物の全codec/破損例の網羅ではない。

### 5.3b 明示的な音声worker契約（2026-10-26）

- `audio_profile_for()` が既存固定モデルからtext/audio用profileを派生させる。contractは`normalized-f32:text4096:mono-f32le-16000hz-audio30000ms:v1`。key/SQLite保存先はlegacy text/coverと異なり、表示名/配置変更では変わらない。本番の選択profileや設定へ自動登録しない。
- 音声profileだけaudio towerを有効・vision towerを無効にする。既存defaultは従来どおりaudio無効。generic sentence-transformersには音声を無条件追加しない。
- `EncoderProcess.encode('audio',PCMWindow)`→`audio_protocol`→`ai_worker`→adapterを接続。strictな16kHz/mono/f32le、時刻/長さ、finite/alignedなimmutable bytes、最大30秒/1,920,000bytesを両側で検証する。IPCはbase64と明示fieldのみ、path/URL/handleなし。不正な音声はworker起動前に拒否する。
- worker入力行は最大12Mi文字で終了判定し、既存8MiB画像payloadを維持する。音声以外の既存profile/operationを保持し、返却vectorは既存の次元/有限性/正規化検査を通す。通常索引・音声512D保存・GUIにはまだ自動接続しない。
- 新しいworker/profile/protocolと関連release/PCMのCPU45 PASS、基本Python3.11のworker9 PASS。default legacy key保全、専用key/契約変更、bad payloadの起動前拒否、private wire roundtrip、fake CPU workerのbad→good応答と過大行終了を確認。実モデルの音声APIは前節の限定GPUで確認済みだが、この新しいprivate IPC経由の実GPUは未実施。ソースの機能追加であり基本ZIP04/installed Alphaへは未収録。

予備品質の条件と結果は[音声入力評価](audio-input-evaluation.md)を参照。R06最終方式選定、長時間音声の逐次producer/atomic保存/検索接続・無音対策・実録音/実曲の評価は残る。既存512D音響空間へ768Dを流用しない。

**デジタル無音の局所保護**：検証済みPCMが全sampleで正/負のゼロの場合、parentはモデル起動前に`None`（索引候補なし）を返す。workerも同条件で`skip/digital_silence`を返し、未知のskip理由を無音扱いしない。小音量の非ゼロ値は通す。これは完全なVAD/雑音判定ではなく、general silenceの品質受入や空結果の永続化ではない。future producerは「完了したが候補なし」と未処理を区別して保存する必要がある。

最終worker関連12 testsが開発Python/基本Python3.11ともPASS。最大30秒/1,920,000bytesを実所有subprocess/pipeで転送し、profile handshake、次元/正規化、終了/残存なしまで確認。child内のTorch/modelはfake CPU fixtureであり、実GPU/重みを使わない。実モデルの前記API評価と、private IPCのCPU試験を合算して新worker経由GPU成功とは記さない。

### 5.4 原子性と中断・再開契約
- 音声1アイテムあたりのセグメント登録はSQLiteトランザクション内で不可分（Atomic）に実行。既存の同一 `item_id` の古いセグメントを全削除した上で一括挿入。
- 処理中のキャンセル（`cancel.is_set()` / `check()`）を各セグメント抽出間、候補バッチ間、および多数セグメント評価中（256セグメントごと）に監視し、キャンセル時は部分的な不完全セグメントを残さず即時中断。
- 元ファイルのハッシュ/更新日時が一致する（`source_revision` が等しい）場合は、既存の `ai_audio_segments` を再利用し、重複推論を防止。`get_segments(include_vectors=False)` により raw float32 BLOB を直接再利用可能とし、不要な再エンコードおよびリスト生成アロケーションを完全排除。
- 元ファイルが変更・削除された場合は、既存の `_current_rows` および鮮度検査により、旧セグメントは検索対象から自動除外される。破損ベクトルが含まれる場合は `fresh()` が False を返し安全に再索引へ誘導。

---

## 6. 時刻根拠（Timepoint Grounding）表示契約

検索結果（`MediaRow`）に `audio_match_ms`（開始ミリ秒）および `audio_match_snippet` が付与された場合の表示規則：

1. **時刻フォーマット**:
   `FormatVideoTimestamp(ms)`（例: `0:15`, `3:42`, `1:05:20`）
2. **根拠ラベル (`AIEvidence`)**:
   `音声発話一致（0:15 · 「おはようございます」）\n類似度 0.892`
   文字一致がある場合：
   `音声発話一致（0:15 · 「おはようございます」） · 文字一致1/1語\n類似度 0.892`
3. **無音・破損・未索引時の保護**:
   無音ファイル、破損した音声、発話が検出されなかったファイルは `ai_audio_segments` に行が作られず、`audio_match_ms` は `null` となる。0件のセグメントを無理やり0:00にフォールバックさせて偽の一致を起こしてはならない。

---

## 7. 未完を解消する受入

既存APIを消さずに、実音声入力・安全な読み取り/上限・取消/再開・モデル版/由来の分離・無音/破損の扱いをproducerへ接続する。ファイル名や注入記述子だけで正解が分かるfixtureを内容認識の証拠にしない。発話/環境音/曲調/音同士の類似を未知の生成・許可済みfixtureで測り、品質と資源の限界を明示してからR06/R07/R08/R14を完了にする。

## 8. R08/R09 音響特徴・類似検索・GUI統合仕様

### 8.1 SQLiteスキーマ (`ai_audio_acoustics`)

```sql
CREATE TABLE IF NOT EXISTS ai_audio_acoustics(
    item_id INTEGER NOT NULL,
    source_revision TEXT NOT NULL,
    at_ms INTEGER NOT NULL CHECK(at_ms >= 0 AND at_ms <= 86400000),
    vector BLOB NOT NULL,
    descriptors TEXT NOT NULL,
    contract TEXT NOT NULL,
    PRIMARY KEY(item_id, at_ms)
);
```

- **空間分離契約**: 512次元 float32（リトルエンディアン、2,048バイト）、$L_2$ 正規化済み。768D発話/テキストベクトルや視覚ベクトルとの照合は `score_candidates` で明示的に `ValueError` 拒絶。
- **日本語音響記述子**: `descriptors` カラムに最大64件の音響・音楽タグ（例: 雨音、ピアノ、ジャズ、環境音、爆発音）をJSON配列で保持。現在は供給済み記述子を照合する。元音声の無音判定や誤認防止の実品質はproducer接続後に検証する。
- **音響類似検索**: `AISearch.similar(item_id)` で `origin['kind'] == 'audio'` の場合、`source='acoustic'`、`origin_kind='audio'` で512Dマルチフレーム最大類似度集約を実行。起点自身は自己除外し、最も類似度の高かった候補側時刻 `audio_match_ms` と起点側時刻 `origin_match_ms` を付与。
- **WinUI連携**:
  - `AudioPlayerPolicy`: 8種類の拡張子（.mp3, .flac, .wav, .ogg, .opus, .m4a, .aac, .wma）を安全に検証。
  - `ArchiveReaderClient.OpenAudioRangeAsync`: バックエンドの `/api/library/audio/{item}/...` からバイト範囲を安全に取得。
  - `VideoPlayerView`: `isAudio=true` モードでサムネイルホバープレビューを隠し、シークバー・再生・一時停止・音量コントロールを提供。一致時刻へ自動シーク。
  - 文脈メニュー: 音声アイテム選択時に「似た音声・曲を探す」を表示。
