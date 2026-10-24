# 通常起動とAI追加環境を分ける配布計画

> **2026-10-25 現在**：基本ZIP、背景検査/配置保存GUI、EmbeddingGemma 2/WDの実取得が進んだ。現行の次作業は[current-handoff](current-handoff.md)、モデルは[AI取得](ai-acquisition.md)、runtime配布の通知不足は[収集結果](runtime-notice-inventory.md)。以下のLD4/LD5 TODOは当時の計画で、再実装指示ではない。runtimeの実公開物/完全NOTICE/clean Windowsは依然未完。


> **最新2026-10-22**：[LD4a既存folderの背景検査job](ai-setup-jobs.md)。非同期開始/実hash進捗/中止/atomic保存/終了cleanupまで。LD4はPARTIAL、次trusted catalogとtransactional取得の生成HTTP検証。basic03は前段snapshotのまま、GUI/download/clean Windowsは未受入。

2026-10-21。ユーザーが「ZIP解凍→本体を開く、AIを使う場合だけ画面から追加」「初回/更新時の完全検査、普段は軽い確認」の方針で開発を明示承認した。新しいPortableの通常起動に関して、以前の「毎回全SHA必須」を本書で置き換える。原本/DB/source guardの緩和や既存配布の書換えは許可しない。

## 利用者から見た完成形

1. 基本ZIPを解凍してAredoko.exeを開く。Python/.NET SDK/winapp CLI/pip操作を要求しない。
2. AI未導入でもファイル名/タグ検索、登録/整理、画像/本/動画の閲覧を利用できる。
3. 「AI検索を使う」から必要な追加環境とモデルを取得する。対応済みの配置済み環境/モデルの指定、公式から手動取得する経路も提供する。
4. 追加取得は容量/実進捗/取消/再開/不足理由を表示。初回から黙ってダウンロードしない。製品の速度上限は既定なし、任意上限のみ。
5. 普段の起動ではGPUライブラリ全量を毎回読み直さない。完全検査は初回/更新/変更検出/明示修復時。Check-Startup.cmdは開発確認用で通常利用に要求しない。

## 今回の実装と到達点

### LD1 通常起動の検査を分離 — CPU_DONE

tools/startup_validation.pyを新規実装し、Portable launcherに接続。初回は既存preflight（全SHA/全inventory/通常path/祖先link/type/hardlink/実import/media probe）を通し、その前後の全file metadataが安定した時だけ外部のrelease-validationへreceiptをatomic保存する。失敗/取消/更新途中のreceiptを成功として公開しない。

次回は全inventoryの増減・file identity/size/mtime/ctime/mode/link属性を確認し、bin/backend/tools/bootstrap/Python coreとDLLsを再hashする。bulk site-packagesとmedia runtimeはmetadata照合とする。root絶対位置/manifest SHA/probe契約が変わる、receiptが壊れる、metadataが変わる場合は完全検査へ戻す。既知のhash不一致は拒否し、現在の壊れた内容を新しい正常値として学習しない。空間的な原本guardや旧MSIX経路は保持する。

**保証の違い**：metadata方式は通常の破損/変更検出であり、bulk fileの全bytesを暗号学的に再証明しない。metadataを意図的に保存/偽装した改変や、同権限でのcache/manifest改変に対する署名の代わりではない。元のmanifest自体もpublisher signatureではない。この方式を「従来の全SHAと同等」と報告しない。完全検査API verify_release/preflight/--check/--verify-onlyは以前のまま。developer launcherの--full-checkで強制完全preflightを追加したが、ルートAredoko.exeの修復ボタン/引数はまだ未接続。

走査は既存_parallel_treeの全lexical guardを維持し、最新leafの通常file/reparse/hardlink検査を追加。metadataだけのために同じ祖先走査を重複しない。内容を読む主要hashは従来の_verify_fileで再guardする。cacheは配布の外に置き、lease/通常path検査/新しいtempへの書込/flush+fsync/replace/取消を使う。user media/modelsのmetadataを収集しない。

full/軽量とも進捗は実際に処理する件数/bytesのみ。軽量時のhash総量を5GBと表示せず、完了していないfull検査を装わない。初回receipt作成の追加metadata走査はコストがある。起動ごとのmetadata取得もゼロにはしておらず、即時起動は保証しない。

### LD3 AI追加環境とモデル配置 — CPU_DONE（製品GUI未接続）

[独立契約・実装・検証・限界](ai-runtime-setup.md)。既存packの明示検証/保存、runtime不足とmodel不足の別診断、next-restart適用、現在app worker隔離起動を接続。最新sourceのbasic03候補696files/656,061,210bytesで実同梱Python/backend/診断/生成PNG登録検索preview/正常終了/DB整合をCPU確認。初回3.982480s/通常1.488302s（warm単発、GUI未確認）。02を上書きせず、新docsは準備時snapshot。GET診断と開発CLIまでであり、自動download/製品設定画面/重い検証のHTTP保存jobはLD4/LD5。任意packの推論互換性・配布元認証・clean Windowsを受入済みにしない。

### LD2 PyTorchなしの基本候補 — CPU_DONE（native未確認）

既存prepare_python_runtime.pyの非AIモードを利用し、明示した既存CPython/Pillowだけを新規data/basic-runtime-20261021-01へ構成。元のPython/venv/モデルは変更しない。さらに新規dist/portable-basic-20261021-02/Aredokoへbootstrap/自己完結WinUI/基本Python/動画toolを梱包した。torch/transformersは含まない。

| 実物 | 展開後のfiles | 展開後bytes |
| --- | ---: | ---: |
| 従来の全AI入り候補 | 24,329 | 5,554,470,502 |
| 新しい基本候補 | 692 | 656,009,829 |

約656MBは**ZIP圧縮前のフォルダ容量**。ZIPは未作成。FFmpeg/ffprobe約444MBは基本候補にも含む。別取得に分けても、GPU追加環境を導入した後の合計容量が消えるわけではない。

実基本候補の同梱Pythonを-I/-B・無関係なcwd・無効なPYTHONHOME/PYTHONPATHで実行し、torchを発見しないことを確認。実production backendを専用空DB/ephemeral loopback portで起動し、所有instance/session→stdin EOF正常終了0→SQLite integrity_check=okを確認。基本環境のSQLite/PIL/importとFFmpeg probeもPASS。通常利用のGUI/画像登録・閲覧の一連/clean Windows/既存DB再起動保持をこの結果から完成としない。 同じ実同梱環境で生成PNG1枚だけの登録→scan完了→ファイル名検索1件→画像preview686bytes→AI未導入状態の確認もPASS。生成原本SHA/mtimeは不変、EOF正常終了/DB integrityもPASS（basic-portable-cpu-20261021-02/report.json）。GUI操作の受入とは区別する。

通常起動のcacheは通常data/release-validationへ保存する。Check-Startup.cmdは毎回新しい専用dataのため、既存通常cacheを使わず初回完全確認になる開発用モードで、日常の入口ではない。

### 実測とテスト

- 初期の新規テスト16 PASS/4.343s。
- 既存配布/起動/IPC/所有権を含む120 PASS/127.228s（最後の重複走査整理前）。その後の整理と追加境界3件は関連25 PASS/6.405s。重複加算しない。
- 最初のregression01はrunnerのtests. prefix指定ミス9 import errors。02は配布fixtureに新モジュールを含め忘れ15 errors。fixtureを製品契約に合わせ03で120 PASS。失敗logを保持。
- 基本候補の完全preflight+receipt **3.994672s**、変更のない2回目 **1.527048s**。real probeを含むがGUI表示までの時間ではなく単発/warmな観測でありcold/p95ではない。
- 旧5.55GB候補では最初のcache試作が55.795823sとfull hash/inventory46.595100sより遅いと判明。重複祖先チェックを整理し24.045317sへ。ただしbulk入り版には多数file走査の負担が残る。最初のreceipt作成は151.235581s。計数instrumentのfull hash bytes加算にthread raceがあったため、その古いbytes値は採用しない。全hash検査の成功やwall timeとは別の計測不備で、元logを保持する。
- 最終の5.55GB再計測は同じ完全検査済みreceiptを使い、重いfullを不要に繰り返さず、hash-only計測契約をproduct probe契約と分離。実model/GUI/GPUは0。

証拠はdata/ai-ui/startup-validation-*、basic-portable-cpu-20261021-01/report.json、basic-runtime-20261021-01-prepare.log、portable-basic-20261021-0{1,2}-package.log。02基本候補が最終source snapshotで、01は整理前。旧candidate/installed Alpha/shortcutsは更新していない。既存GUI固定flow3/3は維持し、今回GUI再試験はしていない。

## この後の実行順（R13/PZ3を具体化）

| ID | 次の作業 | 状態/受入 |
| --- | --- | --- |
| LD3 | AI追加環境の独立契約と既存folder選択 | CPU_DONE。[契約/サービス/診断/検証](ai-runtime-setup.md)。独立pack ABI/SHAと明示保存、next-restart適用、worker隔離。製品GUI/取得はLD4/5、実GPU互換性未確認 |
| LD4 | 追加環境/モデルの取得job | TODO。承認された取得元/版/hashを持つcatalog、未完stage→検証→新version公開、取消/再開/破損/容量/認証/オフラインを生成HTTPでCPU検証。既存の正常pack/model/indexを上書きしない。システムpip/driver導入をしない。実downloadは別途具体物を示して許可 |
| LD5 | 簡潔な初回/設定GUI | TODO。AI追加/既存指定/手動案内、実進捗、再試行、修復の完全検査を一つの入口に整理。基本閲覧を取得でblockしない。旧GUI capを別名でresetせず、具体buildを用意して新GUI範囲を確認 |
| LD6 | 基本ZIP・AI追加後のclean Windows受入 | TODO。SDK/Python/開発用登録なしで解凍→通常起動→生成素材登録/検索/閲覧/終了→保存保持、AI追加/既存指定、更新/再配置、完全修復を受入。NVIDIA driver要件とアプリ同梱runtimeを区別。今回のhost isolationだけで代用しない |

上記は機能の廃止ではなく導入時期/梱包の分離。モデル交換/既存索引identity、全機能、P0 2/2閉鎖、専用OCR保留、U09/U11/U13/U14、ALPHA後実音声/音楽を維持。R13 DOING/ALPHA未完/R14 PARTIAL。新しいGPU/GUI/依存取得/Actions/main merge/旧shutdownなし。
