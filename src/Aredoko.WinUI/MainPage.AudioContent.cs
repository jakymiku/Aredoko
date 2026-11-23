using Aredoko.Core;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private JsonObject AudioIndexConditions()
    {
        var conditions=new JsonObject{["view"]=view is "favorites" or "shelf"?view:"all"};
        if(FolderSearch.NormalizeNonEmpty(selectedSearchRoots) is {} roots)
        {
            var values=new JsonArray();foreach(var id in roots)values.Add((JsonNode?)JsonValue.Create(id));
            conditions["root_ids"]=values;
        }
        return ShelfProtocol.Restrict(conditions,selectedShelfIds);
    }
}
