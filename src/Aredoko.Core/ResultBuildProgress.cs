using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record ResultBuildProgress(string State,int Processed,int? Total)
{
    public static ResultBuildProgress Parse(JsonObject root,string expectedId,JsonObject conditions)
    {
        try
        {
            var state=root["state"]?.GetValue<string>();
            var processed=root["processed"]?.GetValue<int>();
            int? total=root["total"]?.GetValue<int>();
            if(root["session_id"]?.GetValue<string>()!=expectedId||!JsonNode.DeepEquals(root["conditions"],conditions)||
                state is not ("building" or "ready")||processed is null or <0||total is <0||
                (total is int expected&&processed>expected)||
                (state=="ready"&&(total is null||processed!=total))||root.ContainsKey("items"))
                throw new InvalidDataException("Invalid result build progress");
            return new(state,processed.Value,total);
        }
        catch(Exception ex) when(ex is JsonException or InvalidOperationException or FormatException or OverflowException)
        {throw new InvalidDataException("Invalid result build progress",ex);}
    }
}
