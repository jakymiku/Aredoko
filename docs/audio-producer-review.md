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
