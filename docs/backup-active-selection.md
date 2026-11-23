# P5：使用中モデルと次回用設定の保全

## 到達点（2026-10-24）

既存の未コミット4ファイル案を退避・確認し、`c30bc34`へfast-forwardした後、その案を土台に実装した。退避はignored `data/ai-ui/active-selection-20261024-01/starting-diff.patch` とstarting-state.json。reset/stash/他の変更の上書きなし。

バックアップには「いま使っている定義」と「保存済みの次回用選択」を分離して残す。保存済みsettingsの元bytesを上書きしない。AIProfileSettingsは起動時に検証したModelProfile定義を小さいimmutable bytesとして保持する。既定モデル、local選択、明示overrideを同じ仕組みで扱う。Taggerは実際のadapterが保持するWDProfile定義を使い、候補ファイルの順序から選ばない。モデル・Pythonの実行/コピー/取得をしない。

## 形式2

`aredoko-recovery` version2（復元receiptもversion2）を新規出力する。既存のversion1は読み取り・復元可能。旧アプリはversion2を拒否するため、新しいmetadataを無視して異なるモデルで起動することはない。上位version・未知fieldは拒否。

- `active_selection`は必須。`ai_profile` / `tagger_profile`は検証済みpayloadへの相対pathまたはnull（未収録）、`ai_override`は元の明示overrideの有無を表すbool。`true`ならAI定義への参照が必須。
- 起動時のAI定義は `active/ai-profile.json`（role `active_profile`）、WD定義は `active/tagger-profile.json`（role `active_tagger_profile`）。各1件・8KiB上限、設定型を検証し、通常のサイズ/SHA/構成・取消・原本guardを適用する。
- `profiles/`最大64件、`tagger-profiles/`最大16件の元の保存枠を消費しない。snapshotを普通のprofile一覧へ追加しないため、再バックアップで増殖せず、同名の利用者profileを上書きしない。全payload上限はversion1の148件、version2は150件。
- 保存済み `ai-settings.json` は元bytesのまま収録。存在しなければ、設定を選択したCOPYにだけ暗黙のpending `default` を記録する。元の設定ファイルを新規作成しない。
- 設定を含めない選択では、profile/snapshot/選択metadataを取り込まない。manifestのnullable選択は未収録を示し、既存の起動設定を勝手に削除しない。
- 復元先は参照・payload全体を検証してから切り替え、AIとTaggerを正確な復元ファイルへrebaseする。旧version1の単独taggerは従来通り。旧複数taggerはactive不明のため順序から推測せず、既存の明示指定を保持する。
- offline CLIも `--active-profile <含めたprofileのfilename>` / `--active-tagger-profile <含めたtaggerのfilename>` で明示可能。HTTP callerから任意の定義/設定pathを渡す口は追加していない。

## 確認

生成CPUのみ。最終関連79 PASS/31.611s（新selection12＋既存storage/live/switch）。AI settings/job/backup HTTP22 PASS/6.016s、restore jobs/prepared/HTTP/実所有backend handoff40 PASS/7.665sは別の関連確認。初回67件の2 FAILは旧期待（pendingをactiveへ上書き、taggerを未選択で推定）で、rawを保持。途中fixture/設計整理の実行を最終件数へ合算しない。

明示overrideとpending両保全、既定→pending変更、local→pending変更、起動後の外部定義変更に影響されないactive、複数WDの非順序選択、64/16件保存枠、再バックアップの衝突/増殖なし、取消、設定省略、legacy1、metadata/上位版/path改変、切替/rollback・元設定保全を確認した。C#/GUI/GPU/実モデル/私物DBは変更・実行していない。

## 復元後の一時指定解除（実装済み）

元が通常起動（ai_override=false）の場合、復元初回は当時のactiveで開き、そのready確認後に一時的なai_profile指定を解除し、次の通常再起動ではpendingを適用する。元が明示override=trueなら固定指定を保持する。解除失敗/中断時もコミット済みsentinelを残して次回安全に後処理し、旧libraryへ誤rollbackしない。この動作を実装した。初回backendには所有launcherだけが`--ai-profile-transient`を渡し、GUIの次回選択を許可する。ready後に現在のlaunch設定をlease下で読み直し、同じ一時指定だけをatomic更新で外す。後から保存されたruntime/theme/別の明示モデル指定は保持する。launcherはcommitted cleanup後に設定を再読し、古い一時指定を使わない。新しい明示CLI指定は再読後も保持する。

生成CPU確認：一時指定/cleanup関連19 PASS/8.174s、所有launcher引数と実所有backend HTTPの新規2 PASS/1.072s、破損sentinel形状1 PASS/0.392s。既存settings/switch40 PASS/11.881s、release lifecycle/portable startup26 PASS/47.129s。各実行は別の確認であり合算しない。実所有backendは存在しないAI interpreter/modelsを指定して推論しない。busy lease、設定replace失敗、sentinel削除失敗はいずれもcommitted証拠を保持し、再試行しても二重履歴や誤rollbackをしない。

## 2026-10-24 形式2 active/pending・model_locations のネイティブ復元検証（PASS）

`tools/test_native_restore.py` に `--format2 --release` モードを追加し、通常の `Aredoko.exe`（`Bootstrap.cs` + `StartupPipe` + `launch_release.py`）経由で形式2バンドルのネイティブ復元→自動再起動（Phase 1）→通常終了→次回起動（Phase 2）を一貫検証した。出力は `data/ai-ui/restore-v2-native-20261024/run01..05`（全試行のraw・PNG・commands.logを保持）。`dist/portable-basic-20261024-03` は変更していない。

- `run01..03`（ハーネス診断・修正）：Windows 11 `#32770` ファイル選択ダイアログ（`復元元のZIPバックアップ`）で `--depth 20` がExplorerの `ProperTreeHost` で256要素上限に達していた点を `--depth 3` に修正し、ComboBox `1148`/`1136` 内の `DropDown` ボタン（`name="開く"`）と区別して `automationId=="1"`（`type="SplitButton"`, `name="開く(O)"`）を一意選択するようハーネスを修正。
- `run04`（製品バグ特定）：Phase 0 のネイティブZIP選択・形式2検証・同意再起動・Phase 1 での復元active profile（`Restored Active V2`）一時適用・`launch-settings.json` からの一時 `ai_profile` 解放・`model_locations`（active/pending/WD 3件）および役割別rootの保持・WD `0.65` 定義の復元まで全項目PASS。一方、Phase 1 終了時に `Aredoko.exe` ランチャーが待機タイムアウトした原因を診断し、`launch_release.py` の復元2周目起動（`attempt == 1`）で `startup_pipe` は `None` にする一方 `progress`（`pipe.control`）を引き続き渡していたため、`app_ready` 後（`Bootstrap.cs` 側で `interactive == true`）に `progress` フレームが送出されて `Bootstrap.cs` がプロトコルエラー（`"起動通知を確認できません。"`）となる製品バグを特定。
- 製品修正と単体テスト：`tools/launch_release.py` で `progress=progress if attempt==0 else None` とし、`tools/startup_ipc.py` の `StartupPipe.publish()` でも `_interactive` 到達後の `progress` 送出を抑止。`tests/test_restore_handoff.py` と `tests/test_startup_ipc.py` に回帰テストを追加し **25 PASS / 10.524s**。
- `run05`（修正ステージング `data/ai-ui/restore-v2-native-20261024/staged-release/Aredoko` で完全PASS）：Phase 0（`pid=50216`）で `bundle.zip` 選択・準備・同意再起動 → Phase 1（`pid=18308`）で `active="restored"` / `selected="local:pending.json"` / `models_root=placed-running-v2` / 一時 `ai_profile` 解放 / `model_locations` 保全を確認し通常終了（`bootstrap 1 exit=0`）→ Phase 2（`pid=43148`）の次回 `Aredoko.exe` 起動で `active="local:pending.json"`（`Restored Pending V2`, dim 16）と `models_root=placed-pending-v2` への解決、元 `catalog.sqlite`（`current-fixture`）と生成メディアの不変、全所有プロセスの正常終了（`exit=0`, 残存0）を確認。6 PNG全目視。

clean Windows・実モデル推論を伴う受入は引き続き別範囲。その後のP6モデルvalidator/registry/取得済みroot接続の実装と実機結果は[AI取得](ai-acquisition.md)へ進んだ。再開時の次の1件は[current-handoff](current-handoff.md)を優先する。配布元/NOTICE/実artifact未確定のcatalogを有効化しない。
