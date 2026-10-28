using Aredoko.Core;

internal static class MediaPresentationTests
{
    public static void Run(Action<bool,string> check)
    {
        var row=new MediaRow{Title="生成画像.png",Location="生成画像.png"};
        check(row.DetailLocationLabel==""&&row.LocationLabel=="生成画像.png","details omit a repeated bare filename while properties retain the original location");
        row.Location="素材/生成画像.png";
        check(row.DetailLocationLabel=="素材/生成画像.png","relative subfolder context is retained");
        row.Title="別の表示名";row.Location="生成画像.png";
        check(row.DetailLocationLabel=="生成画像.png","a display title cannot hide a different filename");
        row.Title="TEST.PNG";row.Location="test.png";
        check(row.DetailLocationLabel=="test.png","detail presentation never changes path case semantics");
        row.Location="./";
        check(row.DetailLocationLabel=="登録フォルダ直下の画像（一冊）","logical root books retain their location explanation");
    }
}
