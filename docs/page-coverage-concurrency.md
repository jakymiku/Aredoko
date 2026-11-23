# 大冊の準備状況確認：catalogロックを復号中に保持しない

2026-10-18。CPU・生成データだけでcoverage/planのcatalog競合を測定・軽減した。今回モデル推論・GPU/GUI・新download・私物走査は実施していない。

## 変更と整合性

`PageVectors.coverage`は、最初のcatalog guardで同scopeの本・許可状態・同revisionのpage head/全page ID対応を読み、**vectorの復号/finite/単位長/contract確認はcatalog guard外でstream**する。従来の`unpack`と検査条件/範囲選択は変えない。1万ページvectorの処理中に、他スレッドの整理/フォルダ編集がcatalogロックだけを理由に待たされることを避ける。

復号接続は必ず閉じてからAI終了を再確認し、次の短いcatalog guardを取る。同scopeの現アイテム・許可/除外/有効root・同snapshot ID/revision/page count・scan未実行を再検査し、最後に従来どおり原本のhandle/パス前後検査とrevision照合を行う。snapshotのページ対応は既存の不変データとして扱い、headが替われば`ReaderChanged`で開き直し。scopeから外れれば利用不可、scan中はbusy、AI終了はunavailable。原本が書き換わっていればreadyを消してstale等を返す。

棚変更は`_state_epoch`だけでは検出できないため、最後に実際のmetadataを再検索する。source stat/リンク/junction確認をcacheで省略しない。SQL readerを閉じる前にcatalog guardを取り直さず、AI DBへ書くpublisherとのlock順を逆転しない。モデル推論・vector書換え・index refresh・schema/profile変更・自動索引は追加しない。

## 固定fixtureでのCPU測定

新`tools/benchmark_coverage_lock.py`は既存coverage fixture generatorを再利用し、新規専用DB/CBZで**1冊10,000ページ、768D vectorは偶数ページ5,000本**を保存。coverageは5,000の準備済み範囲、planは次の欠け128ページを返す。同一fixture/receipt・原本hash/mtime・vector DB SHA・snapshotを前後照合する。NoModel.encodeは例外で推論を禁止、encoder呼出0。出力は`data/page-coverage/lock-v1-20261018/`、既存label/証拠の上書きは拒否。

| 操作 | 全体秒（guard競合分離 前→後） | 全体秒（今回 非確保・重複finite省略） | 今回短縮率 | guard合計秒（前→後→今回） |
| --- | ---: | ---: | ---: | ---: |
| coverage | 0.346302 → 0.363624 | **0.221163** | **39.18%** | 0.340308 → 0.034238 → 0.038309 |
| plan | 0.380105 → 0.404126 | **0.251285** | **37.82%** | 0.370705 → 0.060438 → 0.071637 |

coverageのguard保持合計は**約340ms→34ms（約90%削減）**を維持。前回のguard競合分離で総所要が0.364s/0.404sへ微増していた点に対し、今回`unpack`の重複成分finite走査を`_score_packed`と同様の非負二乗和検査へ置換し、さらに`coverage`内の準備確認で768要素リスト生成を排した非確保検証（`allocate=False` / `_is_valid_packed`）を適用した。これにより総所要は**0.364s→0.221s（39.18%短縮）**、planは**0.404s→0.251s（37.82%短縮）**へ改善した。

各操作は1回、guard計器あり、Python3.14.4 / Core i7-13700K。ユーザーPCの他作業/OS cache/順序/cold-warm効果は分離しておらず、UIの体感待ち上限・処理全体のRAM・実モデル/私物/1TBの性能保証ではない。以前の1024冊65,536page検索10.80秒/同日12.21秒/今回9.98秒とは別の操作/fixtureで、`rank`のスコア全bit契約・RRF方式・1冊1回guardに変更はない。

coverageとplanの**全JSON応答SHAが変更前後で完全一致**（coverage144,861 bytes、plan12,749 bytes）。page IDs/範囲/件数/元版/model/profile/scope・空き128選択が同じ。既存の単16page/長冊128page/複数本128page・中断/固定再開/全機能を維持、再索引不要。

## 回帰と限界

- 新並行回帰7件：復号中に別スレッドのお気に入り編集が完了し同じcoverageを返す、棚scope変更/除外/登録解除を拒否、原本書換えをstale・新snapshotを開き直しへ、scan開始/AI終了の再検査。編集スレッドはguardを1秒以内に取れることを確認する。生成テストだけを変更し、私物を使わない。
- 初回対象14件中4FAILは、テスト補助が非再入catalog Lockを保持したままpublic編集APIから再取得したため。補助を「取得可能性を確認→解放→public API」に修正し、初回ログも保持。製品コードを迂回/弱めてテストを通していない。scan検査も加え、対象**15 PASS /16.711秒**。
- 新ベンチ回帰**1 PASS /0.912秒**：小さな生成fixtureで応答比較・原本/DB/snapshot不変・呼出0・label上書き拒否・source変更拒否/failed reportを検証。全Pythonの最終結果は[最新handoff](codex-handoff.md)を参照。
- 今回は子テストプロセスに`CUDA_VISIBLE_DEVICES=-1`とoffline環境を設定し、システム設定や他アプリのGPU利用は変えていない。GUI/native・実GPU/モデル・.NET/Core/Releaseの再実行はなし（C#/XAML未変更）。旧batch取消PNG未完・新長冊GUI40項目/6枚目視の履歴はそのまま。P0 2/2終了・OCR保留・WD未承認分離を維持する。

```powershell
python tools/benchmark_coverage_lock.py prepare --output data/page-coverage/<fresh-run> --pages 10000
python tools/benchmark_coverage_lock.py measure --output data/page-coverage/<fresh-run> --label lock-before
# 改善コードで同fixtureへ新labelを取得（prepare/既存labelを上書きしない）
python tools/benchmark_coverage_lock.py measure --output data/page-coverage/<fresh-run> --label lock-after
python tools/benchmark_coverage_lock.py compare --output data/page-coverage/<fresh-run> --before lock-before --after lock-after
```

この変更は大冊coverage/planでのcatalog競合だけを対象とする。通常のページ検索`rank`の1冊1回guard、内積演算とスコアの全bit契約、実モデル精度、音声/音楽内容や一般job queueを変更/実装したとはしない。
