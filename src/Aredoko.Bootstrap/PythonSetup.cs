// Native first-stage preparation: no Python or modern .NET installation needed.
// Explicit developer/packaging CLI for now; normal bootstrap integration is pending.
using System;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using Microsoft.Win32.SafeHandles;

internal static class PythonSetup
{
    [StructLayout(LayoutKind.Sequential)] struct FileInformation { public uint Attributes; public System.Runtime.InteropServices.ComTypes.FILETIME Created,Access,Written; public uint Volume,SizeHigh,SizeLow,Links,IndexHigh,IndexLow; }
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetFileInformationByHandle(SafeFileHandle handle, out FileInformation information);

    static void SingleLink(FileStream stream)
    {
        FileInformation information;
        if(!GetFileInformationByHandle(stream.SafeFileHandle, out information) || information.Links != 1)
            throw new IOException("Hardlinked runtime files are not accepted.");
    }
    static volatile bool cancelled;
    const string Url = "https://api.nuget.org/v3-flatcontainer/python/3.13.17/python.3.13.17.nupkg";
    // NuGet catalog entry for Python Software Foundation's python 3.13.17.
    const string Hash = "DmZ5KLtPGVc8bNiPZRM7LgeyQ6XHFvM1tWqma7nsb4IyglbSLDop4joCdqxcam14YhH+q1JIkK0eVmKRlsaynA==";

    static int Main(string[] args)
    {
        try
        {
            Console.CancelKeyPress += delegate(object sender, ConsoleCancelEventArgs eventArgs) { eventArgs.Cancel = true; cancelled = true; };
            if(args.Length == 3 && args[0] == "--fetch") { Fetch(args[1], args[2]); return 0; }
            if(args.Length != 2 && !(args.Length == 3 && args[2] == "--verify")) throw new ArgumentException("Usage: PythonSetup.exe <output-directory> <package-or-download> [--verify]");
            Prepare(args[0], args[1], args.Length == 3);
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

    static void Fetch(string artifact, string destination)
    {
        CheckCancelled();
        string url, expected;
        bool python = artifact == "cpython";
        if(python) { url = Url; expected = Hash; }
        else if(artifact == "pillow")
        {
            url = "https://files.pythonhosted.org/packages/a6/9b/7a58e61d62be561da3a356fe2384d4059a6345fc130e23ef1c36a5b81d24/pillow-12.3.0-cp313-cp313-win_amd64.whl";
            expected = "1cca606cd25738df4ed873d5ad46bbdb3d83b5cbca291f6b4ff13a4df6b0bbe8";
        }
        else throw new ArgumentException("Unknown fixed artifact.");
        destination = Path.GetFullPath(destination);
        var parent = Path.GetDirectoryName(destination);
        DirectoryGuard(parent);
        if(File.Exists(destination) || Directory.Exists(destination)) throw new IOException("Artifact destination already exists.");
        var temporary = Path.Combine(parent, "artifact-" + Guid.NewGuid().ToString("N") + ".partial");
        Download(url, temporary);
        using(var input = new FileStream(temporary, FileMode.Open, FileAccess.Read, FileShare.Read))
        using(var sha = python ? (HashAlgorithm)SHA512.Create() : SHA256.Create())
        {
            SingleLink(input);
            var hash = sha.ComputeHash(input);
            var actual = python ? Convert.ToBase64String(hash) : BitConverter.ToString(hash).Replace("-", "").ToLowerInvariant();
            if(actual != expected) throw new IOException("Official artifact hash mismatch; not published.");
        }
        CheckCancelled();
        DirectoryGuard(parent);
        File.Move(temporary, destination);
        Console.WriteLine("Verified official artifact: " + artifact);
    }

    static void Download(string url, string destination)
    {
        CheckCancelled();
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
        var request = (HttpWebRequest)WebRequest.Create(url);
        request.AllowAutoRedirect = false;
        request.Timeout = 60000;
        request.ReadWriteTimeout = 60000;
        // The owner can cancel while GetResponse or a response read is blocked.
        using(var monitor = new Timer(delegate { if(CancellationRequested()) request.Abort(); }, null, 100, 100))
        {
            try
            {
                using(var response = (HttpWebResponse)request.GetResponse())
                {
                    if(response.StatusCode != HttpStatusCode.OK) throw new IOException("Unexpected package response.");
                    if(response.ContentLength > 128L * 1024 * 1024) throw new IOException("Package exceeds download limit.");
                    using(var input = response.GetResponseStream())
                    using(var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write))
                    {
                        var buffer = new byte[65536]; long total = 0; int count;
                        while((count = input.Read(buffer, 0, buffer.Length)) != 0)
                        {
                            CheckCancelled(); total += count;
                            if(total > 128L * 1024 * 1024) throw new IOException("Package exceeds download limit.");
                            output.Write(buffer, 0, count);
                        }
                    }
                }
            }
            catch(WebException) { CheckCancelled(); throw; }
            catch(IOException) { CheckCancelled(); throw; }
        }
        CheckCancelled();
    }

    static void Prepare(string destination, string package, bool verify)
    {
        CheckCancelled();
        destination = Path.GetFullPath(destination);
        var parent = Path.GetDirectoryName(destination);
        DirectoryGuard(parent);
        if(verify) DirectoryGuard(destination);
        else if(Directory.Exists(destination) || File.Exists(destination))
            throw new IOException("Refusing to overwrite an existing environment.");
        var stage = Path.Combine(parent, "python-stage-" + Guid.NewGuid().ToString("N"));
        if(!verify || package == "download") Directory.CreateDirectory(stage);
        // Failed staging is retained for diagnosis, never published as usable.
        var archive = Path.Combine(stage, "python.nupkg");
        if(package == "download")
        {
            Console.WriteLine("Downloading official CPython 3.13.17...");
            Download(Url, archive);
        }
        else
        {
            package = Path.GetFullPath(package);
            DirectoryGuard(Path.GetDirectoryName(package));
            if((File.GetAttributes(package) & FileAttributes.ReparsePoint) != 0) throw new IOException("Package links are not accepted.");
            if(verify) archive = package;
            else File.Copy(package, archive, false);
        }
        // Keep the exact bytes locked from verification through extraction.
        using(var input = new FileStream(archive, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            SingleLink(input);
            using(var sha = SHA512.Create())
                if(Convert.ToBase64String(sha.ComputeHash(input)) != Hash)
                    throw new IOException("Official package SHA512 mismatch. Environment not published.");
            input.Position = 0;
            var payload = Path.Combine(stage, "payload");
            if(!verify) Directory.CreateDirectory(payload);
            using(var zip = new ZipArchive(input, ZipArchiveMode.Read, true))
            {
                var expected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach(var entry in zip.Entries)
                {
                    CheckCancelled();
                    var name = entry.FullName.Replace('/', '\\');
                    if(name.Contains(":") || name.StartsWith("\\") || Array.Exists(name.Split('\\'), part => part == ".." || part == "."))
                        throw new IOException("Invalid package entry.");
                    var baseDirectory = verify ? destination : payload;
                    var output = Path.GetFullPath(Path.Combine(baseDirectory, name));
                    if(!output.StartsWith(baseDirectory + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                        throw new IOException("Package path escaped staging.");
                    if(verify)
                    {
                        if(name.EndsWith("\\")) { DirectoryGuard(output); continue; }
                        if(!expected.Add(output)) throw new IOException("Duplicate package file.");
                        DirectoryGuard(Path.GetDirectoryName(output));
                        if((File.GetAttributes(output) & (FileAttributes.ReparsePoint | FileAttributes.Directory)) != 0)
                            throw new IOException("Runtime file must be ordinary.");
                        using(var source = entry.Open())
                        using(var target = new FileStream(output, FileMode.Open, FileAccess.Read, FileShare.Read))
                        using(var sha = SHA256.Create())
                        {
                            SingleLink(target);
                            if(target.Length != entry.Length || Convert.ToBase64String(sha.ComputeHash(source)) != Convert.ToBase64String(sha.ComputeHash(target)))
                                throw new IOException("Runtime file changed: " + name);
                        }
                        continue;
                    }
                    if(name.EndsWith("\\")) { Directory.CreateDirectory(output); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(output));
                    using(var source = entry.Open())
                    using(var target = new FileStream(output, FileMode.CreateNew, FileAccess.Write))
                        source.CopyTo(target);
                }
                if(verify)
                {
                    VerifyInventory(destination, expected);
                    Console.WriteLine("Existing Python matches the verified official package.");
                    return;
                }
            }
            if(!File.Exists(Path.Combine(payload, "tools", "python.exe")) || !Directory.Exists(Path.Combine(payload, "tools", "Lib", "venv")))
                throw new IOException("Expected CPython/venv layout missing.");
            DirectoryGuard(parent);
            CheckCancelled();
            Directory.Move(payload, destination);
        }
        Console.WriteLine("Official package verified and extracted: " + destination);
        Console.WriteLine("AI dependencies and model compatibility have NOT been verified.");
    }

    static void VerifyInventory(string directory, HashSet<string> expected)
    {
        CheckCancelled();
        DirectoryGuard(directory);
        foreach(var child in Directory.GetFileSystemEntries(directory))
        {
            var attributes = File.GetAttributes(child);
            if((attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("Runtime contains a link.");
            if((attributes & FileAttributes.Directory) != 0) VerifyInventory(child, expected);
            else if(!expected.Contains(child)) throw new IOException("Unlisted runtime file: " + child);
        }
    }

    static bool CancellationRequested()
    {
        if(cancelled) return true;
        var marker = Environment.GetEnvironmentVariable("AREDOKO_SETUP_CANCEL");
        if(!String.IsNullOrEmpty(marker) && File.Exists(marker)) cancelled = true;
        return cancelled;
    }

    static void CheckCancelled()
    {
        if(CancellationRequested()) throw new OperationCanceledException("Python preparation cancelled; environment not published.");
    }
}
