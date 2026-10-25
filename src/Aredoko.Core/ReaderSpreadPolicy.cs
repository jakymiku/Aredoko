namespace Aredoko.Core;

public enum ReaderDisplayMode { Single, RightToLeft, LeftToRight }

public static class ReaderSpreadPolicy
{
    public static int Anchor(int page, int count, ReaderDisplayMode mode)
    {
        if(count<1||count>10000||page<0||page>=count)throw new ArgumentOutOfRangeException(nameof(page));
        if(!Enum.IsDefined(mode))throw new ArgumentOutOfRangeException(nameof(mode));
        return mode==ReaderDisplayMode.Single||page==0?page:page%2==0?page-1:page;
    }
    public static int[] Pages(int page,int count,ReaderDisplayMode mode)
    {
        var start=Anchor(page,count,mode);
        if(mode==ReaderDisplayMode.Single||start==0||start+1>=count)return [start];
        return mode==ReaderDisplayMode.RightToLeft?[start+1,start]:[start,start+1];
    }
    public static int Next(int page,int count,ReaderDisplayMode mode)
    {var start=Anchor(page,count,mode);return start+(mode==ReaderDisplayMode.Single||start==0?1:2);}
    public static int Previous(int page,int count,ReaderDisplayMode mode)
    {var start=Anchor(page,count,mode);return mode==ReaderDisplayMode.Single?start-1:start<=1?0:start-2;}
    public static int Move(int page,int count,ReaderDisplayMode mode,int direction,bool loop)
    {
        if(direction is not (-1 or 1))throw new ArgumentOutOfRangeException(nameof(direction));
        var target=direction>0?Next(page,count,mode):page==0?-1:Previous(page,count,mode);
        if(!loop)return target;
        return target>=count?0:target<0?Anchor(count-1,count,mode):target;
    }
}
