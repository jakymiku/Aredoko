namespace Aredoko.Core;

/// <summary>Safe recovery guidance based only on bounded state codes, never raw errors or paths.</summary>
public static class AISetupRecovery
{
    public static string Reason(string state)=>state switch
    {
        "preferences_invalid"=>"保存したAI設定を読み取れません。",
        "runtime_invalid"=>"選択した実行環境のファイルを確認できません。",
        "ai_libraries_missing"=>"Pythonはありますが、AI用のライブラリが不足しています。",
        "legacy_runtime_unverified"=>"開発用の実行環境です。配布用環境としての確認は済んでいません。",
        "model_profile_invalid"=>"モデルの設定を読み取れません。",
        "model_revision_missing"=>"モデルの版を確認するファイルがありません。",
        "model_revision_mismatch"=>"モデルの版が設定と一致していません。",
        "model_files_missing"=>"モデルに必要なファイルが不足しています。",
        "model_invalid"=>"モデルのファイルを確認できません。",
        _=>"未導入、または配置の確認が必要です。"
    };

    public static string Describe(AISetupPlan plan)
    {
        if(plan.SkipAI)return "AIを使わずに、ファイル名・タグ検索と閲覧を続けられます。後から設定でAIを追加できます。";
        var lines=new List<string>();
        if(plan.ProfileSelectionInvalid)lines.Add("保存したモデル選択を確認できません。「索引・詳細設定へ」で有効なモデルを選び直してください。現在の索引や原本は削除しません。");
        if(plan.Unsupported.Count>0)lines.Add("選んだ機能の一部は現在のモデルに対応していません。「索引・詳細設定へ」で対応モデルを選択してください。");
        foreach(var requirement in plan.Requirements.Where(row=>!row.FilesPresent))
        {
            var label=requirement.Id=="embedding-runtime"?"実行環境":"検索用モデル";
            var action=requirement.State switch
            {
                "preferences_invalid"=>"「診断情報」で状態を控え、以前のバックアップを確認してください。設定ファイルの削除や初期化は行いません。",
                "model_profile_invalid"=>"「索引・詳細設定へ」で使用するモデルを選び直し、次回起動に設定してください。",
                "model_revision_mismatch" or "model_revision_missing"=>"設定と同じ版のモデルを取得するか、対応する配置済みモデルを指定してください。版の目印だけを書き換えず、以前のモデルと索引を保持してください。",
                "runtime_invalid" or "ai_libraries_missing" or "legacy_runtime_unverified"=>"「配置済みの環境・モデルを指定」から、以前の正常なAredoko用実行環境を選んで検査できます。システムPythonやドライバーは変更しません。",
                _=>"取得候補または配置済みのフォルダを確認してください。既存の正常な配置を上書きせずに指定できます。"
            };
            lines.Add($"{label}：{Reason(requirement.State)}\n{action}");
        }
        if(plan.RestartRequired)lines.Add("設定を保存した後は、Aredokoを閉じて通常の入口から再起動します。表示中の環境は切り替わりません。");
        if(lines.Count==0)lines.Add(plan.Requirements.Count==2&&plan.Requirements.All(row=>row.FilesPresent)
            ?"ファイルの配置は確認できています。AI検索を使えない場合は「索引・詳細設定へ」で対象と索引の状態を確認してください。対応機器や推論の動作は、この確認だけでは判定していません。"
            :"環境の情報を確認できません。「必要な環境を確認」で更新するか、診断情報を確認してください。");
        lines.Add("元の画像・動画・音声、タグ、棚、索引を削除する操作は行いません。困った場合も基本検索と閲覧を継続できます。診断情報は自動送信しません。");
        return string.Join("\n\n",lines);
    }
}
