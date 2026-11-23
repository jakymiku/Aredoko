# 2026-10-20 ブラッシュアップ監査と現在の残り

開始HEAD `07347a2`。Argon更新を取り込んだうえで、コード・生レポート・配備ファイルを確認した。
この記録が以前の「R01〜R14全完了」より優先する。既存の実装・合格した限定テストは維持し、音声抽出と製品受入の未完を区別する。

## 今回の修正

- 詳細欄の画像/動画/音声ボタンを横一列から2段へ配置。名前・イベント・AutomationId・有効/無効状態は保持。音声選択時には自動内容索引が未対応であることを表示し、未索引の類似検索でも「索引を作れば解決」と案内しない。
- `PageBatchRequests.Create` が `JsonArray.Add<T>` を選ぶ問題を、`JsonNode` overloadの明示で修正。アプリ側IL2026が解消した。SDK由来のIL2104は2件残り、ゼロ警告とはしない。
- 配布準備は既存の出力先（空でも）を拒否し、再帰削除しない。新規先だけにコピーし、manifestを最後に公開。失敗した新規先は未完のまま残し、別の新規先でやり直す。原本/実DBの収集やcheckpointはしない。
- `config/ai-profiles` と起動引数helper、利用ガイドの参照先Markdownを同梱。古い開発用AppX/publish出力は集めない。PowerShellの実プロセスで空白/日本語/末尾バックスラッシュ等のargv保持を確認。配布構成でバックアップCLIが `backend/app` を参照するよう修正。
- WinApp起動の実バイト検証を追加。配備cache名をv2へ分離し、誤配備済みの旧cacheを再利用しない。Releaseでは未trimのbin DLLではなく、現在のx64 R2Rアセンブリと生成depsを照合する。通常開発launcherも不一致なら所有ウィンドウだけを閉じ、失敗を明示する。

## UIテストの重要な訂正：表示した画面は最新版ではなかった

新規の詳細ボタン検証で初回はfixtureキー誤り、再試行1はログのPathシリアライズ誤りで停止。再試行2でボタンが見つからず停止し、failure.pngを確認した。**この画面を最新UIの退行と判断したのは誤り**だった。

新harnessが `--arch x64` だけを指定し `-p Platform=x64` を省略した結果、10月12日のAnyCPU系AppXが配備された。起動DLL SHA256 `371f24c7d2dc71dac83bd78084e161095705c5673759257c2e8cb3664d01c911` は `bin/Release/.../AppX/Aredoko.WinUI.dll` と一致。現在のXAML/実装の画面ではなく、最新UIを巻き戻す根拠には使わない。UI巻き戻し/resetは実施していない。

`-p Platform=x64` を加えた **no-launch配備確認だけ**を別の新規先で実施。`data/ai-ui/detail-layout-probe-20261020-01` のDLLは現行 `obj/x64/.../R2R` と一致し、新しい `AudioSearchHint` フィールドを含む。Core DLL/生成deps/runtimeconfig/resources.priの5ファイルが一致。古い配備は同じガードで拒否した。これは画面確認やclean-machine起動の合格ではない。

- 生記録：`data/ai-ui/detail-polish-20261020-01/02/03`。最後のfailure.png 1枚は目視済み（旧UIと判明、現行受入は未確認）。失敗reportは成功に書き換えない。
- 初回＋修正再試行2回を消費。`winui-ui-testing/SKILL.md` の同一フロー上限を保持し、4回目のGUI再実行はしていない。harnessのPlatform/配備照合/スクロール順修正は構文確認のみ。過去の復旧/book-batch上限とも別で、いずれも勝手にresetしない。
- 最新ユーザーのGPU/GUI許可は保持する。このフローの再試行上限を恒久的GPU/GUI禁止として扱わない。

## 検証した範囲

| 対象 | 結果と限界 |
| --- | --- |
| Python 配布準備 | `test_release_staging.py` 10 PASS。生成fixture、既存先保護、失敗時manifestなし、実PowerShell argv、配布内CLIの実backup→新規restore/integrity_check |
| Python 復旧 | `test_storage_backup.py` 24 PASS |
| Python 配備ガード | `test_winapp_layout.py` 5 PASS。現在の実no-launch配備5ファイル一致・古い配備拒否も確認 |
| Core | Release全件PASS。音声の誤案内に対する2チェックを追加 |
| WinUI | x64 SelfContained Release成功、0 errors / SDK由来IL2104 2 warnings。WinUIAnalyzerは未導入で未実施 |
| GUI | 上記新規flowはFAIL/現行画面未確認。旧UIのPNGを現行の合格/退行証拠にしない |
| 原本/モデル | 生成fixtureのみ。私物走査/原本変更/新モデル・依存取得/GPU推論なし。既存の実GPU記録は再実行していない |

## R06〜R09：音声の現在地

`AudioSpeechVectors.put_segments` と `AudioAcousticVectors.put_features` は保存・比較用APIだが、production索引処理から呼ぶPCM/発話/音響抽出producerがない。通常の索引作成では音声のファイル名・タグは扱えても、録音内容や曲調の自動索引は完成していない。既存音声再生・保存済み特徴の検索/類似・時刻根拠は維持する。

`test_audio_acceptance.py` のGPU13/GUI5 PASSは、手入力の発話テキストを実EG2で埋め込み、人工512D特徴/記述子を注入した接続検証。元音声からの認識・無音判定・曲調理解の精度受入ではない。既存EG2の直接音声能力の限界、追加VRAM、別モデル方式の優位性を構造だけで断定しない。R06の実入力比較を再開し、契約を保ちつつ方式を確定する。新モデル取得は別途明示許可が必要。

## R11/R13/R14：受入の残り

- R11：最新ビルドの詳細パネルをLight/Dark・小窓で目視確認。High Contrast、100〜200%DPI、Narrator/キーボード全導線、コントラスト数値は未受入。チェックリスト存在を検証済み扱いにしない。
- R13：現在はstaging準備。Python/AI依存・モデルは未同梱。Windows App SDK依存/パッケージidentity/署名/更新/アンインストールをclean環境で未受入。実インストールや証明書信頼の変更は今回していない。
- R14：限定GPU/GUI/規模テストの合格記録は残すが、R07/R08の実入力とR11/R13を満たすまでM1/M2/RC全完了とはしない。旧R10 GUI生reportは9チェックであり、10ではない。Python629総数なら626 PASS/3 SKIPと区別する。

次の順序は [completion-roadmap.md](completion-roadmap.md) の現行台帳。UI起動の正しさ→配布の実条件→音声の実入力評価を優先する。P0 2/2/OCR保留、全機能/簡潔GUI、原本保護、Actionsなし、既存Draft PR5/main未mergeを保持する。

## コミット前のコードレビュー

WinUI Design / Code Review skillsに沿って変更差分を確認。Grid/ボタンの復元済み参照API、既存イベント/AutomationId、有効条件、テーマブラシ/既存文字スタイル、折返し、4px刻み余白を保持。同期UI更新だけで新しいasync void/ブロック処理は追加しない。CLI引数はシェル評価せず、stagingは既存先削除なし、原本読み取りなし。アプリ側trim警告はJsonNode overloadで修正。WinUIAnalyzer未実施・SDK IL2104 2件・GUI目視未確認は残るため製品受入完了とはしない。
