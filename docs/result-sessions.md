# P2 固定順序の結果セッション（backend/API・Core契約）

2026-10-22。P1B実装 `18c366e` に続く小区分。**P2はPARTIAL**。backend/API・Core clientに続き、[native所有session/range/非同期neighbor/選択復帰をsource接続](result-session-native-connection.md)した。Core/WinUI build/native受入は未確認で、現在の配布で60件を越えて送れると報告しない。

## API

全てPOST `/api/library/results/<action>`、token/Origin/Host必須、body32KiB以内、新APIの重複JSON/未知fieldを拒否する。

| action | 本文 | 内容 |
| --- | --- | --- |
| create | session_id、conditions | client生成32桁hex ID。全ページを固定してready後に公開 |
| status | session_id | 状態・総数・元条件 |
| range | session_id、offset、limit | offsetから1–120件。元の順位と根拠を保持 |
| neighbor | session_id、item_id、direction | -1/+1。混在結果の検索順で画像だけを前後取得。ordinalは全結果内の0始まり位置 |
| close | session_id | 所有領域を破棄。作成中は協調取消、遅延readyを拒否 |

conditions.modeはliteral/history/semantic/similar/page-text/pending-proposals/pending-proposals-semantic。各方式の既存query/kind/view/root_ids、またはAI scope/source/literal_only/group_threshold/result_group、候補/本文のshelf/modelをそのまま使う。similarはitem_idを指定。既存APIにないsort/棚機能は追加せず拒否し、現在の順序を固定する。旧page APIは互換維持。

rangeは既存検索metadata＋items・offset/limit・conditions・session_idを返す。neighborは対象がなければneighbor:null。読込失敗・scope/版の変更をnull（末尾）と偽らず409＋result_session_changed。有効期限/終了は410＋result_session_expired、保持されている元条件と要求のcurrent_idを返す。容量不足/同時作成は503で全件未公開。別条件の結果を既存sessionへ混ぜない。

## 固定と再検証

- 最大120件の既存検索pageを順に消費し、順位・ID・根拠・metadataを専用一時SQLiteへ保存。全件metadataのRAM配列/画像/modelは保持しない。AI/類似/タグ候補意味検索は**一度の推論/順位計算と同じScoreSpool**を、任意result_sinkへ渡す。追加range/neighborはAIを呼ばない。同順位の既存stable ID順を維持する。
- catalogの共有connectで、queryに影響するwriteの世代をcommitと同時に記録。登録/scanの既存epoch、active profileとindex DB data_versionも固定する。view_history/reader_progress/scan_jobsだけの書込は結果世代を変えず、閲覧中に履歴順を組み替えない。永続schema/table/triggerを追加しない。
- 登録状態/除外/祖先/metadata/物理identity（device/inode/size/mtime/ctime）を取得時にも確認。同じsize/mtimeの差替えも拒否。folder本は既存tag_sourceの版確認を再利用し、類似検索の起点も確認。privateな物理identityを製品応答へ漏らさない。
- 通常文字検索にあった「除外設定を変えてもscan前は結果に残る」問題も修正。履歴以外にも現在の除外規則をSQL条件で適用する。
- 所有backendの書込とDB leaseを前提にする。第三者が生のSQLite接続でleaseを無視してcatalogを書き換えることへの完全な検知機構ではない。index変更は保持monitor接続で検知し、通常のread transaction/WALを保持し続けない。

## 資源・寿命・未検証

3session、idle15分、結果DB合計512MiB以内。ranked作成時は既存ScoreSpool上限256MiBを先に予算から予約。結果DBのrollback journalはMEMORYで、全DB大のjournalをdiskへ二重確保しない。容量不足は成功/部分結果にしない。所有reaper/close/backend終了で削除し、close先行IDも15分の有界tombstoneで再公開を拒否する。

この予算は管理下の結果DBとranked作成の予約であり、無関係な旧page検索・SQLite内部sort spill・OS一時領域全体のhard quota/RSSを実測保証したものではない。P7の複数session/大規模/容量/終了計測は未実行。全件固定が終わるまでcreateはreadyにならず、進捗GUIは未接続。

`LibraryApi.Results`に反射不要DOM方式のCore clientを追加。条件copy、ID一致、範囲/件数、画像neighbor、expiry時の条件/現在ID、idempotent close、応答8MiB上限を扱う。**Coreテストのソースは追加したが.NET SDKがないため実行・build未確認**。

## 検証

生成125画像＋混在metadata、60→61/61→60/120→121、history固定、root/filter/除外/解除、タグ編集、物理差替え、期限/条件保持、3session/容量不足、作成中close、disk保存、AI query1回・追加取得の再推論なし、旧類似pageと同値、7方式の実loopback HTTPを確認。

- 初回15件:13 PASS/2 FAIL（fixtureが走査順をfilename順と誤認、substring件数の期待誤り）。rawを保持。
- 修正後の関連83 PASS/14.745s。
- 物理版pin追加後15件:14 PASS/1 ERROR。通常文字検索のscan前除外漏れを修正し、source/production関連24 PASS/3.688s。
- 7方式APIの追加1 PASS/1.295s。
- 最後の影響回帰は141 PASS/1 runner ERROR（存在しないtest_tag_candidate_search指定）、26.413s。production/AI/spool/similarity/tag semantics/page text/関連語/backupを含む。正しい候補検索テストを別途指定し1 PASS/0.738s。既に通った141件はrunner名の修正だけを理由に再実行せず、重複合算しない。
- 最後に期限切れclose markerの自動除去を修正し、その新規回帰1 PASS/0.117s。

生logはignored `data/ai-ui/result-sessions-20261022/`。実model/GPU/private scan/GUI/Windows/.NET/Actionsは実行せず、旧Alpha/basic03/shortcut/DB/schema/元ファイルは変更していない。P1B/P2をnative受入済み、M1/M2完成としない。

## 次の1件（下記はbackend実装時の履歴、最新はnative接続文書）

Windows依存のあるUI接続を始める前に、既存SDK/cacheで追加CoreテストとPortable buildを一回確認。MainPageで条件ごとにsessionを所有し、page追加取得でrangeを使う。ImageViewerSequenceを非同期neighborへ接続し、古い応答/expiryを拒否、close後に最後のitemの選択とscrollを戻す。閲覧によるhistory追加ではsessionを作り直さない。GUIを再実行できなければ未確認を残し、独立backend項目へ移る。既存GUI cap・raw失敗・全機能/OCR保留を維持。

今回のraw log（失敗・途中版も保持）は [永続検証記録](validation/20261022-work/) を参照。


## 2026-10-25 bounded cursorと検証の接続共有
通常/履歴の結果作成はcatalog.searchの任意result_sinkへ接続する。COUNT/フィルタ/順位SQLを一度だけ評価し、同じcursorから最大120件ずつ消費する。従来の単ページAPIのOFFSET・返却形式は維持。部分一致、関連語のdirect/related順位、検索根拠、棚/登録フォルダ/履歴条件は共通の返却整形を使用する。AI側の既存順位spoolは変更しない。

FrozenResultは1ページにつき1接続で最新metadataを取得するが、各原本の祖先・物理identityを引き続き検査する。前後のgenerationと各itemの取消を検証し、恒久的なアクセスcacheは作らない。停止時はbuilderを最大5秒待ち、生成中workspaceを早く削除しない。上限・全件順序確定・部分結果を公開しない規則は維持。

生成関連：result_session27、production7、文字/関連語/棚/履歴43 testsをそれぞれPASS。120件の旧検証/バッチ検証の全payload一致、接続1回・原本guard120回、途中の編集/登録解除で失効、取消後のwriter利用を確認。計測 `data/ai-ui/p3-global-edge-20261025/cursor50k-report.json`：同じ120件を0.363005s→0.048205s、5万metadataの全snapshotはcProfile有効で24.498863s、末尾range/owner close成功。50k実ファイルscanやcold/warm統計ではない。

旧COUNT反復を残した最初の全件測定は長時間化して9,720件時点で中断（正確な全件比較時間なし）。所有一時結果DBだけの排他lockによるtimeoutを使い、解除時の一時directory cleanup PermissionErrorもrawに残す。元catalog/原本/他アプリは変更せず、当該試験process終了済み。旧baselineを全件完走や速度倍率の根拠にしない。初回snapshotを全件完成してから公開する設計の待ち時間は今後の残件。
