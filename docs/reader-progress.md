# 読書位置と見開き方向の保存

実装commit **9accf85e27dea0b3a39d3e49ceaf64161af3e59f**。[最新handoff](codex-handoff.md)を正とする。

CBZ/ZIPを詳細の「本を開く」で開くと、本ごとに最後に表示できたページと表示方向を復元します。方向は設定または右クリックの「単ページ」「見開き（右→左）」「見開き（左→右）」で変更します。表紙は単独、それ以降は2枚ずつ。見開きの保存位置はペアの先頭で、再開時も同じ組を表示します。

表示できたページだけをAredokoのDBへ自動保存し、元の本や手動タグは変更しません。本が更新され、登録情報を再スキャンすると、古い位置の復元を止め先頭から開きます（表示方向は保持）。「最初から開き直す」はcoverを表示し、成功するとcoverを新しい読書位置にします。読み込みに失敗したページや、読み込み途中で閉じた未表示ページは保存しません。

保存に失敗しても閲覧は続けられます。下部の案内を確認し、設定/右クリックの「読書位置を保存し直す」を使用します。位置取得に失敗した場合は先頭から表示し、古い位置は移動/方向変更/明示保存まで上書きしません。保存中は操作を直列化し、通信は5秒で期限切れになります。フォルダ登録解除/除外中は読書位置のAPIも利用不可。再登録では位置を保持します。

## APIと安全境界

| Method / route | 内容 |
| --- | --- |
| GET `/api/library/reader/{id}/progress` | `{"progress":null}` または `{"progress":{"revision":"64桁のhex","page":0,"mode":"rtl"}}` |
| POST 同route | 本文 `{"revision":"64桁のhex","page":0,"mode":"single"}`、成功 `{"saved":true}` |

pageは0..9999かつ現manifestのpage_count未満。modeはsingle/rtl/ltr。未知field・bool/不正page・不正ID/URLは400。GETはHost/token、POSTはさらにOrigin必須（403）。非本/未接続/解除・除外は404、stale revision/scan busyは409、preview枠busyは503。POSTの現manifest検査は既存のactive root・除外/link/索引stat安全境界を再利用し、scan publication guardとDB transaction内で保存します。revisionは既存のmetadataによる変更検出tokenで内容hashではありません。別tableへの追加で既存タグ/schemaを壊さず、任意file pathを受け付けません。

C#は固定IDroute・反射不要JSON・応答4KiB・正のContent-Length/MIME/受信長/取消/5秒deadline。既存画像/page/video要求の40秒deadlineは維持。

## 検証と限界

全Python271 PASS158.203秒・Core188 PASS・最終Release28.99秒PASS（既存IL2104 2warning、WinUI analyzer未実行）。新API7 tests。native02は55 checks/keys34/skip0/10PNG全目視/正常close2/warning0。Light/Darkで再open・app再起動・RTL方向/位置、保存/取得503、手動retry、corrupt/cancel・タグdraft、実生成book変更/rescanを確認。native backend processは継続、backend再初期化でのDB保存はPythonで確認。旧native01の55PASSでも目視の保存状態ラベルを修正した履歴を保持。

```powershell
$env:NO_PROXY='127.0.0.1,localhost'
python -m unittest discover -s tests -p test_reader_progress.py -v
dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore
dotnet build src/Aredoko.WinUI -c Release -p:Platform=x64 -p:SelfContained=true --no-restore
python tools/test_image_viewer_ui.py --reader-progress-only --output data/ai-ui/reader-progress-new
```

native batchは所有test appと生成DBだけを使い、book.cbzのrevision変更fixtureのみ明示許可。他source/settingsは不変。既存user appがあると停止、port8769を使うため他native batchと直列実行。証拠はignored data/ai-uiに保存、Gitへ含めません。

全codec/高DPI/Contrast/Narrator/全Tab/500px未満/極端に低い高さ/titlebar X・Alt+F4、遅いDB/5秒timeout/複数client競合のnative試験、zoom/scroll保存・履歴/削除UI・フォルダ本は後続。実素材の読書品質・大量負荷の保証ではありません。
