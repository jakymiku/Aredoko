namespace Aredoko.Core;

/// <summary>Safe recovery guidance based only on bounded state codes, never raw errors or paths.</summary>
public static class AISetupRecovery
{
    public static string Reason(string state)=>state switch
    {
        "preferences_invalid"=>AppText.L("保存したAI設定を読み取れません。","Cannot read saved AI settings."),
        "runtime_invalid"=>AppText.L("選択した実行環境のファイルを確認できません。","Cannot verify files in the selected runtime folder."),
        "ai_libraries_missing"=>AppText.L("Pythonはありますが、AI用のライブラリが不足しています。","Python is present, but required AI libraries are missing."),
        "legacy_runtime_unverified"=>AppText.L("開発用の実行環境です。配布用環境としての確認は済んでいません。","Development runtime detected; not verified as a portable release runtime."),
        "model_profile_invalid"=>AppText.L("モデルの設定を読み取れません。","Cannot read model configuration."),
        "model_revision_missing"=>AppText.L("モデルの版を確認するファイルがありません。","Model revision file is missing."),
        "model_revision_mismatch"=>AppText.L("モデルの版が設定と一致していません。","Model revision does not match settings."),
        "model_files_missing"=>AppText.L("モデルに必要なファイルが不足しています。","Required model files are missing."),
        "model_invalid"=>AppText.L("モデルのファイルを確認できません。","Cannot verify model files."),
        _=>AppText.L("未導入、または配置の確認が必要です。","Not installed, or folder needs verification.")
    };

    public static string Describe(AISetupPlan plan)
    {
        if(plan.SkipAI)return AppText.L("AIを使わずに、ファイル名・タグ検索と閲覧を続けられます。後から設定でAIを追加できます。","You can continue using filename/tag search and browsing without AI, and add AI later in Settings.");
        var lines=new List<string>();
        if(plan.ProfileSelectionInvalid)lines.Add(AppText.L("保存したモデル選択を確認できません。「AI検索を設定」で有効なモデルを選び直してください。現在のAI検索データや原本は削除しません。","Could not verify saved model selection. Choose a valid model in Configure AI. Existing AI indexes and original files are kept."));
        if(plan.Unsupported.Count>0)lines.Add(AppText.L("選んだ機能の一部は現在のモデルに対応していません。「AI検索を設定」で対応モデルを選択してください。","Some selected features are unsupported by the current model. Select a compatible model in Configure AI."));
        foreach(var requirement in plan.Requirements.Where(row=>!row.FilesPresent))
        {
            var label=requirement.Id=="embedding-runtime"?AppText.L("実行環境","AI Runtime"):AppText.L("検索用モデル","Search Model");
            var action=requirement.State switch
            {
                "preferences_invalid"=>AppText.L("「診断情報」で状態を控え、以前のバックアップを確認してください。設定ファイルの削除や初期化は行いません。","Save a copy of Diagnostics and check your backups. Existing config files will not be wiped automatically."),
                "model_profile_invalid"=>AppText.L("「AI検索を設定」で使用するモデルを選び直し、次回起動に設定してください。","Reselect your model in Configure AI for the next launch."),
                "model_revision_mismatch" or "model_revision_missing"=>AppText.L("設定と同じ版のモデルを取得するか、対応する配置済みモデルを指定してください。版の目印だけを書き換えず、以前のモデルとAI検索データを保持してください。","Download the matching model revision or point to a matching folder without modifying revision markers."),
                "runtime_invalid" or "ai_libraries_missing" or "legacy_runtime_unverified"=>AppText.L("「配置済みの環境・モデルを指定」から、以前の正常なAredoko用実行環境を選んで検査できます。システムPythonやドライバーは変更しません。","Select and verify an existing Aredoko runtime folder from Manual Setup. System Python and GPU drivers are never altered."),
                _=>AppText.L("取得候補または配置済みのフォルダを確認してください。既存の正常な配置を上書きせずに指定できます。","Review download options or select an existing folder without overwriting valid setups.")
            };
            lines.Add($"{label}{AppText.L("："," — ")}{Reason(requirement.State)}\n{action}");
        }
        if(plan.RestartRequired)lines.Add(AppText.L("設定を保存した後は、Aredokoを閉じ通常の入口から再起動します。表示中の環境は切り替わりません。","Close Aredoko and launch it again after saving settings. The active environment changes on restart."));
        if(lines.Count==0)lines.Add(plan.Requirements.Count==2&&plan.Requirements.All(row=>row.FilesPresent)
            ?AppText.L("ファイルの配置は確認できています。AI検索を使えない場合は「AI検索を設定」で対象とAI検索データの状態を確認してください。対応機器や推論の動作は、この確認だけでは判定していません。","Files are in place. If AI search is unavailable, check Scope and Index status in Configure AI. Hardware inference is verified separately.")
            :AppText.L("環境の情報を確認できません。「必要な環境を確認」で更新するか、診断情報を確認してください。","Could not retrieve environment details. Refresh plan or check Diagnostics."));
        lines.Add(AppText.L("元の画像・動画・音声、タグ、棚、AI検索データを削除する操作は行いません。困った場合も基本検索と閲覧を継続できます。診断情報は自動送信しません。","Original media, tags, shelves, and AI indexes are never deleted. Basic search and viewing always remain usable, and diagnostics are never sent automatically."));
        return string.Join("\n\n",lines);
    }
}
