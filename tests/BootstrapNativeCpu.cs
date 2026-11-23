using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;

// Load the actual bootstrap and exercise its private Win32 pipe/process owner.
// No Form is constructed, no app/backend/model is launched.
class BootstrapNativeCpu
{
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr process,uint milliseconds);
    [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr process,out uint code);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr handle,uint code);
    static int Main(string[] args)
    {
        if(args.Length!=3)return 2;
        IntPtr owned=IntPtr.Zero;Stream input=null,output=null;
        try
        {
            var assembly=Assembly.LoadFrom(Path.GetFullPath(args[0]));
            var native=assembly.GetType("Bootstrap",true).GetNestedType("Native",BindingFlags.NonPublic);
            var start=native.GetMethod("Start",BindingFlags.Static|BindingFlags.NonPublic);
            var python=Path.GetFullPath(args[1]);
            string command="\""+python+"\" -I -X utf8 -B -u -c \"import sys;line=sys.stdin.buffer.readline();sys.stdout.buffer.write(line);sys.stdout.buffer.flush()\"";
            using(var log=new FileStream(args[2],FileMode.CreateNew,FileAccess.Write,FileShare.Read))
            {
                var values=new object[]{python,command,Path.GetDirectoryName(Path.GetFullPath(args[0])),log.SafeFileHandle.DangerousGetHandle(),null,null};
                owned=(IntPtr)start.Invoke(null,values);input=(Stream)values[4];output=(Stream)values[5];
                byte[] expected=Encoding.UTF8.GetBytes("generated 日本語 pipe check\n");
                input.Write(expected,0,expected.Length);input.Flush();input.Dispose();input=null;
                var read=Task.Run(delegate {using(var reader=new StreamReader(output,new UTF8Encoding(false,true)))return reader.ReadLine();});
                if(!read.Wait(5000)||read.Result!="generated 日本語 pipe check")throw new IOException("Owned inherited pipe roundtrip failed");
                output=null;
                uint code;if(WaitForSingleObject(owned,5000)!=0||!GetExitCodeProcess(owned,out code)||code!=0)throw new IOException("Owned child did not exit normally");
                Console.WriteLine("PASS actual bootstrap handle-list inheritance, retained child identity, UTF8 roundtrip and normal exit; GUI not created");
            }
            return 0;
        }
        catch(Exception error){Console.Error.WriteLine(error);return 2;}
        finally
        {
            if(input!=null)input.Dispose();
            if(owned!=IntPtr.Zero){if(WaitForSingleObject(owned,5000)!=0){TerminateProcess(owned,2);WaitForSingleObject(owned,5000);}CloseHandle(owned);}
            if(output!=null)output.Dispose();
        }
    }
}
