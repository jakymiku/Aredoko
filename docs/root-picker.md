# AI対象フォルダの検索・ページ選択

2026-10-13。AI索引→「AI検索と索引の対象」→「フォルダを探す」で全登録フォルダを名前/パスの部分一致（大文字小文字を区別しない）で絞り込み、32件ずつページ表示する。先頭256を超える未選択フォルダも新規に選べる。選択は表示ページとは独立し、検索で隠れても保存/件数確認の対象へ含める。一致件数と個別選択数を別に表示。

## 操作と境界

- 個別選択は最大256件。上限到達時は未選択のCheckBoxを無効化し、選択済みを外すと枠が戻る。空選択はゼロで、全rootへの暗黙拡張はしない。「登録フォルダをすべて対象にする」は既存のroot_ids:nullを保存する。
- 検索、ページ送り、パス表示はscope draftを変更せず、件数確認や保存済み判定を失効させない。CheckBox・種類・棚の条件変更が確認を失効。保存してからAI検索/次の索引へ適用し、未保存で閉じると破棄する。
- 行のパスは2行＋ellipsis/tooltipでコンパクトにし、「パス」ボタンで読み取り専用TextBoxへ全文を表示。折り返し、最大120 DIP、通常のテキスト選択/コピー経路。個人情報をクラウドへ送らない。clipboardの内容は今回読み書きしない。
- 欠落した保存IDは「登録が見つかりません（ID …）」として一覧・検索に含め、明示的に外して修復できる。欠落IDが残るscopeは既存APIが拒否し、全rootへfallbackしない。登録一覧はdialog開始時の観測で、新規登録後は開き直す。
- 選択を保持するRootPickerはUIを持たないCore。snapshot ID配列でJSON DOM requestを作る。表示用CheckBox/パスButtonは最大32行に限定。managed ItemsSourceの過去のComWrappers crashを避けたnative controlsの手動生成を維持。全登録rootのmetadataはメモリに持ち、フィルタはUIスレッド上の線形文字比較/ID sortなので、膨大な登録rootそのものの性能は保証しない。

## 検証

- Core **29 checks PASS**（従来19＋新規10）。非表示選択保持、258番目の新規選択、ページ最終2件/前後境界、case-insensitive filter、欠落ID、256上限と枠解放、過剰restoreの原子性。reflection-free JSON契約も維持。
- 全Python **150 tests PASS / 101.163秒**。Release x64 SelfContained **PASS / 34.02秒 / errors0 / 既存IL2104 2warnings**。Python構文/CLI/diff確認。手動WinUIレビューは所有/閉鎖/async version/保存freeze、theme標準controls、Automation IDs、32行境界を確認。専用analyzerは未導入・未実行。全体のMVVM移行/日本語resource化/AOTは別工程。
- 初回native01は16checks/2 PNG全目視後、readonly probeでforeground安全確認に拒否されFAIL。02は明示CLI focusも前面化前に拒否され5checks/1 PNG目視でFAIL。両方にowned PID cleanup fallback。入力ガードを解除せず、03で通常の所有窓activationを試し、拒否時はkeyboard未検証と記録する。停止規約の2回fix-and-rerun以内。
- native03 **51 checks PASS / 6 PNG全目視 / scoped visual PASS / 正常close 2回**、keyboard=partial、cleanup warnings=0。 OSが所有窓の前面化を拒否した操作は入力せず、同じowned HWNDのUIAで機能確認を続行。keyboard_skippedへ明記し、全キーボード経路PASSとは扱わない。01ではSpace選択/Enterページ送りが観測済みだが途中失敗の別履歴。
- 03は生成901 metadata、実PNG75件、258root。Light/Dark、1200x800/700x620、DPI96/HighContrast off（読み取りのみ）。root258を新規発見/選択、empty filterでも2選択維持、32行/9ページ、root1＋258の78件CPU確認/保存、Dark再起動後の復元、未保存の258解除をclose/reopenで破棄、全文パスのexact value、GPU worker未ロード、生成PNG75と基礎fixture17の不変を確認。clipされる一覧行とは別に狭幅全文欄を目視し全パスを確認。
- 今回の901件は生成metadataの直接挿入で、大量filesystem走査/GPU索引/検索品質の証拠ではない。5万件一覧・gridのnative結果は前回の[library-scale.md](library-scale.md)。既存scaleモードは新root pickerに合わせfiltered-rootチェックへ更新したが、今回再実行はしない。

## 疎な複数root計測

```powershell
python tools/measure_sparse_roots.py --output data/ai-ui/root-picker-sparse-new
python tools/test_ai_profile_ui.py --editor-only --root-picker-checks --output data/ai-ui/root-picker-native-new
```

出力は新規ignoredフォルダのみ。5万metadataのうち実PNG75件はroot1に維持し、残りのmetadataだけをテストDB内で再配置。明示257/258の2rootsに、前方2件/後方2件/100件おき500件を置く。NoInferenceでGPUを呼ばず、各5回のCPU件数確認、独立した予定ID配列との照合、cap/fresh、元PNG bytes/mtimeを検査。最終CLI03 **10checks PASS**。

| 分布 | 対象件数 | 中央値ms | 最大ms |
|---|---:|---:|---:|
| early-two | 2 | 108.232 | 116.520 |
| late-two | 2 | 64.328 | 66.286 |
| distributed-500 | 500 | 84.419 | 93.162 |

前回の複数root keyset修正はこの3分布でも正しく動く。sortなし・索引計画の一般的な速度保証ではなく、単一root計画との比較/巨大root数/全catalog transaction snapshotを測ったものでもない。以前のCLI相当helper01とrepo CLI02もPASS、03はmain guard整理後の確定結果。計測値は背景負荷等を含み、p95ではない。

## 次の3手

1. フォルダ選択の高DPI/High Contrast/読み上げ・全面keyboardと、大量root metadataの応答性を別の環境条件で確認する。
2. text/coverの根拠を持つ新しいholdoutを凍結し、混合順位を評価する。既存v1へ観測後tuningしない。
3. Laya日本語quality gateを独立して再評価。既定無効を維持し、reader/Komga/フォルダ本集約は別slice。
