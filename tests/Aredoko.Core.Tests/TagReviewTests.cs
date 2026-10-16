using Aredoko.Core;
using System.Net;
using System.Text;
using System.Text.Json.Nodes;

static class TagReviewTests
{
    static readonly string Revision=new('a',64);
    static string History()=>$$"""
    {"item_id":7,"source_revision":"{{Revision}}","available":true,"reason":"","next_before":null,"batches":[
      {"id":4000000000,"item_id":7,"source_revision":"{{Revision}}","stale":false,
       "evidence":{"item_id":7,"revision":"{{Revision}}","kind":"cover","page":0},
       "producer":{"model":"test-only","model_revision":"fixed","adapter":"fixture","version":"1","preprocessing":"cover"},
       "proposals":[{"id":5000000000,"tag":"候補","explanation":"先頭ページだけの根拠","page":0,"state":"pending","accepted_tag":null,"version":0}]}]}
    """;
    static HttpResponseMessage Json(string text)=>new(HttpStatusCode.OK){Content=new StringContent(text,Encoding.UTF8,"application/json")};
    sealed class Handler(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> handle):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)=>handle(request,cancellation);}
    public static async Task Run(Action<bool,string> check)
    {
        var parsed=TagReviewProtocol.Parse(Encoding.UTF8.GetBytes(History()),7);
        check(parsed.Batches[0].Candidates[0].Id==5000000000&&parsed.Batches[0].Id==4000000000,"tag IDs preserve Int64");
        check(parsed.Batches[0].Candidates[0].StateLabel=="未承認"&&parsed.Batches[0].EvidenceKind=="cover","pending and cover provenance remain explicit");
        foreach(var field in new[]{"item_id","source_revision","producer","evidence","proposals"})
        {
            var broken=JsonNode.Parse(History())!;broken["batches"]![0]!.AsObject().Remove(field);
            try{TagReviewProtocol.Parse(Encoding.UTF8.GetBytes(broken.ToJsonString()),7);check(false,"missing tag field "+field);}
            catch(InvalidDataException){check(true,"missing tag field rejected "+field);}
        }
        var stale=JsonNode.Parse(History())!;stale["source_revision"]=new string('b',64);stale["batches"]![0]!["stale"]=true;
        check(TagReviewProtocol.Parse(Encoding.UTF8.GetBytes(stale.ToJsonString()),7).Batches[0].Stale,"changed physical source marks candidate stale");
        var duplicate=JsonNode.Parse(History())!;duplicate["batches"]![0]!["proposals"]!.AsArray().Add(duplicate["batches"]![0]!["proposals"]![0]!.DeepClone());
        try{TagReviewProtocol.Parse(Encoding.UTF8.GetBytes(duplicate.ToJsonString()),7);check(false,"duplicate proposal");}catch(InvalidDataException){check(true,"duplicate proposal rejected");}
        var fault="";var calls=0;
        using var api=new LibraryApi(new Handler(async(request,cancellation)=>
        {
            calls++;if(request.RequestUri!.AbsolutePath=="/api/session")return Json("""{"mode":"production","token":"fixture"}""");
            check(request.Headers.GetValues("X-Aredoko-Token").Single()=="fixture"&&request.Headers.GetValues("Origin").Single()=="http://127.0.0.1:8769","tag client retains authenticated local session");
            if(fault=="cancel")await Task.Delay(Timeout.Infinite,cancellation);
            if(fault=="size")return new(HttpStatusCode.OK){Content=new ByteArrayContent(new byte[TagReviewProtocol.MaxJsonBytes+1])};
            if(fault=="mime")return new(HttpStatusCode.OK){Content=new StringContent(History(),Encoding.UTF8,"text/html")};
            if(request.RequestUri.AbsolutePath.EndsWith("/review"))
            {
                var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync(cancellation))!;
                check(body["proposal_id"]!.GetValue<long>()==5000000000&&body["tag"]!.GetValue<string>()=="修正タグ","review serializes exact candidate and edited tag");
                return Json("""{"proposal_id":5000000000,"version":1,"state":"accepted","accepted_tag":"修正タグ"}""");
            }
            check(request.RequestUri.PathAndQuery=="/api/library/tag-suggestions/7?limit=10","bounded item history route");return Json(History());
        }));
        await api.ConnectAsync();await api.TagReviews.HistoryAsync(7,null,CancellationToken.None);
        await api.TagReviews.ReviewAsync(7,parsed.Batches[0].Candidates[0],true," 修正タグ ",CancellationToken.None);
        foreach(var mode in new[]{"size","mime"})
        {fault=mode;try{await api.TagReviews.HistoryAsync(7,null,CancellationToken.None);check(false,"tag response "+mode);}catch(InvalidDataException){check(true,"tag response rejects "+mode);}}
        fault="cancel";using var cancel=new CancellationTokenSource();var pending=api.TagReviews.HistoryAsync(7,null,cancel.Token);cancel.Cancel();
        try{await pending;check(false,"tag cancellation");}catch(OperationCanceledException){check(true,"tag read cancellation is distinct from timeout");}
        var before=calls;try{await api.TagReviews.EvidenceAsync(7,"bad",CancellationToken.None);check(false,"invalid evidence revision");}catch(ArgumentException){check(calls==before,"invalid evidence revision sends no request");}
        check(!TagReviewProtocol.CanOpen(new(){Location="video.mp4",Availability="present"})&&TagReviewProtocol.CanOpen(new(){Location="book.CBZ",Availability="present"}),"review entry only for supported present image and archive");
        var searchMethod4=SearchMethod.FromIndex(4);
        check(!searchMethod4.IsAI&&searchMethod4.IsTagCandidates&&searchMethod4.Source=="pending-proposals","search method 4 routes to pending tag candidates without AI embedding requirement");
        var candidateReq=TagReviewProtocol.CandidateSearchRequest("solo","image","unreviewed",1,new[]{5,2},"棚A","wd-v3");
        check(candidateReq["query"]!.GetValue<string>()=="solo"&&candidateReq["page"]!.GetValue<int>()==1&&
              candidateReq["root_ids"]!.AsArray().Select(n=>n!.GetValue<int>()).SequenceEqual(new[]{2,5})&&
              candidateReq["shelf"]!.GetValue<string>()=="棚A"&&candidateReq["model"]!.GetValue<string>()=="wd-v3",
              "candidate search request normalizes roots and filters");
        foreach(var badRoots in new IReadOnlyList<int>[]{Array.Empty<int>(),new[]{1,1},new[]{0}})
        {
            var badRejected=false;
            try{TagReviewProtocol.CandidateSearchRequest("","image","all",0,badRoots);}catch(ArgumentException){badRejected=true;}
            check(badRejected,"candidate search rejects invalid root_ids");
        }
        var searchJson=$$"""
        {"total":1,"page":0,"limit":60,"search_mode":"pending-proposals","items":[
          {"id":7,"title":"book.cbz","kind":"book","tags":["確定"],"shelf":"","favorite":false,"reviewed":false,
           "root_id":2,"relative_path":"book.cbz","availability":"present","size_bytes":100,"mtime_ns":200,
           "proposal_match":{"batch_id":4000000000,"source_revision":"{{Revision}}","source_state":"stale","state":"pending",
             "tags":["candidate-one","candidate-two"],
             "producer":{"model":"wd-swinv2","model_revision":"rev1","adapter":"wd","version":"1","preprocessing":"cover-v1"},
             "evidence":{"item_id":7,"revision":"{{Revision}}","kind":"cover","page":0} } }]}
        """;
        var parsedSearch=TagReviewProtocol.ParseCandidateSearch(Encoding.UTF8.GetBytes(searchJson),0);
        check(parsedSearch.Total==1&&parsedSearch.Items[0].Proposal is {BatchId:4000000000,SourceState:"stale"} prop&&
              prop.Summary.Contains("未承認タグ候補: candidate-one、candidate-two")&&prop.Summary.Contains("本の先頭ページのみ")&&prop.Summary.Contains("元ファイル変更あり"),
              "candidate search response parses provenance, cover evidence, and stale state");
        var semanticMethod=SearchMethod.FromIndex(6);
        check(semanticMethod.IsTagCandidates&&semanticMethod.IsTagSemantic&&!semanticMethod.IsAI,"separate pending-tag semantic search mode");
        var semanticSearch=JsonNode.Parse(searchJson)!.AsObject();
        semanticSearch["search_mode"]="pending-proposals-semantic";semanticSearch["score_kind"]="cosine";
        semanticSearch["pending_total"]=2;semanticSearch["indexed_total"]=1;semanticSearch["index_remaining"]=1;
        semanticSearch["items"]![0]!["semantic_score"]=.82;
        semanticSearch["items"]![0]!["proposal_match"]!["embedding_model"]="google/embeddinggemma-2";
        var meaning=TagReviewProtocol.ParseCandidateSearch(Encoding.UTF8.GetBytes(semanticSearch.ToJsonString()),0,true);
        check(meaning.PendingIndexRemaining==1&&meaning.Items[0].Proposal is {SemanticScore:.82,EmbeddingModel:"google/embeddinggemma-2"},"pending semantic score/model and remaining index are explicit");
        check(meaning.Items[0].Proposal!.Summary.Contains("タグ候補の意味一致")&&meaning.Items[0].Proposal!.Summary.Contains("類似度")&&meaning.Items[0].AIEvidence=="","one semantic evidence explanation without duplicate generic AI label");
        foreach(var mutateMeaning in new Action<JsonObject>[] {
            o=>o["indexed_total"]=2,
            o=>o["index_remaining"]=0,
            o=>o["items"]![0]!["semantic_score"]=2,
            o=>o["items"]![0]!["proposal_match"]!.AsObject().Remove("embedding_model"),
            o=>o["pending_total"]=-1
        })
        {
            var broken=semanticSearch.DeepClone().AsObject();mutateMeaning(broken);
            var rejected=false;try{TagReviewProtocol.ParseCandidateSearch(Encoding.UTF8.GetBytes(broken.ToJsonString()),0,true);}catch(InvalidDataException){rejected=true;}
            check(rejected,"invalid semantic pending-tag evidence/count rejected");
        }
        foreach(var mutate in new Action<JsonObject>[]{
            o=>o["search_mode"]="wrong",
            o=>o["page"]=2,
            o=>o["items"]![0]!["proposal_match"]!["state"]="accepted",
            o=>o["items"]![0]!["proposal_match"]!["source_state"]="unknown",
            o=>o["items"]![0]!["proposal_match"]!["tags"]=new JsonArray(),
            o=>o["items"]![0]!["proposal_match"]!["evidence"]!["item_id"]=99
        })
        {
            var broken=JsonNode.Parse(searchJson)!.AsObject();mutate(broken);
            var rejected=false;
            try{TagReviewProtocol.ParseCandidateSearch(Encoding.UTF8.GetBytes(broken.ToJsonString()),0);}catch(InvalidDataException){rejected=true;}
            check(rejected,"invalid candidate search payload rejected");
        }
    }
}
