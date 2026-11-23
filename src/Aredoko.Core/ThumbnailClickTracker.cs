namespace Aredoko.Core;

// Track the first thumbnail even if opening details moves it before click two.
public sealed class ThumbnailClickTracker
{
    private int? priorId;
    private long priorTime;
    private double priorX,priorY;
    public int? Register(int? sourceId,long now,double x,double y,long interval,double width,double height)
    {
        if(priorId is int id&&(sourceId is null||sourceId==id)&&now>=priorTime&&now-priorTime<=interval&&
            Math.Abs(x-priorX)<=width/2&&Math.Abs(y-priorY)<=height/2)
        {priorId=null;return id;}
        priorId=sourceId;priorTime=now;priorX=x;priorY=y;return null;
    }
    public void Reset()=>priorId=null;
}
