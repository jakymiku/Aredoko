using Aredoko.Core;
using System.Text.Json;
void Check(bool result,string name){if(!result)throw new Exception(name);Console.WriteLine("PASS "+name);}
Check(!JsonSerializer.IsReflectionEnabledByDefault,"reflection disabled");
AppBuildIdentityTests.Run(Check);
await ImageSourceInfoTests.Run(Check);
await ThumbnailTests.Run(Check);
await AnimationStreamTests.Run(Check);
await ResultSessionTests.Run(Check);
await ShelfTests.Run(Check);
await RootFavoritesTests.Run(Check);
await ResultNavigationTests.Run(Check);
ResultBufferTests.Run(Check);
NavigationHistoryTests.Run(Check);
RootShelvesTests.Run(Check);
await ResultWindowTests.Run(Check);
var state=new EditorState("雨、青い夜,雨", "本棚",true,false);
Check(state.ParsedTags.SequenceEqual(new[]{"雨","青い夜"}),"tag normalization");
using var doc=JsonDocument.Parse(Protocol.CreateUpdate(7,state.ParsedTags,state.Shelf,state.Favorite,state.Reviewed));
Check(doc.RootElement.GetProperty("changes").GetProperty("tags")[1].GetString()=="青い夜","Release-safe JSON Unicode update");
var row=Protocol.ParseItem("""{"id":7,"title":"夜","kind":"book","tags":["青"],"shelf":"","favorite":false,"reviewed":false,"relative_path":"本/夜.cbz","availability":"missing"}""");
Check(row.Location=="本/夜.cbz"&&row.Availability=="missing","location contract");
Check(!EditorState.IsDirty(state,state),"selection starts clean");
Check(EditorState.IsDirty(state,state with {Favorite=false}),"favorite marks dirty");
Check((state with {Tags=new string('a',61)}).Validate()!=null,"tag boundary");
var requests=new RequestVersion();var old=requests.Next();var latest=requests.Next();
Check(!requests.IsCurrent(old)&&requests.IsCurrent(latest),"stale search rejected");

var cache=new BoundedLru<string,int>(2);cache.Set("a",1);cache.Set("b",2);cache.TryGet("a",out _);cache.Set("c",3);
Check(cache.Count==2&&!cache.TryGet("b",out _)&&cache.TryGet("a",out _),"bounded cache evicts least recently used");
cache.Set("a",4);Check(cache.Count==2&&cache.TryGet("a",out var value)&&value==4,"cache refresh does not grow");
cache.Clear();Check(cache.Count==0,"cache cleared across sessions");
bool rejected=false;try{PreviewPolicy.ValidateDimensions(50000,50000);}catch(InvalidDataException){rejected=true;}
Check(rejected,"oversized decoded image rejected");

rejected=false;try{PreviewPolicy.ValidateDimensions(uint.MaxValue,uint.MaxValue);}catch(InvalidDataException){rejected=true;}
Check(rejected,"image dimension multiplication cannot overflow");


Check(Protocol.ParseSearch("""{"total":0,"items":[],"coverage_limit":10000}""").CoverageLimit==10000,"AI coverage from server");
Check(Protocol.ParseSearch("""{"total":0,"items":[]}""").CoverageLimit is null,"literal/old API coverage optional");
var completeSearch=Protocol.ParseSearch("""{"total":50001,"items":[],"coverage_limit":10000,"index_limit":10000,"search_complete":true,"search_candidate_total":50002,"indexed_total":50001}""");
Check(completeSearch.SearchComplete&&completeSearch.CoverageLimit is null&&completeSearch.SearchCandidateTotal==50002&&completeSearch.IndexedTotal==50001,"complete scope separates search counts from index job cap");
var incompleteSearch=Protocol.ParseSearch("""{"total":0,"items":[],"coverage_limit":10000,"search_complete":false}""");
Check(!incompleteSearch.SearchComplete&&incompleteSearch.CoverageLimit==10000,"old incomplete response retains legacy limit");
foreach(var invalidComplete in new[]{
    """{"total":0,"items":[],"search_complete":"true"}""",
    """{"total":1,"items":[],"search_complete":true,"search_candidate_total":2,"indexed_total":3}""",
    """{"total":3,"items":[],"search_complete":true,"search_candidate_total":2,"indexed_total":2}""",
    """{"total":0,"items":[],"search_complete":true,"search_candidate_total":-1,"indexed_total":0}"""
})
{
    var invalidRejected=false;try{Protocol.ParseSearch(invalidComplete);}catch(InvalidDataException){invalidRejected=true;}
    Check(invalidRejected,"complete search rejects inconsistent coverage contract");
}
var expanded=Protocol.ParseSearch("""{"total":2,"items":[{"id":1,"title":"poster.png","kind":"image","tags":["東方","巫女"],"shelf":"","favorite":false,"reviewed":false,"match":"direct"},{"id":2,"title":"reimu.png","kind":"image","tags":["博麗霊夢"],"shelf":"","favorite":false,"reviewed":false,"match":"related"}],"expansions":[{"term":"東方","added":["博麗霊夢","霊夢","Reimu","霧雨魔理沙"],"truncated":true},{"term":"巫女","added":["博麗霊夢"]}]}""");
Check(expanded.Expansions.Count==2&&expanded.Expansions[0].Truncated&&!expanded.Expansions[1].Truncated&&expanded.Expansions[0].Added.Length==4,"related-term expansions parsed");
Check(expanded.Items[0].Match=="direct"&&expanded.Items[1].KindAndTags.StartsWith("関連語の候補 · ")&&!expanded.Items[0].KindAndTags.StartsWith("関連語"),"related-only rows are labelled");
var notice=Protocol.DescribeExpansions(expanded.Expansions);
Check(notice.Contains("東方→博麗霊夢、霊夢、Reimu ほか1語")&&notice.Contains("巫女→博麗霊夢）")&&!notice.Contains("霧雨魔理沙"),"expansion notice is bounded");
Check(Protocol.DescribeExpansions(Protocol.ParseSearch("""{"total":0,"items":[]}""").Expansions)=="","no dictionary means no notice");
Check(Protocol.DescribeExpansions(new[]{new SearchExpansion("東方",new[]{"a"},true)}).Contains("東方→a ほか）"),"truncated expansion is disclosed");

var scope=System.Text.Json.Nodes.JsonNode.Parse("""{"root_ids":[2],"kind":"image","shelf":"素材"}""")!.AsObject();
var scopedIndex=AIScopeRequests.Scoped(scope);
var scopedSearch=AIScopeRequests.Search("青い素材","","favorites",1,"cover",scope);
scope["root_ids"]!.AsArray().Add((System.Text.Json.Nodes.JsonNode?)System.Text.Json.Nodes.JsonValue.Create(9));scope["shelf"]="別の棚";
Check(scopedIndex["scope"]!["root_ids"]!.AsArray().Count==1&&scopedSearch["scope"]!["shelf"]!.GetValue<string>()=="素材","AI request owns frozen scope JSON");
Check(scopedSearch["view"]!.GetValue<string>()=="favorites"&&scopedSearch["source"]!.GetValue<string>()=="cover","search filters remain separate from AI scope");
Check(!AIScopeRequests.Search("雨","audio","all",0,"all",null).ContainsKey("scope"),"legacy API scope omitted");
using var scopedDoc=JsonDocument.Parse(scopedIndex.ToJsonString());
Check(scopedDoc.RootElement.GetProperty("scope").GetProperty("shelf").GetString()=="素材","scope request uses reflection-free JSON DOM");


var picker=new RootPicker(Enumerable.Range(1,258).Select(id=>new RootChoice(id,$"架空/root-{id:000}")));
picker.Restore([1]);picker.Filter("root-258");
Check(picker.Visible.Single().Id==258&&picker.Select(258,true),"root beyond256 can be discovered and selected");
picker.Filter("no match");Check(picker.Visible.Count==0&&picker.Selected.SequenceEqual(new[]{1,258}),"hidden selections survive empty filter");
picker.Filter("");picker.Move(8);Check(picker.Visible.Count==2&&picker.PageCount==9&&picker.IsSelected(258),"root page boundary keeps selection");
picker.Move(99);Check(picker.Page==8,"root page forward bounded");picker.Move(-99);Check(picker.Page==0,"root page backward bounded");
picker.Restore(Enumerable.Range(1,256));Check(!picker.Select(258,true)&&picker.SelectionCount==256,"selection cap blocks overflow");
Check(picker.Select(1,false)&&picker.Select(258,true)&&picker.SelectionCount==256,"uncheck frees a selection slot");
picker.Restore([999]);picker.Filter("見つかりません");Check(!picker.Visible.Single().Registered&&picker.Select(999,false),"missing saved root is visible and explicitly removable");
picker.Restore([1]);picker.Filter("ROOT-001");Check(picker.Visible.Single().Id==1&&picker.Selected.SequenceEqual(new[]{1}),"root filter is case insensitive and draft neutral");
bool tooMany=false;try{picker.Restore(Enumerable.Range(1,257));}catch(ArgumentException){tooMany=true;}
Check(tooMany&&picker.Selected.SequenceEqual(new[]{1}),"oversize restore cannot partially replace draft");


foreach(var (index,ai,source) in new[]{(0,false,"all"),(1,true,"all"),(2,true,"cover"),(3,true,"text"),(4,false,"pending-proposals"),(5,false,"page-text")})
{
    var method=SearchMethod.FromIndex(index);
    Check(method.IsAI==ai&&method.Source==source,$"search method {index} preserves API route/modality");
}
var textRequest=AIScopeRequests.Search("曖昧な素材","image","favorites",2,SearchMethod.FromIndex(3).Source,scopedIndex["scope"]!.AsObject());
Check(textRequest["source"]!.GetValue<string>()=="text"&&textRequest["kind"]!.GetValue<string>()=="image"&&textRequest["view"]!.GetValue<string>()=="favorites"&&textRequest["page"]!.GetValue<int>()==2&&textRequest["scope"]!["root_ids"]!.AsArray().Count==1,"text-only mode preserves filters/page and frozen scope");
bool invalidMode=false;try{SearchMethod.FromIndex(7);}catch(ArgumentOutOfRangeException){invalidMode=true;}
Check(invalidMode,"invalid search mode cannot silently broaden retrieval");

await ArchiveReaderTests.Run(Check);


Check(RelatedTerms.SplitWords(" 霊夢、reimu,霊夢，Reimu　れいむ ").SequenceEqual(new[]{"霊夢","reimu","Reimu","れいむ"}),"related words split on Japanese and ASCII separators");
Check(RelatedTerms.Validate("",[],["東方"])!=null&&RelatedTerms.Validate("博麗 霊夢",[],["東方"])!=null&&RelatedTerms.Validate("博麗霊夢",[],[])!=null,"related-term draft requires one headword and a word");
Check(RelatedTerms.Validate("博麗霊夢",Enumerable.Range(0,17).Select(i=>$"w{i}").ToArray(),[])!=null&&RelatedTerms.Validate("博麗霊夢",[new string('a',61)],[])!=null,"related-term limits mirror API");
Check(RelatedTerms.Validate("博麗霊夢",["霊夢"],["東方","巫女"]) is null,"valid related-term draft");
var upsert=RelatedTerms.Upsert(" 博麗霊夢 ",["霊夢"],["東方","巫女"]);
Check(upsert["term"]!.GetValue<string>()=="博麗霊夢"&&upsert["related"]!.AsArray().Count==2&&upsert.Count==3,"related-term upsert body");
var deleteBody=RelatedTerms.Delete(" 博麗霊夢 ");Check(deleteBody.Count==1&&deleteBody["term"]!.GetValue<string>()=="博麗霊夢","related-term delete body");
var termList=RelatedTerms.ParseList(System.Text.Json.Nodes.JsonNode.Parse("""{"items":[{"term":"博麗霊夢","aliases":["霊夢"],"related":["東方","巫女"]},{"term":"","aliases":[],"related":[]},{"term":"x"}]}""")!);
Check(termList.Count==2&&termList[0].Summary=="博麗霊夢（別名: 霊夢） ← 東方、巫女"&&termList[1].Aliases.Length==0,"related-term list parsed defensively");

Check(RelatedTerms.CheckImport("""{"format":"aredoko-related-terms","version":1,"entries":[]}""") is null,"related-term export accepted");
Check(RelatedTerms.CheckImport("not json")!=null&&RelatedTerms.CheckImport("[]")!=null&&RelatedTerms.CheckImport("""{"format":"other","version":1,"entries":[]}""")!=null,"non-export files rejected before upload");
Check(RelatedTerms.CheckImport("""{"format":"aredoko-related-terms","version":2,"entries":[]}""")!=null&&RelatedTerms.CheckImport("""{"format":"aredoko-related-terms","version":"1","entries":[]}""")!=null&&RelatedTerms.CheckImport("""{"format":"aredoko-related-terms","version":1,"entries":{}}""")!=null,"wrong version or entries shape rejected");
Check(RelatedTerms.CheckImport(new string(' ',RelatedTerms.MaxImportBytes+1))!=null,"oversized import rejected");
Check(RelatedTerms.DescribeImport(System.Text.Json.Nodes.JsonNode.Parse("""{"imported":1200,"added":1000,"replaced":200}""")!)=="1,200件を読み込みました（追加1,000・置換200）。","import summary text");

var partialSearch=Protocol.ParseSearch("""{"total":1,"items":[{"id":1,"title":"a.png","path":"a.png","kind":"image","tags":["巫女"],"shelf":"","favorite":false,"reviewed":false,"match":"partial"}],"partial":{"words":2,"required":1}}""");
Check(partialSearch.PartialWords==2&&partialSearch.Items[0].KindAndTags.StartsWith("一部の語のみ一致 · "),"partial fallback parsed and labelled");
Check(Protocol.DescribePartial(2)=="2語すべてに一致する作品はありません。1語に一致する作品を表示しています。"&&Protocol.DescribePartial(null)=="","partial notice text");
var evidenceSearch=Protocol.ParseSearch("""{"total":3,"items":[{"id":1,"title":"a.png","kind":"image","tags":["東方","巫女"],"shelf":"","favorite":false,"reviewed":false,"match":"direct","search_evidence":{"direct_words":["東方","巫女"],"related_words":[],"missing_words":[]}},{"id":2,"title":"b.png","kind":"image","tags":["博麗霊夢"],"shelf":"","favorite":false,"reviewed":false,"match":"partial","search_evidence":{"direct_words":[],"related_words":["東方"],"missing_words":["未知"]}},{"id":3,"title":"c.png","kind":"image","tags":[],"shelf":"","favorite":false,"reviewed":false}]}""");
Check(evidenceSearch.Items[0].Evidence is {AllDirect:true}&&evidenceSearch.Items[0].Evidence!.Direct.SequenceEqual(new[]{"東方","巫女"}),"direct-only evidence parsed");
Check(evidenceSearch.Items[1].Evidence is {AllDirect:false}&&evidenceSearch.Items[1].Evidence!.Related.SequenceEqual(new[]{"東方"})&&evidenceSearch.Items[1].Evidence!.Missing.SequenceEqual(new[]{"未知"}),"related and missing words parsed per row");
Check(evidenceSearch.Items[2].Evidence is null&&Protocol.DescribeEvidence(null)=="","old/list rows have no evidence");
Check(Protocol.DescribeEvidence(evidenceSearch.Items[1].Evidence)=="関連語で一致：東方 / 一致なし：未知"&&Protocol.DescribeEvidence(evidenceSearch.Items[0].Evidence)=="入力語で一致：東方、巫女","evidence description separates direct/related/missing");
var odd=Protocol.ParseItem("""{"id":4,"title":"d","kind":"image","tags":[],"shelf":"","favorite":false,"reviewed":false,"search_evidence":{"direct_words":"東方","related_words":[1,null,""," "],"missing_words":{}}}""");
Check(odd.Evidence is null,"malformed evidence ignored without throwing");
Check(Protocol.ParseItem("""{"id":5,"title":"e","kind":"image","tags":[],"shelf":"","favorite":false,"reviewed":false,"search_evidence":[]}""").Evidence is null,"non-object evidence ignored");
var many=string.Join(",",Enumerable.Range(0,40).Select(i=>$"\"w{i}\""));
var bounded=Protocol.ParseItem("{\"id\":6,\"title\":\"f\",\"kind\":\"image\",\"tags\":[],\"shelf\":\"\",\"favorite\":false,\"reviewed\":false,\"search_evidence\":{\"direct_words\":["+many+"],\"related_words\":[\"r\"],\"missing_words\":[\""+new string('x',200)+"\"]}}").Evidence!;
Check(bounded.Direct.Length==SearchEvidence.MaxWords&&bounded.Related.Length==0&&bounded.Missing.Length==0,"evidence word budget shared across lists");
var longWord=Protocol.ParseItem("{\"id\":7,\"title\":\"g\",\"kind\":\"image\",\"tags\":[],\"shelf\":\"\",\"favorite\":false,\"reviewed\":false,\"search_evidence\":{\"missing_words\":[\""+new string('x',63)+"\uD83D\uDE00tail\"]}}").Evidence!;
Check(longWord.Missing[0]==new string('x',63)+"…","long evidence word truncated without splitting a surrogate pair");
Check(Protocol.DescribeEvidence(new SearchEvidence(["a","b","c","d","e","f"],[],[]))=="入力語で一致：a、b、c、d ほか2語","evidence description bounded per part");
Check(!new SearchEvidence([],[],[]).AllDirect,"empty evidence is not all-direct");
var videoRow=new MediaRow{Id=9,Title="clip.mp4",Kind="video",Availability="present"};
Check(!ImageViewerPolicy.CanOpen(videoRow)&&!ArchiveManifest.CanOpen(videoRow),"video row does not advertise image or book viewer");
Check(RelatedTerms.CountExport("""{"format":"aredoko-related-terms","version":1,"entries":[{"term":"a"},{"term":"b"}]}""")==2,"export count read from the written document");
Check(ErrorText.Localize("Entry 3: aliases must be a single word without spaces")=="3件目: 別名に空白は入れられません（1語ずつ「、」で区切ってください）。","nested import error localized");
Check(ErrorText.Localize("At most 2000 related-term entries after import")=="関連語は2,000件まで登録できます（読み込み後の合計）。"&&ErrorText.Localize("Use at most 16 search words")=="検索語は16語までにしてください。","limit errors localized");
Check(ErrorText.Localize("スキャン中です。")=="スキャン中です。"&&ErrorText.Localize("Something new")=="Something new","Japanese and unknown messages pass through");
Check(ErrorText.FromResponse("""{"error":"Related-term entry not found"}""",404)=="その見出し語は登録されていません。"&&ErrorText.FromResponse("<html>",502)=="バックエンドでエラーが起きました（502）。"&&ErrorText.FromResponse("""{"error":""}""",400)=="要求を処理できませんでした（400）。","response bodies mapped without throwing");

foreach(var body in new[]{"[]","123","true","\"plain string\""})
    Check(ErrorText.FromResponse(body,503)=="バックエンドでエラーが起きました（503）。","non-object JSON error body: "+body);

Check(FolderSearch.LiteralRoute("東方 巫女","image","favorites",2,3).EndsWith("&page=2&root_id=3"),"literal root filter and paging encoded");
Check(!FolderSearch.LiteralRoute("x","","all",0).Contains("root_id"),"all-folder literal route remains unscoped");
var rootScope=System.Text.Json.Nodes.JsonNode.Parse("""{"root_ids":[2,3],"kind":"image","shelf":"AI画像"}""")!.AsObject();
var intersection=FolderSearch.RestrictAI(rootScope,3)!;
Check(intersection["root_ids"]!.AsArray().Count==1&&intersection["shelf"]!.GetValue<string>()=="AI画像","folder intersects AI shelf/kind scope");
Check(FolderSearch.RestrictAI(rootScope,4)!["root_ids"]!.AsArray().Count==0&&rootScope["root_ids"]!.AsArray().Count==2,"disjoint folder stays empty and saved scope is unchanged");
Check(FolderSearch.RestrictAI(new System.Text.Json.Nodes.JsonObject {{"root_ids",new System.Text.Json.Nodes.JsonArray()}},3)!["root_ids"]!.AsArray().Count==0,"empty saved scope cannot broaden");
Check(FolderSearch.RestrictAI(null,3)!["root_ids"]![0]!.GetValue<int>()==3,"explicit folder supported with legacy AI scope");
Check(FolderSearch.LiteralRouteMulti("東方","image","all",0,new[]{5,2}).EndsWith("&page=0&root_ids=2,5"),"multi-root literal route sorts and encodes root_ids");
Check(FolderSearch.LiteralRouteMulti("東方","image","all",0,new[]{4}).EndsWith("&page=0&root_id=4"),"single-element root_ids uses legacy root_id");
var multiIntersect=FolderSearch.RestrictAIMulti(rootScope,new[]{1,2,3})!;
Check(multiIntersect["root_ids"]!.AsArray().Select(n=>n!.GetValue<int>()).SequenceEqual(new[]{2,3}),"multi-root selection intersects saved AI scope");
Check(FolderSearch.RestrictAIMulti(rootScope,Array.Empty<int>())!["root_ids"]!.AsArray().Count==0,"empty multi-root selection never broadens AI scope");
var simMultiReq=SimilaritySearch.RequestMulti(7,"image","all",0,rootScope,new[]{1,3});
Check(simMultiReq["scope"]!["root_ids"]!.AsArray().Select(n=>n!.GetValue<int>()).SequenceEqual(new[]{3}),"similarity multi-root request intersects saved AI scope");
foreach(var badRoots in new IReadOnlyList<int>[]{Array.Empty<int>(),new[]{2,2},new[]{0},new[]{-1},Enumerable.Range(1,257).ToArray()})
{
    var badRejected=false;
    try{FolderSearch.LiteralRouteMulti("q","","all",0,badRoots);}catch(ArgumentException){badRejected=true;}
    Check(badRejected,"invalid multi-root literal selection rejected: "+badRoots.Count);
}
var parsedRoots=RegisteredRootRow.ParseList(System.Text.Json.Nodes.JsonNode.Parse("""
{"items":[
  {"id":1,"path":"C:\\lib\\media-1\\works","enabled":1,"online":true,"default_shelf":"AI画像","excludes":["*.tmp"],"present_count":12,"last_scanned_at":"2026-10-15T10:00:00Z"},
  {"id":2,"path":"C:\\lib\\media-2\\works","enabled":1,"online":false,"default_shelf":"","excludes":[],"present_count":5,"last_scanned_at":null},
  {"id":3,"path":"C:\\lib\\old\\works","enabled":0,"online":true,"default_shelf":"背景","excludes":[],"present_count":3,"last_scanned_at":null}
]}
""")!);
Check(parsedRoots[0].Name=="works"&&parsedRoots[0].ShortPath=="media-1/works"&&parsedRoots[1].ShortPath=="media-2/works","same leaf folders have distinguishable short paths");
Check(parsedRoots[0].StatusLabel.Contains("接続OK")&&parsedRoots[1].StatusLabel.Contains("未接続")&&parsedRoots[2].StatusLabel.Contains("登録解除済み"),"root status labels distinguish online offline and unregistered");
var batchMixed=new FolderSettingsDraft(new[]{parsedRoots[0],parsedRoots[1]});
Check(batchMixed.IsBatch&&batchMixed.Summary.IsMixed&&batchMixed.Summary.DisplayText=="複数の設定値"&&!batchMixed.IsDirty&&batchMixed.ResolveShelfToSave() is null,"batch draft with mixed shelves starts at KeepExisting and saves nothing until edited");
batchMixed.ShelfMode=BatchShelfMode.ClearToNone;
Check(batchMixed.IsDirty&&batchMixed.ResolveShelfToSave()=="","batch ClearToNone explicitly clears shelf to empty string");
batchMixed.ShelfMode=BatchShelfMode.NewShelf;batchMixed.NewShelfName="  新棚  ";
Check(batchMixed.ResolveShelfToSave()=="新棚","batch NewShelf trims new shelf name");
batchMixed.RecordSucceeded(1);
Check(batchMixed.TargetIds.SequenceEqual(new[]{2}),"partial failure keeps only remaining failed root for retry");
var (scopeSummary,scopeWarn)=FolderScopeDescriber.DescribeSearchScope(parsedRoots,new[]{1,3},true,rootScope);
Check(scopeSummary.Contains("media-1/works")&&scopeWarn is not null&&scopeWarn.Contains("登録解除")&&scopeWarn.Contains("1/2"),"scope describer warns on unregistered selection and AI scope narrowing");
var groupedRequest=AIScopeRequests.Search("ミク","image","all",0,"cover",rootScope,false,.5,"other");
Check(groupedRequest["group_threshold"]!.GetValue<double>()==.5&&groupedRequest["result_group"]!.GetValue<string>()=="other","manual boundary and group preserved in request");
var evidence=Protocol.ParseSearch("""{"total":1,"score_kind":"cosine","group_boundary":0.5,"leading_total":3,"other_total":3,"items":[{"id":1,"title":"image.png","kind":"image","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.8,"literal_words":1,"literal_hits":0,"similarity_group":"leading"}]}""");
Check(evidence.GroupBoundary==.5&&evidence.OtherTotal==3&&evidence.Items[0].AIEvidence.Contains("文字一致0/1語")&&evidence.Items[0].AIEvidence.Contains("0.800"),"AI groups and relative score parsed without percentages");
evidence.Items[0].LiteralHits=1;Check(evidence.Items[0].AIEvidence.StartsWith("名前・タグで全語一致"),"literal evidence does not claim character certainty");
evidence.Items[0].ScoreKind="reciprocal-rank";Check(evidence.Items[0].AIEvidence.Contains("順位統合値"),"RRF uses separate score label");

await ImageViewerTests.Run(Check);

Check(ReaderSpreadPolicy.Pages(2,5,ReaderDisplayMode.Single).SequenceEqual(new[]{2}),"single reader keeps exact page");
Check(ReaderSpreadPolicy.Pages(0,5,ReaderDisplayMode.RightToLeft).SequenceEqual(new[]{0}),"spread cover stays alone");
Check(ReaderSpreadPolicy.Pages(1,5,ReaderDisplayMode.RightToLeft).SequenceEqual(new[]{2,1}),"RTL puts later page on left");
Check(ReaderSpreadPolicy.Pages(2,5,ReaderDisplayMode.LeftToRight).SequenceEqual(new[]{1,2}),"LTR normalizes to same pair");
Check(ReaderSpreadPolicy.Next(0,5,ReaderDisplayMode.RightToLeft)==1,"next cover enters first spread");
Check(ReaderSpreadPolicy.Next(1,5,ReaderDisplayMode.RightToLeft)==3,"next spread skips both visible pages");
Check(ReaderSpreadPolicy.Previous(1,5,ReaderDisplayMode.RightToLeft)==0,"previous first spread returns cover");
Check(ReaderSpreadPolicy.Previous(3,5,ReaderDisplayMode.LeftToRight)==1,"previous later spread uses previous pair");
Check(ReaderSpreadPolicy.Pages(3,4,ReaderDisplayMode.RightToLeft).SequenceEqual(new[]{3}),"unpaired final page stays alone");
Check(ReaderSpreadPolicy.Next(3,4,ReaderDisplayMode.LeftToRight)>=4,"last spread next is out of range");
Check(ReaderSpreadPolicy.Pages(9999,10000,ReaderDisplayMode.RightToLeft).SequenceEqual(new[]{9999}),"bounded large book final page");
try{ReaderSpreadPolicy.Pages(0,0,ReaderDisplayMode.Single);Check(false,"invalid empty book");}catch(ArgumentOutOfRangeException){Check(true,"empty spread book rejected");}
var clicks=new ThumbnailClickTracker();
Check(clicks.Register(5,1000,20,30,500,4,4) is null,"first thumbnail click does not open");
Check(clicks.Register(null,1200,21,30,500,4,4)==5,"double click survives layout moving thumbnail away");
Check(clicks.Register(5,1250,21,30,500,4,4) is null,"triple click does not open twice");
Check(clicks.Register(6,1300,21,30,500,4,4) is null,"different thumbnail cannot activate old ID");
Check(clicks.Register(6,1900,21,30,500,4,4) is null,"slow second click stays single");
Check(clicks.Register(6,2000,40,30,500,4,4) is null,"far second click stays single");
clicks.Reset();Check(clicks.Register(null,2100,40,30,500,4,4) is null,"cancel/modal reset cannot activate old image");

await ReaderProgressTests.Run(Check);
await ViewerPerformanceTests.Run(Check);

await VideoRangeTests.Run(Check);
await SimilarityTests.Run(Check);

await TagReviewTests.Run(Check);
Check(new MediaRow{Location="作品A/",Availability="present",Kind="book"} is var folderBook && folderBook.IsFolderBook && ArchiveManifest.CanOpen(folderBook) && TagReviewProtocol.CanOpen(folderBook) && !ImageViewerPolicy.CanOpen(folderBook),"folder book opens in reader and tag review");
Check(new MediaRow{Location="Vol.1/p1.png",Availability="present",Kind="image"} is var page && !page.IsFolderBook && new MediaRow{Location="作品A/",Availability="missing"} is var gone && !ArchiveManifest.CanOpen(gone) && !TagReviewProtocol.CanOpen(gone),"files and missing folder books are not folder readers");
Check(new MediaRow{Location="./"}.LocationLabel=="登録フォルダ直下の画像（一冊）"&&new MediaRow{Location="a.png"}.LocationLabel=="a.png","folder book location label");
Check(RegisteredRootRow.ParseList(System.Text.Json.Nodes.JsonNode.Parse("""{"items":[{"id":1,"path":"C:/b","enabled":1,"online":true,"folder_books":true},{"id":2,"path":"C:/c","enabled":1,"online":true}]}""")!) is var roots && roots[0].FolderBooks && !roots[1].FolderBooks && roots[0].ModeLabel=="画像フォルダを一冊として扱う","root folder-book mode parsed (absent means off)");
Check(ErrorText.Localize("Folder book mode cannot change after scanning").StartsWith("「画像フォルダを一冊として扱う」")&&ErrorText.Localize("This root is already registered")=="このフォルダはすでに登録されています。","folder registration errors localized");

await FeedbackTests.Run(Check);
PageImageTests.Run(Check);
await PageCoverageTests.Run(Check);
PageBatchTests.Run(Check);
await PageChunkTests.Run(Check);
await IndexContinuationTests.Run(Check);

await SearchCancellationTests.Run(Check);
AudioSpeechTests.Run(Check);
StatusClarityTests.Run(Check);

foreach(var available in new[]{300d,700d,1200d,2400d})
foreach(var size in new[]{60,100,180})
{
    var width=LibraryTileLayout.Width(available,size);
    var columns=Math.Max(1,(int)Math.Floor(available/(232*size/100d+8)));
    Check(width>0&&Math.Abs((width+8)*columns-available)<.001,"tile row fills available width "+available+" / "+size);
}
Check(LibraryTileLayout.Width(1200,60)<LibraryTileLayout.Width(1200,180),"smaller tiles increase column count");
Check(double.IsFinite(LibraryTileLayout.Width(double.NaN,100)),"tile layout handles unavailable width");
