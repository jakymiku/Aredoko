# R03 — ローカルDBのバックアップと新規復元

> 2026-10-22 viewer設定互換修正: 現行version1 writerの `library_item_scale`（60–180/20刻み）、`theme`（system/light/dark）、`enlarge_small_images` を既存wheel方向とともに検証・保存・復元できる。旧2field/途中拡張版も受け入れ、bytesを正規化せず保持。未知field/上位version/不正型・値/重複key/2048byte超は拒否。生成bundleの現行設定往復・再hashした不正設定の復元拒否・旧形式を含む関連28 PASS/5.493s（raw `validation/20261022-p3-window/python-backup-settings.log`）。停止前提の既存backup修正であり、P5起動中job/GUI/restore切替は未実装。

> 2026-10-18追記：最新のユーザー許可で[限定GPU/native受入](release-readiness.md)を実施。GPU28 PASS、actual復元launcherのLight検索/設定とDark起動/編集保持を確認、Dark小窓詳細以降は未完。下記の「延期/未実機」記述はCPU実装時点の履歴。全R14/M1/M2の合格とは扱わない。

2026-10-18。版付きの復旧bundle、停止中のDB一式取得、既存先へ上書きしないCLIを実装する。R03は実装・CPU検証済み（CPU_DONE）。GUIの設定画面への導線はR10、復元先からのnative起動受入はR14とする。モデル/索引方式・元ファイル・既存機能を変更しない。

## 保存先の棚卸し

| 対象 | 実保存先 | bundle/復元先 | 扱い |
| --- | --- | --- | --- |
| 登録root/場所、タグ/棚/お気に入り/確認済み、関連語、閲覧履歴/読書位置、scan記録 | 指定catalog SQLite | `catalog.sqlite` | 必須。手動整理を含む |
| ページsnapshot/ID・保存本文、候補/承認/却下履歴・根拠 | 同じcatalog内の対応table | 同じcatalog | 既存の本文を保持するだけで、専用OCRの導入ではない |
| モデル別のtext/cover、動画frame、本文page、未承認候補vector、索引job/再開情報 | catalog名に続く `.ai.sqlite` / `.ai.<24hex>.sqlite` | 新catalog名に対応したsidecar | filenameと保存profile keyを照合。最大64profile。明示省略可能 |
| AI選択/profile ID・scope・resource方針 | 指定settings JSON（通常LocalAppData/Aredoko） | `settings/ai-settings.json` | 明示指定のみ。未指定はmanifestに記録 |
| viewerのwheel方向・一覧倍率・theme・小画像拡大 | 指定viewer-settings JSON | `settings/viewer-settings.json` | 明示指定のみ |
| ユーザーembedding profile | 指定profile directory内JSON＋明示追加file | `profiles/<name>.json` | 最大64件。ModelProfileとして検証 |
| 任意のWD profile/設定値 | 明示指定JSON | `tagger-profiles/<name>.json` | 最大16件。WDProfileとして検証 |
| 元画像/動画/本/音声、モデル重み・venv、logs・一時score DB、session token/検索取消ID | 対象外 | 含めない | 無断走査・download・外部送信なし |

保存先を推測してLocalAppDataや私物を一括走査しない。CLIは明示catalogの直下で、そのcatalogに対応するsidecar名だけを列挙し、明示profile directoryのJSONだけを列挙する。command-lineだけの起動方針（port/ranking/Layaなど）は自動収集しない。必要なembedding/WDのoverrideは明示profile-fileへ渡す。配布時のschema JSON同梱はR13へ引き継ぐ。

## 停止・一貫性・publish

1. **AredokoのGUI/バックエンドを終了してから手動実行**する。現行production mainとCLIは、catalog横の `.owner.lock` にOSの排他lockを保持する。使用中は失敗し、別processの終了/killは行わない。lock fileは削除せず、kernelが終了/crash時に解放する。古いlease未対応の実行中versionや、直接ProductionCatalog/production_handlerを呼ぶ開発toolの停止までは検出できないため、全所有者の停止を前提とする。
2. catalog→全選択sidecarのSQLite接続とdata_versionを記録し、全DBにBEGIN IMMEDIATEを取得。取得中の変更を検出したら失敗する。書込予約を全て保持した状態で、別のread接続からSQLite backup APIを実行する。business SQLの更新や稼働中DBの単純file copyは行わず、committed WALもsnapshotへ含める。busy時は待ち続けず失敗する。
3. 通常file/全祖先・reparse/symlink/hardlinkを確認し、file identity、DB版、sidecar/profile membership、設定bytesを終了前に再確認する。設定JSONの確認は前後の楽観的検査であり、非協調的な外部writerのABA変更や全ファイルの分散atomic性/TOCTOU完全解消まで保証しない。停止前提を迂回しない。
4. 出力は**新規directoryのみ**。作成中の出力catalogも完了markerまでleaseで保護する。snapshotはjournal_mode DELETEへ揃え、WAL/SHM/journalをpayloadとしてコピーしない。成功時だけmanifestを最後に書く。通常の失敗/取消は、作成した同一identityの出力directoryだけを片付ける。電源断やcleanup自体の失敗ではpartial directoryが残り得るが、完成manifestなしのbundleは復旧に使わない。既存directoryを再利用しない。

DB write予約はsourceを変更するSQLではないが、他のwriterを止める。バックアップを日常操作と同時に裏で自動実行する機能ではない。元メディアのstat/画像decode/モデル推論は行わない。

## bundle format v1と復旧

`manifest.json`は `format:aredoko-recovery` / `version:1`、日時、Python/platform表示、cache_policy、未指定設定一覧、各fileのrole/path/bytes/SHA256（DBはschema指紋・vectorはprofile）を持つ。pathはroleごとの固定相対名だけを許可し、絶対path・..・重複・未知field/role・過大値・JSON重複keyを拒否する。SHA256は破損検出であり、外部から来たbundleの発行者を認証する署名ではない。

- 現行SQLite user_version=0と[固定したtable/column契約](../app/storage_schema_v1.json)を確認。必須tableと既知optional tableを許可し、未知version/table/column、trigger/view、integrity_check/foreign_key_check失敗は拒否。古いbundle versionを推測して書き換えない。既存アプリの開く際のmigrationは維持するが、任意の古い/新しいDBに対応する汎用migrationではない。
- 全選択payloadをSHA/size・schema/profile/JSON検証してから、新規復元先へbounded copyする。file増加やcopy後不一致・manifest変更を拒否。SQLite companion fileのあるlive payloadも拒否する。restoreは元bundle/catalog・既存設定・現行profile directoryへ書き戻さず、restore内の `recovery.json` を最後に保存する。
- `--omit-ai` backupは再生成可能な別DBを最初から省略。vector fileが失われた/壊れたbundleは通常restoreを拒否し、**明示 `--without-ai` のときだけ**手動catalog/設定を救出する。省略はrecovery.jsonへ記録し、モデル別索引の明示再準備が必要。catalog内の保存本文・候補履歴・ページsnapshotは消さない。
- interrupted/running jobの記録はコピー時には保持する。ProductionCatalog/VectorStoreを開くと既存のrunning/cancelling→interrupted処理を適用し、**自動再開しない**。同scope/profile/版/固定pageを確認した明示再開だけを従来どおり許可する。
- root pathは元の登録値を保つ。ホストやPython runtimeによる物理source token差があっても、値を書き換えてcurrent扱いにしない。常にsource再検証が必要とreportし、実際の物理検査が不一致ならstale/再スキャン/明示再索引へ進む。manualタグ/履歴/読書位置の記録は失わず、変更後の本への誤ジャンプを許可しない。

初期上限：bundle 32GiB（CLI max-bytesで64KiB〜256GiB）、最大148 entry、manifest256KiB、設定/profile16KiB（viewer2KiB）、copy/hash buffer1MiB。DB backupは256pageごとに容量/取消を確認し、backup APIのcopyはprogress callbackで経過600秒を超えると失敗する（整合検査/hash/restore等を含む全体deadlineの保証ではない）。destinationの空きは、全DB write予約後のpage_count×page_size（WAL内のcommitted分を含む）を使った推定量の2倍＋8MiBで事前確認する。SQLite native領域/RSS・全処理のp95を実測した合格値ではなく、実容量不足でも元データを上書きしないための工学的上限。restoreでvectorを省略してもmanifest全体の宣言容量上限は検査する。

## 手動コマンド例

変数には自分で確認した対象と**まだ存在しない出力directory**を設定する。以下の案内は実利用DBで実行した記録ではない。指定しなかった設定は自動で探さない。

```powershell
python tools/backup_library.py backup --catalog $CatalogFile --settings $AISettingsFile --viewer-settings $ViewerSettingsFile --profiles $ProfilesDirectory --output $NewBackupDirectory
python tools/backup_library.py restore --bundle $BackupDirectory --output $NewRestoreDirectory
# AI別DBを省略することを明示して、手動整理を復元する場合
python tools/backup_library.py restore --bundle $BackupDirectory --output $AnotherNewRestoreDirectory --without-ai
```

embeddingのcommand-line overrideは `--profile-file`、WD設定は `--tagger-profile-file` で明示追加できる（繰返し可）。バックアップ保存先は個人のmetadata/元path/保存本文を含むためGitHubへ追加しない。

復元したcatalogは新directoryの `catalog.sqlite`。設定を使用するときは、**復元されたものだけ**既存launcherの `-AISettings` / `-AIProfilesDirectory` / `-ViewerSettings` へ指定する。WD overrideを使う場合は `-TaggerProfile`、単独embedding overrideは従来の `-AIProfile` を選ぶ。未収録の設定/directoryを指定しない。モデル重みは既存app側のmodelsを使い、存在しない場合も自動取得しない。新しいprofile directoryは `--ai-profiles-dir` としてPython hostへ明示的に渡せる。通常の起動引数はそのまま使える。

## CPU検証・未確認

開始HEAD `e05837788b75bc3fced811848c4cd36c4a13abaa`、実装 `896c7f52838efb47cebb028098a3f8134be188b9`。初回fixture16件中15ERRORは公開ページ一覧に内部snapshot_idがあると仮定した新テストの誤り。fixtureだけをpage_headsのSQL参照へ修正し、16PASS、その後設定/profile回帰と補強44PASSを確認した。最初の未保存raw outputはtool履歴にあり、data/recovery/r03-checks-20261018-01/initial-fixture-summary.jsonは**要約**である。全raw logが保存されたとは扱わない。生成スキーマ取得補助もSQLite接続close漏れによるWindows temp cleanup失敗を修正し、所有tempだけを確認後に片付けた。製品backupの不合格を隠す修正ではない。

**全Python570件：567 PASS /3 Windows platform SKIP /440.775035秒**。専用Python3.11.9関連 **54 PASS /31.346266秒**。最終前の568件全体/52件専用環境も合格したが、その後のtarget lease/WAL見積もり2件補強後に最終全体を1回確認している。ログ/source SHAは `data/recovery/r03-checks-20261018-01/` へ新規保存。C#/XAML未変更のため今回Core/Releaseは再実行しない（以前の528/Release合格は履歴）。launcherはPowerShell AST構文・空白を含む生成pathでの実引数組立を検証し、process起動0。実UI/起動CLIのnative伝達・AOT/High Contrast/Narrator・実モデル/実私物1TB性能/実別ホスト復元・停電中断は未検証。GPU/GUIは現在の指示で延期し、必要時事前確認する。

次はR04の明示索引継続。R03のGUI導線は既存設定へ簡潔に統合するR10で、backup専用の複雑な管理画面を追加しない。P0累積2/2終了・専用OCR保留・旧book-batch取消PNG未完、全機能と原本保全を維持する。
