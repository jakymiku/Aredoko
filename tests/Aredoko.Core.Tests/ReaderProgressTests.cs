using Aredoko.Core;
using System.Net;
using System.Net.Http;
using System.Text;

internal static class ReaderProgressTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var revision=new string('a',64);var book=new ArchiveManifest(9,5,revision);
        var saved=new ReaderProgress(revision,2,ReaderDisplayMode.RightToLeft);
        check(saved.RestorePage(book)==1,"saved spread normalizes to pair anchor");
        check(saved.RestorePage(book with{Revision=new string('b',64)})==0,"changed revision restores cover");
        check((saved with{Page=9}).RestorePage(book)==0,"shortened book restores cover");
        check(ReaderProgress.Parse(Encoding.UTF8.GetBytes("{\"progress\":null}")) is null,"new book has no saved progress");
        var payload=saved.ToJson().ToJsonString();
        check(ReaderProgress.Parse(Encoding.UTF8.GetBytes("{\"progress\":"+payload+"}"))==saved,"progress JSON round trip without reflection");
        foreach(var value in new[]{"{\"progress\":{}}","{\"progress\":{\"revision\":\""+revision+"\",\"page\":true,\"mode\":\"single\"}}","{\"progress\":{\"revision\":\""+revision+"\",\"page\":0,\"mode\":\"bad\"}}"})
        {try{ReaderProgress.Parse(Encoding.UTF8.GetBytes(value));check(false,"bad progress");}catch(InvalidDataException){check(true,"invalid progress JSON rejected");}}
        using var stub=new Stub(async(req,token)=>
        {
            check(req.RequestUri!.AbsolutePath=="/api/library/reader/9/progress","fixed numeric reading progress route");
            check(req.Headers.GetValues("X-Aredoko-Token").Single()=="fiction","progress keeps auth token");
            if(req.Method==HttpMethod.Post)
            {
                check(req.Headers.GetValues("Origin").Single()=="http://127.0.0.1:8769","progress keeps session Origin");
                check(await req.Content!.ReadAsStringAsync(token)==payload,"save sends bounded explicit JSON");
            }
            return new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(req.Method==HttpMethod.Get?"{\"progress\":"+payload+"}":"{\"saved\":true}",Encoding.UTF8,"application/json")};
        });
        using var http=new HttpClient(stub){BaseAddress=new Uri("http://127.0.0.1:8769/")};http.DefaultRequestHeaders.Add("X-Aredoko-Token","fiction");http.DefaultRequestHeaders.Add("Origin","http://127.0.0.1:8769");var client=new ArchiveReaderClient(http);
        check(await client.ProgressAsync(9,CancellationToken.None)==saved,"GET progress parsed");await client.SaveProgressAsync(book,2,ReaderDisplayMode.RightToLeft,CancellationToken.None);
        try{await client.SaveProgressAsync(book,5,ReaderDisplayMode.Single,CancellationToken.None);check(false,"bad page");}catch(ArgumentOutOfRangeException){check(true,"invalid save page rejected before transport");}
        using var bad=new HttpClient(new Stub((_,_)=>Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent("{\"saved\":false}",Encoding.UTF8,"application/json")}))){BaseAddress=http.BaseAddress};
        try{await new ArchiveReaderClient(bad).SaveProgressAsync(book,0,ReaderDisplayMode.Single,CancellationToken.None);check(false,"unconfirmed save");}catch(InvalidDataException){check(true,"unconfirmed save is a failure");}
    }
    private sealed class Stub(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)=>send(request,cancellation);}
}
