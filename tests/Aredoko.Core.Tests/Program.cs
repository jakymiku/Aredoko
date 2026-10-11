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
