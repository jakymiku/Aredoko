# P4 登録フォルダのお気に入り（2026-10-23）

rootをmedia itemに偽装せず、registered_root_preferencesへ独立保存する。catalog1→2はBEGIN IMMEDIATEでtable作成とuser_version更新を同時commit、途中失敗はrollback。version0は従来棚移行後に2へ進む。旧binaryはversion2を拒否し、通常DB/旧Alphaは今回起動・移行しない。version1の既存棚APIは新backendでも維持する。

認証付きPOST /api/library/roots/favorite はroot_id/favorite(bool)だけ。重複JSON、不正型/未知root、scan競合を拒否する。GET rootsにfavorite/shelf_idsを追加し、旧Core応答の省略はfalse/空で互換維持。解除でfavoriteを消さず、再登録時に戻す。完全purge時だけ関連metadataを掃除する。

登録フォルダcardの星とcontext menu、favorite絞込、左「お気に入り」内の登録フォルダ一覧を追加。登録中favoriteだけを表示し、開くとそのroot全体の通常libraryへ進む。作品favoriteとは独立し、タグ等のdraftは単独favorite操作で保存しない。既存の共通template host/コンテナー/テーマを使う。

backup validator/厳密schema inventoryも同じ単位でcatalog0/1/2へ対応。versionとroot preference tableの不整合・上位版・未知schemaを拒否。旧catalog内のvector tableに限り既知catalog2を認識し、standalone vector DBはversion0のまま。

確認: root preferences最終6 PASS/1.729s（前の5 PASS/0.892sを合算しない）。既存棚移行7 PASS/1.257s、backup/restore28 PASS/19.728s、Core904項目PASS。Portable build0 errors/既知3 warnings11.79s。生成DBの移行失敗rollback、旧binary拒否、再登録/restart、実backup→新規restore、metadata purge、HTTP auth/bool/duplicate JSONを確認した。フォルダfavorite GUIは未受入、棚flow3/3とは別の機能として後続まとめ確認へ残す。

既存の棚flowでPC恒久lockとした説明は訂正済み。実clickと棚カード/代表画像/作成/改名は確認したが、最後のrename refresh待機不足でflow全体はFAIL。source修正後の4回目は実行しない。詳しくはshelf-ui-20261023.md。

次はroot初期棚の複数選択とfill-unsetの原子保存、それからP5起動中backup。P3の未確定native/性能、P6/P7/実音声も未完。使用量残り10%目安で保存/commit/push/handoffのみ、シャットダウンしない。
