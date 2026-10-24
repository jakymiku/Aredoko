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
