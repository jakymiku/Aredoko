# P4 画面の戻る・進む（2026-10-23）

セッション内の最大64画面を保持するCore NavigationHistoryを追加。検索条件/種類/方式/root/shelf/AI候補区分/類似起点/ページ/可視アンカー/選択/詳細開閉、登録フォルダの絞込とチェック対象を保持する。検索結果は再取得し現在の解除/除外/原本条件を再検証する。閲覧履歴DBとは別で、元メディアや読書位置を変更しない。

上部の戻る/進む、Alt+矢印、マウス前後を接続した。viewerが開いている間は既存の画像/ページ送りが担当する。新しい遷移で古いforward分岐を捨て、同じlocationの更新は増殖しない。未保存編集は既存確認を通し、キャンセル/失敗時は履歴cursorを進めない。管理画面へ進む際、承認した破棄が実際にsaved draftへ戻るようにし、同じ破棄を再質問し続けない。

Core901項目PASS（新しい履歴8項目を含む）。Portable最初build0 errors/既知3 warnings14.82s。破棄同期の最終変更後のbuild結果はローカルnavigation-history-build-final-20261023.log。WinUIスキルのテーマ/入力/反射/所有処理レビュー実施。GUIはWindowsロック中のため実行せず、mouse/Alt/選択/scroll/dirtyの実機受入は未確認。削除・順位変更後の選択先が再取得範囲から外れた場合は選択を捏造しない。

先の棚接続commitはb0a00c4。次はroot favoriteとroot複数初期棚UI、その後P5起動中backup/restore。旧P3試行上限/棚flow残り2回を維持し、別名でresetしない。旧Alpha/通常DB/原本/CIは変更していない。今回シャットダウンはしない。
