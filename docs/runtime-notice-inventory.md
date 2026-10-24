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
