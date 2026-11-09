// Native first-stage preparation: no Python or modern .NET installation needed.
// Explicit developer/packaging CLI for now; normal bootstrap integration is pending.
using System;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;

internal static class PythonSetup
{
    const string Url = "https://api.nuget.org/v3-flatcontainer/python/3.13.17/python.3.13.17.nupkg";
    // NuGet catalog entry for Python Software Foundation's python 3.13.17.
    const string Hash = "DmZ5KLtPGVc8bNiPZRM7LgeyQ6XHFvM1tWqma7nsb4IyglbSLDop4joCdqxcam14YhH+q1JIkK0eVmKRlsaynA==";

    static int Main(string[] args)
    {
        try
        {
            if(args.Length != 2) throw new ArgumentException("Usage: PythonSetup.exe <new-output-directory> <verified-package-or-download>");
            Prepare(args[0], args[1]);
            return 0;
        }
        catch(Exception error)
        {
            Console.Error.WriteLine(error.Message);
            return 1;
        }
    }

    static void DirectoryGuard(string path)
    {
        for(var current = Path.GetFullPath(path); current != null; current = Path.GetDirectoryName(current))
        {
            var attributes = File.GetAttributes(current);
            if((attributes & FileAttributes.ReparsePoint) != 0 || (attributes & FileAttributes.Directory) == 0)
                throw new IOException("Runtime parent must be an ordinary directory without links.");
        }
    }

    static void Prepare(string destination, string package)
    {
        destination = Path.GetFullPath(destination);
        var parent = Path.GetDirectoryName(destination);
        DirectoryGuard(parent);
        if(Directory.Exists(destination) || File.Exists(destination))
            throw new IOException("Refusing to overwrite an existing environment.");
        var stage = Path.Combine(parent, "python-stage-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(stage);
        // Failed staging is retained for diagnosis, never published as usable.
        var archive = Path.Combine(stage, "python.nupkg");
        if(package == "download")
        {
            Console.WriteLine("Downloading official CPython 3.13.17...");
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            var request = (HttpWebRequest)WebRequest.Create(Url);
            request.AllowAutoRedirect = false;
            request.Timeout = 60000;
            request.ReadWriteTimeout = 60000;
            using(var response = (HttpWebResponse)request.GetResponse())
            {
                if(response.StatusCode != HttpStatusCode.OK) throw new IOException("Unexpected package response.");
                if(response.ContentLength > 128L * 1024 * 1024) throw new IOException("Package exceeds download limit.");
                using(var input = response.GetResponseStream())
                using(var output = new FileStream(archive, FileMode.CreateNew, FileAccess.Write))
                {
                    var buffer = new byte[65536];
                    long total = 0;
                    int count;
                    while((count = input.Read(buffer, 0, buffer.Length)) != 0)
                    {
                        total += count;
                        if(total > 128L * 1024 * 1024) throw new IOException("Package exceeds download limit.");
                        output.Write(buffer, 0, count);
                    }
                }
            }
        }
        else
        {
            package = Path.GetFullPath(package);
            DirectoryGuard(Path.GetDirectoryName(package));
            if((File.GetAttributes(package) & FileAttributes.ReparsePoint) != 0) throw new IOException("Package links are not accepted.");
            File.Copy(package, archive, false);
        }
        // Keep the exact bytes locked from verification through extraction.
        using(var input = new FileStream(archive, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            using(var sha = SHA512.Create())
                if(Convert.ToBase64String(sha.ComputeHash(input)) != Hash)
                    throw new IOException("Official package SHA512 mismatch. Environment not published.");
            input.Position = 0;
            var payload = Path.Combine(stage, "payload");
            Directory.CreateDirectory(payload);
            using(var zip = new ZipArchive(input, ZipArchiveMode.Read, true))
            {
                foreach(var entry in zip.Entries)
                {
                    var name = entry.FullName.Replace('/', '\\');
                    if(name.Contains(":") || name.StartsWith("\\") || Array.Exists(name.Split('\\'), part => part == ".." || part == "."))
                        throw new IOException("Invalid package entry.");
                    var output = Path.GetFullPath(Path.Combine(payload, name));
                    if(!output.StartsWith(payload + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                        throw new IOException("Package path escaped staging.");
                    if(name.EndsWith("\\")) { Directory.CreateDirectory(output); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(output));
                    using(var source = entry.Open())
                    using(var target = new FileStream(output, FileMode.CreateNew, FileAccess.Write))
                        source.CopyTo(target);
                }
            }
            if(!File.Exists(Path.Combine(payload, "tools", "python.exe")) || !Directory.Exists(Path.Combine(payload, "tools", "Lib", "venv")))
                throw new IOException("Expected CPython/venv layout missing.");
            DirectoryGuard(parent);
            Directory.Move(payload, destination);
        }
        Console.WriteLine("Official package verified and extracted: " + destination);
        Console.WriteLine("AI dependencies and model compatibility have NOT been verified.");
    }
}
