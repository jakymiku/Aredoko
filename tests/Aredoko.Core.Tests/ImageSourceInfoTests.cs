using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json.Nodes;
using Aredoko.Core;

internal static class ImageSourceInfoTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var value=new JsonObject{{"item_id",7},{"revision",new string('a',64)},
            {"mime","image/webp"},{"size_bytes",1400},{"animation_candidate",true}};
        byte[] Data()=>Encoding.UTF8.GetBytes(value.ToJsonString());
        var info=ImageSourceInfo.Parse(Data(),7);
        check(info.Mime=="image/webp"&&info.AnimationCandidate&&!info.IsNativeGif,"renamed WebP avoids native GIF decoder");
        value["mime"]="image/gif";
        check(ImageSourceInfo.Parse(Data(),7).IsNativeGif,"real GIF selects native animation independent of filename");
        value["mime"]="image/png";value["animation_candidate"]=false;
        check(!ImageSourceInfo.Parse(Data(),7).AnimationCandidate,"static renamed image avoids frame preparation");
        foreach(var(key,bad) in new (string,JsonNode?)[]{("item_id",8),("revision","broken"),("mime","text/html"),
            ("size_bytes",0),("size_bytes",PreviewPolicy.ViewerSourceBytes+1),("animation_candidate","true")})
        {
            var before=value[key]?.DeepClone();value[key]=bad?.DeepClone();var rejected=false;
            try{ImageSourceInfo.Parse(Data(),7);}catch(InvalidDataException){rejected=true;}
            check(rejected,"invalid image source info rejected: "+key);value[key]=before;
        }
        using var handler=new Stub(request=>
        {
            check(request.RequestUri!.PathAndQuery=="/api/library/preview/7/info","format probe uses fixed bounded route");
            check(request.Headers.Contains("X-Aredoko-Token"),"format probe preserves session authentication");
            var response=new HttpResponseMessage(HttpStatusCode.OK){Content=new ByteArrayContent(Data())};
            response.Content.Headers.ContentType=new MediaTypeHeaderValue("application/json");return response;
        });
        using var http=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1:8769/")};
        http.DefaultRequestHeaders.Add("X-Aredoko-Token","fixture");
        check((await new ArchiveReaderClient(http).ImageInfoAsync(7,CancellationToken.None)).Mime=="image/png","format probe response parsed without frame enumeration");
    }
    private sealed class Stub(Func<HttpRequestMessage,HttpResponseMessage> handle):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token)=>Task.FromResult(handle(request));}
}
