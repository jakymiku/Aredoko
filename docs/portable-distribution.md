# ZIP解凍型配布への移行（2026-10-21 ユーザー指定）

## 決定と対象

今後の標準配布は **ZIPを解凍し、ルートのAredoko.exeをダブルクリック**する形式とする。インストール操作、試験証明書の信頼追加、MSIX登録、Python/.NET SDK/winapp CLI/動画runtimeの別途導入、バックエンドの手動起動を通常利用者に要求しない。起動入口はGUIとbackendを一括管理する。単一EXEへの圧縮や起動時の巨大な再展開は目的にせず、必要なDLL/runtimeをフォルダ内に同梱する。

前回のMSIX検証はコマンドで非対話installしたため、インストーラー画面は出なかった。通常アプリ項目がGUIだけを起動する不足もあり、利用者へ開発用コマンドを案内するのは適切でなかった。今後の標準ZIPではインストーラー自体が不要になる。旧Alpha MSIX/Development登録/TrustedPeopleの試験証明書/配布artifactは記録として保持し、無断アンインストールや証明書削除は行わない。Store/MSIXは将来の任意経路として残せるが、標準ZIPの完了を妨げる前提にしない。

**これは配布形式のポータブル化**。DB/タグ/索引/設定の既定は従来のユーザーデータ領域に保持し、版ごとの実行ファイルと分離する。ZIPを新しいフォルダへ解凍して更新しても、原本/保存状態を消さない。USBへDBも丸ごと移す「完全持ち運びモード」は今回の決定には含めず、無断移行しない。モデルはライセンスと明示許可に従い、既存の外部保存先指定を維持。新規取得や同梱を暗黙に行わない。

## 方式と現在の実測

Microsoftの公式手順は、WinUI 3を`WindowsPackageType=None`とし、Windows App SDK/.NETの両runtimeを自己完結で含めるフォルダ配布をサポートする。これはユーザーが明示した配布方式変更に基づく実装で、起動エラーを隠す自動fallbackではない。既定Developmentのpackaged設定と旧Alphaは保持する。

- [WinUI unpackaged配布](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/unpackage-winui-app)
- [自己完結runtimeとregistration-free WinRT](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/self-contained-deploy/deploy-self-contained-apps)

`Aredoko.WinUI.csproj`へ明示`AredokoPackageChannel=Portable`を追加した。別`Configuration=Portable`を必須とし、build/objが既存Releaseと混ざらないようにした。WindowsPackageType=None / WindowsAppSDKSelfContained=true / SelfContained=true / PublishSingleFile=false / PublishAppxPackage=false / EnableWinAppRunSupport=false。SDKのregistration-free WinRT自動初期化もtrueと実評価された。既定DevelopmentはMSIXのまま。通常の`winapp package`を無理にunpackaged化して通すのではなく、このchannelは`dotnet publish`を使う。

```powershell
# 開発担当者向け。既存キャッシュのみ、GUI/登録/installなし。
dotnet publish src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Portable -p:Platform=x64 -p:AredokoPackageChannel=Portable --no-restore -o C:/AI/Aredoko/data/portable-feasibility/20261021-01/frontend
```

実publish成功：**354ファイル / 159,999,549 bytes**。WinUI/Windows App SDK/.NETのnative runtimeを含む。Analyzer runtime混入0、runtimeconfigはincludedFrameworksを持ち外部framework要求なし。誤ってRelease構成とPortable channelを組み合わせる操作はguardで拒否。既知WUI1001 picker提案3件とSDK IL2104警告2件は保持し、抑制していない。新依存/model取得0、GPU0、GUI0、OS/install/cert変更0。生ログは`data/ai-ui/portable-frontend-publish-20261021-01.log`、監査は`data/ai-ui/portable-feasibility-20261021.json`。

**この成果物は画面部品だけ**。Python/動画runtime/所有bootstrapはまだ含まないため、完成ZIP・解凍後すぐ使える製品として案内しない。MSIX版のGUI起動だけが成功しても製品起動とならなかった問題を繰り返さない。

ソース監査でPackage.Current/ApplicationData.Current等への実呼出は見つからなかったが、これは全API互換性の証明ではない。現在のHWNDを渡すファイル/フォルダpicker、native window、画像/動画/音声/アニメ/本、drag-and-drop等は実unpackaged/clean Windowsで受け入れる必要がある。機能削減や別UIへの移行で回避しない。

## R13の実行順（現在の正）

| 順番 | 作業 | 状態と完了条件 |
| --- | --- | --- |
| PZ1 | 独立したWinUI portable publish | **CPU_DONE**。実publish/自己完結出力/既定MSIX保持/誤構成拒否を確認。native未確認 |
| PZ2 | ルートAredoko.exeの所有bootstrap | TODO。別途SDK不要の入口から同梱Python launcher→backend→portable GUIを起動。絶対path/作成時刻/保持handle/子processを照合し、他のAredokoやPID再利用を終了しない。port/instance/lease/所有EOFを維持。起動中の進捗・失敗/ログを見せる |
| PZ3 | portable frontendと全runtimeの梱包 | TODO。明示portable modeと出力manifestを結び、旧MSIXのEXEを誤流用しない。Python/AI依存/動画tool/NOTICEを含み、外部Pythonや既存MSIX登録へfallbackしない。既存の全SHA/祖先link/type/hardlink検査を保持 |
| PZ4 | 配布ZIPと更新手順 | TODO。存在しない新規先のみ作成、相対path/全inventory照合。日本語・空白path/再配置でbackend HTTP/保存/終了をCPU確認。DBや原本/modelを配布へ収集しない。旧artifactを上書きしない |
| PZ5 | 明示許可後のnative/clean Windows受入 | TODO。package identityなしを実確認し、解凍→Aredoko.exe→登録/検索/閲覧/終了→再起動/保存保持、更新/フォルダ削除後のデータ保持。SDK/Python/WinAppSDK事前installに助けられない環境で検証。必要なGPUは別途最新許可に従う |

PZ2/PZ3は明示portable modeだけで`subprocess`によるGUI起動を許し、旧MSIX modeの正式activation/登録照合を黙って緩めない。現在のlaunch_release.pyはMSIX専用のままなので、portable publishをそのまま渡せばよい状態ではない。bootstrapを後付けリンクへ押し出さず、製品ZIPの必須入口にする。

これらはR13内の実装順であり、新しい完成マイルストーンではない。R13 DOING / ALPHA-0未完 / R14 PARTIAL / M1/M2/RC未完。ALPHA成立後の実音声/音楽R06–R09→WinUI改善は維持。通常実装はSolで進行可能。Astra必須ではないが、所有process/復旧の設計を大きく変える場合は追加レビューを推奨する（委任やモデル変更の自動許可ではない）。

## 再実行・保全

旧native flow `alpha-msix-owned-lifecycle-v1`の3/3上限は保持する。今回GUIは実行しておらず、portableという別名で試行権限をresetしない。PZ5へ入る前に、用意した具体的artifactと固定検証範囲についてユーザーの新たな明示許可を得る。既存の配布方式変更の承認は、新model取得・私物走査・OS変更・GUI上限解除の許可とは分ける。

旧評価・失敗記録・試験証明書/登録・原本/実DB/元venv・機能を保全。P0累積2/2閉鎖・専用OCR保留・簡潔GUI・Actions0・main mergeなし・配布物の外部公開なしを保持する。
