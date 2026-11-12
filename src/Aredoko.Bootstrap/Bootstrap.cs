// Built with the Windows-inbox .NET Framework compiler; no WinUI/Python load
// until this small Windows Forms/native-control window has been shown.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32.SafeHandles;

internal sealed class Bootstrap : Form
{
    const string Format="aredoko-startup-pipe-v1";
    readonly string session=Guid.NewGuid().ToString("N");
    readonly bool smoke;
    readonly Label stage=new Label(), count=new Label();
    readonly ProgressBar progress=new ProgressBar();
    readonly Button cancel=new Button(), logs=new Button();
    readonly object inputLock=new object();
    Stream input;
    bool helloSent;
    volatile bool cancelRequested, interactive, finished;
    volatile bool awaitingConsent;
    bool allowClose, failed;
    string logPath;
    string setupCancelPath;
    long lastFrame=Stopwatch.GetTimestamp();
    readonly System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer();
    readonly JavaScriptSerializer json=new JavaScriptSerializer { MaxJsonLength=4096, RecursionLimit=8 };

    [STAThread] static int Main(string[] args)
    {
        if(args.Length==1&&args[0]=="--self-test")
        {
            try
            {
                var p=new JavaScriptSerializer().DeserializeObject("{\"format\":\"aredoko-startup-progress-v1\",\"sequence\":1,\"stage\":\"file_hashes\",\"state\":\"running\",\"completed_files\":2,\"total_files\":4,\"completed_bytes\":10,\"total_bytes\":20}") as Dictionary<string,object>;
                if(ProgressText(p).Item3!=50)return 2;
                var download=SetupDownloadProgress("aredoko-download-progress 500000 1000000");
                if(download==null||download.Item2!=50||SetupDownloadProgress("aredoko-download-progress 1 0").Item2.HasValue)return 2;
                if(SetupDownloadProgress("aredoko-download-progress 20 10")!=null)return 2;
                try{Number(true);return 2;}catch(IOException){}
                try{ValidateKeys("{\"kind\":1,\"kind\":2}");return 2;}catch(IOException){}
                foreach(var invalid in new[]{null,"","relative","C:relative",@"\root-relative"})
                {try{LocalDataRoot(invalid);return 2;}catch(IOException){}}
                if(LocalDataRoot(Path.GetTempPath())!=Path.GetFullPath(Path.GetTempPath()))return 2;
                return 0;
            }catch{return 2;}
        }
        if(args.Length>1||(args.Length==1&&args[0]!="--startup-check"))return 2;
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        var form=new Bootstrap(args.Length==1);Application.Run(form);return form.failed?2:0;
    }
    Bootstrap(bool check)
    {
        smoke=check;Text=check?"Aredoko 起動チェック":"Aredoko";
        AutoScaleMode=AutoScaleMode.Dpi;ClientSize=new Size(470,230);
        FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;StartPosition=FormStartPosition.CenterScreen;
        Font=new Font("Yu Gothic UI",10);
        try{Icon=System.Drawing.Icon.ExtractAssociatedIcon(Application.ExecutablePath);}catch(Exception){}
        var heading=new Label { Text="Aredokoを起動しています",AutoSize=true,Location=new Point(24,20),Font=new Font(Font,FontStyle.Bold) };
        stage.SetBounds(24,58,420,36);stage.Text=check?"専用の空のライブラリで起動を確認します。":"準備が終わるまでお待ちください。";
        progress.SetBounds(24,104,420,16);progress.Style=ProgressBarStyle.Marquee;
        count.SetBounds(24,129,420,30);
        cancel.SetBounds(334,181,110,30);cancel.Text="キャンセル";
        logs.SetBounds(24,181,130,30);logs.Text="ログを開く";logs.Visible=false;
        Controls.AddRange(new Control[]{heading,stage,progress,count,cancel,logs});
        cancel.Click+=delegate { if(finished){allowClose=true;Close();}else CancelStartup(); };
        logs.Click+=delegate {try{if(logPath!=null&&File.Exists(logPath))Process.Start(new ProcessStartInfo(logPath){UseShellExecute=true});}catch(Exception){stage.Text="ログを開けませんでした。";} };
        FormClosing+=delegate(object sender,FormClosingEventArgs e){
            if(e.CloseReason==CloseReason.WindowsShutDown||e.CloseReason==CloseReason.TaskManagerClosing){allowClose=true;return;}
            if(!allowClose&&!finished){if(cancelRequested&&!interactive){allowClose=true;return;}e.Cancel=true;CancelStartup();}
        };
        // Rendering and the message pump precede all filesystem/runtime work.
        Shown+=delegate { Refresh();new Thread(Run){IsBackground=true,Name="Aredoko owner"}.Start(); };
        timer.Interval=1000;timer.Tick+=delegate {
            if(!finished&&!interactive&&!cancelRequested&&!awaitingConsent&&(Stopwatch.GetTimestamp()-lastFrame)/(double)Stopwatch.Frequency>180)
            {stage.Text="準備に時間がかかっています。終了処理を待っています。";CancelStartup();}
        };timer.Start();
    }
    void UI(Action action){try{if(!IsDisposed)BeginInvoke(action);}catch(InvalidOperationException){}}
    void CancelStartup()
    {
        if(interactive||cancelRequested)return;cancelRequested=true;
        cancel.Enabled=false;stage.Text="終了処理中です。しばらくお待ちください。";
        if(setupCancelPath!=null)
        {
            try { using(var marker=new FileStream(setupCancelPath,FileMode.CreateNew,FileAccess.Write,FileShare.Read)){} }
            catch(IOException error) { count.Text="取消通知を保存できませんでした: "+error.Message; }
        }
        new Thread(delegate(){try{Send("cancel");}catch(Exception){}}){IsBackground=true}.Start();
    }
    void Send(string command)
    {
        var bytes=Encoding.ASCII.GetBytes("{\"format\":\""+Format+"\",\"command\":\""+command+"\",\"session_id\":\""+session+"\"}\n");
        lock(inputLock){if(input!=null){if(command=="cancel"&&!helloSent)return;input.Write(bytes,0,bytes.Length);input.Flush();if(command=="hello")helloSent=true;}}
    }
    static string LocalDataRoot(string candidate)
    {
        // Match the Python owner. KnownFolder ignores a process-local override,
        // which otherwise scatters bootstrap logs outside that session's data.
        if(String.IsNullOrEmpty(candidate)||!Path.IsPathRooted(candidate)||Path.GetPathRoot(candidate).Length<3)
            throw new IOException("保存先を確認できません。");
        return Path.GetFullPath(candidate);
    }
    static void Ordinary(string path,bool directory)
    {
        path=Path.GetFullPath(path);var current=path;
        while(current!=null)
        {
            var attributes=File.GetAttributes(current);
            if((attributes&FileAttributes.ReparsePoint)!=0||((attributes&FileAttributes.Directory)!=0)!=(current!=path||directory))
                throw new IOException("リンクを含む配置は使用できません。");
            current=Path.GetDirectoryName(current);
        }
        if(!directory)
        {
            using(var file=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read))
            {Native.FileInfo info;if(!Native.GetFileInformationByHandle(file.SafeFileHandle,out info)||info.Links!=1)throw new IOException("通常のファイルを使用してください。");}
        }
    }

    static string ManagedDirectory(string parent,string name)
    {
        Ordinary(parent,true);
        var path=Path.Combine(parent,name);
        if(!Directory.Exists(path))Directory.CreateDirectory(path);
        Ordinary(path,true);return path;
    }

    static FileStream OpenVerifiedSetupHelper(string root,Dictionary<string,object> metadata)
    {
        const string relative="tools/PythonSetup.exe";
        const string invalid="基本環境の準備ファイルが配布情報と一致しません。ZIPを確認し、新しいフォルダに展開してください。";
        object value;
        var entries=metadata.TryGetValue("entries",out value)?value as System.Collections.IEnumerable:null;
        if(entries==null)throw new IOException(invalid);
        var matches=entries.OfType<Dictionary<string,object>>().Where(entry=>
        {
            object path;
            return entry.TryGetValue("path",out path)&&String.Equals(path as string,relative,StringComparison.OrdinalIgnoreCase);
        }).ToArray();
        object bytes, hash;
        if(matches.Length!=1||!matches[0].TryGetValue("bytes",out bytes)||!(bytes is int||bytes is long)
            ||!matches[0].TryGetValue("sha256",out hash)||!(hash is string))throw new IOException(invalid);

        var helper=Path.Combine(root,"tools","PythonSetup.exe");
        Ordinary(helper,false);
        var file=new FileStream(helper,FileMode.Open,FileAccess.Read,FileShare.Read);
        try
        {
            Native.FileInfo info;
            if(!Native.GetFileInformationByHandle(file.SafeFileHandle,out info)||info.Links!=1||(info.Attributes&0x400)!=0
                ||file.Length!=Convert.ToInt64(bytes))throw new IOException(invalid);
            using(var sha=SHA256.Create())
                if(BitConverter.ToString(sha.ComputeHash(file)).Replace("-","").ToLowerInvariant()!=(string)hash)
                    throw new IOException(invalid);
            return file;
        }
        catch{file.Dispose();throw;}
    }

    void SetupCommand(string executable,string arguments,string root,FileStream log,string operation)
    {
        if(cancelRequested)throw new OperationCanceledException();
        Ordinary(executable,false);
        UI(delegate {stage.Text=operation+"中です…";count.Text="処理が完了するまでお待ちください。";progress.Style=ProgressBarStyle.Marquee;});
        var downloading=arguments.StartsWith("--fetch ",StringComparison.Ordinal);
        using(var child=new Process())
        {
            child.StartInfo=new ProcessStartInfo(executable,arguments) {UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,WorkingDirectory=root};
            child.StartInfo.EnvironmentVariables.Remove("PYTHONHOME");child.StartInfo.EnvironmentVariables.Remove("PYTHONPATH");
            child.StartInfo.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"]="1";
            child.StartInfo.EnvironmentVariables["PYTHONUTF8"]="1";
            child.StartInfo.EnvironmentVariables["AREDOKO_SETUP_CANCEL"]=setupCancelPath;
            var logLock=new object();
            DataReceivedEventHandler record=delegate(object sender,DataReceivedEventArgs line) {
                if(line.Data==null)return;
                var download=downloading?SetupDownloadProgress(line.Data):null;
                if(download!=null)
                {
                    UI(delegate {
                        if(cancelRequested)return;
                        count.Text=download.Item1;
                        if(download.Item2.HasValue){progress.Style=ProgressBarStyle.Continuous;progress.Value=download.Item2.Value;}
                    });
                    return;
                }
                var bytes=Encoding.UTF8.GetBytes(line.Data+Environment.NewLine);
                lock(logLock){log.Write(bytes,0,bytes.Length);log.Flush();}
            };
            child.OutputDataReceived+=record;child.ErrorDataReceived+=record;
            child.Start();child.BeginOutputReadLine();child.BeginErrorReadLine();
            // Children poll the cancellation marker; do not terminate a venv
            // writer and then let another startup race its incomplete files.
            while(!child.WaitForExit(100))Interlocked.Exchange(ref lastFrame,Stopwatch.GetTimestamp());
            child.WaitForExit();
            if(cancelRequested)throw new OperationCanceledException();
            if(child.ExitCode!=0)throw new IOException(operation+"に失敗しました。ログを確認してください。");
        }
    }

    static Tuple<string,int?> SetupDownloadProgress(string line)
    {
        var fields=line.Split(' ');
        const long limit=128L*1024*1024;
        long received,total;
        if(fields.Length!=3||fields[0]!="aredoko-download-progress"
            ||!Int64.TryParse(fields[1],NumberStyles.None,CultureInfo.InvariantCulture,out received)
            ||!Int64.TryParse(fields[2],NumberStyles.None,CultureInfo.InvariantCulture,out total)
            ||received>limit||total>limit||total>0&&received>total)return null;
        var done=String.Format(CultureInfo.CurrentCulture,"{0:F1} MB",received/1000000.0);
        if(total==0)return Tuple.Create<string,int?>("取得済み "+done,null);
        var expected=String.Format(CultureInfo.CurrentCulture,"{0:F1} MB",total/1000000.0);
        return Tuple.Create<string,int?>("取得済み "+done+" / "+expected,(int)(received*100/total));
    }

    string EnsurePython(string root,string local,FileStream log)
    {
        var bundled=Path.Combine(root,"runtime","python","python.exe");
        var manifest=Path.Combine(root,"manifest.json");Ordinary(manifest,false);
        if(new FileInfo(manifest).Length>32*1024*1024)throw new IOException("配布情報が大きすぎます。");
        var metadata=new JavaScriptSerializer {MaxJsonLength=32*1024*1024}.DeserializeObject(File.ReadAllText(manifest,Encoding.UTF8)) as Dictionary<string,object>;
        const string identifier="cpython-3.13.17-pillow-12.3.0-win-x64-v1";
        if(metadata!=null&&!metadata.ContainsKey("managed_python")) {Ordinary(bundled,false);return bundled;}
        if(metadata==null||!metadata.ContainsKey("managed_python")||!Equals(metadata["managed_python"],identifier)
            ||!metadata.ContainsKey("python_bundled")||!Equals(metadata["python_bundled"],false)
            ||!metadata.ContainsKey("frontend_activation")||!Equals(metadata["frontend_activation"],"portable")
            ||!metadata.ContainsKey("media_tools_bundled")||!Equals(metadata["media_tools_bundled"],true)
            ||!metadata.ContainsKey("ai_runtime_bundled")||!Equals(metadata["ai_runtime_bundled"],false))
            throw new IOException("同梱Pythonが見つかりません。配布物を確認してください。");
        if(Directory.Exists(Path.Combine(root,"runtime","python")))
            throw new IOException("Python非同梱版に予期しないPythonフォルダがあります。別の新規フォルダへ展開してください。");
        // The native helper runs before the Python owner's full release preflight.
        using(var verifiedHelper=OpenVerifiedSetupHelper(root,metadata))
            return EnsureManagedPython(root,local,log,identifier,verifiedHelper.Name);
    }

    string EnsureManagedPython(string root,string local,FileStream log,string identifier,string helper)
    {
        var app=ManagedDirectory(local,"Aredoko");
        var artifacts=ManagedDirectory(app,"runtime-artifacts");var runtimes=ManagedDirectory(app,"runtimes");
        var package=Path.Combine(artifacts,"python.3.13.17.nupkg");
        var wheel=Path.Combine(artifacts,"pillow-12.3.0-cp313-cp313-win_amd64.whl");
        var basePython=Path.Combine(runtimes,"cpython-3.13.17");var environment=Path.Combine(runtimes,identifier);
        setupCancelPath=Path.Combine(app,"logs","setup-cancel-"+session);
        // One owner for this shared setup location. Existing backend data and
        // working environments are not deleted or overwritten.
        var lease=Path.Combine(app,"runtime-setup.owner.lock");
        if(File.Exists(lease))Ordinary(lease,false);
        using(var owner=new FileStream(lease,FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None))
        {
            Native.FileInfo ownerInfo;
            if(!Native.GetFileInformationByHandle(owner.SafeFileHandle,out ownerInfo)||ownerInfo.Links!=1||(ownerInfo.Attributes&0x400)!=0)
                throw new IOException("基本環境の保存先を確認できません。");
            if(cancelRequested)throw new OperationCanceledException();
            if(!File.Exists(package)||!File.Exists(wheel))
            {
                if(smoke)throw new IOException("基本環境が未導入です。通常のAredoko.exeから準備してください。");
                DialogResult choice=DialogResult.Cancel;
                awaitingConsent=true;
                Invoke((Action)delegate { choice=MessageBox.Show(this,"Aredokoの基本機能に必要なPython 3.13.17とPillow 12.3.0を公式配布元から取得します。\n取得は約22MBです。展開・構築用に300MB以上の空き容量を推奨します。\nアプリ専用領域へ保存し、システムのPythonやPATHは変更しません。\nAI環境・モデルはここでは取得しません。\n\n準備を開始しますか？","Aredoko 初回準備",MessageBoxButtons.OKCancel,MessageBoxIcon.Information); });
                awaitingConsent=false;
                Interlocked.Exchange(ref lastFrame,Stopwatch.GetTimestamp());
                if(choice!=DialogResult.OK)throw new OperationCanceledException();
            }
            if(!File.Exists(package))SetupCommand(helper,"--fetch cpython \""+package+"\"",root,log,"Pythonの取得");
            if(!File.Exists(wheel))SetupCommand(helper,"--fetch pillow \""+wheel+"\"",root,log,"画像処理ライブラリの取得");
            SetupCommand(helper,"\""+basePython+"\" \""+package+"\""+(Directory.Exists(basePython)?" --verify":""),root,log,"Pythonの検証と配置");
            var script=Path.Combine(root,"tools","prepare_basic_runtime.py");Ordinary(script,false);
            SetupCommand(Path.Combine(basePython,"tools","python.exe"),"-I -X utf8 -B \""+script+"\" --wheel \""+wheel+"\" --output \""+environment+"\""+(Directory.Exists(environment)?" --verify":""),root,log,"基本環境の構築・確認");
        }
        return Path.Combine(environment,"Scripts","python.exe");
    }
    void Run()
    {
        IntPtr process=IntPtr.Zero;
        try
        {
            var root=Path.GetDirectoryName(Application.ExecutablePath);
            Ordinary(Application.ExecutablePath,false);
            // Console-subsystem python.exe initializes valid redirected stdio.
            // CREATE_NO_WINDOW keeps it console-free; pythonw may expose None streams.
            var python=Path.Combine(root,"runtime","python","python.exe");
            var script=Path.Combine(root,"tools","launch_release.py");
            Ordinary(script,false);
            var local=LocalDataRoot(Environment.GetEnvironmentVariable("LOCALAPPDATA"));
            Ordinary(local,true);
            var logDirectory=Path.Combine(local,"Aredoko","logs");
            // Validate each ancestor before creating a child. Never follow a junction.
            var appDirectory=Path.Combine(local,"Aredoko");
            if(!Directory.Exists(appDirectory))Directory.CreateDirectory(appDirectory);Ordinary(appDirectory,true);
            if(!Directory.Exists(logDirectory))Directory.CreateDirectory(logDirectory);Ordinary(logDirectory,true);
            logPath=Path.Combine(logDirectory,"startup-"+session+".log");
            using(var log=new FileStream(logPath,FileMode.CreateNew,FileAccess.Write,FileShare.Read))
            {
                Native.FileInfo logInfo;if(!Native.GetFileInformationByHandle(log.SafeFileHandle,out logInfo)||logInfo.Links!=1)throw new IOException("ログの保存先を確認できません。");
                python=EnsurePython(root,local,log);Ordinary(python,false);log.Flush();
                Stream output;
                process=Native.Start(python,"\""+python+"\" -I -X utf8 -B -u \""+script+"\" "+(smoke?"--startup-smoke":"--startup-owned"),root,log.SafeFileHandle.DangerousGetHandle(),out input,out output);
                bool resultSeen=false, helloSeen=false;
                Send("hello");if(cancelRequested)Send("cancel");
                using(output)
                {
                    while(true)
                    {
                        string frame=ReadFrame(output);if(frame==null)break;
                        Interlocked.Exchange(ref lastFrame,Stopwatch.GetTimestamp());
                        ValidateKeys(frame);
                        var value=json.DeserializeObject(frame) as Dictionary<string,object>;
                        if(value==null||!value.ContainsKey("kind")||!value.ContainsKey("format")||!value.ContainsKey("session_id")
                            ||!Equals(value["format"],Format)||!Equals(value["session_id"],session))throw new IOException("起動通知を確認できません。");
                        string kind=value["kind"] as string;
                        if(kind=="hello"&&value.Count==3&&!helloSeen){helloSeen=true;continue;}
                        if(!helloSeen||resultSeen)throw new IOException("起動通知の順序を確認できません。");
                        if(kind=="progress"&&value.Count==4&&!interactive)
                        {
                            var snapshot=value["progress"] as Dictionary<string,object>;
                            var update=ProgressText(snapshot);UI(delegate { if(!cancelRequested){stage.Text=update.Item1;count.Text=update.Item2;progress.Style=update.Item3<0?ProgressBarStyle.Marquee:ProgressBarStyle.Continuous;if(update.Item3>=0)progress.Value=update.Item3;} });
                        }
                        else if(kind=="app_ready"&&value.Count==3&&!interactive)
                        {interactive=true;UI(delegate {Hide();});}
                        else if(kind=="result"&&value.Count==5)
                        {
                            resultSeen=true;
                            string status=value["status"] as string;
                            if(status=="session_complete"&&interactive){}
                            else if(status=="cancelled"&&!interactive)cancelRequested=true;
                            else throw new IOException("起動を完了できませんでした。");
                        }
                        else throw new IOException("起動通知を確認できません。");
                    }
                }
                // Retained HANDLE proves this exact child. No PID/name search.
                if(Native.WaitForSingleObject(process,30000)!=0)throw new IOException("終了処理を待っています。ログを確認してください。");
                uint exitCode;if(!Native.GetExitCodeProcess(process,out exitCode)||(!cancelRequested&&exitCode!=0)||!resultSeen)
                    throw new IOException("起動を完了できませんでした。");
            }
            finished=true;UI(delegate {allowClose=true;Close();});
        }
        catch(OperationCanceledException)
        {
            finished=true;UI(delegate {allowClose=true;Close();});
        }
        catch(Exception error)
        {
            failed=true;finished=true;
            // Closing only our pipe requests cooperative cleanup before ready.
            lock(inputLock){if(input!=null){input.Dispose();input=null;}}
            UI(delegate {Show();count.Text="停止した処理: "+stage.Text;stage.Text=error is IOException?error.Message:"起動を完了できませんでした（"+error.Message+"）。";progress.Style=ProgressBarStyle.Continuous;progress.Value=0;cancel.Enabled=true;cancel.Text="閉じる";logs.Visible=logPath!=null&&File.Exists(logPath);});
        }
        finally
        {
            lock(inputLock){if(input!=null){input.Dispose();input=null;}}
            if(process!=IntPtr.Zero)Native.CloseHandle(process);
        }
    }
    static string ReadFrame(Stream stream)
    {
        var bytes=new List<byte>();int value;
        while((value=stream.ReadByte())!=-1){bytes.Add((byte)value);if(bytes.Count>4096)throw new IOException("起動通知が長すぎます。");if(value==10)return new UTF8Encoding(false,true).GetString(bytes.ToArray());}
        if(bytes.Count!=0)throw new IOException("起動通知が途切れました。");return null;
    }
    static void ValidateKeys(string frame)
    {
        // JavaScriptSerializer alone accepts duplicate keys. Check object scopes
        // before deserializing; protocol keys are deliberately plain ASCII.
        var scopes=new Stack<HashSet<string>>();
        for(int i=0;i<frame.Length;i++)
        {
            if(frame[i]=='{'){scopes.Push(new HashSet<string>());if(scopes.Count>8)throw new IOException("起動通知が深すぎます。");}
            else if(frame[i]=='}'){if(scopes.Count==0)throw new IOException("起動通知を確認できません。");scopes.Pop();}
            else if(frame[i]=='['||frame[i]==']')throw new IOException("起動通知を確認できません。");
            else if(frame[i]=='"')
            {
                int start=++i;bool escaped=false;
                for(;i<frame.Length&&frame[i]!='"';i++)if(frame[i]=='\\'){escaped=true;i++;}
                if(i>=frame.Length)throw new IOException("起動通知が途切れました。");
                int next=i+1;while(next<frame.Length&&Char.IsWhiteSpace(frame[next]))next++;
                if(next<frame.Length&&frame[next]==':')
                {if(escaped||scopes.Count==0||!scopes.Peek().Add(frame.Substring(start,i-start)))throw new IOException("起動通知の項目が重複しています。");}
            }
        }
        if(scopes.Count!=0)throw new IOException("起動通知が途切れました。");
    }
    static long Number(object value)
    {
        if(!(value is int)&&!(value is long))throw new IOException("進捗の数値を確認できません。");
        long result=Convert.ToInt64(value);if(result<0)throw new IOException("進捗の数値を確認できません。");return result;
    }
    static Tuple<string,string,int> ProgressText(Dictionary<string,object> p)
    {
        string[] keys={"format","sequence","stage","state","completed_files","total_files","completed_bytes","total_bytes"};
        if(p==null||p.Count!=8||keys.Any(k=>!p.ContainsKey(k))||!Equals(p["format"],"aredoko-startup-progress-v1")||Number(p["sequence"])<1)
            throw new IOException("進捗を確認できません。");
        var labels=new Dictionary<string,string>{{"manifest","アプリのファイルを確認しています"},{"file_hashes","アプリのファイルを確認しています"},{"inventory","ファイルの配置を確認しています"},{"runtime_layout","実行環境を準備しています"},{"python_imports","実行環境を準備しています"},{"media_probe","動画の実行環境を確認しています"},{"backend_start","検索の準備をしています"},{"frontend_start","画面を開いています"}};
        string name=p["stage"] as string,state=p["state"] as string;
        if(name==null||!labels.ContainsKey(name)||!new[]{"running","complete","failed","cancelled"}.Contains(state))throw new IOException("処理段階を確認できません。");
        long files=Number(p["completed_files"]),bytes=Number(p["completed_bytes"]);
        long? total=p["total_files"]==null?(long?)null:Number(p["total_files"]),totalBytes=p["total_bytes"]==null?(long?)null:Number(p["total_bytes"]);
        if((total.HasValue&&files>total.Value)||(totalBytes.HasValue&&bytes>totalBytes.Value))throw new IOException("進捗の範囲を確認できません。");
        string text=total.HasValue?String.Format("ファイルの確認 {0:N0} / {1:N0}　{2:N1} MiB",files,total.Value,bytes/1048576.0):"";
        int percent=total.HasValue&&total.Value>0?(int)Math.Min(100,files/(double)total.Value*100):-1;
        return Tuple.Create(labels[name],text,percent);
    }

    static class Native
    {
        [StructLayout(LayoutKind.Sequential)] internal struct FileInfo {public uint Attributes;public System.Runtime.InteropServices.ComTypes.FILETIME Created,Access,Written;public uint Volume,SizeHigh,SizeLow,Links,IndexHigh,IndexLow;}
        [StructLayout(LayoutKind.Sequential)] struct Security {public int Size;public IntPtr Descriptor;[MarshalAs(UnmanagedType.Bool)]public bool Inherit;}
        [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Startup {public int Size;public string Reserved,Desktop,Title;public uint X,Y,Width,Height,XChars,YChars,Fill,Flags;public short Show,ReservedSize;public IntPtr ReservedPtr,In,Out,Error;}
        [StructLayout(LayoutKind.Sequential)] struct Extended {public Startup Info;public IntPtr Attributes;}
        [StructLayout(LayoutKind.Sequential)] struct ProcessInfo {public IntPtr Process,Thread;public uint Id,ThreadId;}
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool CreatePipe(out IntPtr read,out IntPtr write,ref Security security,uint size);
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool SetHandleInformation(IntPtr handle,uint mask,uint flags);
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,int flags,ref IntPtr size);
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,IntPtr attribute,IntPtr value,IntPtr size,IntPtr previous,IntPtr returned);
        [DllImport("kernel32.dll")]static extern void DeleteProcThreadAttributeList(IntPtr list);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool CreateProcessW(string app,StringBuilder command,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr environment,string cwd,ref Extended startup,out ProcessInfo info);
        [DllImport("kernel32.dll",SetLastError=true)]internal static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32.dll",SetLastError=true)]internal static extern uint WaitForSingleObject(IntPtr process,uint milliseconds);
        [DllImport("kernel32.dll",SetLastError=true)]internal static extern bool GetExitCodeProcess(IntPtr process,out uint code);
        [DllImport("kernel32.dll",SetLastError=true)]internal static extern bool GetFileInformationByHandle(SafeFileHandle handle,out FileInfo info);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool QueryFullProcessImageNameW(IntPtr process,uint flags,StringBuilder image,ref uint size);
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetProcessTimes(IntPtr process,out System.Runtime.InteropServices.ComTypes.FILETIME creation,out System.Runtime.InteropServices.ComTypes.FILETIME exit,out System.Runtime.InteropServices.ComTypes.FILETIME kernel,out System.Runtime.InteropServices.ComTypes.FILETIME user);
        static void Check(bool success){if(!success)throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());}
        internal static IntPtr Start(string exe,string command,string cwd,IntPtr stderr,out Stream input,out Stream output)
        {
            input=output=null;var security=new Security{Size=Marshal.SizeOf(typeof(Security)),Inherit=true};
            IntPtr childIn=IntPtr.Zero,parentIn=IntPtr.Zero,parentOut=IntPtr.Zero,childOut=IntPtr.Zero,list=IntPtr.Zero,handles=IntPtr.Zero;
            ProcessInfo pi=new ProcessInfo();bool initialized=false;
            try
            {
                Check(CreatePipe(out childIn,out parentIn,ref security,0));Check(CreatePipe(out parentOut,out childOut,ref security,0));
                Check(SetHandleInformation(parentIn,1,0));Check(SetHandleInformation(parentOut,1,0));Check(SetHandleInformation(stderr,1,1));
                IntPtr size=IntPtr.Zero;InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref size);
                if(size==IntPtr.Zero)throw new IOException("起動情報を準備できません。");
                list=Marshal.AllocHGlobal(size);Check(InitializeProcThreadAttributeList(list,1,0,ref size));initialized=true;
                handles=Marshal.AllocHGlobal(IntPtr.Size*3);Marshal.WriteIntPtr(handles,0,childIn);Marshal.WriteIntPtr(handles,IntPtr.Size,childOut);Marshal.WriteIntPtr(handles,IntPtr.Size*2,stderr);
                Check(UpdateProcThreadAttribute(list,0,new IntPtr(0x20002),handles,new IntPtr(IntPtr.Size*3),IntPtr.Zero,IntPtr.Zero));
                var start=new Extended{Info=new Startup{Size=Marshal.SizeOf(typeof(Extended)),Flags=0x100,In=childIn,Out=childOut,Error=stderr},Attributes=list};
                long started=DateTime.UtcNow.ToFileTimeUtc();
                Check(CreateProcessW(exe,new StringBuilder(command),IntPtr.Zero,IntPtr.Zero,true,0x08080000,IntPtr.Zero,cwd,ref start,out pi));
                // Retain the creation handle and prove its path and creation time.
                var image=new StringBuilder(32768);uint count=32768;Check(QueryFullProcessImageNameW(pi.Process,0,image,ref count));
                System.Runtime.InteropServices.ComTypes.FILETIME created,ended,kernel,user;Check(GetProcessTimes(pi.Process,out created,out ended,out kernel,out user));
                long time=((long)(uint)created.dwHighDateTime<<32)|(uint)created.dwLowDateTime;
                if(time<started||!String.Equals(Path.GetFullPath(image.ToString()),Path.GetFullPath(exe),StringComparison.OrdinalIgnoreCase))throw new IOException("起動した実行環境を確認できません。");
                input=new FileStream(new SafeFileHandle(parentIn,true),FileAccess.Write);parentIn=IntPtr.Zero;
                output=new FileStream(new SafeFileHandle(parentOut,true),FileAccess.Read);parentOut=IntPtr.Zero;
                var result=pi.Process;pi.Process=IntPtr.Zero;return result;
            }
            finally
            {
                if(pi.Thread!=IntPtr.Zero)CloseHandle(pi.Thread);if(pi.Process!=IntPtr.Zero)CloseHandle(pi.Process);
                foreach(var h in new[]{childIn,childOut,parentIn,parentOut})if(h!=IntPtr.Zero)CloseHandle(h);
                SetHandleInformation(stderr,1,0);
                if(initialized)DeleteProcThreadAttributeList(list);if(list!=IntPtr.Zero)Marshal.FreeHGlobal(list);if(handles!=IntPtr.Zero)Marshal.FreeHGlobal(handles);
            }
        }
    }
}
