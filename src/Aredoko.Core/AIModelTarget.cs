using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

// Physical weights/layout identity, deliberately separate from a vector namespace.
public sealed record AIModelTarget(string Role,string ModelId,string Revision,string Directory)
{
    public void Validate()
    {
        if(Role is not ("embedding" or "tagger")||string.IsNullOrWhiteSpace(ModelId)||ModelId.Length>160||ModelId.Any(char.IsControl))throw new InvalidDataException("Invalid model identity");
        AIDownloadCatalog.Digest(Revision,Revision.Length==40?40:64);
        if(string.IsNullOrEmpty(Directory)||Directory.Length>128||Directory.Any(c=>char.IsControl(c)||"\\:<>\"|?*".Contains(c)))throw new InvalidDataException("Invalid model directory");
        foreach(var part in Directory.Split('/'))
        {
            var stem=part.Split('.')[0].ToUpperInvariant();
            if(part is "" or "." or ".."||part.EndsWith(' ')||part.EndsWith('.')||stem is "CON" or "PRN" or "AUX" or "NUL"||stem.Length==4&&(stem.StartsWith("COM")||stem.StartsWith("LPT"))&&stem[3] is >= '1' and <= '9')throw new InvalidDataException("Invalid model directory");
        }
    }
    internal static AIModelTarget Parse(JsonElement value,bool withRoot=false)
    {
        var fields=value.EnumerateObject().Select(p=>p.Name).ToArray();
        var expected=withRoot?new[]{"role","model_id","revision","directory","root"}:new[]{"role","model_id","revision","directory"};
        if(fields.Length!=expected.Length||!fields.Order().SequenceEqual(expected.Order()))throw new InvalidDataException("Invalid model target fields");
        var target=new AIModelTarget(AIDownloadCatalog.Text(value,"role",16),AIDownloadCatalog.Text(value,"model_id",160),AIDownloadCatalog.Text(value,"revision",64),AIDownloadCatalog.Text(value,"directory",128));
        target.Validate();return target;
    }
    internal JsonObject ToJson()
    {Validate();return new(){["role"]=Role,["model_id"]=ModelId,["revision"]=Revision,["directory"]=Directory};}
}
public sealed record AIModelLocation(AIModelTarget Target,string Root);
