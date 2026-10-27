namespace Aredoko.Core;

/// <summary>Read-only next steps. File placement never implies inference readiness.</summary>
public static class AISetupGuidance
{
    public static string Describe(AISetupPlan plan,int selection,AIDownloadJob? download,AIEnvironmentJob? environment)
    {
        if(plan.SkipAI)return "フォルダを登録し、アイテム一覧を更新すると、ファイル名・タグで検索できます。AIは設定から後で追加できます。";
        var lines=new List<string>();
        if(download?.Active==true)
            lines.Add(download.State=="cancelling"?"AI環境の取得を中止しています。取得画面で結果を確認できます。":"AI環境の取得はバックグラウンドで続いています。取得画面で進捗や中止を確認できます。");
        else if(download?.State=="cancelled")lines.Add("前回のAI環境の取得は中止されています。取得画面から再開できます。");
        else if(download?.State=="failed")lines.Add("前回のAI環境の取得は完了していません。取得画面で理由を確認してください。");
        else if(download?.Published==true)lines.Add("取得済みのAI環境があります。取得画面の設定ボタンから使用する環境を指定してください。取得だけでは設定は変わりません。");
        if(environment?.Active==true)
            lines.Add("配置の検査・保存が進行中です。配置画面で結果を確認し、完了してから再起動してください。");
        else if(environment?.State=="cancelled")lines.Add("配置の検査は中止されています。前の設定を保持しています。必要なら配置画面から確認し直してください。");
        else if(environment?.State=="failed")lines.Add("配置の検査は完了していません。配置画面で理由を確認してください。");
        if(plan.ProfileSelectionInvalid)
            lines.Add("保存したモデル選択を「索引・詳細設定へ」で確認してください。起動中のモデルは切り替わっていません。");
        else if(plan.RestartRequired)
            lines.Add("次はAredokoを閉じ、いつものAredoko.exeから起動し直してください。保存した環境は再起動後に反映されます。");
        else if(plan.Requirements.Count!=2||plan.Requirements.Any(row=>!row.FilesPresent)||plan.Unsupported.Count>0)
            lines.Add("不足する実行環境・モデルを取得または指定してください。配置と動作確認が済むまでは基本検索と閲覧を使えます。");
        else lines.Add("配置を確認しました。推論・対応機器の動作確認とは別です。次は「索引・詳細設定へ」で、登録したフォルダの索引を作成します。");
        var features=AISetupSelection.FromMask(selection);
        var steps=new List<string>();
        if(features.Contains("semantic")||features.Contains("image_similarity"))steps.Add("意味検索・類似画像：画像や本の索引");
        if(features.Contains("video"))steps.Add("動画の内容検索：動画の準備欄から映像の索引（音声は対象外）");
        if(features.Contains("audio"))steps.Add("音声・音楽の内容検索：音声の準備欄から音の索引");
        if(steps.Count>0)lines.Add("環境の準備後に行うこと：\n"+string.Join("\n",steps));
        lines.Add("取得・配置の確認だけで、索引作成や推論が自動で始まることはありません。");
        return string.Join("\n\n",lines);
    }
}
