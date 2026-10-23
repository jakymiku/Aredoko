# 2026-10-23 終了引き継ぎ（翌日の入口）

## 再開基準

Repository C:\AI\Aredoko、branch feat/winui3-production-mvp-20261011、既存Draft PR #5を継続。実装HEAD **3e740a685c292e472085f4f918206978eabee7de**。その後はこの終了文書/台帳のcommitのみ。fetch/status/logとPRを確認し、他AIの更新を上書き/resetしない。

今夜の依頼は、使用枠残り10%前後で安全な区切り→保存・最小確認→commit/push/handoff→Stop-Computer（Forceなし）。終了準備開始は残り15%、以降は文書と保存状態確認のみ。**このshutdownは一度限り。翌日の再開で再実行しない。ロードマップ全体の完了ではない。** この文書保存時にはshutdown未実行。実行結果はチャット最終tool結果を根拠にし、記録済みというだけで電源OFF成功と推測しない。

## 今夜の実装commit

- 1cd7dc3: 標準ListView container要求時だけcardを生成、再利用時に画像/request/flyout/handlerの古い所有を解放。選択/フォーカスはnative文字列keyへ。
- f86cd60: 自分のタグ/favorite/承認保存後のobsolete result sessionを再作成。保存済み＋再取得失敗を区別しdraftを保護。
- 859b7f8: 双方向連続読み込み、120件追加・600件UI metadata/key上限、head/tail evictionとanchor補正。ResultWindowは別途120×5。viewer ordinalをwindow開始位置から算出。
- 6c29048: trimmed配布でのObservableCollection ABI例外を修正。外部generic型明示＋CsWinRT unsafe生成コードを有効化、通常buildだけで実機合格としない。
- b1cf0b6: 履歴個別/全削除、確認UI、削除前generationの遅延record拒否、読書位置/metadata保全。
- 4e23da6: 独立棚・item/root複数所属・旧scalarの原子移行・旧binary拒否・backup契約。
- 3e740a6: ProductionCatalog version1起動移行、scan/update/root登録/設定/purge、Shelf CRUD/assign API、全検索共通shelf_ids/旧名の副所属一致を接続。

## 確認範囲と未確認

P3 Coreは最新873 assertions PASS。Portable build/publishはエラー0、既知WUI1001×3、publishでは既存SDK IL2104×2も残る。native card flow3/3は最後が限定PASS（145生成件、draft/save/page往復/source invariance/normal exit）。continuous flow3/3は最終もFAIL：745件中1–180の追加とviewer60↔61の位置表示は通ったが、最後のdecode完了を待たずに閉じるrunnerで右詳細が059のまま。コードは最後にContentOpenedした項目へ戻すため、最後の61が実表示できていたか未確定。修正waitは未実行。**完全なreturn/120 viewer境界/tail/reverse/draft/RSS/thumbnail速度を合格にしない。** raw失敗を保持し、別名で同じflowを追加反復しない。

履歴Python20 PASS/9.841s、Portable build0 errors/既知3 warnings11.98s。GUIの履歴削除操作はUNRUN。

棚保存35は34 PASS/1新fixtureのDB close漏れ、失敗1だけ修正後PASS。製品接続66は64 PASS/2 ERROR（rollback fixture・旧同居vectors互換）、修正focused47は46 PASS/1新fixtureメソッド名typo、最後に失敗1＋追加HTTP1の2 PASS/0.997s。さらにResultSessions21 PASS/22.971s、Prototype Catalog6 PASS/1.181s。重複合算せず、全rawを保持。

詳しい根拠: [container](p3-native-containers-20261023.md)、[continuous](p3-continuous-browse.md)、[履歴](history-deletion.md)、[棚](multi-shelf-storage.md)。rawはignored data/ai-ui、GitHubに全rawがあるとは言わない。今回GPU推論・私物scan・新model/dependency・Actions・main mergeなし。テスト用WinUIは全て通常終了、原本/普段DB/旧Alpha/basic03/shortcutは更新していない。

**ソース・build・配布物は別。** 最新の個別native candidateは履歴/棚の最新sourceより古い。最新版ZIP/インストール版が出来たとは言わない。新しくsourceからbackendを起動するとcatalog version1へ移行するため、旧AlphaをそのDBへ戻して使う運用にしない（旧Alphaの通常DB自体は今回変更していない）。

## 次の1件（Core/UI棚接続）

CoreにShelf descriptor/list/CRUD/assignとMediaRow.ShelfIds、検索条件shelf_idsを追加。棚nav→棚一覧（名前/件数/代表画像/空棚）→同じ共通libraryへ接続する。右詳細は複数選択で保存し、旧scalar TextBoxだけの編集から移す。APIのOR棚/他条件ANDを使い、frontend独自filter/rankを増やさない。未保存draft・選択・削除確認・result sessionの取消と保存後再取得を維持する。

現状旧WinUIはscalar shelfを含めてsaveするため、新APIで複数棚へ所属させたitemの保存は安全に拒否される。これを完成仕様にせずCore/UIを優先。通常legacy単一棚の操作は確認済み。次にroot favorite/画面履歴、P5 online backup/安全なrestore、P6 download/setup/ZIP、P7まとめ受入、M1後に実音声R06–R09。完成形UIを全機能終了まで延期しない。WinUI維持/共通backend/専用OCR保留を維持。

Native再確認が必要なら上記の未確定箇所と候補・範囲をまとめて扱い、消費済み3/3を勝手にresetしない。新しい作業範囲でも先にlive tree/APIを確認し、owner PID/実payload/専用DBを守る。既存roadmapとこの最新入口を使い、完了した調査や基盤を作り直さない。
