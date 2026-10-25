# 圧縮ファイルの統合種類フィルター（U6）

2026-10-25。利用者の「ZIPではCBZが見つからない」に対応する検索カテゴリ。

- 一覧の種類選択を「圧縮ファイル」に変更し、hintでZIP・CBZを明示。保存/応答の `archive=ZIP`、`book=CBZ/PDF/EPUB/フォルダ本` は維持する。CBZのcard表記は圧縮ファイル、既存の本ビューアで開く。旧 `kind=archive` は引き続きZIPだけを選ぶ。
- 新 `kind=compressed` は共通SQL predicateでZIPとCBZのみを対象とし、UIで後からfilterしない。本カテゴリからも従来通りCBZが見つかる。PDF/EPUB/フォルダ本は混入させない。RAR/7zを新規対応した意味ではない。
- 通常/履歴/favorite/棚、AI検索/類似の共通候補取得、保存済みAI scope、未承認タグ候補、ページ本文、結果sessionへ同じpredicateを適用。AI設定には新しいscope種類を末尾追加し、旧種類のindex/意味を維持する。DB移行・既存vectorの作り直しは不要。
- U4b補強：本文/未承認候補の従来 `status<>'excluded'` も `present` に揃え、成功scanでmissingと確定した原本が通常検索へ戻らないようにした。本文/候補のデータ自体は残す。
- CPU compressed7、既存AI scope12/production8、Core1132 PASS。生成ZIP/大文字CBZとPDF/EPUB/画像、scope交差、frozen結果、本文/候補のmissing除外を確認。偽エンコーダーのみ、実モデル/GPUなし。Portable frontend07 publish成功、既知警告を保持。ログは `data/ai-ui/continuation-20261025b/`。
- この変更のGUI/Light/HC/DPIは未実施。frontend06/native-selection03のU4b/U5確認をU6のGUI結果と混同しない。新ZIP候補と未受入はcurrent-handoffを優先する。
