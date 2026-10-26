# AI runtime通知原文の収集とpackへの同梱

2026-10-25。P6の配布準備用。パッケージをimport/実行せず、明示した準備済みruntimeの配布metadataとライセンス原文だけを扱う。法的承認や全native依存の権利確認を自動判定するツールではない。

## 作成と使用

```powershell
python tools/collect_ai_runtime_notices.py --source <prepared-runtime> --output <new-notice-directory>
python tools/prepare_ai_runtime_pack.py --source <same-prepared-runtime> --notices <notice-directory> --output <new-pack>
```

collectorはPythonのroot通知、dist-info直下・PEP 639 licenses配下・RECORDが示すpackage内通知を元bytesのまま新規先へ収録する。Name/Version/宣言/相対path/サイズ/SHAをmanifestへ記録し、絶対入力pathをmanifestに入れない。取得/インストール/推論/ドライバー操作はない。1 file4MiB、原文全体32MiB、最大2048 files。入力の通常path/祖先/link/読取前後identityを検査する。

範囲外/親参照を勝手に辿らない。legacyのLicense-Fileが `../LICENSE` を宣言する場合は、不足として保持する。RECORDは実行OSのPath構文を解析後、安全な相対pathへ検証する（Windowsの実在wheelのbackslashにも対応）。宣言不足ならcollectorは原文と一覧を保存してexit2とし、完全性を装わない。outputの上書き・source内作成は禁止する。

pack作成の `--notices` は、原文全SHA・全inventory・参照・不足フラグの整合と、作成対象runtimeの配布metadata/元通知との一致を確認する。欠落/古いbundleはコピー前に拒否し、コピー後も一致を確認して `THIRD_PARTY_LICENSES/` として封印pack inventoryへ含める。旧CLI/既存packの読取互換は維持する。この同梱をもって公開許可取得済みとはしない。

## 実在する準備済み環境の棚卸し

既知の旧候補 `dist/portable-wincheck-20261021-02/Aredoko/runtime/python` のmetadataだけを読み、新しい `data/ai-ui/runtime-notices-20261025-03` へ収集。**52 distributions / 89 notice entries / 1,100,581 bytes**。5GB runtimeを再複製・全再hash・実行していない。

残る不足は2件：

- flatbuffers 25.9.23：原文LICENSEは収集済みだが、metadata宣言 `../LICENSE` は安全な相対path契約外。上流wheelとの対応を確認して扱いを決める。
- tokenizers 0.23.3：この準備済みruntimeには該当配布通知の原文がない。固定版の上流出所・LICENSE/必要NOTICEを確認し、入力元を勝手に改変せず補う。

CUDA等のnative依存を含む公開reviewと、不変の実artifact公開先も未完。runtimeの製品取得registryはまだ0件。このcollectorのexit2をテスト失敗や「致命的アプリバグ」と混同しない。実モデルの2取得カタログは独立して利用できる。

## 確認

生成CPU10 tests PASS、従来runtime pack/保存の25 tests PASS（別実行）。PEP 639/legacy RECORD/原文保持/出力衝突/改変/不足/親参照/Windows構文/重複Name/hardlink/対象runtimeとの一致・同梱を確認。

rawは `data/ai-ui/embedding-catalog-review-20261025/runtime-notices-*`。初回はWindowsでcase違いのfixture directoryが衝突、次に実flatbuffersの親参照、torchvision RECORDのWindows区切りを診断して修正。途中の未完収集を成功へ書き換えていない。GUI/GPU/外部取得0。


## 固定上流の補完を明示して封印する（2026-10-25）

`--supplements <reviews.json>` をcollectorに追加。任意の不足を自動承認せず、配布物Name/Version/**METADATA全SHA**・未解決License-File宣言の完全一致・通知bytes/SHA・40桁commit固定の公式raw URLを明示する。branch URL/親path/重複/改変/別metadataは新規出力作成前に拒否。外部URLはprovenanceとして保存するだけで、ツール自身は取得しない。元runtimeのファイルを追加・改変しない。

`config/runtime-notices/legacy-cuda128-20261021/reviews.json` はこの準備済み環境専用。tokenizers v0.23.3のtagをcommit `301277072263fb3830eb66eec7e47adadf76f1dc` へ解決した[LICENSE](https://github.com/huggingface/tokenizers/blob/301277072263fb3830eb66eec7e47adadf76f1dc/LICENSE)（11,357 bytes）、flatbuffers v25.9.23のcommit `187240970746d00bbd26b0f5873ed54d2477f9f3` の[LICENSE](https://github.com/google/flatbuffers/blob/187240970746d00bbd26b0f5873ed54d2477f9f3/LICENSE)（11,358 bytes）を原文で保存。後者は実dist-info内LICENSEと全bytes一致も確認した。Gitの改行変換を無効化して原文hashを保持。公式PyPIの当該版metadata/公式GitHub tag/固定treeを読み、LICENSEだけを取得した。依存コード取得・実行なし。

```powershell
python tools/collect_ai_runtime_notices.py --source <same-prepared-runtime> --supplements config/runtime-notices/legacy-cuda128-20261021/reviews.json --output <new-notice-directory>
```

新bundle `data/ai-ui/runtime-notices-20261025-04` は **52 distributions / 91 entries / 1,123,366 bytes**、配布metadataについての不足0件。seal時にも元metadata/元通知/補完原文を照合し、pack内へ補完provenanceと原文を保全する。生成16 tests PASS（従来10＋補完6、2配布物を含む封印確認）。これはdistribution通知の収録完了であり、CUDA/Rust等の全native依存の公開監査や再配布承認ではない。`redistribution_approved=False` を維持し、runtime公開URL/取得registryは未登録のまま。


## ローカル実pack・取得モデルの限定動作（2026-10-25）

`data/ai-ui/local-runtime-pack-20261025-01` を既知の準備済みruntimeから新規作成。**23,903 files / 4,947,898,990 payload bytes**、manifest SHA `52406ef10fa4f131a0ed81396621c2126afc2c84e42a245c5c34b142f6077b64`、全inventory/hash封印PASS。Python3.11/x64/PyTorch2.9.1+cu128/CUDA12.8/onnxruntime1.23.2。通知bundleを同梱、元環境は変更せず、インストール/追加依存取得0。通常起動時にこのpack作成検査を反復する仕様ではない。

別途ユーザーのGPU/CPU許可により、今回取得したEG2/WDとこのpackを使って生成2画像・専用DBで各モデル1回の動作確認を行った。`data/ai-ui/acquired-runtime-smoke-20261025-01/report.json` PASS：EG2 CUDA・有限正規化768D（worker推論1,138ms/peak931.8MiB、初回pack全検査/起動込み172.447s）、WD CPU・候補6（4.511s）。これは精度や冷起動時間のベンチマークではない。入力size/mtime、生成画像SHA/mtime保全・DB integrity=ok。所有workerは既存adapterの終了処理で停止（exit1、正常exit0とは記さない）、残存なし。GUI/追加ネットワーク/通常設定変更なし。

公開向けruntime監査・不変の公開先・実runtime取得catalogは引き続き未完。23,903 fileごとのHTTPS取得は要求回数が大きいため、正式公開前にruntimeの輸送単位も検討する。架空URLでregistryを有効化しない。配布物04には最終WD準備判定修正と初回案内は含まれず、最新sourceを候補へ更新する必要がある。

## 2026-10-26：native通知の既知の収集漏れを修正

既存packのmanifest棚卸しで、ONNX Runtime 1.23.2の`onnxruntime/ThirdPartyNotices.txt`（333,022bytes）が旧collectorの先頭語判定から漏れていたことを確認。`ThirdPartyNotices`/`THIRD_PARTY_NOTICES`/`third-party-licenses`等のtext名をdist-infoとRECORDから認識するよう修正した。既存path/通常file/byte上限は維持し、`.dll`等を通知本文として取り込まない。単にdistributionのLICENSEが揃った状態をnative通知の完全性と混同しない。

生成19 tests PASS：原文保持、表記違い、dist-info直下、旧判定bundleの新封印時拒否、既存補完/封印/危険pathの関連確認。既知の同じ準備済みsourceと固定supplementsから、新規`data/ai-ui/snapshot-review-20261026/runtime-notices05`を作成。**52 distributions / 92 entries / 1,456,448bytes**、不足distribution0、追加本文SHA`e00f828e0a33de591a355ae6606d2625f5758da7d2c844db7821c9dd3e3647b6`。sourceは実行/変更せず、約5GBの再複製/再hashもしていない。

旧sealed pack/archiveはそのまま保持する。次のpack封印では新NOTICE束を使用し、旧束の不足を許容しない。CUDA/cuDNN等のnative依存の対応付けと公開review、不変host/registry、clean Windowsは引き続き未完。`redistribution_approved=False`を維持する。

## 宣言native・RECORD・NOTICEの対応付け（2026-10-26）

`tools/inspect_runtime_native.py --source <sealed-pack> --notices <bound-notice-bundle> --output <new-report.json>` を追加。manifest、dist-info METADATA/RECORDを宣言SHAに照合し、nativeのサイズとPE architecture headerだけを読む。選択環境/ライブラリのimport・実行、巨大DLL全hash、再packはしない。出力はpackの外へ新規作成する。

既存packと新NOTICE束05で `runtime-native-review02.json` を作成。manifest SHA`52406ef…`：**325 native files、285が16 distributionsのRECORDへ対応、40が未対応、重複owner0/不明PE0**。PEはamd64 315/x86 6/arm64 4。異なるarchitectureの一部はpip/setuptoolsに含まれるlauncher stubで、x64アプリの誤配布と即断・自動削除しない。主要ownerはtorch40、scipy110、scikit-learn71、numpy21、torchvision11、pillow8、onnxruntime3等。

未対応40は`DLLs/`のCPython標準拡張・libcrypto/libssl/libffi/sqlite/tcl/tk、本体python exe/dll、vcruntime等。RECORDにないことはライセンス不存在の証明ではない。rootのPython通知と、各同梱nativeの原文/公式配布条件を個別に対応付ける必要がある。torchのRECORDにはCUDA/cuDNN/cuBLAS/CUPTI/Intel OpenMP等も含まれるため、torchというownerだけで独立nativeの公開reviewを済ませない。

生成CPU7 PASS。初回はWindows/Python3.14でpath.statのctime（creation）とfstatのctime（change）が異なることを検知して停止した。各clockをそれぞれ前後比較し、path/handle間はidentity/size/mtimeを照合するよう修正、clock差の許容とhandle内変更拒否を回帰確認した。失敗ログを保持する。

報告は宣言済みinventoryの対応付けであり、全payload SHA・extra-tree全体・PE import/delay-import/dynamic依存グラフ・静的link由来・法的承認の検証ではない。これらの未実施flagと`redistribution_approved=False`を明示する。生証拠は`data/ai-ui/snapshot-review-20261026/`。基本ZIP/installed Alpha/旧runtimeを変更せず、外部取得0。
