using System.Text.Json.Nodes;
namespace Aredoko.Core;

// Own the JSON nodes; editing a dialog must never mutate a running request.
public static class AIScopeRequests
{
    public static JsonObject Scoped(JsonObject scope) => new() { ["scope"] = scope.DeepClone() };
    public static JsonObject Search(string query,string kind,string view,int page,string source,JsonObject? scope,bool literalOnly=false,double? groupThreshold=null,string resultGroup="all")
    {
        var request=new JsonObject {{"query",query},{"kind",kind},{"view",view},{"page",page},{"source",source}};
        if(resultGroup!="all")request["result_group"]=resultGroup;
        if(groupThreshold is double threshold && double.IsFinite(threshold))request["group_threshold"]=threshold;
        if(literalOnly)request["literal_only"]=true;
        if(scope is not null)request["scope"]=scope.DeepClone();
        return request;
    }
}
