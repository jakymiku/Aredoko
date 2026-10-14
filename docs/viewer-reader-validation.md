# 共通画像・読書ビューアのWindows検証

> 最新：読書位置保存のnative02が55checks/34keys/10PNG全目視PASS。[変更範囲と実revision fixture](reader-progress.md)・両handoff最新を正とし、以下は各時点の履歴。

2026-10-14。実装commit **ed943b7703718085d05004c99dcc3393d1bf06df**。生成素材のみ・所有test appのみ。最終ソースのwindow検証と、以前のmodal段階を混同しない。

| Run（data/ai-ui、Git対象外） | 結果 |
| --- | --- |
| image-viewer-native-01 | FAIL 15 checks / keys 0 / skip 3 / PNG 3 / graceful close 1 / cleanup warnings 0 |
| image-viewer-native-02 | PASS 56 checks / keys 14 / skip 0 / PNG 12 / graceful close 0 / cleanup warnings 2 |
| image-viewer-navigation-01 | FAIL 17 checks / keys 1 / skip 0 / PNG 2 / graceful close 0 / cleanup warnings 1 |
| image-viewer-navigation-02 | PASS 86 checks / keys 30 / skip 0 / PNG 20 / graceful close 2 / cleanup warnings 0 |
| image-viewer-navigation-03 | PASS 88 checks / keys 30 / skip 0 / PNG 20 / graceful close 2 / cleanup warnings 0 |
| image-viewer-overlay-01 | FAIL 45 checks / keys 23 / skip 0 / PNG 11 / graceful close 0 / cleanup warnings 1 |
| image-viewer-overlay-02 | PASS 104 checks / keys 52 / skip 0 / PNG 24 / graceful close 2 / cleanup warnings 0 |
| image-viewer-doubleclick-01 | FAIL 2 checks / keys 0 / skip 0 / PNG 1 / graceful close 1 / cleanup warnings 0 |
| image-viewer-doubleclick-02 | FAIL 2 checks / keys 0 / skip 0 / PNG 1 / graceful close 1 / cleanup warnings 0 |
| image-viewer-doubleclick-03 | FAIL 2 checks / keys 0 / skip 0 / PNG 1 / graceful close 1 / cleanup warnings 0 |
| viewer-reader-native-01 | PASS 82 checks / keys 24 / skip 0 / PNG 24 / graceful close 2 / cleanup warnings 0 |
| viewer-reader-native-02 | PASS 84 checks / keys 24 / skip 0 / PNG 24 / graceful close 2 / cleanup warnings 0 |
| viewer-window-image-01 | FAIL 30 checks / keys 8 / skip 0 / PNG 5 / graceful close 0 / cleanup warnings 1 |
| viewer-window-image-02 | PASS 110 checks / keys 56 / skip 0 / PNG 24 / graceful close 2 / cleanup warnings 0 |
| viewer-window-reader-01 | FAIL 12 checks / keys 1 / skip 0 / PNG 1 / graceful close 0 / cleanup warnings 1 |
| reader-progress-native-01（旧状態表示） | PASS55 /keys34 /skip0 /PNG10全目視 /close2 /warning0、目視修正後02へ |
| reader-progress-native-02 | PASS55 /keys34 /skip0 /PNG10全目視 /close2 /warning0、[progress詳細](reader-progress.md) |
| viewer-window-reader-02 | PASS 88 checks / keys 24 / skip 0 / PNG 24 / graceful close 2 / cleanup warnings 0 |
| viewer-doubleclick-01 | PASS 22 checks / keys 16 / skip 0 / PNG 8 / graceful close 2 / cleanup warnings 0 |
| video-evidence-02 | FAIL 5 checks / keys 0 / skip 0 / PNG 2 / graceful close 1 / cleanup warnings 0 |
| video-evidence-03 | FAIL 8 checks / keys 0 / skip 0 / PNG 3 / graceful close 1 / cleanup warnings 0 |
| search-evidence-01 | PASS 30 checks / keys 0 / skip 0 / PNG 6 / graceful close 2 / cleanup warnings 0 |
| video-native-01 | PASS 50 checks / keys 0 / skip 0 / PNG 10 / graceful close 2 / cleanup warnings 0 |
| video-player-01 | PASS 70 checks / keys 30 / skip 0 / PNG 12 / graceful close 2 / cleanup warnings 0 |


全保存PNGを1枚ずつ目視。最終window画像24枚/reader24枚、追加double-click 8枚、検索根拠6枚、動画＋検索根拠最終10枚（および中間失敗5枚）、専用window動画再生12枚は余白・dock・状態/エラー/暗いcanvas/resizeを確認。以前のmodal reader01/02も各24枚目視したが、旧modalの外枠は最終windowで置換した。

## 結果の読み方

- checksは契約assert数でありテスト件数/coverage割合ではない。keysは安全guard後に送った実入力、skipは未送信。mouseは所有canvasへCLI SendInput hover/右クリック。操作ボタンのUIA invokeと物理入力を区別する。
- `viewer-doubleclick-01`で一覧（未選択状態からのレイアウト移動を含む）・グリッド・詳細サムネイルのdouble-click、未保存編集の別作品選択キャンセル、CBZサムネイルからの専用読書ウィンドウ起動・Esc終了をLight/Darkで確認し**PASS（22 checks / keys 16 / skip 0 / PNG 8）**。
- `search-evidence-01`で語別検索根拠（`SearchEvidence<id>`：直接＋関連、関連のみ、partialの直接＋欠落、関連＋欠落、全語直接一致での非表示）、未保存draft保持、`魔法"少女`・`C:\textures`タグ検索、`[`の0件をLight/Dark・wide/narrowで確認し**PASS（30 checks / keys 0 / skip 0 / PNG 6）**。
- `video-native-01`でLight/DarkのSAR 8:9動画DetailPreview 4:3比率、MP4/MKV/WebMリスト・グリッド「動画の先頭フレーム」、破損動画「プレビューなし」、503 fallbackと再接続後の再取得、検索移動による遅延要求取消、動画double-clickでviewer非起動、および語別検索根拠・引用符/バックスラッシュ/`[`検索まで一括確認し**PASS（50 checks / keys 0 / skip 0 / PNG 10）**（中間`video-evidence-02`/`03`の失敗履歴も表に保持）。
- `video-player-01`で専用window動画再生（`VideoPlayerDialog`）のLight/Dark・1200×820と700×620狭幅、生成MP4（H.264）とWMV（WMV2）の再生・一時停止・前後1秒seek・音量増減/消音、FFV1 MKV（FFmpeg先頭フレームは表示しつつWindows標準再生は非対応案内）と破損MP4の案内表示、503再試行、409更新案内、上下帯の端dock・library無効化・auto-hide/F10/Esc、背景Ctrl+S抑止、未保存タグdraft・`BtnOpenVideo` focus復帰を確認し**PASS（70 checks / keys 30 / skip 0 / PNG 12）**。
- overlay01はhide gate未通過（modal pointer handler/hover transportを同時修正）。window-image01は閉じたHWNDへのwait-forで停止し所有processの終了fallback1。window-image02は所有windowの一覧でcloseを待ってmainへ復帰しPASS。実装のviewer closeは成功していた。失敗も表に残す。
- readerの409は注入応答。元book改変/実rescanではない。Python reader16は別のbackend契約試験、古いnative105の実revision試験も当時の履歴として維持。
- 最終image4file/reader5fileのbytes/mtime/hash・settings bytes不変。AIcalls/worker0、正常close2ずつ、cleanup warnings0。新モデル/依存/CI実行なし。data/ai-uiのevidenceはignoredでGit非公開。
- Core147/preview Python12 2.363秒/reader Python16 8.584秒。最終Release25.47秒・0errors・既存IL2104 2warnings抑制なし。手動WinUI review/Python構文/diff確認。専用WinUI analyzer未導入/未実行。

専用window読書01はFAIL12/1PNG/keys1/skip0/fallback1。操作帯はIDのみでUIA peerが生成されず停止し、アクセシブル名を付けて02で検証した。手動レビューで一覧全体のdouble-tap旧選択入口を除き、thumbnail自身のIDを持つ経路だけを残した。画像02以後の変更はこの未検証入口の限定とreader帯Nameのみで、画像button/viewport実装は変更なし。専用windowの修正再実行は計2cycleで終了。

## 再開時

```powershell
dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore
python -m unittest discover -s tests -p test_previews.py -v
python -m unittest discover -s tests -p test_reader.py -v
dotnet build src/Aredoko.WinUI -c Release -p:Platform=x64 -p:SelfContained=true --no-restore
python tools/test_image_viewer_ui.py --output data/ai-ui/viewer-window-new-image
python tools/test_image_viewer_ui.py --reader-spread-only --output data/ai-ui/viewer-window-new-reader
```

既存Aredokoがあると停止する。native testsはport8769を共有するため直列実行。`--double-click-only`は別の明示された実機確認時に用いる（本turn再実行しない）。自分で起動したPID/window/foreground/focusを検証してから入力。Windowsが拒否するとskip/停止、無関係なアプリは操作しない。WM_CLOSE優先、owned processのみ終了fallbackを記録。

High DPI/Contrast/Narrator/全Tab/修飾左右/全codec/500px未満の幅/ネイティブtitlebar X・Alt+F4/実素材1TB・数万件・元解像度品質は未検証。日本語resource化/MVVM全体移行は既存MVPの継続課題。表示上のfit100%は原寸pixelではない。[最新handoff](codex-handoff.md)と[画像操作](image-viewer.md)、[読書操作](archive-reader.md)を参照。
