# P3 結果ウィンドウ・可視サムネイル優先

## 現行追記：媒体に合わせた詳細操作（2026-10-24）

詳細の画像/本/動画/音声コマンドは、選択した種類に対応する主操作だけを表示する。未接続ファイルは対応操作をdisabledで残し、AIタグ候補も対応媒体のみ表示する。通常一覧と棚の共通ライブラリを維持し、保存/未保存/ダブルクリック/閲覧後のfocus導線は変えない。検索根拠は一覧で2行に収め、全文はtooltip/アクセシビリティと既存詳細から参照可能。棚画像が一時Unloaded→Loadedとなった場合の倍率再取得delegateも再登録する。

候補 `data/ai-ui/ui-polish-review-20261024/frontend01` はPortable publish成功（既知WUI1001×3/SDK IL2104×2）。ユーザーの今回の明示許可で、生成2 PNG/CBZ/ZIP/1秒動画/無音WAV・独立DB/設定を使いDark一連とLightの関連操作を確認した。`dark01` は媒体5種類の主操作/AI候補表示、hidden draft、明示保存、棚一覧→同じライブラリ、原本不変、exit0がPASS。Lightは `light01` の媒体別表示と `light04-navigation` の保存/棚往復/原本不変/exit0がPASS。全PNGを目視。実動画/音声の再生やGPU推論・HC/物理DPIはこの試験に含めない。

先行LightのFAILは保持：`light01` 保存完了前の遷移、`light02` テストが「保存しました」を「保存済み」と誤期待、`light03` 画面レイアウト変更時のUIA peer失効。実際のEditor再有効化を待ち、idempotentな選択だけ失効時にtree再取得・1回再試行する。媒体別matrixを無変更反復せず、最後は未到達のLight保存/棚往復だけに縮小。全所有app exit0/残存0。以下の旧「次」は作成当時の履歴で、現行順は統合ロードマップを参照。


2026-10-22。開始remote `996814119b3a83a588c9b8824874a99c49c68ec8`。既存P2 result sessionとP3派生cacheを継続。**P3 PARTIAL**、Windows/Core実行環境なし。全件表示のdata virtualization/標準containerへの移行は未完で、以下を実機合格と扱わない。

## 結果ウィンドウ

`ResultWindow`は120件単位・最大5block（保持metadata最大600件）の共通C#処理。全件数と独立したdictionaryで管理し、現在範囲と前後のみ保持、遠い移動で旧blockを捨てる。既存session.RangeAsyncを使い、検索やAI順位は作り直さない。1回の表示要求は最大120件でblock境界を跨げる。範囲外/0件でもbackendの説明metadataを維持する。

表示範囲はcache済みでも必ずrange再取得し、scope/原本版/expiry検証を省略しない。近傍metadataは先読みするが、表示に昇格した時に再検証する。SearchResponseの根拠/coverage/類似状態/部分一致等を維持する。表示範囲変更は前の取得を取消し、世代と所有tokenを再確認して遅い応答を破棄する。同時HTTPは最大2。取消を無視するtransportも返却後に新しいcacheへ公開できない。これは保持cacheの上限で、in-flight応答や現行画面が参照中のrowは別に存在する。

MainPageの現在の60件/本文20件page UIをこのwindowへ接続し、次の標準container/連続scrollへ使える層を用意した。検索変更・session終了・Stopでwindowの取消/解放、viewerの選択復帰と未保存draft確認は既存導線を維持。**連続scroll・ListViewItem手作り撤去・5万件native表示が完成した意味ではない**。

## サムネイル優先とメモリ入場制御

既存GET thumbnailへ任意`priority=visible|nearby`を追加。省略はvisibleで互換維持。生成2件・別key最大32を維持し、未開始の可視要求を近傍より先へ、同順位はFIFO。同じkeyへ可視waiterが参加すると昇格し、そのwaiterだけ取消すと残った近傍要求に戻る。共有相手が残る作業は取消さない。既に開始したcodec処理は強制中断しない。

原本guardにも2枠の制限があり、生成完了した共有waiterの再検証が競合して即503になる問題を修正。busyだけを取消可能・最大10秒の範囲で待ち直す。原本変更/解除/除外の拒否は再試行で覆さない。

復号は`width*height*12 + edge*edge*16`の保守的な作業量見積りで、64MiB予約枠へ入場させる。見積りが枠を超える従来対応画像は単独実行し、対応形式/16Mpixel上限を狭めない。失敗/取消で予約を返却、終了後は新入場不可。**これは実RSS64MiBのhard capではない**。Pillow/native内部、圧縮入力、Windows BitmapImageは別、単体超過もある。decoded全体RAM目標の実測/最終達成は未完。

## WinUI接続

CoreのThumbnailPolicyが表示幅・高さ×RasterizationScaleを128/256/512/1024へ切上げ、要求サイズを制限。現在のtile/list/detailの取得へ接続。tileのsize変更は80ms集約し、古いbitmapを保持して新しい派生画像を待つ。Unloaded/再表示で取消と世代確認、遅延応答による画像混入を拒否する。2026-10-24追加：MainPage.xaml.cs で XamlRoot.Changed を購読し、DIPサイズ変更を伴わないモニター間移動で RasterizationScale が変化した際にも80ms集約タイマー（itemSizeTimer）から実現済みライブラリカード（containerRefresh）・棚カード（shelfRefresh）・詳細プレビューの派生edgeを再評価し、既存bitmapを保持したまま必要時のみ新しいDPIバケット（128/256/512/1024）を再取得する。

成功時の「画像プレビュー/先頭画像」常設labelを撤去。gridの通常「画像・登録済み・tags」行を省き、媒体と名前を優先。未接続/未準備/検索由来・AI根拠は維持、listの種別/tagsと詳細編集は維持。省略した長名はtooltip/読み上げへ。完成形のicon/nav/detail drawer/全theme仕上げは未完。

## 実行した確認

- Python初回46実行: 43 PASS/3 FAIL、2.651s。失敗は優先queue後の原本guard枠競合。共通fixture class importによる20件重複実行も含んでおり、unique数として合算しない。
- 原本busy待機とfixture importを修正後、thumbnail/cache/HTTP/共有・昇格・取消・decode予約の**26 PASS/1.840s**。
- result session/API・既存XAML stub生成の関連**24 PASS/4.216s**。stub生成はC# compileではない。
- raw: `docs/validation/20261022-p3-window/`。初回失敗を保持し、同じ検証を再加算しない。
- Coreの5万件window上限/跨ぎ/近傍→可視再検証/遠い移動/古い応答/重複ID/expiry/終了、DPI edge/nearby routeテストを追加したが、**ソースのみ・未実行**。
- Python ASTとdiffを確認。新依存/取得/CI/GUI/GPU/private scanなし。普段DB/原本/旧Alpha/basic03/shortcutを更新していない。

## 次の1件とWindows gate

共通windowを標準container再利用と連続scrollへ接続し、左nav/検索・media一覧/右詳細の完成形UIへ進める。過去WinRT/ComWrappers問題があるため、既存SDK/cacheでCore→Portable buildを各1回実行し、型情報/x:Bindと変更画面を確認する。Windowsで50k生成metadataの実メモリ/realized cells/画像混入、60/120境界、選択/未保存/scroll、size・DPI・Light/Darkをまとめて確認する。旧GUI capを新名称でresetしない。

実機だけが必要な確認は保留し、独立して進められるP4複数棚/履歴/root favoritesのbackendへ移れる。P4 schema移行は旧scalar所属の保全/旧app書込拒否/backup互換を同時に扱う。P0/P4–7/ALPHA/M1/M2を完了としない。
