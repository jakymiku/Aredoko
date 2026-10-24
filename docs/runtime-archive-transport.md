# Optional AI runtime: single ZIP transport

2026-10-25。P6の任意runtime取得を、ファイルごとのHTTPSから**1つのZIP取得＋所有stageでの展開**へ接続した。旧v1/v2カタログとモデル2件のfingerprint/profile/namespaceは変更しない。実runtimeの製品registryは公開監査/配布先が未完のため0件のまま。

## 契約と安全性

v3はruntime専用、archive roleの固定ZIP1個と `runtime_archive` の3値（manifest_sha256、unpacked_bytes、unpacked_files）をsource-owned fingerprintへ含める。ZIP SHAだけでなく、展開先inventoryのSHAも固定する。ネットワーク中断は既存Rangeで再開する。展開中の中止は公開前で止まり、次回は検証済みZIPから無通信で展開を再開する。最後の所有publication gateでだけ新versionへrenameする。既存の公開済みpackは改変・修復しない。

`runtime_archive.py` は `extractall` を使わず、bounded inventoryとZIP全memberを先に照合。path traversal/絶対/予約名/case alias/親case不一致/リンク/重複/非対応圧縮/暗号化/余分なfileを拒否する。1 path最大32 components、ZIP entry上限200001、manifest32MiB、runtime payload64GiB/100000 files。親prefix全保持をせず、並べた隣接path比較でメモリ増大を避ける。1MiB単位の転送と各file SHA/CRC、普通のpathと読取前後identity、manifest ABI/isolated _pthを確認する。原本・通常DB・外部環境は変更しない。選択したコードをimport/実行しない。

展開先は新規directory、再開は取得ownerが所有する未公開stageだけに適用する。stage内のmanifestにある不完全な通常fileのみを再生成し、未知file/リンクは保全して拒否する。圧縮＋展開容量と余裕領域を空き容量判定へ含める。UIは取得/展開後の容量を分け、`extracting` 状態で中止を有効にし、展開中を表示する。モデル取得の既存画面は維持する。

## publisher手順（公開・登録とは別）

```powershell
python tools/prepare_ai_runtime_archive.py --source <sealed-runtime> --output <new-runtime.zip>
python tools/build_ai_runtime_catalog.py --archive-path <runtime.zip> --output <new-catalog.json> --id <id> --revision <fixed-revision> --base-url <actual-immutable-HTTPS-directory> --license <reviewed-summary> --license-url <official-license-page> --allow-host <actual-host>
```

準備時に元manifestに対して各fileをstreaming hashしながら圧縮し、原文NOTICEも含める。カタログ作成ではZIPをstreamで再検証し、自己申告だけで公開しない。取得catalogのsource registrationは別reviewで行う。推測URLや仮のproduction hashは登録しない。ZIP/receiptは新規先のみ、失敗時の部分出力は証拠として残す。

## 確認と限界

- 展開/publisher15 tests、生成HTTP取得7、従来runtime25/取得14/owned job6は各PASS（別実行）。Core1025 assertions PASS、Portable publish0 errors/既知WUI1001×3/SDK IL2104×2。publisher初回はdigest import漏れのNameErrorを修正、再確認済み。
- 新規native `data/ai-ui/runtime-archive-native-20261025/run01`：生成ZIP/専用DB・Dark、容量の2区分、展開中中止、無通信再開、公開だけでは設定を変えず、明示確認でnext restart保存。17 checks PASS、5 PNG目視、通常exit0/残存なし、selected fixtureの実行試行0、artifact request1回。旧モデル/復元flowの反復ではない。
- 実在ローカルpackの1回の圧縮/展開往復：`data/ai-ui/runtime-transport-20261025-01/runtime-cuda128.zip` **3,033,364,547 bytes**、SHA `1b9dbdbca3fe3d7e15de3a40a860bd0f19dd5bdb5a8fa5c8a6ccd7128d8c441d`。展開 **23,903 payload files / 4,947,898,990 bytes**、manifest SHA `52406ef10fa4f131a0ed81396621c2126afc2c84e42a245c5c34b142f6077b64`。全file hash/通知52配布物のsource binding一致、展開87.524s（単回CPU、通信速度ではない）。roundtrip-report.json参照。GPU/モデル実行/外部取得/送信/通常設定変更0。

これは実行環境の輸送実装とローカル整合の確認であり、公開向けnative依存の権利監査・不変URL・署名・clean Windows動作受入ではない。実runtime catalogは未登録。ZIPの約3GBは基本版へ含めず任意追加のまま。
