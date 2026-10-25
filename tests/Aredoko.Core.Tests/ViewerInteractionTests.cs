using Aredoko.Core;

static class ViewerInteractionTests
{
    public static void Run(Action<bool,string> check)
    {
        foreach(var mode in Enum.GetValues<ReaderDisplayMode>())
        foreach(var count in new[]{1,2,3,4,5,10000})
        {
            var last=ReaderSpreadPolicy.Anchor(count-1,count,mode);
            check(ReaderSpreadPolicy.Move(last,count,mode,1,true)==0,$"loop last to cover {mode}/{count}");
            check(ReaderSpreadPolicy.Move(0,count,mode,-1,true)==last,$"loop cover to last spread {mode}/{count}");
            check(ReaderSpreadPolicy.Move(last,count,mode,1,false)>=count,$"non-loop end remains boundary {mode}/{count}");
            check(ReaderSpreadPolicy.Move(0,count,mode,-1,false)==-1,$"non-loop start remains boundary {mode}/{count}");
        }
        check(ViewerViewportMath.ZoomOffset(0,800,1,2)==400,"button zoom preserves viewport center");
        check(ViewerViewportMath.ZoomOffset(400,800,2,1)==0,"zoom out returns to centered fit");
        check(ViewerViewportMath.ZoomOffset(50,100,2,3)==100,"pan offset participates in zoom anchor");
        check(ViewerViewportMath.ZoomOffset(0,800,2,1)==0,"zoom clamps left edge");
        var rejected=false;try{ViewerViewportMath.ZoomOffset(0,800,0,2);}catch(ArgumentOutOfRangeException){rejected=true;}
        check(rejected,"invalid zoom input rejected");
        var path=Path.Combine(Path.GetTempPath(),"aredoko-viewer-"+Guid.NewGuid().ToString("N")+".json");
        try
        {
            File.WriteAllText(path,"""{"version":1,"wheel_up_advances":true,"enlarge_small_images":true}""");
            var old=ViewerInputSettings.Load(path);
            check(old.EnlargeSmallImages&&!old.LoopBookPages&&!old.AlwaysShowControls&&old.WheelUpAdvances,"old viewer preferences retain enlargement and safe defaults");
            var updated=old with{LoopBookPages=true,AlwaysShowControls=true};updated.Save(path);
            check(ViewerInputSettings.Load(path)==updated,"viewer-only choices persist without losing existing preferences");
        }
        finally{if(File.Exists(path))File.Delete(path);}
    }
}
