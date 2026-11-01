# agent-desktopの限定評価（2026-11-01）

ユーザー指定の開発用GUIツール。Aredokoの依存・配布物には追加しない。既存WinAppハーネスを全面置換しない。

- 公式 vercel-labs/agent-desktop v1.0.2、Windows x64 archive 1,578,236 bytes。公式同版checksumsとのSHA256一致（`2186c76e7df197c0e67365e45d36d869f74714c56bb8a73817e2a66f3e18e222`）。これはorigin attestationではない。Apache-2.0。
- ローカル専用先 `data/dev-tools/agent-desktop/v1.0.2/`。PATH/global npm/OS設定を変更していない。再取得を自動化せず、今後の導入は現在の許可条件に従う。
- 使用前に同梱 `skills get desktop` / `skills get platform` / `status` と対象commandのhelpを読む。既定headlessを維持し、失敗を理由に `--headed` へ切り替えない。
- `--window-id` はWindows HWNDの10進値へ `w-` を付ける。同版source `crates/windows/src/system/window/window_ops.rs`で確認。`find.data.matches`の参照は`ref_id`。UI変更後は参照を取り直す。
- `tools/agent_desktop_probe.py` はハーネス所有PID/HWNDだけに限定。read/semantic操作のログはignored専用evidenceへ保存し、私物の全desktop snapshotや外部送信をしない。
- 生成素材/専用DBでowned snapshotとnative AutomationIdによる1件の特定に成功。最初の生HWND指定、次の`ref`誤読の試験FAILを保持。保存済み応答で`ref_id`修正を確認したが、semantic collapse/操作後foreground維持はまだ未確認。
- headless操作はバックグラウンドUIAを意味する。試験アプリの通常起動時にWindowsが前面表示することまで防止しない。現在のユーザー指定どおり、GUI/GPU試験は対象を示して確認する。

次は新しい変更のGUI確認に、既存の読取を反復せず小さいsemantic操作を1件だけ併せる。失敗時はdelivery/retry契約とlive stateで判断し、物理入力へ拡張しない。

追記：frontend02/source8cc23fcの設定確認後にsemantic操作だけを再度併せたが、snapshot成功後のfindで状態fileのatomic replaceに失敗（INTERNAL / Windows error1175 / not_delivered / safe）。Aredoko操作前のthird-party storage errorで、セキュリティ設定や状態file削除で回避していない。製品の設定4操作は通過し、Darkはtoolなしで8checks/exit0。以後の通常試験は既存WinAppを継続する。agent-desktop単独の無変更再試行は行わず、必要な新試験か修正版があるときに限り再評価する。
