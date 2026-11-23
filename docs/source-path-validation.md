# 読み取り前後の祖先リンク確認（2026-10-18）

Antigravityの`f33a96c`までの更新を引き継いだ後、原本確認の最適化で省かれた登録rootより上の検査を復元した。既存のvector非確保検証/透過保存・重複resolve削減・RRF・全機能は維持する。

## 検出した境界と変更

- `_safe_path`のroot cacheがhitすると、root自身だけをstatし、親祖先のlink/reparse確認を省いていた。catalogの`_state_epoch`はファイルシステム上のリンク変更では進まないため、同一検索バッチでもこの確認結果を再利用できない。
- `_read`の事後検査はroot自身/その配下/leafを確認するが、rootより上を確認しなくなっていた。読み取り中に木が移動して祖先junction経由になった場合、開いたleafとパスのinode/devが同じでも、リンク禁止の契約を満たさない。
- cacheにはroot path/祖先path列/解決済みrootを保持し、**link/reparseの許可結果はcacheしない**。読み取り前と公開前に全祖先を`stat(follow_symlinks=False)`で確認する。事後検査は全祖先＋root＋root下の中間directoryを重複なしで確認し、既存のleaf/handle/サイズ/mtime/ctime確認も維持。`_safe_path`は1冊1回、cached rootのresolve再実行は不要。
- linked sourceは従来の`PreviewUnavailable`、reader/ページ根拠等は`ReaderChanged`で拒否。OSError等の既存処理は維持し、原本/索引/モデル/profile/schemaを変更しない。再索引不要。フォルダ本の既存`_check_folder`は前後に祖先を確認しており、今回は変更しない。

## CPU回帰

新2テストはjunction/reparseとsymlinkの両方を模擬する。cache済みrootの読み取り前2subcase、cache有無×preview/tag_source/page_catalog×2種の事後確認12subcase。修正前は合計14subcaseがすべてFAIL（例外が出ない）し、修正後はpreview関連**22 PASS /4.991秒**。旧「親statを省く」テストを、祖先を再確認しつつ同じcache tupleとsourceだけのresolveを使う契約へ修正した。最終全体回帰は[最新handoff](codex-handoff.md)を参照。

テストは生成PNG/CBZ、実際の読み取りhandleと模擬Path.stat属性だけを使う。実Windows junctionの付け替えを実施した証拠ではなく、OS全体のTOCTOUを解消したという主張もしない。GPU/GUIテストは今回ユーザー指示で後回しにし、必要時は実行前に確認する。これは今回の作業条件である。

## 同じ固定生成fixtureの結果

1,024冊×64page、768D、`data/page-search-scale/v1-20261017-01/`。旧`サンプルv2`の7.10秒は省略された祖先検査を含まない履歴で、現行結果は`ancestor-checks-20261018`。この安全検査の復元を速度改善とは呼ばない。

| 冊数 | 旧v2秒 | 現行秒 | 現行guard合計秒 | 単一最大秒 | outer holds |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | 0.251592 | 0.330380 | 0.074501 | 0.005722 | 64 |
| 256 | 1.000417 | 1.463479 | 0.467140 | 0.006427 | 256 |
| 1024 | 7.102995 | 8.573716 | 2.151947 | 0.008740 | 1024 |

raw score.hex/順位/page ID・版・model根拠、通常mergerの結果SHA、root限定512冊、空集合は前後完全一致。原本fingerprint・vector DB SHA不変、モデル呼出0。1冊1回guardとstreamingを保持。別tracemalloc passは73.385058秒・Python割当peak 1,030,307bytes（native/OS cache/アプリ全RAMは含まない）。計器あり時間を通常時間と混ぜない。

各規模1回・昇順・Python3.14.4、前回v2の測定とは別実行。他作業/OS・SQLite cache/順序/cold-warm影響は未分離で、差のすべてを変更効果と断定しない。実モデル品質/実私物/GUI/HTTP/1TB性能は未測定。測定時のpreviews.py SHA256 `7b717793f4dfd57bd95676c7941352a71b923229c6810e03d4979b922ff76d90`（実装commitは最新handoff）。既存reportの`page_semantics_sha256`だけではpreviews.py版が分からないためここへ明記する。

```powershell
python -m unittest discover -s tests -p test_previews.py
python tools/benchmark_page_search.py measure --output data/page-search-scale/v1-20261017-01 --label <new-label>
python tools/benchmark_page_search.py compare --output data/page-search-scale/v1-20261017-01 --before safepath-v2-after-20261018 --after <new-label>
```

既存fixtureの再prepare/既存labelの上書きはしない。以前の最適化内訳と履歴は[ページ検索性能](page-search-performance.md)、実モデルの代表素材確認は[代表評価](representative-asset-evaluation.md)を参照。代表14枚の成功は任意の画像内文字に対するOCR能力保証ではなく、索引時間の前後値も単発の観測値で最適化だけの因果効果は未分離。専用OCR保留/P0累積2/2終了は変更しない。
