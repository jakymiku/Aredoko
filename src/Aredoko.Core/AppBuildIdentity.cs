using System.Reflection;
using System.Text;

namespace Aredoko.Core;

// Build metadata only; does not inspect user media, Git, or the machine at runtime.
public sealed record AppBuildIdentity(string Version,string SourceRevision,string Channel,string Configuration,string Directory)
{
    public static AppBuildIdentity FromAssembly(Assembly assembly,string directory)
    {
        var version=assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
            ??assembly.GetName().Version?.ToString()??"不明";
        var channel=assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
            .FirstOrDefault(item=>item.Key=="AredokoChannel")?.Value??"不明";
        var configuration=assembly.GetCustomAttribute<AssemblyConfigurationAttribute>()?.Configuration??"不明";
        return new(version,RevisionFromVersion(version),channel,configuration,directory);
    }

    public static string RevisionFromVersion(string version)
    {
        var split=version.IndexOf('+');
        var revision=split<0?"":version[(split+1)..];
        return revision.Length is >=7 and <=64&&revision.All(char.IsAsciiHexDigit)?revision:"不明";
    }

    public string ToDiagnosticText()
    {
        var text=new StringBuilder();
        text.AppendLine("--- 実行中のアプリ ---");
        text.AppendLine($"ビルド元コミット: {SourceRevision}");
        text.AppendLine($"配布種別: {Channel}");
        text.AppendLine($"ビルド構成: {Configuration}");
        text.AppendLine($"実行場所（ユーザー名は伏字）: {DiagnosticsReport.RedactPath(Directory)}");
        return text.ToString();
    }
}
