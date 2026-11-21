using Aredoko.Core;
internal static class ResultBufferTests
{
    private static SearchResponse Range(int offset,int count)=>new(){Total=50000,Items=Enumerable.Range(offset,count).Select(i=>new MediaRow{Id=i+1}).ToList()};
    public static void Run(Action<bool,string> check)
    {
        var buffer=new ResultBuffer(0,Range(0,60));
        buffer.Extend(60,Range(60,120));
        check(buffer.Items[59].Id==60&&buffer.Items[60].Id==61&&buffer.Items[120].Id==121,"incremental 60/61 and120/121 retain server ordering");
        while(buffer.End<50000)buffer.Extend(buffer.End,Range(buffer.End,Math.Min(120,50000-buffer.End)));
        check(buffer.Items.Count==600&&buffer.Start==49400&&buffer.End==50000,"50k forward scroll bounds metadata to600");
        while(buffer.Start>0){var start=Math.Max(0,buffer.Start-120);buffer.Extend(start,Range(start,buffer.Start-start));}
        check(buffer.Start==0&&buffer.Items.Count==600&&buffer.Items[60].Id==61,"reverse scrolling re-fetches beginning in stable order");
        var before=buffer.Items;
        try{buffer.Extend(buffer.End+1,Range(buffer.End+1,10));check(false,"gap rejected");}catch(InvalidDataException){check(ReferenceEquals(before,buffer.Items),"gap failure leaves buffer unchanged");}
        var duplicate=Range(buffer.End,10);duplicate.Items[0].Id=buffer.Items[0].Id;
        try{buffer.Extend(buffer.End,duplicate);check(false,"duplicate rejected");}catch(InvalidDataException){check(ReferenceEquals(before,buffer.Items),"duplicate failure leaves buffer unchanged");}
        var changed=Range(buffer.End,10);changed.Total=49999;
        try{buffer.Extend(buffer.End,changed);check(false,"scope total rejected");}catch(InvalidDataException){check(ReferenceEquals(before,buffer.Items),"changed session total cannot mix metadata");}
        var large=new ResultBuffer(0,Range(0,60),capacity:2400);
        while(large.End<1500)large.Extend(large.End,Range(large.End,120));
        check(large.MaxCapacity==2400&&large.Start==0&&large.Items.Count==1500&&large.End==1500,"custom 2400 capacity retains 1500 items without head eviction");
    }
}
