namespace Aredoko.Core;

/// <summary>Read-only next steps. File placement never implies inference readiness.</summary>
public static class AISetupGuidance
{
    public static string Describe(AISetupPlan plan,int selection,AIDownloadJob? download,AIEnvironmentJob? environment)
    {
        if(plan.SkipAI)return AppText.L("フォルダを登録し、アイテム一覧を更新すると、ファイル名・タグで検索できます。AIは設定から後で追加できます。","Add a folder and scan items to search by filename and tags. You can enable AI later in Settings.");
        var lines=new List<string>();
        if(download?.Active==true)
            lines.Add(download.State=="cancelling"?AppText.L("AI環境の取得を中止しています。取得画面で結果を確認できます。","Cancelling AI runtime download. Check the Download screen for status."):AppText.L("AI環境の取得はバックグラウンドで続いています。取得画面で進捗や中止を確認できます。","AI runtime download is running in the background. Check progress or cancel in the Download screen."));
        else if(download?.State=="cancelled")lines.Add(AppText.L("前回のAI環境の取得は中止されています。取得画面から再開できます。","The previous AI download was cancelled. You can resume it from the Download screen."));
        else if(download?.State=="failed")lines.Add(AppText.L("前回のAI環境の取得は完了していません。取得画面で理由を確認してください。","The previous AI download did not finish. Check the reason in the Download screen."));
        else if(download?.Published==true)lines.Add(AppText.L("取得済みのAI環境があります。取得画面の設定ボタンから使用する環境を指定してください（取得だけでは設定は変わりません）。","Downloaded AI runtime is ready. Select it from the Download screen (downloading alone does not activate it)."));
        if(environment?.Active==true)
            lines.Add(AppText.L("配置の検査・保存が進行中です。配置画面で結果を確認し、完了してから再起動してください。","Verifying and saving folder selection. Wait for it to finish, then restart Aredoko."));
        else if(environment?.State=="cancelled")lines.Add(AppText.L("配置の検査は中止されています。前の設定を保持しています。必要なら配置画面から確認し直してください。","Folder verification was cancelled. Previous settings were kept. You can verify again anytime."));
        else if(environment?.State=="failed")lines.Add(AppText.L("配置の検査は完了していません。配置画面で理由を確認してください。","Folder verification did not complete. Check the reason on the folder selection screen."));
        if(plan.ProfileSelectionInvalid)
            lines.Add(AppText.L("保存したモデル選択を「AI検索を設定」で確認してください。起動中のモデルは切り替わっていません。","Check saved model selection in Configure AI. The active model has not changed."));
        else if(plan.RestartRequired)
            lines.Add(AppText.L("次は Aredoko を閉じ、いつものAredoko.exeから起動し直してください。保存した環境は再起動後に反映されます。","Next, close Aredoko and reopen Aredoko.exe. Your saved AI settings take effect after restart."));
        else if(plan.Requirements.Count!=2||plan.Requirements.Any(row=>!row.FilesPresent)||plan.Unsupported.Count>0)
            lines.Add(AppText.L("不足する実行環境・モデルを取得または指定してください。導入完了まで基本検索と閲覧を使えます。","Download or select the missing runtime/model. Standard search and viewing remain usable until setup completes."));
        else lines.Add(AppText.L("配置を確認しました（推論・対応機器の動作確認とは別）。次は下の［AI検索を設定へ →］から検索データを作成してください。","Files verified (separate from live hardware inference). Next, click Configure AI below to build indexes."));
        var features=AISetupSelection.FromMask(selection);
        var steps=new List<string>();
        if(features.Contains("semantic")||features.Contains("image_similarity"))steps.Add(AppText.L("・意味検索・類似画像：画像や本の索引を作成","• Semantic & Similar Image Search: build image and book indexes"));
        if(features.Contains("video"))steps.Add(AppText.L("・動画の内容検索：動画の準備欄から映像索引（音で探す場合は「動画内の音声」で別の索引）","• Video Content Search: build video frame index (and Video Audio index if needed)"));
        if(features.Contains("audio"))steps.Add(AppText.L("・音声・音楽の内容検索：音声の準備欄から音の索引を作成","• Audio & Music Search: build audio index"));
        if(steps.Count>0)lines.Add(AppText.L("【準備後に作れる検索データ】\n","[Indexes You Can Build Next]\n")+string.Join("\n",steps));
        return string.Join("\n\n",lines);
    }
}
