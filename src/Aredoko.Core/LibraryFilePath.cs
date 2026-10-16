namespace Aredoko.Core;

public static class LibraryFilePath
{
    public static string Resolve(string root,string relative)
    {
        if(string.IsNullOrWhiteSpace(root)||!Path.IsPathFullyQualified(root)||string.IsNullOrWhiteSpace(relative))throw new InvalidDataException("登録先を確認してください。");
        if(relative=="./")return Path.GetFullPath(root);
        if(Path.IsPathRooted(relative)||relative.Any(c=>char.IsControl(c)||c is ':' or '"'))throw new InvalidDataException("登録先が無効です。");
        var parts=relative.TrimEnd('/').Replace('\\','/').Split('/');
        if(parts.Any(p=>p.Length==0||p is "." or ".."))throw new InvalidDataException("登録先が無効です。");
        var basis=Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        var target=Path.GetFullPath(Path.Combine(new[]{basis}.Concat(parts).ToArray()));
        var comparison=OperatingSystem.IsWindows()?StringComparison.OrdinalIgnoreCase:StringComparison.Ordinal;
        var prefix=Path.EndsInDirectorySeparator(basis)?basis:basis+Path.DirectorySeparatorChar;
        if(!target.StartsWith(prefix,comparison))throw new InvalidDataException("登録先の外は開けません。");
        return target;
    }
    public static string Describe(MediaRow row,string root)
    {
        var type=row.IsFolderBook?"画像フォルダ（一冊）":Path.GetExtension(row.Location).TrimStart('.').ToUpperInvariant();
        var size=row.Size>=1024L*1024*1024?$"{row.Size/(1024d*1024*1024):N2} GB":row.Size>=1024*1024?$"{row.Size/(1024d*1024):N2} MB":$"{row.Size/1024d:N1} KB";
        var modified="";
        if(!row.IsFolderBook)
        {
            try{modified="\n更新日時: "+DateTimeOffset.FromUnixTimeMilliseconds(row.Modified/1000000).ToLocalTime().ToString("yyyy/MM/dd HH:mm:ss");}
            catch(ArgumentOutOfRangeException){}
        }
        return $"種類: {type}\n容量: {size}（{row.Size:N0} バイト）{modified}\n登録フォルダ: {root}\n場所: {row.LocationLabel}";
    }
}
