# 大規模ライブラリの生成データ検証

2026-10-13。製品SQLiteカタログへ直接生成した50,000件のmetadata、登録フォルダ258件、実PNG75件でCPU/APIとWinUIを確認。残り49,925件には実メディアがない。個人フォルダの走査、実ファイル5万件・1TBの解析、GPU索引、検索の順位品質の証拠ではない。

## 修正と維持した契約

複数root指定のkeyset列挙で、SQLiteがroot側から結合し各256行ページで候補全体を並べ直していた。複数rootだけCROSS JOINでitem ID rangeを先頭に固定し、単一rootとscope省略の既存計画を維持。出力はID昇順、除外・種類・棚と最大10,000件の規約を維持する。901件の独立したmetadata期待値で256行境界、limit260、除外と種類を照合。疎なroot分布など別の分布で常に速いと保証しない。

WinUIのroot StackPanelが設定画面を大きく伸ばすため、保存済み258番目の選択に到達できなかった。標準ScrollViewerに最大160 DIPで収め、長いCheckBox内容をstretch/折返し。先頭256＋保存済みID、最大512 controlsの従来の境界は維持。root一覧は未仮想化で、256番目以後の未選択rootを新規選択する検索UIは未実装。明示scope配列上限256と設定16KiB上限を緩めない。

## 再実行

新しい未使用の出力先が必要。生成DB/PNG/スクリーンショットはignoredのローカル成果物だけで、Gitへ追加しない。

```powershell
python tools/measure_library_scale.py --output data/ai-ui/library-scale-cpu-new
dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore
python tools/test_ai_profile_ui.py --editor-only --scale-checks --output data/ai-ui/library-scale-native-new
```

CPUは5回の中央値/最大値。95パーセンタイルやUIのフレーム描画時間ではない。fixture作成も含め実ファイルは生成PNGだけ。scope候補件数取得にモデルを呼べば失敗するNoInferenceを使用。

| CPU operation | Before median / max (ms) | After median / max (ms) |
|---|---:|---:|
| `first_page` | 62.861 / 67.234 | 63.281 / 76.985 |
| `last_page` | 101.947 / 104.374 | 97.381 / 100.446 |
| `literal_tag` | 82.769 / 91.259 | 90.524 / 92.177 |
| `favorites` | 9.011 / 10.945 | 8.353 / 8.726 |
| `coverage_all` | 1380.302 / 1400.775 | 1400.202 / 1426.438 |
| `coverage_256` | 14221.082 / 14775.335 | 1409.959 / 1442.919 |
| `coverage_last_root` | 28.686 / 32.105 | 24.734 / 29.401 |

256rootの件数確認は約14.2秒から1.41秒（この分布で約10倍）。全root約1.40秒、単一の最後のroot約24.7ms。背景処理やSQLite planへの依存があり、一般的な速度保証ではない。

## 検証結果と失敗履歴

- CPU `library-scale-cpu-01` / `02` はともに14検査PASS。5万候補/対象1万/fresh0、256roots保存とrestart、258番目のroot194件、257個・未知ID拒否、空scopeゼロ件、生成PNG bytes/mtime/digest不変。
- 最終Python全150 tests PASS / 92.363秒。新規fixture/keyset3 tests PASS / 2.328秒。最初の追加テストは期待値側の除外rootを誤り失敗し、実際のmetadata配分へ修正してから全体を再実行。
- C# Core19 checks PASS。x64 SelfContained Release PASS / 35.82秒、errors0・既存IL2104 warnings2（抑制なし）。Python構文とdiff checkも確認。手動WinUIレビューではnative controls/Automation ID・theme・bounded extent・JSON DOM・所有/破棄/保存規約維持を確認。専用analyzerは未導入/未実行。
- `library-scale-native-01` は最後の保存rootへ到達できずFAIL。4 PNGを目視し、選択欄のbounded viewport修正後に02を実行。正常closeできず所有テストPID終了へfallbackした履歴を保持。
- `library-scale-native-02` はlocal native **45 checks PASS / 12 PNG全目視 / scoped visual PASS**。Light/Dark、1200x800と700x620、DPI96・HighContrast off（読み取りのみ）。5万件/834ページ、次ページ、最後のitem50000文字検索、狭幅グリッド、first256＋saved258の257選択肢、restartでsaved258を保持、194件/全5万・上限1万の件数表示と全root保存。生成PNG75件と別の基礎fixture17件のbytes/mtime/hash不変、2回正常close、GPU worker未ロード。
- Native観測時間Light/Dark: launch-to-ready4.454/4.141秒、next-page1.123/1.155秒、literal-last1.350/5.351秒、scope openからlast-root観測12.095/30.532秒。WinApp CLI/UIA・待機・繰返しscrollを含むためユーザー操作の純粋な応答時間や性能合格基準ではない。最後のrootは操作可能になったが、多数選択の使い勝手には改善余地がある。
- スクロール境界で行の一部が見える。狭幅の長いroot画像は選択CheckBoxとパス先頭を確認する証拠で、長い全文が同時に見える証拠ではない。一部にハーネスのCtrl+F tooltip/追加HWNDの縁が入る。全パス確認、keyboard、High DPI/High Contrast/読み上げの操作評価は未実施。

scope検索品質・モデル・fusionは今回変更しない。前回の実CUDA品質ベースラインは[別の結果](search-quality-baseline.md)。Layaは品質gate未通過の既定無効実験のまま。大量実ファイル走査/音声本文理解/reader/Komga/AOT/配布と区別する。

## 次の3手

1. 疎な複数root分布でもkeysetを計測し、多数rootの新規選択/全文表示・keyboardと高DPIの操作を確認する。
2. 新しいholdoutを先に固定し、text/coverの根拠を分けて混合順位を評価する。v1へ観測後tuningしない。
3. Layaの日本語品質gate再評価を独立して実施。reader/Komga/フォルダ本集約は別sliceにする。
