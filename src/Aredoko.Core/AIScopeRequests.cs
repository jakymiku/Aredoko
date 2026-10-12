using System.Text.Json.Nodes;
namespace Aredoko.Core;

// Own the JSON nodes; editing a dialog must never mutate a running request.
public static class AIScopeRequests
{
    public static JsonObject Scoped(JsonObject scope) => new() { ["scope"] = scope.DeepClone() };
    public static JsonObject Search(string query,string kind,string view,int page,string source,JsonObject? scope)
    {
        var request=new JsonObject {{"query",query},{"kind",kind},{"view",view},{"page",page},{"source",source}};
        if(scope is not null)request["scope"]=scope.DeepClone();
        return request;
    }
}
