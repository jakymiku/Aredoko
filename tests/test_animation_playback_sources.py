"""Generated APNG/GIF regressions, no GUI, model loading or source mutation."""
import io
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from image_animations import AnimationInspector
from PIL import Image


class AnimationPlaybackSources(unittest.TestCase):
    def apng(self,poster):
        red=Image.new('RGBA',(32,24),(255,0,0,255))
        blue=Image.new('RGBA',(32,24),(0,0,255,255))
        output=io.BytesIO()
        if poster:
            Image.new('RGBA',(32,24),(0,0,0,255)).save(output,format='PNG',save_all=True,
                append_images=[red,blue],default_image=True,duration=[80,120],loop=2)
        else:red.save(output,format='PNG',save_all=True,append_images=[blue],duration=[80,120],loop=2)
        return output.getvalue()

    def verify(self,poster):
        data=self.apng(poster);inspector=AnimationInspector();revision=('a' if poster else 'b')*64
        manifest=inspector.inspect(io.BytesIO(data),len(data),revision,7,'image/png')
        self.assertTrue(manifest['animated']);self.assertEqual(manifest['frame_count'],2)
        self.assertEqual(manifest['durations_ms'],[80,120]);self.assertEqual(manifest['loop_count'],2)
        for frame,color in ((0,(255,0,0,255)),(1,(0,0,255,255))):
            rendered=inspector.render_frame(io.BytesIO(data),len(data),revision,frame)
            with Image.open(io.BytesIO(rendered)) as image:self.assertEqual(image.getpixel((16,12)),color)
        with self.assertRaises(ValueError):inspector.render_frame(io.BytesIO(data),len(data),revision,2)
        self.assertEqual(data,self.apng(poster))

    def test_apng_poster_is_excluded_from_loop_and_frame_numbers(self):self.verify(True)
    def test_apng_without_poster_keeps_first_real_frame(self):self.verify(False)

    def test_gif_and_static_frames_keep_existing_contract(self):
        out=io.BytesIO();Image.new('RGB',(32,24),'red').save(out,format='GIF',save_all=True,
            append_images=[Image.new('RGB',(32,24),'blue')],duration=[80,120],loop=0)
        data=out.getvalue();inspector=AnimationInspector()
        result=inspector.inspect(io.BytesIO(data),len(data),'c'*64,8,'image/gif')
        self.assertEqual(result['frame_count'],2);self.assertEqual(result['durations_ms'],[80,120])
        self.assertEqual(result['loop_count'],0)
        for frame,color in ((0,(255,0,0,255)),(1,(0,0,255,255))):
            with Image.open(io.BytesIO(inspector.render_frame(io.BytesIO(data),len(data),'c'*64,frame))) as image:
                self.assertEqual(image.getpixel((16,12)),color)


if __name__=='__main__':unittest.main()
