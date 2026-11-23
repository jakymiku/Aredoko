using System.Reflection;
using Aredoko.Core;

internal static class AppBuildIdentityTests
{
    public static void Run(Action<bool,string> check)
    {
        var assembly=typeof(AppBuildIdentityTests).Assembly;
        var directory=Path.Combine(Path.GetTempPath(),"aredoko-build-id");
        var identity=AppBuildIdentity.FromAssembly(assembly,directory);
        check(identity.Version==assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
            "diagnostic version comes from actual running assembly");
        check(identity.Directory==directory&&identity.Configuration=="Release","build identity keeps explicit executable location and configuration");
        check(AppBuildIdentity.RevisionFromVersion("1.2.3+"+new string('b',40))==new string('b',40),"SDK informational commit is recognized");
        check(AppBuildIdentity.RevisionFromVersion("1.2.3")=="不明"&&AppBuildIdentity.RevisionFromVersion("1.2.3+not-a-commit")=="不明",
            "non-Git builds never invent a source revision");
        var privateDirectory=@"C:\Users\SensitiveName\Apps\Aredoko";
        var report=(identity with{Directory=privateDirectory}).ToDiagnosticText();
        check(!report.Contains("SensitiveName")&&report.Contains("配布種別:"),"copied build diagnostic redacts username and retains channel");
    }
}
