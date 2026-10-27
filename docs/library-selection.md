# ライブラリ複数選択・一括整理（U5）

## 基盤（2026-10-25）
- 選択はセルや現在pageではなく、frozen result sessionとstable item ID/ordinalで所有。`LibrarySelection` は600行windowの外でもIDを保持し、範囲は既存rangeを最大120件ずつ読む。条件/session変更や取消後の古い応答は採用しない。
- 初期の一括上限は**256作品**。超過は明示して拒否し、途中切断や部分保存をしない。上限内でもメタデータだけを保持し、選択のための画像復号はしない。
- 認証付き `POST /api/library/results/locate {session_id,item_ids}` は現scopeに残るID/ordinalだけ返す。`edit {session_id,item_ids,operation,shelf_ids}` はfavorite_add/remove、shelves_add/removeを提供。favoriteと棚は曖昧toggleにしない。棚の追加/解除で別の棚の所属を失わない。
- editは所有session lock→catalog guard→1 transaction。全IDがsession内、現root/除外/metadata/原本版が同じ、存在・利用可能であることを全件確認してから更新。取消/索引世代変化はcommit前にも確認してrollback。成功時は元sessionが世代変更で無効になり、同条件で作り直してlocateで選択を再配置する。
- 棚は既存の最大64所属を維持。合算が超える場合や不明な棚では全件rollback。原本の書換え/削除は行わない。
- CPU selection API9 PASS（混在favorite/追加棚/解除/範囲外/原本変更/解除/取消rollback/不正入力/認証・二重JSON・旧session拒否）。Coreでは600件外保持、60/120跨ぎのrange、上限/取消/古い応答/誤順位/locate/64bit棚IDを確認。証拠は `data/ai-ui/continuation-20261025b/`。
- 基盤commit **454dba0**。以降のUI接続/受入は次節を優先する。

## WinUI接続と限定実機（2026-10-25）
- Extended選択、Ctrl/Shift、未ロード範囲の所有range準備/中止、256件上限、選択件数と一覧外件数、複数右クリックの明示favorite/棚追加・解除、明示詳細の複数summaryを接続。単クリックで詳細を開かず、単一draftの破棄確認も維持。
- 編集後は同条件sessionへ置換し、locateで残るIDを再配置。最大600行の現在windowと可視anchorを保ち、60行へ戻さない。literalのfavorite編集は生存card/サムネイルを再利用し、対象の除去/補充/移動だけ反映。AI根拠変更や棚変更など安全な比較ができない場合は600行以内の再描画へ戻す。
- 一括保存中と一覧更新中を表示し、次の一括操作を一時無効化。タグ保存もDB commit直後を「操作可能な完了」と表示しない。同期SelectionItem providerを壊さないよう、ボタン無効化はイベントを返してから行う。
- frontend05/06は正しい自己完結Portable構成＋実評価receipt。GUIはユーザー許可の新規2回＋追加1回。01は補助PS1の実行ポリシー拒否（OS設定/Bypass変更なし）、02は一括保存後の再検索待ちを固定sleepで待つハーネスが早すぎた。進捗/無効化を実装修正し、06で03を実行。
- **native-selection03：18項目PASS、全体はFAILのまま保持**。Shiftキーによる2件選択、明示summary、一括favorite/棚、600件を越えた一覧外2件保持、favorite限定結果の対象除去、修正した起動時設定保存/再起動/初画面後queue/所有中止/タグdraft維持/明示保存、所有frontend2プロセスの通常終了を確認。6枚PNG全目視、Dark通常幅で重なりなし。
- 最終の「一覧を更新」だけタグ保存後の再検索完了前に押され、未実施。harnessを `TxtTags.IsEnabled=true` 待ちへ修正し、タグ保存の進捗文言も改善。**追加GUIは行っていない**。旧U4の3試行と生ログも維持。新しいGUIには今回ユーザーの回答を得る。
- 未確認：Ctrl+マウス/右クリック・grid・逆方向Shift/範囲取消・Light/HC/DPI、最終refreshボタン。source実装済みと実機未受入を分ける。GPU/実モデル0、通常DB/私物/旧Alpha/Actions変更0。次はU6のZIP/CBZ統合種類filter。

## 2026-10-26：閉じた詳細パネルでの一括操作と再受入

- グリッドでCtrl＋クリック→右クリックfavorite保存の直後、一覧の置換中に次の棚操作を押せて無反応に見える隙間を確認。詳細を閉じていても選択欄へ保存/一覧更新/完了を表示し、一括メニュー・詳細・選択解除は処理中に無効化。完了後に同じ選択のメニューを作り直す。providerを同期disableしない既存のyieldは維持。
- 新しい生成native `data/ai-ui/startup-review-20261026/selection02` はLightでShift複数選択、一括favorite/棚、600行外保持、favorite限定解除、起動時設定保存/再起動/所有中止/draft保持/明示保存/最終refreshまでPASS。所有frontend2回通常終了、6PNG目視。従来のFAIL記録は書き換えない。
- `grid02` はDarkで実Ctrl＋マウスの非隣接2件、右クリックfavorite/棚の対象一致、grid→listの選択保持、明示解除を確認。3PNG目視、元生成画像不変、所有frontend正常終了。`grid01` はfavoriteのDB反映をUI完了と誤解した待機不足と、閉じた詳細では進行が見えない製品の改善点を分離してFAIL保持。
- `selection01` は通常版が開いていて既存backendへ接続し、生成Item1が見つからず保存操作前に停止。試験serverへWindows排他bindと起動ID/接続時の照合を追加した。別のAredokoが稼働中なら試験はbind時に停止し、通常版を閉じたり接続先として流用しない。
- 未確認はHC/物理DPI移動、長時間の実媒体RSS、範囲選択の入力中取消など。上の限定PASSを全製品/配布/clean Windowsの受入へ流用しない。

### 表示切替の先頭アンカー
- リサイクルされたcontainer辞書の先頭が画面の先頭とは限らず、grid→listで先頭/選択画像を画面外へ送る原因になっていた。アンカーは可視Y座標→結果順で選び、表示範囲外・既に消えたcontainerを除外する。partial rowの位置と既存の末尾固定は維持。
- `startup-review-20261026/grid03` の新候補でCtrl/right-click一括操作に加え、切替後のItem1可視を確認。全3PNGを目視し、先頭と選択枠の保持を確認した。

### 2026-10-26 範囲読み込みの中断
- 同じ検索の追加ページ取得を中断すると、有効な結果sessionまで破棄し、詳細editorも無効のまま残る不具合を修正。現在versionの同一sessionに対する取消だけはsession/既存行を維持し、ページ番号とeditorを戻す。条件変更・期限切れ・通常の失敗での破棄は維持する。
- `startup-review-20261026/cancel-range01` は不具合を再現したFAILとして保持。修正後の`cancel-range02`は生成1,201枚の専用DBで61–120の行/選択/編集保持、暗黙保存なし、121以降の再取得、新しい入力による検索、正常終了を確認。3PNGも目視済み。全検索方式・長時間試験の受入を代替しない。

### 2026-10-28 お気に入り1件変更の全件再作成を回避

通常の`literal`/`view=all`だけ、お気に入り保存後に所有結果の当該payloadを更新し、順序/件数/selection/他の行を保つ。`keep_session`は任意bool、旧4field APIは従来通り失効する。世代を進めるのは自分の1transactionだけと照合し、root/index/他の書込の変更を吸収しない。保存前は選択元の実file/scope/取消を検証し、保存後は同じcatalog guard内でprivate snapshotを更新する。private更新やstamp確認が失敗した場合、metadataは保存済みで`kept_session=false`と返し、保存失敗とは偽らず再検索へ戻す。favorites view/AI順位/棚編集は全再取得のまま。

Coreはcreate時のcapabilityがある場合のみ拡張を要求し、旧serverには従来fieldだけを送る。WinUIの単体favorite（詳細checkbox/右click共有handler）は保持成功時にcaption/menuだけを更新し、未保存タグ/棚を保存しない。既存のviewport rangeは移動ごとに原本を再検証する。新しいGUI試験`--favorite-patch`はUIA checkboxで同じsession/再検索0/タグdraft保持を確認する用意まで、native未実施。

関連Python14/既存session35/Core10/WinUI build PASS。生成5万PNGの既存fixtureをread-only確認してDBだけcopyした1回のCPU確認は、snapshot30.633秒とは別に、**favorite保存＋snapshot更新11.949ms、provider呼出は初回の1回のみ、選択元確認1件、先頭/末尾ID保持、DB integrity=ok、元fixture DB不変**。raw `data/ai-ui/continuation-20261028/favorite-50k01/report.json`。GUI全体の応答やcold初回表示の速度保証ではない。GPU/GUI/通常DB/Alphaを使用していない。
