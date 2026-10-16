using Aredoko.Core;
using System.Net;
using System.Text.Json.Nodes;

internal static class FeedbackTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var normal=new ViewerInputSettings();var inverted=new ViewerInputSettings(true);
        check(normal.WheelStep(-120)==1&&normal.WheelStep(120)==-1&&normal.WheelStep(0)==0,"wheel default down advances / up returns / zero ignored");
        check(inverted.WheelStep(120)==1&&inverted.WheelStep(-120)==-1,"wheel direction inversion");
        var dir=Path.Combine(Path.GetTempPath(),"aredoko-feedback-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(dir);
        try
        {
            var file=Path.Combine(dir,"settings.json");
            check(!ViewerInputSettings.Load(file).WheelUpAdvances,"missing viewer settings uses default");
            inverted.Save(file);check(ViewerInputSettings.Load(file).WheelUpAdvances,"viewer direction survives restart");
            normal.Save(file);check(!ViewerInputSettings.Load(file).WheelUpAdvances&&Directory.GetFiles(dir).Length==1,"atomic settings overwrite leaves no temporary files");
            foreach(var text in new[]{"{}","null","[]","broken","{\"version\":2,\"wheel_up_advances\":true}","{\"version\":1,\"wheel_up_advances\":\"true\"}",new string('x',2049)})
            {File.WriteAllText(file,text);check(!ViewerInputSettings.Load(file).WheelUpAdvances,"corrupt or unsupported settings fallback: "+text[..Math.Min(text.Length,40)]);}
            check(LibraryFilePath.Resolve(dir,"素材/画像 1.png")==Path.Combine(dir,"素材","画像 1.png"),"Unicode file resolves under registered root");
            check(LibraryFilePath.Resolve(dir,"./")==Path.GetFullPath(dir),"folder book root resolves to registered root");
            var drive=Path.GetPathRoot(dir)!;
            check(LibraryFilePath.Resolve(drive,"direct.png")==Path.Combine(drive,"direct.png"),"drive-root library containment");
            foreach(var path in new[]{"../escape.png","a/../escape.png","/root.png","\\\\server\\share","https://example.invalid","a:stream","a//b","a\"b","a\nb"})
            {bool rejected=false;try{LibraryFilePath.Resolve(dir,path);}catch(InvalidDataException){rejected=true;}check(rejected,"shell path rejects escape/URI/control: "+path);}
            var row=new MediaRow{Kind="image",Location="a.png",Size=54802L*1024,Modified=1700000000000000000};
            var description=LibraryFilePath.Describe(row,dir);
            check(description.Contains("PNG")&&description.Contains("更新日時")&&description.Contains(dir),"file properties include extension/date/root");
            row.Kind="book";row.Location="./";check(!LibraryFilePath.Describe(row,dir).Contains("更新日時"),"folder revision token is not a date");
        }
        finally{Directory.Delete(dir,true);}
        var roots=RegisteredRootRow.ParseList(JsonNode.Parse("""{"items":[{"id":1,"path":"fixture","enabled":1,"online":true},{"id":2,"path":"fixture2","enabled":1,"online":true,"recursive":false}]}""")!);
        check(roots[0].Recursive&&!roots[1].Recursive,"old root defaults recursive / direct-only parsed");
        var calls=new List<string>();using var api=new LibraryApi(new Stub(request=>{calls.Add(request.RequestUri!.PathAndQuery);return new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent("{\"total\":0,\"items\":[]}")};}));
        await api.SearchMultiAsync("豆","image","history",1,false,"all",null,[2,1]);
        check(calls.Single().Contains("view=history")&&calls[0].Contains("root_ids=1,2")&&calls[0].Contains("page=1"),"history request preserves scope/query/page");
        foreach(var mode in new[]{(true,"all"),(false,"pending-proposals")})
        {bool rejected=false;try{await api.SearchMultiAsync("豆","","history",0,mode.Item1,mode.Item2,null,null);}catch(ArgumentException){rejected=true;}check(rejected&&calls.Count==1,"history rejects unsupported mode before HTTP");}
    }
    private sealed class Stub(Func<HttpRequestMessage,HttpResponseMessage> response):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token)=>Task.FromResult(response(request));}
}
