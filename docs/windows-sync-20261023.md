# Windows同期・起動版診断と設定導線（2026-10-23）

## 取り込んだ最新状態

実機は1969ab4/clean tree、fetchでremote6bb267f（10commit先行）を確認しfast-forwardのみで統合。PR #5も6bb267f/open/Draft/unmerged。P1B逐次再生、P2結果session/native接続、P3 thumbnail/cache/window/優先制御、viewer設定のbackup互換は他AIの完了分として再実装していない。

## 今回の実装

- `76d8004b4dbf3111b579442990cb4545cdd89df0`: ResultSearchConditionsのroot配列がJsonArray.Add<int>を通り、反射無効時にNotSupportedExceptionとなるWindows確認失敗を修正。JsonValueの明示生成で既存Release-safe契約へ。新機能の検証で初めて再現した実不具合で、反射設定を緩めない。
- `70b5b31de2bf6e570409ebbb1da3691974d2da01`: AppBuildIdentityで実際のassemblyのinformational version/元commit/構成とcompile時channel、明示実行場所を診断へ表示。コピー時はユーザー名を伏字。runtimeでGit/原本を走査しない。SDKが元commitを持たないbuildは「不明」。この情報は未commit変更の有無やpayload hash一致を証明しない。今回のbuildは76d8004基点+作業差分であり、70b5b31の配布候補を作ったわけではない。
- 設定saveを本文からContentDialogの標準下部primary buttonへ移動し、closeと並べる。SettingsSave automation IDをstyleで維持し、save成功/失敗ともdialogと入力を残す。テーマ即時反映と既存設定保持を維持。
- フォルダ操作をAuto列へ寄せ、全folder操作だけ16DIP分離。狭幅の2行切替は維持。共通AredokoSurfaceStyle/section paddingを登録/選択panelへ適用し、native theme resourceを使う。全面UIや連続scrollではない。

## 実行した確認

- Core初回はResultSearchConditions.Createで反射無効の例外。raw `core.log` を保持。局所修正後862 PASS assertion、診断テスト追加後867 PASS assertion。件数を合算しない。
- Portable x64 build初回0 errors/既存WUI1001×3、UI変更後も0 errors/同3 warnings（20.51s）。最終の診断注記だけ文字列修正は追加buildを反復しない。publish/trimmed配布/native GUIを受入済みとはしない。
- 他AI追加のPython関連86実行/85 PASS/1 FAIL（72.479s）。旧basic03の埋込Pythonで起動したchildがrepoの新ai_setup_jobsを発見できず、lease拒否前にModuleNotFoundErrorとなったrunner環境の失敗。既存.venv-aiの正しいmodule探索で**失敗した1件だけ**再確認し1 PASS/2.267s。アプリのlease/guardを変更していない。既存basic03へ新source moduleを追加/上書きしない。
- 新しいCore/WinUIの型/APIをproject参照で確認、標準ContentDialog例を参照しcode review。copy匿名化、native footer保存/失敗、旧UIA ID、theme resources、選択/非同期/検索契約を確認。GPU/GUI/実モデル/新asset取得/私物scan/通常DB・設定の変更なし。

raw logはローカルignored `data/ai-ui/windows-sync-20261023-01/`。初回失敗を消さない。rawがGitHubに同梱されているとは主張しない。

## 残り・次の作業

P0は診断/source共通surfaceを実装したが新配布receiptとの照合/nativeテーマ/操作は未受入。P1B/P2のCore/Portable build待ちは解消、実GUIのloop/速度/60↔61/120→121/close復帰は未受入。P3は標準container/連続scroll/完成形主画面、monitor移動時DPI更新、decoded全体RAM実測が残る。

次はResultWindowを標準containerと連続scrollへ接続し、既存dirty/selection/ordinalを保つ。過去WinRT binding crashを避け型情報/x:Bindを確認する。独立小作業としてP0の残る共通スタイル適用も継続。GUIは過去capsをresetせず、具体候補/まとめ範囲で新許可を得る。GUI待ちだけで独立したP4 backendを止めない。

P4複数棚/履歴削除/root favorite/navigation→P5 online backup/安全なrestore→P6 LD4b–6→P7、M1後に実音声/音楽R06–R09。旧Alpha/basic03/shortcutを更新せず、新ZIP/新配布なし。R13 DOING/R14 PARTIAL/M1/M2未完、専用OCR保留/全機能/旧caps/raw失敗を保持。今回はshutdown指示なし、過去の一度限りの指示を再適用しない。
