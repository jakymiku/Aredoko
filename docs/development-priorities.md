# Aredoko — 現在の開発優先順位

2026-10-18。ユーザー依頼に基づき、完成までの順序と完了条件を[completion-roadmap.md](completion-roadmap.md)のR01〜R14へ一本化した。旧P0〜P5と累積checkpointは[履歴](development-priorities-history-20261018.md)に保存し、再開時の指示として使わない。

## 現在の判断

主要な登録・整理・文字/画像/本ページ検索・WD候補・閲覧・時間付き動画索引は実装済み。次は微細なCPU最適化の反復より、索引の継続、動画/音声の未完機能、使い勝手・配布・受入を進める。

**R01はDONE、R02〜R05はCPU_DONE（大規模検索/所有取消、復旧基盤、継続索引、動画類似）。R06は[音声・音楽方式設計凍結DONE](audio-content-design.md)。R07は[発話区間索引/時刻根拠CPU_DONE](audio-content-design.md)。R08/R09は[音響特徴検索・類似検索・WinUI再生統合CPU_DONE](audio-content-design.md)。次はR10初回設定・未索引/上限/失敗状態・資源管理の仕上げ。** [所有取消の証拠/限界](search-cancellation.md)を確認し、GUI全体の取消配線R10・性能受入R12・必要実機受入R14（GPU/GUI一括検証）を完了と扱わない。 [全件検索の仕様/証拠](full-library-search.md)・[契約](large-library-contract.md)を読む。検索候補の1万件打切りは解消、1回の索引jobは最大1万件のまま。 設計の難しいR01/R02/R03/R06/R08にはAstra推奨を付け、通常実装はSolで進められるよう分割した。担当割当は推奨であり自動モデル切替ではない。

M1は画像/本/動画の日常利用β、M2は音声/音楽内容も含む製品版候補。M1を全媒体完成版と呼ばず、既存機能を削って完成扱いにしない。詳細な依存・状態・完了条件・実機確認項目は実行計画だけを更新する。

## 維持する制約

- 長期目的は[product-vision.md](product-vision.md)。本専用/特定モデル専用アプリへ狭めない。
- P0改善は累積2/2で終了。新しい実運用根拠なしに第3試行へ戻らず、専用OCRは直接画像/ページ索引でも漏れが多いと判明した場合に限り検討する。
- 生成/許可済み素材で検証し、私物を無断走査・変更・送信しない。物理版/祖先リンク確認・scope/profile分離を省略しない。
- 全機能を維持し、GUIを簡潔にする。テスト説明は通常画面でなく記録へ置く。
- 最新のユーザー指示でGPU/GUIテストは許可済み。[限定実機受入](release-readiness.md)はGPU PASS/native PARTIAL。古い延期は現在の禁止ではない。今回のnative修正再試行2回は終了し、残gateを合格扱い/予算resetしない。独立したR04の開発を進める。
- 新依存/モデル取得は明示許可。Actions起動なし。既存production branch / Draft PR5を継続しmainへmergeしない。
- 実装/CPU_DONE/実機未確認を区別し、合格していないタスクをDONEにしない。対象テストと必要な確認が通れば次へ進み、同じ確認を根拠なく繰り返さない。

最新結果は[codex-handoff.md](codex-handoff.md)・[chat-handoff.md](chat-handoff.md)。本計画の追加で製品の実装済み機能や過去の試行数は変わらない。
