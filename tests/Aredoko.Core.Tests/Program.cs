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

var scope=System.Text.Json.Nodes.JsonNode.Parse("""{"root_ids":[2],"kind":"image","shelf":"素材"}""")!.AsObject();
var scopedIndex=AIScopeRequests.Scoped(scope);
var scopedSearch=AIScopeRequests.Search("青い素材","","favorites",1,"cover",scope);
scope["root_ids"]!.AsArray().Add((System.Text.Json.Nodes.JsonNode?)System.Text.Json.Nodes.JsonValue.Create(9));scope["shelf"]="別の棚";
Check(scopedIndex["scope"]!["root_ids"]!.AsArray().Count==1&&scopedSearch["scope"]!["shelf"]!.GetValue<string>()=="素材","AI request owns frozen scope JSON");
Check(scopedSearch["view"]!.GetValue<string>()=="favorites"&&scopedSearch["source"]!.GetValue<string>()=="cover","search filters remain separate from AI scope");
Check(!AIScopeRequests.Search("雨","audio","all",0,"all",null).ContainsKey("scope"),"legacy API scope omitted");
using var scopedDoc=JsonDocument.Parse(scopedIndex.ToJsonString());
Check(scopedDoc.RootElement.GetProperty("scope").GetProperty("shelf").GetString()=="素材","scope request uses reflection-free JSON DOM");
