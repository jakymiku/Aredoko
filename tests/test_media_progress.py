"""Display labels do not change source files or disclose parent paths."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from media_progress import item_title


class MediaProgressTests(unittest.TestCase):
    def test_basename_only_and_unicode_name_preserved(self):
        self.assertEqual(item_title('C:\\private\\録音.wav'),'録音.wav')
        self.assertEqual(item_title('/private/video.mp4'),'video.mp4')
        self.assertEqual(item_title('夜の空と星🌟.mkv'),'夜の空と星🌟.mkv')

    def test_controls_empty_and_long_labels_are_bounded(self):
        self.assertEqual(item_title('a\n\tb.wav'),'a  b.wav')
        self.assertEqual(item_title(None),'');self.assertEqual(item_title('  '),'')
        emoji=item_title('🌟'*160+'.mp4');self.assertLessEqual(len(emoji.encode('utf-16-le'))//2,160);self.assertTrue(emoji.endswith('…'))
        label=item_title('長'*300+'.mp4');self.assertEqual(len(label),160);self.assertTrue(label.endswith('…'))


    def test_two_item_job_reports_each_basename_and_clears_after_commit(self):
        import test_audio_direct_jobs as audio_fixture
        import test_video_direct_jobs as video_fixture
        from unittest.mock import patch
        for kind,fixture in (('audio',audio_fixture.DirectAudioJobTests),('video',video_fixture.DirectVideoJobTests)):
            with self.subTest(kind=kind):
                case=fixture('runTest');case.setUp();self.addCleanup(case.doCleanups)
                second=case.media/('second'+case.path.suffix);second.write_bytes(case.path.read_bytes())
                case.catalog.index.scan(case.root);case.catalog.sync_index()
                names={row['id']:row['title'] for row in case.catalog.search()['items']};seen=[]
                update=case.jobs._update
                def observed(**changes):
                    if changes.get('item_progress') is not None:seen.append(dict(changes['item_progress']))
                    return update(**changes)
                with case.supplied(),patch.object(case.jobs,'_update',side_effect=observed):
                    case.jobs.start(limit=2);case.jobs.thread.join(8)
                self.assertFalse(case.jobs.thread.is_alive());self.assertEqual(case.jobs.status()['state'],'completed')
                self.assertEqual({row['item_id'] for row in seen},set(names))
                self.assertTrue(all(row['item_title']==names[row['item_id']] for row in seen))
                self.assertIsNone(case.jobs.status()['item_progress'])


if __name__=='__main__':unittest.main()
