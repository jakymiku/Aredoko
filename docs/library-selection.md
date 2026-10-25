# ライブラリ複数選択・一括整理（U5）

## 基盤（2026-10-25）
- 選択はセルや現在pageではなく、frozen result sessionとstable item ID/ordinalで所有。`LibrarySelection` は600行windowの外でもIDを保持し、範囲は既存rangeを最大120件ずつ読む。条件/session変更や取消後の古い応答は採用しない。
- 初期の一括上限は**256作品**。超過は明示して拒否し、途中切断や部分保存をしない。上限内でもメタデータだけを保持し、選択のための画像復号はしない。
- 認証付き `POST /api/library/results/locate {session_id,item_ids}` は現scopeに残るID/ordinalだけ返す。`edit {session_id,item_ids,operation,shelf_ids}` はfavorite_add/remove、shelves_add/removeを提供。favoriteと棚は曖昧toggleにしない。棚の追加/解除で別の棚の所属を失わない。
- editは所有session lock→catalog guard→1 transaction。全IDがsession内、現root/除外/metadata/原本版が同じ、存在・利用可能であることを全件確認してから更新。取消/索引世代変化はcommit前にも確認してrollback。成功時は元sessionが世代変更で無効になり、同条件で作り直してlocateで選択を再配置する。
- 棚は既存の最大64所属を維持。合算が超える場合や不明な棚では全件rollback。原本の書換え/削除は行わない。
- CPU selection API9 PASS（混在favorite/追加棚/解除/範囲外/原本変更/解除/取消rollback/不正入力/認証・二重JSON・旧session拒否）。Coreでは600件外保持、60/120跨ぎのrange、上限/取消/古い応答/誤順位/locate/64bit棚IDを確認。証拠は `data/ai-ui/continuation-20261025b/`。
- **まだUIへは接続していない**。次の単位はExtended選択、複数右クリック、一括棚選択、複数詳細summary、選択を保つ差分更新。GUI/GPUは今回のユーザー回答が必要。
