"""Real >512 MiB logical MP4, tiny sparse allocation; no model or user media."""
import ctypes
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_video_window_decode as fixture
from production import ProductionCatalog
from previews import PreviewReader


class LargeVideoSourceTests(unittest.TestCase):
    def test_guarded_representative_frames_accept_a_large_seekable_sparse_mp4(self):
        fixture.VideoWindowTests.setUpClass()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                base=Path(temporary);media=base/'media';media.mkdir();source=media/'generated-large.mp4'
                shutil.copyfile(fixture.VideoWindowTests.path,source)
                target=528*1024*1024
                with source.open('r+b') as output:
                    if os.name=='nt':
                        import msvcrt
                        from ctypes import wintypes
                        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
                        kernel.DeviceIoControl.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
                        kernel.DeviceIoControl.restype=wintypes.BOOL
                        returned=wintypes.DWORD()
                        # Mark only this generated file sparse before extending
                        # it; this changes no volume or system configuration.
                        if not kernel.DeviceIoControl(msvcrt.get_osfhandle(output.fileno()),0x900C4,None,0,None,0,ctypes.byref(returned),None):
                            self.skipTest('Generated sparse file unsupported on this filesystem')
                    output.seek(0,2);remaining=target-output.tell()
                    output.write(struct.pack('>I4s',remaining,b'free'))
                    output.seek(target-1);output.write(b'\0')
                if os.name=='nt':
                    high=wintypes.DWORD();kernel.GetCompressedFileSizeW.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(wintypes.DWORD)]
                    kernel.GetCompressedFileSizeW.restype=wintypes.DWORD
                    low=kernel.GetCompressedFileSizeW(str(source),ctypes.byref(high))
                    self.assertLess((high.value<<32)|low,1024*1024)
                before=(source.stat().st_size,source.stat().st_mtime_ns)
                catalog=ProductionCatalog(base/'catalog.sqlite')
                try:
                    root=catalog.add_root(str(media));catalog.index.scan(root);catalog.sync_index()
                    item=catalog.search()['items'][0]['id']
                    frames=PreviewReader(catalog).video_representative_frames(item)
                    self.assertEqual(len(frames),4)
                    self.assertTrue(all(0<=at<3300 and data.startswith(b'\x89PNG') for at,data in frames))
                    self.assertEqual((source.stat().st_size,source.stat().st_mtime_ns),before)
                finally:catalog.close()
        finally:fixture.VideoWindowTests.tearDownClass()


if __name__=='__main__':unittest.main()
