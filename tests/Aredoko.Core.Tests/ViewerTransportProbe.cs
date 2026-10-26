using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Text.Json;
using System.Text.Json.Nodes;
using Aredoko.Core;

// Developer-only probe. Requires a separately created, nonce-owned loopback
// server, never the normal fixed-port app or a remote media source.
static class ViewerTransportProbe
{
    public static async Task Run(string[] args)
    {
        var token=Environment.GetEnvironmentVariable("AREDOKO_PROBE_TOKEN");
        if(args.Length!=4||!Uri.TryCreate(args[1],UriKind.Absolute,out var origin)||
           origin.Scheme!="http"||origin.Host!="127.0.0.1"||origin.Port<1024||origin.Port==8769||
           origin.AbsolutePath!="/"||!string.IsNullOrEmpty(origin.Query)||!string.IsNullOrEmpty(origin.UserInfo)||
           !int.TryParse(args[2],out var item)||item<1||args[3].Length!=32||token is null||token.Length!=64)
            throw new ArgumentException("Dedicated loopback fixture, item and nonce required");
        var connects=new JsonArray();
        var ipv4=Environment.GetEnvironmentVariable("AREDOKO_PROBE_IPV4")=="1";
        using HttpMessageHandler handler=ipv4?new SocketsHttpHandler
        {
            UseProxy=false,AllowAutoRedirect=false,
            ConnectCallback=async(context,cancellation)=>
            {
                if(context.DnsEndPoint.Host!="127.0.0.1"||context.DnsEndPoint.Port!=origin.Port)throw new InvalidOperationException("Unexpected probe endpoint");
                var started=Stopwatch.GetTimestamp();
                var socket=new Socket(AddressFamily.InterNetwork,SocketType.Stream,ProtocolType.Tcp){NoDelay=true};
                try
                {
                    await socket.ConnectAsync(IPAddress.Loopback,origin.Port,cancellation);
                    connects.Add(new JsonObject{["connect_ms"]=Stopwatch.GetElapsedTime(started).TotalMilliseconds,
                        ["started_qpc_seconds"]=started/(double)Stopwatch.Frequency});
                    return new NetworkStream(socket,ownsSocket:true);
                }
                catch{socket.Dispose();throw;}
            }
        }:new HttpClientHandler{UseProxy=false,AllowAutoRedirect=false};
        using var http=new HttpClient(handler){BaseAddress=origin,Timeout=TimeSpan.FromSeconds(10)};
        http.DefaultRequestHeaders.Add("Origin",origin.GetLeftPart(UriPartial.Authority));
        using(var session=JsonDocument.Parse(await http.GetByteArrayAsync("api/session")))
        {
            if(session.RootElement.GetProperty("instance_id").GetString()!=args[3]||
               session.RootElement.GetProperty("mode").GetString()!="production"||
               session.RootElement.GetProperty("token").GetString()!=token)
                throw new InvalidDataException("Unexpected fixture owner");
        }
        http.DefaultRequestHeaders.Add("X-Aredoko-Token",token);
        var result=new JsonObject();
        foreach(var kind in new[]{"info","original"})
        {
            var samples=new JsonArray();long bytes=0;
            for(var number=0;number<3;number++)
            {
                var started=Stopwatch.GetTimestamp();
                using var response=await http.GetAsync($"api/library/preview/{item}/{kind}",HttpCompletionOption.ResponseHeadersRead);
                var headersAt=Stopwatch.GetTimestamp();
                response.EnsureSuccessStatusCode();
                if(response.Content.Headers.ContentLength is not long length||length is <1 or >8*1024*1024)
                    throw new InvalidDataException("Bounded generated response required");
                var data=await response.Content.ReadAsByteArrayAsync();bytes=data.Length;
                var finished=Stopwatch.GetTimestamp();
                samples.Add(new JsonObject{["total_ms"]=Stopwatch.GetElapsedTime(started,finished).TotalMilliseconds,
                    ["headers_ms"]=Stopwatch.GetElapsedTime(started,headersAt).TotalMilliseconds,
                    ["body_ms"]=Stopwatch.GetElapsedTime(headersAt,finished).TotalMilliseconds,
                    ["started_qpc_seconds"]=started/(double)Stopwatch.Frequency});
            }
            result[kind]=new JsonObject{["milliseconds"]=samples,["bytes"]=bytes};
        }
        if(Environment.GetEnvironmentVariable("AREDOKO_PROBE_ANIMATION")=="1")
        {
            var source=ImageSourceInfo.Parse(await http.GetByteArrayAsync($"api/library/preview/{item}/info"),item);
            var started=Stopwatch.GetTimestamp();var opened=await new AnimationStreamClient(http).OpenFirstAsync(source,CancellationToken.None);
            var firstMs=Stopwatch.GetElapsedTime(started).TotalMilliseconds;var times=new JsonArray();var batch=opened.First;var count=batch.Frames.Count;
            await using(var stream=opened.Stream)
            {
                while(!batch.Done)
                {
                    started=Stopwatch.GetTimestamp();batch=await stream.ReadAsync(4,CancellationToken.None);
                    times.Add(JsonValue.Create(Stopwatch.GetElapsedTime(started).TotalMilliseconds));count+=batch.Frames.Count;
                    if(count>20)throw new InvalidDataException("Bounded generated animation required");
                }
            }
            if(count!=10)throw new InvalidDataException("Expected generated two-cycle animation");
            result["animation"]=new JsonObject{["frames"]=count,["width"]=batch.Width,["height"]=batch.Height,["first_ms"]=firstMs,["next_ms"]=times};
        }
        result["ipv4_connects"]=connects;Console.WriteLine(result.ToJsonString());
    }
}
