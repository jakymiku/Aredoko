using System.Runtime.InteropServices;

namespace Aredoko_WinUI;

// Shell item IDs avoid Explorer command-line parsing of spaces, commas and ZIPs.
internal static class ShellReveal
{
    [DllImport("shell32.dll",CharSet=CharSet.Unicode,ExactSpelling=true)]
    private static extern int SHParseDisplayName(string name,IntPtr bindContext,out IntPtr item,uint attributes,out uint result);
    [DllImport("shell32.dll",ExactSpelling=true)]
    private static extern int SHOpenFolderAndSelectItems(IntPtr item,uint count,IntPtr children,uint flags);
    public static void SelectFile(string path)
    {
        IntPtr item=IntPtr.Zero;
        try
        {
            Marshal.ThrowExceptionForHR(SHParseDisplayName(path,IntPtr.Zero,out item,0,out _));
            // With count=0 the API opens the item's parent and selects the item.
            Marshal.ThrowExceptionForHR(SHOpenFolderAndSelectItems(item,0,IntPtr.Zero,0));
        }
        finally {if(item!=IntPtr.Zero)Marshal.FreeCoTaskMem(item);}
    }
}
