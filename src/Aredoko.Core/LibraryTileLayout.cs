namespace Aredoko.Core;

public static class LibraryTileLayout
{
    public static double Width(double available,int scale)
    {
        if(!double.IsFinite(available)||available<=0)return 232;
        var preferred=232*ViewerInputSettings.NormalizeScale(scale)/100d;
        var columns=Math.Max(1,(int)Math.Floor(available/(preferred+8)));
        return Math.Max(1,available/columns-8);
    }
}
