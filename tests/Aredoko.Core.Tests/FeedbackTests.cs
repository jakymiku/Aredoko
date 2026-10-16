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
        check(ErrorText.Localize("Explicit folder purge consent required").Contains("確認ダイアログ")&&ErrorText.Localize("Unregister the root before purging database records").Contains("先に登録を解除"),"purge errors localized");
        var apngRow=new MediaRow{Id=42,Kind="image",Availability="present",Location="anim.APNG"};
        check(ImageViewerPolicy.CanOpen(apngRow)&&ImageViewerPolicy.MayAnimate(apngRow.Location)&&!ImageViewerPolicy.MayAnimate("photo.jpg"),"APNG opens in image viewer and marks animation candidate");
        var animRev=new string('b',64);
        var animJson=System.Text.Encoding.UTF8.GetBytes($$"""
        {"item_id":42,"revision":"{{animRev}}","mime":"image/png","size_bytes":56117260,"width":512,"height":512,"animated":true,"frame_count":3,"loop_count":0,"durations_ms":[120,180,240],"representative_frame":1}
        """);
        var parsedAnim=ImageAnimationManifest.Parse(animJson,42);
        check(parsedAnim.Animated&&parsedAnim.FrameCount==3&&parsedAnim.RepresentativeFrame==1&&parsedAnim.DurationsMs.SequenceEqual(new[]{120,180,240}),"animation manifest parsed without reflection");
        foreach(var badAnim in new[]{
            animJson.Select(b=>b).ToArray() switch { _ => System.Text.Encoding.UTF8.GetBytes($$"""{"item_id":99,"revision":"{{animRev}}","width":512,"height":512,"animated":true,"frame_count":3,"loop_count":0,"durations_ms":[120,180,240],"representative_frame":1}""") },
            System.Text.Encoding.UTF8.GetBytes($$"""{"item_id":42,"revision":"{{animRev}}","width":512,"height":512,"animated":true,"frame_count":65,"loop_count":0,"durations_ms":[100],"representative_frame":0}"""),
            System.Text.Encoding.UTF8.GetBytes($$"""{"item_id":42,"revision":"{{animRev}}","width":512,"height":512,"animated":true,"frame_count":2,"loop_count":0,"durations_ms":[10,100],"representative_frame":0}""")
        })
        {
            var rejected=false;
            try{ImageAnimationManifest.Parse(badAnim,42);}catch(InvalidDataException){rejected=true;}
            check(rejected,"invalid animation manifest rejected");
        }
        var pageId0=new string('c',64);
        var refreshBytes=System.Text.Encoding.UTF8.GetBytes($$"""{"item_id":7,"source_revision":"{{animRev}}","source_kind":"archive","page_count":3,"reused":false}""");
        var refresh=PageEvidenceProtocol.ParseRefresh(refreshBytes,7);
        check(refresh.ItemId==7&&refresh.PageCount==3&&refresh.SourceKind=="archive"&&!refresh.Reused,"page index refresh parsed without reflection");
        var indexBytes=System.Text.Encoding.UTF8.GetBytes($$"""
        {"item_id":7,"source_revision":"{{animRev}}","source_kind":"archive","source_state":"current","page_count":3,"offset":0,"limit":60,
         "pages":[{"page_id":"{{pageId0}}","page":0,"mime":"image/png","size_bytes":1024}]}
        """);
        var indexList=PageEvidenceProtocol.ParseIndexList(indexBytes,7,0,60);
        check(indexList.SourceState=="current"&&indexList.Pages.Single().PageId==pageId0,"page index list parsed");
        var textSearchBytes=System.Text.Encoding.UTF8.GetBytes($$"""
        {"search_mode":"page-text","total":1,"page":0,"limit":20,"items":[
          {"id":7,"title":"book.cbz","kind":"book","tags":[],"shelf":"","favorite":false,"reviewed":false,
           "root_id":1,"relative_path":"book.cbz","availability":"present","size_bytes":1000,"mtime_ns":2000,
           "page_text_match":{"source_revision":"{{animRev}}","source_state":"current","matching_pages":2,
             "pages":[{"page_id":"{{pageId0}}","page":0,"excerpt":"夕焼けの教室で約束した","producer":{"adapter":"ocr","version":"1","model":"ocr-v1","model_revision":"r1","preprocessing":"p1"} }] } }]}
        """);
        var textSearch=PageEvidenceProtocol.ParseSearch(textSearchBytes,0);
        check(textSearch.Total==1&&textSearch.Items[0].PageText is {MatchingPages:2,SourceState:"current"} pt&&pt.Summary.Contains("1ページ")&&pt.Summary.Contains("夕焼けの教室"),"page text search parsed with excerpt and provenance");
        var proof=textSearch.Items[0].PageText!;
        var proofPage=proof.Pages[0] with {Page=1};
        proof=proof with {Pages=new[]{proofPage}};
        var bookManifest=new ArchiveManifest(7,3,animRev);
        check(proof.InitialReaderPage(bookManifest)==1,"matched page jump requires current matching revision");
        check(proof.InitialReaderPage(bookManifest with {Revision=new string('f',64)}) is null,"file change after search cannot apply old page number");
        foreach(var sourceState in new[]{"stale","unverified","unavailable"})
            check((proof with {SourceState=sourceState}).InitialReaderPage(bookManifest) is null,"noncurrent text does not jump: "+sourceState);
        check((proof with {Pages=Array.Empty<PageTextEvidencePage>()}).InitialReaderPage(bookManifest) is null,"missing page evidence does not jump");
        check((proof with {Pages=new[]{proofPage with {Page=3}}}).InitialReaderPage(bookManifest) is null,"out-of-range text page does not jump");
        check((proof with {Pages=new[]{proofPage with {Page=-1}}}).InitialReaderPage(bookManifest) is null,"negative text page does not jump");
        check((proof with {Pages=new[]{proofPage with {Page=0}}}).InitialReaderPage(bookManifest)==0,"explicit first matched page remains valid");
        var videoRowMatch=Protocol.ParseSearch("""{"total":1,"score_kind":"cosine","items":[{"id":15,"title":"clip.mp4","kind":"video","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.912,"video_match_ms":65000,"literal_words":1,"literal_hits":1}]}""").Items[0];
        check(videoRowMatch.VideoMatchMs==65000&&videoRowMatch.AIEvidence.Contains("動画フレーム一致（1:05）")&&videoRowMatch.AIEvidence.Contains("0.912"),"video time-coded AI match parsed and formatted");
    }
    private sealed class Stub(Func<HttpRequestMessage,HttpResponseMessage> response):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token)=>Task.FromResult(response(request));}
}
