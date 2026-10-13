using Aredoko.Core;
using System.Text.Json;
void Check(bool result,string name){if(!result)throw new Exception(name);Console.WriteLine("PASS "+name);}
Check(!JsonSerializer.IsReflectionEnabledByDefault,"reflection disabled");
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


foreach(var (index,ai,source) in new[]{(0,false,"all"),(1,true,"all"),(2,true,"cover"),(3,true,"text")})
{
    var method=SearchMethod.FromIndex(index);
    Check(method.IsAI==ai&&method.Source==source,$"search method {index} preserves API route/modality");
}
var textRequest=AIScopeRequests.Search("曖昧な素材","image","favorites",2,SearchMethod.FromIndex(3).Source,scopedIndex["scope"]!.AsObject());
Check(textRequest["source"]!.GetValue<string>()=="text"&&textRequest["kind"]!.GetValue<string>()=="image"&&textRequest["view"]!.GetValue<string>()=="favorites"&&textRequest["page"]!.GetValue<int>()==2&&textRequest["scope"]!["root_ids"]!.AsArray().Count==1,"text-only mode preserves filters/page and frozen scope");
bool invalidMode=false;try{SearchMethod.FromIndex(4);}catch(ArgumentOutOfRangeException){invalidMode=true;}
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
