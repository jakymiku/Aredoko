# Aredoko — 現在の開発優先順位

2026-10-18。ユーザー依頼に基づき、完成までの順序と完了条件を[completion-roadmap.md](completion-roadmap.md)のR01〜R14へ一本化した。旧P0〜P5と累積checkpointは[履歴](development-priorities-history-20261018.md)に保存し、再開時の指示として使わない。

## 現在の判断

主要な登録・整理・文字/画像/本ページ検索・WD候補・閲覧・時間付き動画索引は実装済み。次は微細なCPU最適化の反復より、索引の継続、動画/音声の未完機能、使い勝手・配布・受入を進める。

**R14はPARTIAL。** [現状監査](polish-audit-20261020.md)と[台帳](completion-roadmap.md)を優先。[今回のR11受入](ui-current-build-acceptance.md)を踏まえ、通常サイズの使い勝手を優先し小窓調整は最低限に留める。現在の順序はR13（実配布条件）→R06（実音声入力評価）とR07/R08のproducer実装。保存/検索の接続テストと実音声認識を区別し、UIの巻き戻しは今回誤起動した旧AppXを根拠にしない。検索/復旧/継続/動画/規模の既存合格を維持する。

M1は画像/本/動画の日常利用β、M2は音声/音楽内容も含む製品版候補。M1を全媒体完成版と呼ばず、既存機能を削って完成扱いにしない。詳細な依存・状態・完了条件・実機確認項目は実行計画だけを更新する。

## 維持する制約

- 長期目的は[product-vision.md](product-vision.md)。本専用/特定モデル専用アプリへ狭めない。
- P0改善は累積2/2で終了。新しい実運用根拠なしに第3試行へ戻らず、専用OCRは直接画像/ページ索引でも漏れが多いと判明した場合に限り検討する。
- 生成/許可済み素材で検証し、私物を無断走査・変更・送信しない。物理版/祖先リンク確認・scope/profile分離を省略しない。
- 全機能を維持し、GUIを簡潔にする。テスト説明は通常画面でなく記録へ置く。
- 最新のユーザー指示でGPU/GUIテストは許可済み。各flowの試行上限を尊重し、[監査](polish-audit-20261020.md)の未確認範囲を合格へ広げない。
- 新依存/モデル取得は明示許可。Actions起動なし。既存production branch / Draft PR5を継続しmainへmergeしない。
- 実装/CPU_DONE/実機未確認を区別し、合格していないタスクをDONEにしない。対象テストと必要な確認が通れば次へ進み、同じ確認を根拠なく繰り返さない。

最新結果は[codex-handoff.md](codex-handoff.md)・[chat-handoff.md](chat-handoff.md)。本計画の追加で製品の実装済み機能や過去の試行数は変わらない。

## 最新のユーザー指定（2026-10-20）：先にALPHA-0を作る

次のCodex / Antigravity / OpenCodeは、まず **[ALPHA-0 ダブルクリック起動可能版](alpha-packaging-milestone.md)** を参照し、R13配布stagingを開発環境不要の起動可能な最初のアルファへ進める。ユーザーは機能拡張や大幅なUI美化より一度使えるWindows版の完成を優先している。既存画像/ZIP/CBZ/動画/音声の機能は削らない。Python/SQLite/AI workerの同梱と実起動/データ保持の確認を省略しない。**完成後は音声・音楽の実解析/内容検索（R06–R09）とWinUI改善へ必ず戻る。** この追記は既存の台帳/製品ビジョン・以前の引継ぎを消さず、R11/R14/M1/M2/RCの未完を完了扱いにしない。



## 2026-10-20 Windows追記：同梱runtimeとfrontend MSIXの実物確認

[Windows実測・生ログ・次の3手](alpha-windows-runtime-validation.md)。既存資産だけでPython/AI/動画runtimeを準備し、同梱環境のimport、EG2 CUDA固定3処理、backend2起動の保存/所有終了と対象CPU38件がPASS。5.52GB stagingの全checkは169.781秒、frontendのみの未署名自己完結MSIXは約65MB。**R13 DOING / ALPHA-0未完 / R14 PARTIAL**。Native activationと所有launcher統合・起動待ち・通常shortcut/署名/install/clean Windowsは未受入。過去のLinux/GUI記録は履歴として保持し、次はALPHAの起動経路を完成させる。成立後の実音声/音楽→WinUI改善は中止しない。
