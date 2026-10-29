# 動画の場面・一致区間の代表素材評価（2026-10-29c）

前回の赤/青clipによるAPI接続確認に加え、ユーザー指定の検証用ZIP2件にある承認済み生成画像を、3本の無音slideshowへ派生した。原ZIP/モデル/通常DB/settingsは変更しない。追加取得・GUI・再生・WD・専用OCRは使わない。実写/動作理解/動画内音声/一般的な検索精度を証明する評価ではない。

## 固定素材・質問

- `scenes-ordered.mp4`：夕焼け教室0–16秒、赤い傘の雨16–32秒、神社と巫女32–48秒、森の魔法陣48–49秒。
- `scenes-reversed.mp4`：上記4場面の逆順、各16/16/16/1秒。
- `scene-control.mp4`：ネオンの路地裏、4秒。
- 1fps/256×384/MPEG4、9区間/102frame。検索語と同じscene名は動画のfile名・手動tagに入れない。直接動画profileのRGB入力→実worker→保存索引→文章検索を使う。
- 質問はscene4種＋neonの日本語5問、雨/神社の英語2問。fixtureのSHAに質問と正解区間を事前固定し、結果を見て変更しない。

## 実測（1 GPUバッチ）

既存EmbeddingGemma 2、子のPyTorch割当上限3,072MiB、空きVRAMが3GiB以上のときだけ実施。3file/9区間を保存し、日本語/英語 **Top1 7/7、平均Recall@3 100%、MRR 1.0、一致区間13/13**。A/B両方にsceneがある質問は2itemとも正しい区間を返すことを確認。1秒tailも `[48,000,49,000)` へ一致。例えば雨はA `[16,000,32,000)` / B `[32,000,48,000)`、教室はA `[0,16,000)` / B `[48,000,49,000)`。

整合性の完全照合 **85.938秒** と、索引作成 **37.047秒** を分離。最終推論telemetryは1424.1MiB/66.6msで、バッチ全体/driverの最大値ではない。速度の一般保証にはしない。画像workerは未起動、動画worker解放後の保存済み類似検索も追加decode/推論なしで動作。Aに最も近いBの一致は雨同士（A16–32秒/B32–48秒）。DB integrity=ok、fixture全SHA/モデルmetadata不変、所有worker停止（既存kill releaseのexit1）。

証拠 `data/ai-ui/continuation-20261029c/video-scene-fixture01/fixture.json`（SHA `bb85770ad5bf4e439ee35f92c9c5dce6eb79896af5a7c47a788251da381c183f`）、`video-scene-gpu01/report.json`、対応log。実行tool SHA `ed3f04eab0d89003a65b52b2fe4dc92f830275a4db281fd4711f24c658fe420c`。UIA/sourceの実機キー確認とは無関係なheadless GPU評価である。

## 再利用

```powershell
python tools/evaluate_video_scene_assets.py prepare --zip <承認済み8枚ZIP> <承認済み6枚ZIP> --output data/ai-ui/<new-fixture>
<既存AI環境>/python.exe -I -B tools/evaluate_video_scene_assets.py run --fixture data/ai-ui/<fixture> --runtime <同AI環境> --output data/ai-ui/<new-evaluation> --gpu
```

prepareは明示された2ZIPだけを読み、新規outputだけへ生成する。runは専用fixture/DB・既存runtime/model・offline cacheを使い、完全照合を推論時間切れの前に完了させる。最大300秒の索引batch後に中断/所有解放。評価完了のpassとaccuracyを分離し、品質低下があっても正直にmetricsへ残す。

CPUの正解/時刻/集計/入力改変・未知file拒否6testsがPASS。最初のprepareはhelper import名が違い、ZIP読取/output作成/GPU開始前に停止した。実在の `video_previews._executable` へ直してCPU生成→GPU1回が成功。成功した同素材のGPU評価をコード/モデル/decoder/順位変更なしで反復しない。次の品質対象は動作を含む代表動画/実音楽・録音等で、別の明示された素材と正解が必要。
