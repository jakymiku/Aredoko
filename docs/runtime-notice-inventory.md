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

## 2026-10-28：静的DLL依存を読取監査、MSVC追加要件を発見

`inspect_runtime_native.py --imports`と`pe_imports.py`を追加。[Microsoft PE仕様](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format)に沿ってPE32/PE32+のRVAをsection/raw境界へ照合し、通常importとdelay-import（RVA/旧VA形式）からDLL名だけを読む。1 file 2MiB/96sections/各table512importsまで。危険なpath/切断header/未終端/曖昧RVA/clock別の原本変更を拒否し、DLLや選択runtimeをload/importしない。basenameと同architectureのinventory候補を記録するが、Windows loaderの実解決・dynamic loading・export forwarder・権利監査とは扱わない。

生成PE9＋NOTICE/native統合9が開発Python3.14でPASS、PE9を同梱Python3.11でもPASS。実packの新規report `data/ai-ui/continuation-20261028/runtime-import-review02.json` は既存manifest `52406ef…`の**325 file全ての静的表を検査、2,757 edges（delay1）、読み取り956,460bytes**。元manifest/通知metadataの対応も保持。全payload再hashやpack作り直しはせず、`redistribution_approved=False`/loader/dynamic未検証を維持する。

**公開前の具体的残件**：`onnxruntime.dll`と`onnxruntime_pybind11_state.pyd`はamd64の`MSVCP140_1.dll`をimportするが、pack内に同名候補がない。[ONNX公式](https://onnxruntime.ai/docs/install/)もWindows向けVC++ runtime要件を明記している。開発PCの成功だけではclean WindowsのWD動作を保証できないため、[Microsoftの再配布対象確認](https://learn.microsoft.com/en-us/cpp/windows/determining-which-dlls-to-redistribute?view=msvc-170)に従う正式な同梱元/条件の確認、または明示導入要件とclean Windows試験が必要。System32からの無断コピー、OSへの自動install、任意DLLサイト取得で埋めない。`caffe2_nvrtc.dll`のdelay-import `nvcuda.dll`もpack外で、GPU driver側依存として別途確認する。basename重複247edgesはloader誤解決の実証ではなく、候補の曖昧さとして残す。


### 2026-10-28 終了前のMSVC配布元preflight（導入なし）

既存Visual Studio Communityの`VC/Redist/MSVC`は`14.44.35112`だけがあり、その直下は`Auxiliary`のみ。期待する`x64/Microsoft.VC143.CRT`は存在しなかった。この標準redist配置を確認した範囲であり、PC全体をDLL探索していない。現在のpack不足を「VSがあるから解決済み」と扱わず、System32や他アプリのDLLをコピーしない。

[Microsoftの配布ファイル判定](https://learn.microsoft.com/en-us/cpp/windows/determining-which-dlls-to-redistribute?view=msvc-170)では、central Redistributableを推奨しつつapp-local配布も可能と説明する。ただしapp-localでは更新提供をアプリ側が担う。[VS2022 REDIST一覧](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution)は正規ライセンスを持つ利用者が該当条件の下で未改変ファイルを配布する範囲を示し、debug_nonredistを除外する。[配布条件の案内](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)も個々のライセンス確認を求める。これをAredokoの権利承認や再配布物の完成とはしない。

次は正規の固定取得元・版・容量/hash・ライセンスを揃え、ZIP方針に合うapp-local CRT一式か、利用者に明示する公式Redistributable導入かを選ぶ。新取得/展開/実行/OS導入/pack変更は今回行っていない。app-local採用時も単に欠けた1DLLを置くだけで完了とせず、そのDLLの依存と実workerの探索経路を確認する。clean Windows未受入。


### 2026-10-28 Work：公式取得案内の再開情報（実体未取得）

[Microsoft公式最新版案内](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170)を再確認。v14の最新版は頻繁に更新されるため表に版番号を載せず、取得後のファイルpropertyで確認する方式。現掲載x64リンクは`https://aka.ms/vc14/vc_redist.x64.exe`であり、固定version/hashの成果物URLではない。対象architectureを一致させ、利用toolset以上のruntimeを使う要件を維持する。推測の版/hashや移動リンクだけでtrusted catalogへ登録しない。

[公式DLL配布指針](https://learn.microsoft.com/en-us/cpp/windows/determining-which-dlls-to-redistribute?view=msvc-170)はcentral配布を推奨し、[再配布条件](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)はVSライセンス等に基づく個別条件の確認を求める。今回の閲覧は個別承認でも導入方針の確定でもない。次は許可済み取得環境で正規成果物の版/bytes/SHA256/署名・適用条件を記録し、app-local同梱なら全依存とworker探索経路、centralなら利用者の明示同意/管理者要件/未導入時の基本機能継続を設計してから受入する。今回DLL/依存の取得・展開・実行/OS導入/pack/registry変更は行わず、情報待ちとして独立した一括favoriteのsource接続を進めた。


### 2026-10-28 静的なMSVC取得物receiptの準備（取得回答待ち）

`tools/inspect_msvc_redist.py --source <EXE> --source-url <公式URL> --output <新JSON>`を追加。最大96MiBの通常EXEをSHA256/サイズ/PE stubで照合し、Windowsの[Get-AuthenticodeSignature](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/get-authenticodesignature)とFileVersionInfoで有効なMicrosoft署名/版/製品名を読む。選択EXEの実行・展開・OS導入・DLLコピーはしない。x64 installerのstubがx86でもpayload architectureと混同せず、payload検証/取得URL由来の証明/再配布承認/clean Windowsはfalseに残す。[公式案内](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)の可変URLを固定catalogの代用にしない。

生成7tests PASS、基本Pythonの初期6testsもPASS。生成した未署名bootstrapを読むWindows metadata確認は、親PS7のPSModulePathによりinbox PS5.1が互換性のないmoduleをautoloadして初回失敗。子processだけinbox Modulesを参照するようにし、署名NotSignedと版を読取成功。実行policy/OS環境を変更しておらず、raw失敗JSONと修正後証拠を保持する。実MSVCファイルは今回まだ取得せず、具体的取得許可の回答待ち。ライセンスや取得物の承認完了とはしない。


### 2026-10-28 明示許可後の実成果物確認

公式x64 EXEを専用先へ1回取得し、**14.51.36247.0 /18,731,856bytes / SHA256 `843068991daaa1f73ad9f6239bce4d0f6a07a51f18c37ea2a867e9beca71295c`**、Windows署名status=Valid/署名者Microsoft Corporationを確認。[公開可能な取得元receipt](msvc-runtime-source-20261028.json)に公式redirect後URL・版・容量・hashを記録。最新版リンクの内容を推測で固定したものではない。installerのPE stubはx86で、内部x64 DLLの検証とは区別した。

公式ページが示す現行v14 runtimeライセンス原文（39,553bytes、SHA`08651651…`）も読み取り保存。インストール・利用の許諾と再配布の条件は同一と扱わず、runtimeの再配布制限と、別途のVisual Studio REDIST許諾との適用関係を確認する必要がある。**取得/署名確認は再配布承認ではない**。元EXE/ライセンスはignored evidence内だけ、Gitにbinaryを含めない。実行/展開/OS導入/DLLコピー/AI pack変更/catalog登録は0。

次は適用するVS配布許諾と対象版の照合、ZIP方針に合う正式なapp-local CRT入手方法の決定→許可された別出力先で依存DLL一式/loader/通知を確認する。central導入を採用する場合も利用者の明示操作と権限・取消を扱い、ソフトが黙ってinstallerを実行する設計にしない。今回の取得許可をインストール許可へ拡張しない。


VS Community 2022の公式原文（62,859bytes/SHA`41a207b1…`）も確認し、Section 4のDistributable Code許諾とREDIST一覧への参照、配布条件を取得receiptへ対応付けた。runtimeの利用者向け条項だけで一律に配布不可とも、署名があるから無条件で配布可とも判断しない。採用するファイル一式とVS許諾の適用・利用者向け第三者条項/NOTICEを整えた後に、新たな明示範囲でstatic展開/依存/loader確認へ進む。今回の範囲でEXE実行やDLLの再配置を行っていない。


### 2026-10-29：インストーラーを起動しない静的展開の準備

取得済みの同一署名済みEXEについて、既存7-Zip 26.01の一覧表示だけを実施（追加取得/展開なし）。WiXの[Burn v2公開構造](https://github.com/wixtoolset/wix3/blob/develop/src/burn/engine/section.cpp)に基づくbounded readerで、UX CAB=offset479744/140070bytes、attached CAB=offset630000/18091661bytesを読み取り確認。元EXEを実行しない。`tools/burn_containers.py`の生成4件PASS。

明示許可後だけ使用する`tools/extract_msvc_review.py`を準備。固定source receipt/hash/現在のMicrosoft署名を照合し、新規の専用先へCABとflat memberを保存する。既存7-Zipを指定し、stdoutを逐次制限（単体64MiB/合計256MiB/512files）、危険path/同名case/予約device/上書きを拒否。installer/MSI action/DLLは実行しない。生成4件PASS。ツールを作ったことは実体展開や配布許諾の完了ではない。

`tools/read_msi_inventory.py`はWindowsの[MSIDBOPEN_READONLY](https://learn.microsoft.com/windows/win32/api/msiquery/nf-msiquery-msiopendatabasew)と固定File/Media SELECTだけで対応表を読む。生成4件と、Windows上で自作したDB fixtureの実API読取/原本hash・mtime保持にPASS。検査ツール自身はcommit/transform/install/action/stream展開APIを使わない。fixture生成時の新DB作成と、選択MSIの読取を区別する。証拠`data/ai-ui/continuation-20261029/`。

**取得済み公式EXEの展開は追加質問の回答待ち**。前回の取得/静的確認許可を展開/OS導入へ拡張せず、実CRT inventory/署名/依存/適用NOTICE/再配布条件・loader/clean Windows・公開host/registryは未完。既存のsealed pack/Alphaは不変。次は回答後に同じsourceから新規先へstatic展開し、File/MediaとCAB内容を対応付ける。


### 2026-10-29：許可後のx64最小runtime実体を静的照合

追加の明示許可後、同じ公式EXEを新規`msvc-static01`へ静的展開。EXE内部は25 files/18,819,437bytesで、arm64とx64のMSI/CABが併存する。x64 minimumのMSI File/MediaをREADONLYで読み、対応するCABだけを別の検査subdirへ展開。**12 files/2,666,168bytes、全てamd64/14.51.36247.0、MSIのID/サイズと一致**。既知の不足`msvcp140_1.dll`もこの正規set内に存在する。[公開可能な固定inventory](msvc-crt-inventory-20261029.json)に全SHA/版/署名者/import/delay-importを記録した。set内のVC系静的依存未解決0、Windows API-set等・実loader/forwarder/混在する旧CRTは別検証。

全12のWindows署名はValid、発行対象名はMicrosoft Windows Software Compatibility Publisher。最初のprobeはCorporate signerだけを想定して停止したが、元EXEの固定SHA/署名とMSI/CAB対応を保ったまま、実際のMicrosoft署名者を記録した。これを任意publisherや署名エラーの無視へ広げていない。初回の過剰条件FAILをrawで保持。原EXEと抽出物のSHA再照合済み。installer/DLL/MSI action実行0、OS install0、既存packへのコピー0、公開0。

今回の追加許可はここまでの静的展開/検査で消費済み。**再配布許諾・通知の適用、アプリlocalへの新規組込み、実worker DLL探索/読み込み、clean Windows、公開host/registryは未完**。不足1DLLだけを無断コピーせず、世代の異なる同梱CRTとの関係を確認して新規packへ扱う。上記のtool準備時「展開回答待ち」は当時の記録で、この実施結果を優先する。


### 2026-10-29 継続：既存packを変更しないapp-local CRT試験候補

`tools/prepare_ai_runtime_crt.py` を追加。明示した既存sealed pack・固定CRT inventory・そのsource reference・完全なPython通知bundle・固定原本license DOCXから、新規のローカル試験packだけを作る。`--check`は作成しない。12 DLLの全名/amd64/版/署名記録/サイズ/SHAを束縛し、rootの旧CRT2個は新しい出力内でだけ置換する。wheel内の同名2個はRECORDとの関係を保つため変更せず、配置をreportする。元pack/元CRT/通常設定/OSは変更しない。

コピー中に元manifestの各bytes/SHAを検証し、新しい出力を再度全検証して封印。失敗/取消では作成した最終markerだけを外し、partial evidenceを残す。古いPython通知を修正版bundleへ入替え、別のnative component manifestに12DLLと原本DOCX/可読TXT/NOTICEのhashを記録。可読TXTはWord段落の抽出で、原本も同梱する。再配布承認・clean Windows・実DLLロードの成功をbuilder自身が宣言することはない。

生成PE/偽license/専用packの10tests PASS（原本/輪内CRT保全、全依存set、通知束縛、改変・危険path・混在版・未知入力・出力重複の拒否、取消、最終検証失敗時のmarker撤去）。前段9件は基本Python3.11でもPASS。実体の `continuation-20261029b/crt-runtime01` は **23,918files/4,950,784,575bytes**、manifest SHA `9ac04f2d56895690dd620971f2d3ae1dcffe731d45ba5225b26a4f86f845f731`、コピー/全検証まで成功。動作確認は次の単位。今回ユーザーの「テストは好きに実行」を専用の配置/実行確認へ適用し、前日の静的展開だけの許可とは区別する。新しい依存取得/installer実行/OS install/公開はしない。

[Microsoftのapp-local指針](https://learn.microsoft.com/en-us/cpp/windows/choosing-a-deployment-method?view=msvc-170)に従い、更新責任もapp側に残る。[2026 REDISTの対象](https://learn.microsoft.com/en-us/visualstudio/releases/2026/redistribution)は適切にライセンスされたVS等とその条項を条件にしており、旧2022条項の保存やDLL署名だけで公開を承認しない。公開時のpublisher適格性/適用条項・利用者向け通知の最終確認は残る。ここは技術的なローカル試験候補で、製品registryに登録していない。


### 同候補のCPU loader確認

`tools/check_ai_runtime_crt.py` は通常のruntime binding/既定オンの完全照合後、PATHから開発用環境を除いた専用子processを2本だけ逐次起動する。PyTorch2.9.1+cu128/TransformersのimportとCPU tensor演算、ONNX Runtime1.23.2のimport/providersが成功し双方exit0。EnumProcessModulesで実際に読んだCRTの場所とbytes SHAをcomponent manifestへ照合し、両processの共通CRT、特にORTの **MSVCP140_1.dllが新packのrootから読まれた**ことを確認した。単なるbasename候補一致をloader合格にしていない。

生証拠 `continuation-20261029b/crt-load01/report.json`。全23,918files/4,950,784,575bytes照合は66.980秒（コピー直後でcache状態が違うため前日の162秒との速度改善比較にはしない）。import/CPUは12.877秒/0.830秒。manifest不変、GUI/GPU推論/モデルロード/通常DB/settings/OS installなし。開発PC上の限定受入であり、WindowsのAPI-set/driver/未ロード機能やclean Windows、公開権利/host/catalogを完成扱いにしない。


### 同CRT候補の実モデル/private worker確認

新しい `crt-runtime01` だけを選択し、既存EmbeddingGemma 2とWD Tagger、生成PNG2枚/専用DBで1バッチ確認。productionの完全照合72.872秒をモデル時間から分離し、EmbeddingGemmaの画像入力768D/有限/単位norm（CUDA、割当上限3,072MiB、telemetry peak931.8MiB）、WDのCPU候補6件がPASS。モデル起動/入力は23.176秒/3.424秒（一般性能値/検索精度ではない）。両所有workerを回収、既存kill解放のexit1/1。全選択入力metadata・生成PNG SHA/mtime不変、専用DB integrity=ok。ダウンロード/通常settings/OS導入なし。

`tools/check_acquired_ai_runtime.py --existing-repository-models`はexactなrepo/models rootも明示選択でき、実際に使う2profileのmodel directoryだけをsnapshotする。別modelを列挙せず、cacheは専用先へ、CUDA予算/空き3GiB条件/完全検査を維持。初回 `crt-models01.log` は試験側の誤ったimport名でCLI開始前停止（GPU/worker開始0）。実在するtagger_profileへ修正しCLI importを確認後、`crt-models02/report.json`が上記PASS。新しいruntime上の接続確認で、全媒体/音楽/実画質・clean Windowsの受入ではない。


### Native部品と通知のbound対応/輸送サイズ

`msvc_component_contract` をbuilderと静的native auditorで共有し、専用component manifestの12DLL/3通知をsealed inventoryと照合する。偽のscope/承認、欠落/重複/改変/architecture不一致は拒否。小さいCRTと通知だけは全SHAを追加確認し、残る巨大native payloadの全検証・loader/権利承認とは分ける。生成5新規＋既存builder/native19関連tests PASS。実同候補の335 native中、Python RECORD対応285、MSVC component対応12、残る未対応38。unmapped_distribution_record_count=50を別記して、件数の意味を隠さない。全PE読取成功、静的VC未解決import0。actual loader/GPUの成功は前節の限定試験で、この静的auditはloader合格を捏造しない。

配布輸送ZIPを1回作成し、全ZIP memberのstreaming SHA検査にPASS：**3,034,460,747bytes**、SHA `094ce0398f85b46cbb0c92635155953b9dec0db857757f1d448ebf440268005f`、作成163.751秒/読取17.629秒。`continuation-20261029b/runtime-transport01/report.json`。既存の単一ZIP v3は利用可能だが、[GitHub Releasesの1asset 2GiB未満](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)を超えるため、そのまま同hostへ置けない。次は互換を維持した分割transportの取得/展開を小単位で追加する。公開host/条項/registryの承認待ちは保ち、実uploadや架空URL登録は行わない。


### 分割輸送は実装済み、公開準備の残件（2026-10-29b）

上節の「次は分割transport」は `292fdf2` で実装・生成HTTP/再開/展開/owned publication確認済み。実ZIPも1.90GB＋1.134GBの2partへ分割して全member/結合bytes SHAが一致し、基本ZIP16にも取得側を収録した。[輸送正本](runtime-archive-transport.md)を参照。実3GB外部配信や公開承認ではない。

次は固定candidateの残る38 native（Python RECORD外）について実物と同梱通知の出所を対応付け、Microsoft等の適用再配布条項・実際の不変host/URLが揃った段階でproduction runtime catalogを登録する。既存の生成HTTP/同pack loader/GPU成功を繰り返して公開監査の代用にしない。権利/hostが未確定なら推測で登録せず、独立したUI/既知未受入を進める。


38件の具体的な内訳も読取確認済み：CPython本体4件（python.exe/pythonw.exe/python3.dll/python311.dll）と `DLLs/` 以下34件（標準拡張、OpenSSL/libffi/SQLite/Tcl/Tk等）。候補rootに `LICENSE.txt` は存在する。**38個のDLL不足や38個の起動エラーを検出した意味ではなく、Python wheelのRECORDにもMSVC componentにも属さないファイルの通知対応が未確定という意味**。次回はこの一覧とCPython同梱通知の実体を対応付けるところから始め、名前だけで第三者部分の再配布許諾を断定しない。既存335件のstatic import/実CRT loader成功は保持する。
