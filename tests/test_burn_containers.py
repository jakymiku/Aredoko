"""Synthetic Burn headers only; no archive tools or selected code execution."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from burn_containers import containers


def bundle(*,original=True):
    data=bytearray(1408);data[:2]=b'MZ';struct.pack_into('<I',data,60,128)
    data[128:132]=b'PE\0\0';struct.pack_into('<H',data,134,1);struct.pack_into('<H',data,148,224)
    struct.pack_into('<H',data,152,0x10b);struct.pack_into('<I',data,152+92,16)
    struct.pack_into('<II',data,152+96+32,1344,64)
    data[376:384]=b'.wixburn';struct.pack_into('<II',data,392,512,512)
    struct.pack_into('<II',data,512,0xf14300,2)
    struct.pack_into('<6I',data,512+24,1024,0,1088 if original else 0,64 if original else 0,1,2)
    struct.pack_into('<2I',data,512+48,64,128)
    for at,size in ((1024,64),(1152 if original else 1408,128)):
        if at+size>len(data):data.extend(b'\0'*(at+size-len(data)))
        data[at:at+4]=b'MSCF';struct.pack_into('<I',data,at+8,size)
    return data


class BurnContainerTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.path=Path(temp.name)/'generated.exe'
    def read(self,data):self.path.write_bytes(data);return containers(self.path)
    def test_original_signature_defines_attached_start_not_final_signature(self):
        data=bundle();before=bytes(data)
        self.assertEqual(self.read(data),[{'index':0,'offset':1024,'bytes':64},{'index':1,'offset':1152,'bytes':128}])
        self.assertEqual(self.path.read_bytes(),before)
    def test_final_signature_fallback_is_bounded(self):
        # A non-original-signature engine places the attached CAB after its
        # signature; unlike a signed complete bundle the signature is in-engine.
        data=bundle(original=False)
        self.assertEqual(self.read(data)[1]['offset'],1408)
    def test_unsigned_stub_plus_ux_fallback(self):
        data=bundle();struct.pack_into('<II',data,152+96+32,0,0);struct.pack_into('<II',data,512+32,0,0)
        data[1088:1092]=b'MSCF';struct.pack_into('<I',data,1096,128)
        self.assertEqual(self.read(data)[1]['offset'],1088)
    def test_malformed_or_ambiguous_containers_are_rejected(self):
        changes=[(512,0),(516,3),(552,2),(556,117),(536,100),(560,0),(564,2**31),(1024,0),
                 (1032,63),(544,100),(548,0),(152+96+32,1100)]
        for offset,value in changes:
            with self.subTest(offset=offset,value=value):
                data=bundle();struct.pack_into('<I',data,offset,value)
                with self.assertRaises(ValueError):self.read(data)
        with self.assertRaises(ValueError):self.read(bundle()[:1200])


if __name__=='__main__':unittest.main()
