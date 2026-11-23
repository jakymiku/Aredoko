"""Generated pixels + fake sessions only; run with existing .venv-ai Python."""
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from tagger_profile import WDProfile,load_profile
from tagger_worker import prepare_image,infer
import numpy as np
from PIL import Image


def image_bytes(image,format='PNG',**kwargs):
    out=io.BytesIO();image.save(out,format=format,**kwargs);return out.getvalue()


class PreprocessTests(unittest.TestCase):
    def test_shape_dtype_bgr_range_and_transparency(self):
        data=image_bytes(Image.new('RGB',(10,10),(255,0,0)))
        array=prepare_image(data,448)
        self.assertEqual(array.shape,(1,448,448,3))
        self.assertEqual(array.dtype,np.float32)
        self.assertTrue(array.flags['C_CONTIGUOUS'])
        np.testing.assert_array_equal(array[0,224,224],[0,0,255])
        data=image_bytes(Image.new('RGBA',(5,3),(255,0,0,0)))
        self.assertTrue(np.all(prepare_image(data,448)==255))

    def test_white_square_padding_and_exif_orientation(self):
        image=Image.new('RGB',(8,4),(0,0,255))
        array=prepare_image(image_bytes(image),448)
        np.testing.assert_array_equal(array[0,0,224],[255,255,255])
        np.testing.assert_array_equal(array[0,224,224],[255,0,0])
        image=Image.new('RGB',(40,20),(0,0,255))
        image.paste((255,0,0),(0,0,20,20))
        exif=Image.Exif();exif[274]=6
        array=prepare_image(image_bytes(image,'JPEG',exif=exif,quality=100),448)
        self.assertGreater(array[0,100,224,2],240) # clockwise orientation => red top
        self.assertGreater(array[0,340,224,0],240) # blue bottom

    def test_corrupt_byte_and_pixel_limits(self):
        for data in (b'',b'not an image',b'x'*(8*1024**2+1)):
            with self.assertRaises((ValueError,OSError)):prepare_image(data,448)
        oversized=SimpleNamespace(width=5000,height=5000)
        oversized.__enter__=lambda:oversized
        class Opened:
            def __enter__(self):return oversized
            def __exit__(self,*args):pass
        with patch('PIL.Image.open',return_value=Opened()):
            with self.assertRaisesRegex(ValueError,'pixel limit'):prepare_image(b'x',448)

    def test_session_signature_and_output_validation(self):
        config=load_profile(ROOT).data();config['label_count']=3
        profile=WDProfile.from_dict(config)
        input=SimpleNamespace(name='input',type='tensor(float)',shape=['batch',448,448,3])
        output=SimpleNamespace(name='output',shape=['batch',3])
        session=SimpleNamespace(get_inputs=lambda:[input],get_outputs=lambda:[output],
                                run=lambda names,feeds:[np.array([[.1,.5,.9]],dtype=np.float32)])
        data=image_bytes(Image.new('RGB',(3,3)))
        self.assertEqual(len(infer(session,data,profile)),3)
        for scores in (np.array([[np.nan,.5,.6]]),np.array([[1.1,0,0]]),np.array([[0,0]])):
            session.run=lambda names,feeds:[scores]
            with self.assertRaises(ValueError):infer(session,data,profile)
        input.shape=['batch',3,448,448]
        with self.assertRaisesRegex(ValueError,'signature'):infer(session,data,profile)


if __name__=='__main__':unittest.main(verbosity=2)
