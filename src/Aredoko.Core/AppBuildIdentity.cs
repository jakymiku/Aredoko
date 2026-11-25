using System.Reflection;
using System.Text;

namespace Aredoko.Core;

// Build metadata only; does not inspect user media, Git, or the machine at runtime.
public sealed record AppBuildIdentity(string Version,string SourceRevision,string Channel,string Configuration,string Directory)
{
    public static AppBuildIdentity FromAssembly(Assembly assembly,string directory)
    {
        var version=assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
            ??assembly.GetName().Version?.ToString()??AppText.L("不明","Unknown");
        var channel=assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
            .FirstOrDefault(item=>item.Key=="AredokoChannel")?.Value??AppText.L("不明","Unknown");
        var configuration=assembly.GetCustomAttribute<AssemblyConfigurationAttribute>()?.Configuration??AppText.L("不明","Unknown");
        return new(version,RevisionFromVersion(version),channel,configuration,directory);
    }

    public static string RevisionFromVersion(string version)
    {
        var split=version.IndexOf('+');
        var revision=split<0?"":version[(split+1)..];
        return revision.Length is >=7 and <=64&&revision.All(char.IsAsciiHexDigit)?revision:AppText.L("不明","Unknown");
    }

    public string ToDiagnosticText()
    {
        var text=new StringBuilder();
        text.AppendLine(AppText.L("--- 実行中のアプリ ---","--- Running Application ---"));
        text.AppendLine($"{AppText.L("ビルド元コミット","Source Commit")}: {SourceRevision}");
        text.AppendLine($"{AppText.L("配布種別","Distribution Channel")}: {Channel}");
        text.AppendLine($"{AppText.L("ビルド構成","Build Configuration")}: {Configuration}");
        text.AppendLine($"{AppText.L("実行場所（ユーザー名は伏字）","Location (username redacted)")}: {DiagnosticsReport.RedactPath(Directory)}");
        return text.ToString();
    }
}
