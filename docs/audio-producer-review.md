# R07の次の一点レビュー：長時間producerと保存・検索への接続

2026-10-26。**Astraクラスの設計レビューを推奨**。全ロードマップの作り直しや、新しいフロントエンドの選定は不要。回答後の実装はSol/Antigravityが小区分で進める。

## 確定済みの入力

- [予備評価](audio-input-evaluation.md)：既存固定EG2、生成8本/日英11query/類似2問で全Top1。小規模合成素材の結果であり実録音/実曲/ASR比較は未完。
- [実装済み契約](audio-content-design.md)：検証済みhandleから最大30秒の16kHz mono f32le、取消/原本/登録再確認。text/audio profile・専用key、bounded private worker、完全ゼロだけskip、最大payloadの実CPU pipeも確認済み。
- 本番text/cover profile、legacy索引、既存512D音響保存、通常DBは維持。新workerを自動索引/GUIへは未接続。

## この範囲だけを決める

1. **worker/namespaceの配置**：専用text/audio workerを必要時だけ所有する方式と、将来の全modality profileへの移行を比較する。queryも対応するnamespaceのencoderへ渡す。画像用workerとの同時VRAM・idle release・取消の所有を定義する。768D直接音声を512D音響や既存transcript列へ無条件に格納しない。
2. **長い音声の完了境界**：全PCMを保持せず30秒以下の窓へ分割する。逐次decode/backpressureと時刻根拠、512MiB/24時間上限、所有childのdeadline/取消/回収を決める。反復seekで空窓が得られただけでEOFと判定すると、timestamp gap後の音を落としうる。exact30秒境界/partial tail/無音/破損/不明durationも明示する。
3. **atomic保存と復旧**：1itemの完了後だけ新revisionへ置換し、取消/失敗/解除時は既存索引を保つ。候補0の成功を未処理と区別する。複数namespaceが動く場合のwriter fence・backup snapshot・再起動/restoreとguard順を定義する。
4. **検索への最小接続**：root/棚/favorite/missing等の共通scopeと安定順を維持し、item単位にbest window/時刻を集約する。直接音声には転写文がないため、架空snippetを表示しない。動画/音声プレイヤーへ時刻を渡す。既存結果sessionや文字/視覚順位を壊さない。

## レビュー後の実装単位

1. 生成65秒/正確60秒/途中gapのCPU fixtureで、bounded窓producer・終了/取消を完成させる。
2. 選んだprofile/namespaceへatomic保存し、失敗・無音0候補・source変更・backup fenceをCPUで確認する。
3. 限定検索/時刻根拠へ接続してbuild/関連test。生成音声だけの実GPU一連は、新たに具体的な許可を得てまとめる。
4. 通常設定/GUIへ明示的な導線を追加する。実録音/曲や比較モデルの取得は別の許可・評価とする。

M1の残受入（HC/物理DPI/clean Windows等）とruntime公開review/hostは独立の残件。R07実装開始をM1/M2/全媒体の完成宣言にはしない。P3の全件snapshot待ちの残改善も[current-handoff](current-handoff.md)から継続する。

## 最初の実装単位：逐次PCM producer（2026-10-26）

長時間decodeの部分だけ先行実装。`audio_stream.PCMStream`は検証済みhandleから1所有FFmpeg/1 readerで30秒以下を逐次出力し、queueは1窓、readerの作業1窓、consumerの受取窓でbackpressureをかける。512MiB原本/24時間decoded上限、入力protocol/format制限、10秒のdecoder待ち/30分session、取消・early break・所有回収を維持。全音声のPCMは保持しない。

`aresample=async=1:first_pts=0`でpresentation時刻のgapを無音として維持する。無音/短い窓をEOFと推測せず、全stdout・float整合性・正常exit・最終source guardまで通った場合だけ`complete=True`。窓は暫定であり、consumerはこれより前に既存索引へ公開してはいけない。`PreviewReader.audio_pcm_stream`は原本版・登録・除外を各yield/EOFに再確認し、audio専用slot1つを所有。HTTPへは追加していない。

生成60/65秒、timestamp gapを持つfragmented MP4、非finite/破損/上限、deadline/取消、戻り値ありの非zero終了、入力変更/登録解除/除外、slot解放をCPUで確認。stream12・source18は開発Python3.14/基本Python3.11の両方PASS、既存preview22 PASS。GPU/モデル/通常DB使用0。**worker配置・新namespaceでのatomic保存/backup fence・検索/GUI接続は未実装で、上記レビューの残りを維持する。**

## 次の実装単位：専用namespaceでのatomic保存（2026-10-26）

`AudioDirectIndex`を内部APIとして追加。呼出元が所有するtext/audio encoderを明示し、そのprofile専用sidecarだけに保存する。選択中のtext/coverや旧768D発話snippet/512D音響とは混在させない。30秒固定の逐次入力をprivate SQLiteへstage（最大16MiB/最大2,880窓）。正常EOF後だけcatalog guard→共有writer fenceの順で予約し、最終原本版・登録/除外・取消を確認して1itemのsource markerと時刻vectorを同一transactionで置換する。silent成功0候補はmarkerへ記録し、未処理と区別する。

新しい`ai_audio_direct_sources`/`ai_audio_direct_windows`のあるaudio sidecarだけ`user_version=1`。既存sidecarは0を維持。backup/restoreの既知schemaとversion確認、inactive root purgeの両table削除も同時更新。decode/encoder待ちではwriter fenceを保持せず、途中のlive backupは以前の完了revisionを見る。vectorのstage読出しは64行ずつで、全window vectorのlistを作らない。検索への公開、通常producer job/GUI、音声workerの起動/idle releaseはまだ未接続。

CPU14（開発/基本Python）PASS：失敗・取消・容量不足・原本変更で旧索引保持、silent marker、名前空間拒否、将来版拒否、stage削除、backup待ち取消、encode中backupの旧revision、旧/新sidecar復元、root purge時の原本保持。既存backup29・profile10もPASS。初回はSQLite接続contextがcloseしない解放漏れと、URI無効のprimary接続からのATTACHを検出し、明示close＋専用read-only接続に修正。次の1 FAILは2窓それぞれで同じroot解除を繰り返したfixtureを1回解除に修正したもの。`data/ai-ui/continuation-20261026b/audio-index/`に診断/修正後ログを保持する。供給PCM/人工vectorによる保存試験であり、実GPU音声検索の精度証拠ではない。
