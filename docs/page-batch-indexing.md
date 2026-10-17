# 複数の本のページをAI検索へ追加する

2026-10-17の最初の複数本ジョブ。既存の[1冊単位のページ索引](page-image-search.md)を保持し、明示した範囲だけを順に処理する。モデル・ランキング・通常AI buildの対象は変えない。

## 操作

1. 保存したAI対象範囲に本の登録フォルダを含める。
2. ライブラリの本を右クリック → **「複数の本をAI検索に追加…」**。
3. **表示中の検索結果**の本をチェックする（最大8冊）。合計ページ数の上限を指定（1〜128、初期値64）。
4. **「範囲を確認」**で各本の次の未準備範囲を取得し、タイトル・ページ番号・今回の合計を読む。この段階では推論/索引を開始しない。
5. **「追加を開始」**。1冊につき次の連続した欠けを最大16ページ、合計上限まで処理する。上限で対象外になる本も事前表示する。全準備済みの本は新規ジョブへ含めない。選択/上限の変更は確認済み範囲を無効化する。
6. 中断すると**完了した本の範囲を保持し、未完了の本の今回範囲は公開しない**。「同じ範囲を再開」で同じ選択を再検査し、完了分は再利用する。
7. 画面やアプリを閉じた後は、設定 →「AI検索の準備」→ **「前回の本の追加を再開」**。対象範囲の読み込み/件数確認が完了した保存済み設定を使う。未保存の範囲変更がある間は実行不可。処理結果・中断・元ファイル変更の警告は隠さない。

検索結果全ページ・全フォルダの本を勝手に集めない。本一覧は現在の検索結果ページにある作品だけ。チェック式の本リストは仮想化ListView内に置き、各行と外側フォームの右にバー用余白を設ける。状態/確認/開始/再開/中断はスクロール外、範囲や本の一覧はスクロール可能。タグの未保存編集・画像/読書・通常の検索・既存1冊手動範囲を保持する。

## 制限と保存の境界

- **1ジョブ1〜8冊、1冊1〜16ページ、合計1〜128ページ**。1冊の全ページを一度に処理するqueueではない。繰り返すと次の欠けへ進む。1TB全体の一括解析・自動再開・常駐スケジューラーは未実装。
- 通常のAI索引/起動/検索では内部ページを自動処理しない。AI未導入/画像非対応profileは拒否。新しいモデルや依存を取得しない。既存のsource/read-only/ZIP/画像上限を広げない。
- 要求の全対象を開始前に検査し、scope・有効root・種類・page ID・head/物理revisionが一致しなければ開始しない。scopeは明示必須、空の選択を全体へ広げない。profileを要求に固定し、途中で別モデルへ移し替えない。
- 既存のshared inference lock/worker/cancel/idle解放を共有。推論中にcatalog guardを保持せず、各本の保存直前にscope/root/page/物理版/取消を再検査する。**各本の選択範囲はtransactionで全公開または未公開**。ジョブ全冊を一括atomicとはしない。
- 本ごとの失敗は記録して次の本へ進む。成功/失敗が混じると`partial`。以前の保存済みvector・手動metadata・元ファイルを削除しない。取消中の途中vectorは保存せず、完了済みの本を再開時に再利用する。
- 最新ジョブの選択（item/revision/page IDs/limit/profile/scope）と状態は既存profile別`ai_state`へ保存。再起動でrunning/cancellingは`interrupted`になるが、自動実行しない。**保持する再開先は最後のAIジョブだけ**。別の通常AI/ページジョブを開始すると再開記録は置き換わる。完成済みvectorは残る。永続的な複数queue履歴ではない。
- 再開は同じ保存scope/profile、同じページ範囲を再検査する。元ファイル・除外・登録先・モデル・scopeが変わった場合は古い範囲を勝手に置換/拡大しない。再開を拒否し、新たに対象を選んで範囲確認する。

## API

loopback/token/Origin/body上限を維持。公開APIへ任意path/model/画像bytesを渡さない。

- `POST /api/library/ai/pages/batch`：全field必須、未知field拒否。

```json
{
  "items": [
    {"item_id": 7, "revision": "64hex", "page_ids": ["64hex"]}
  ],
  "scope": {"root_ids": [1]},
  "page_limit": 64,
  "profile": "現在のprofile key"
}
```

- 本IDの重複・bool ID/limit・空/過剰/重複page IDs・不正版・不一致profile・合計超過を拒否。全対象が現在のscope/版で有効かを検査してからworkerを開始。初期応答は**この要求のjob ID**を返し、完了直後に他ジョブが始まってもその状態と混同しない。
- `GET /api/library/ai/status`：`job:"book-page-batch"`、`job_id`、`processed/total/indexed/reused/skipped`はページ単位、`books_total/books_completed/books_failed`、`books`（item/revision/state/total/processed/indexed/reused/error）、`selections`、`page_limit`、profile/scope。`indexed`は公開したページ数（再利用も含む）。処理したが失敗/取消で未公開の分は`processed`にだけ含む。`skipped`は失敗した本の要求ページ数で、processedと加算して進捗率を作らない。
- ジョブ状態：`running/cancelling/complete/cancelled/interrupted/partial/failed`。本ごとの状態：`pending/running/complete/cancelled/failed`。`interrupted`では終了前の途中進捗が残ることがある。
- `POST /api/library/ai/pages/cancel {"job_id":"32hex"}`：既存のID一致取消を共有。他ジョブは止めない。管理画面の既存`ai/cancel`も維持する。
- `POST /api/library/ai/pages/batch/resume {"job_id":"32hex","scope":{...},"profile":"key"}`：最後の同じジョブがcancelled/interrupted/partial/failedの場合だけ。新job IDと`resumed_from`を返す。complete/古いID/別scope/profileは拒否。再開の全対象も開始前に検査する。
- Coreは1MiBの応答上限、期待job/profile、冊数/ページ上限、冊別状態と公開数/全体集計の整合を検証。別ジョブへ遷移した古いUI応答を使って取消や進捗を表示しない。

## 検証

最終の全体/Windows結果と失敗runは[最新引き継ぎ](codex-handoff.md)を参照。今回の生成素材と模擬vectorによる実行確認を、実モデルの内容検索精度や実ライブラリ速度とは呼ばない。

対象Python：`python -m unittest discover -s tests -p test_page_batch.py`。2冊の成功/同版再利用、取消後の完了分保持・AISearch再生成後の再開、部分失敗の継続/再試行、除外/元ファイル変更、厳密な上限/要求/profile/scope/job、共有worker/caller変更、最大8冊128ページ、HTTP認証/厳密field/他job取消保護。Coreは要求cloneと改変した応答・進捗矛盾を検査する。

native：`python tools/test_tag_review_ui.py --book-batch-only --output data/ai-ui/<fresh-run>`。生成35/8ページの2冊と模擬encoderだけ。preview→1〜16/1〜8の24ページ→最初の本の完了後に取消→app再起動→AI設定から同じ範囲を再開し、16ページ再利用/残8ページ追加を確認する。PNG全確認後にだけGUI合格と記録する。

## 次の境界

複数冊の多数page vector検索/物理版検査/状態集計・catalog guard・時間/DB/メモリを計測する。1冊を複数chunkに分ける長いジョブや履歴queueを追加する場合も、明示上限・版/範囲・途中保存/取消の意味を維持する。代表素材での内容検索/WD日英の評価を進め、索引済み範囲でも漏れが多いときだけOCRを検討する。

### 2026-10-17 最終結果と残る画面確認

全Python454件：**451 PASS / 3 Windows platform SKIP、237.256秒**。新規batch10件。Core **449 PASS**（25checks追加）。Windows x64 SelfContained Release **警告0/エラー0、10.21秒**。compileall/diff/文書リンク確認。初回全Pythonは新エラー2文の日本語辞書漏れ1FAIL（241.542秒）；辞書追加→対象3PASS→全体を一度だけ再検証し合格。初回ログも保持する。

native `book-batch-20261017-03`：**20 runtime checks PASS / app正常終了2 / 6 PNG全目視**。2冊/24pageのpreview（推論0）、16page完了後に中断、未保存タグ維持、app再起動後AI設定で再開、16page再利用/残8page推論、原本bytes/mtime・設定不変を確認。今回実EmbeddingGemma/WD/OCRはloadせず模擬encoderを使う。**全6枚の静止画PASSとはしない**：5枚は読み取り可能、Light取消直後の1枚はdialog拡大途中のframeを捕捉。直後のUIA treeでは再開(130,399,440,32)、中断(130,439,440,32)、閉じる(354,520,216,32)が700x620内にあり操作も成功したが、落ち着いた取消画面のPNGは未確認。以後の人手レビューで静止した見た目を確認する。

初回01は2冊目の行clickで初期選択が外れ、期待2冊と異なりFAILED（1 PNG確認・所有app強制cleanup）。独立checkboxへ変更。02はmodel処理へ入った直後、UIの次の500ms pollより前に進捗を読んでFAILED（3 PNG確認・強制cleanup）；wait-forを加えて03で20checks成功。初回＋修正再実行2回の上限に達したため追加nativeは行わない。UI自動テストスキルの “Maximum **two** fix-and-rerun cycles; then report remaining failures.” に従い、この取消静止画の未確認を記録する。

WinUI API/コードレビュー済み。未保存編集/async/閉じる際の所有job取消・expected profile/job・固定操作/共通scroll gutter・Light/Darkを点検。**WinUIAnalyzer未導入/未実行、High Contrast/Narrator/Native AOT/DPI/キーボード網羅、全冊実GPU/代表品質・多数本性能は未検証**。新DL/依存追加/私物scan/外部media送信/CI dispatchなし。Windows Sandbox無効の既知環境につき許可済みlocal専用PID/HWNDでテストし、全app/backend終了。

多数本のCPU検索費用は[固定測定と同値な計算省略](page-search-performance.md)を追加（生成1024冊/65536page、17.560→13.551秒、raw/merged/root限定一致）。約6秒の物理版/guard費用と実品質・全RAM・全冊応答の検証は残る。
