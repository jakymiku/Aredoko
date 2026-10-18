# R02-A — 上限付きメモリの全体順位計算基盤

2026-10-18、実装commit **`c0c34c1badcccf006fb304e65ab7987ab9162b56`**。R01の[契約](large-library-contract.md)に沿う内部engine。**R02-A単体時点の記録。現在は[R02-B](full-library-search.md)でAPI接続/両規模30条件合格済み。R02-Cの所有取消API等が残るためR02全体はDOING。** 以下の未接続/未確認はA時点の履歴。

## 実装

[ai_score_spool.py](../app/ai_score_spool.py)の`ScoreSpool`はrequest専用のSQLite DBを作り、1作品のmode scoreと小さい根拠JSONを順次保存する。元catalog/profile DBと無関係の一時workspaceで、モデル・依存の追加はない。

- Python bufferは256行、modeは作品内/全体とも最大16、根拠JSONは作品あたり64KiB、返すpage/evidenceは最大120件。全metadata・全vectorをPython辞書へ集めない。
- modeごとの全件count/min/maxと同点平均順位を求め、既存`fuse_modalities`と同じPython演算順でmean-RRFを計算。`max`も対応。scoreのhexを保存してsigned zero/float値を維持し、SQLite SUM/AVGへ置換しない。
- literal条件→先頭32scoreで現行境界→全件のleading/other count→group/pageの順。全件順位と件数を保ち、巨大なpage番号はSQLite int overflow前に空pageへする。
- `cancelled`callbackとSQLite progress handlerでCPU処理の取消。成功/取消/容量不足/重複ID/例外で接続を閉じ、所有workspaceだけを削除。検索jobの所有IDやHTTP認証はまだこのmoduleの責任範囲外。
- SQLite cache8MiB、DB本体上限256MiB。sortのnative一時領域/RSSは別の測定対象。workspace容量超過は`ScoreSpoolError`、取消は`SearchCancelled`として扱う。既存DBを変更して空きを作る処理はない。

## CPU検証

[新規12テスト](../tests/test_ai_score_spool.py)：1,029件の全件oracleに対し両policyの全score.hex/順位一致、256境界を跨ぐ同点・constant・欠mode・3modeの加算/分母順・極端な有限値・signed zero・空集合、literal/group/deep page/evidenceを確認。不正値/根拠上限/phase、取消時のSQLite OperationalError由来、容量不足・例外時の所有folder cleanupも検査する。50,001件の遅延投入でPython割当peak≤32MiBを検査。

- Python3.14.4の対象回帰 **77 PASS /0 SKIP /55.174009秒**：新spool12・監査3と、既存ranking/scope/similarity/tag semantic/page semantic/scale fixture。`data/large-library/r02a-checks-20261018-01/tests.log`。
- 専用venvのPython3.11.9 /SQLite3.45.1でも追加15件 **15 PASS /0 SKIP /10.06507秒**。`tests-python311.log`。モデルload/推論はなし。
- 独立した遅延入力50,001作品/100,002mode scoreの1回診断：**全順位/score.hex SHAが既存全件oracleと完全一致**（`02407103349743e363b4ca5a260aada6fa0f750f753c9ad5d17e75cb7c5d2cdb`）。末尾のdeep pageは81件、workspace削除確認。
- その診断のPython tracemalloc peak **139,587 bytes**、作業DB **15,974,400 bytes**、traced所要 **4.987367秒**。full oracleは記憶量の測定窓の後に別途構築して比較。SQLite native/OS/RSS/GPU・metadata・保存vector復号・物理版・HTTP/GUIを含めない。単発traced値を実検索速度/p95や全RAM量と呼ばない。
- module SHA256 `abd4ae38bebac9a541bb140d263f82b02d1984721c236c5c0a795ca0042f21a4`。`engine.json`に環境/結果/制限を記録。fixture/DB/log/reportはGitHubへ含めない。

全Python529件等を再実行したものではない。C#/XAML・HTTP契約未変更でCore/Release/nativeは今回未実行。GPU/GUIはユーザーの現在指示で延期し、必要時に実行前確認。実モデル精度・アプリ全体の5万件検索・R02の取消APIは未確認/未実装。

## 次の接続順（R02-B/C）

1. `VectorStore.rank_with_content`から既存演算のraw mode score/根拠取得を切り出し、旧関数を同じ全件oracleとして維持。256作品ずつscorer/PageVectorsを呼び、全件列挙をspoolへ流す。返すpageだけmetadata再取得。
2. search（text/cover/combined）→画像起点similar→pending意味を小区切りで接続。literal/group前のglobal融合を保持し、R01両規模を新labelで実行して全30条件の完全性を合格させる。先頭capを期待する旧テストは新契約を確認するものに更新し、既知の失敗を消すだけの期待緩和はしない。
3. catalog `_state_epoch`だけでは通常タグ/棚/favorite編集を検出しないため、保持接続のdata_versionとsource/profile/scope再確認を実装。request-owned取消・認証API・旧ID拒否、容量/worker/close・Core strict応答互換を検証。実機受入はR14へ積み、R02-Aの内部合格と混同しない。

Astraレビュー推奨は[実行計画](completion-roadmap.md)のまま。今回独立Astraレビュー/自動モデル切替/agent委任は行っていない。新しいRRF重み/検索品質調整はない。
