"""Private pair work may batch SQLite polling; publication and cancel stay strict."""
from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
import test_audio_direct_similarity as audio_fixture
import test_video_direct_similarity as video_fixture
from audio_direct_similarity import AudioDirectSimilarity
from video_direct_similarity import VideoDirectSimilarity
from audio_direct_search import AudioSearchChanged
from video_direct_search import VideoSearchChanged
from ai_vectors import dot


class SimilarityVersionBatchTests(unittest.TestCase):
    def fixture(self,kind):
        case=(audio_fixture.DirectSimilarityTests if kind=='audio' else video_fixture.DirectVideoSimilarityTests)('runTest')
        case.setUp();self.addCleanup(case.doCleanups);case.seed();case.add_item()
        return case,(AudioDirectSimilarity if kind=='audio' else VideoDirectSimilarity)(case.index)

    def test_pair_work_avoids_one_sqlite_version_query_per_dot_product(self):
        for kind in ('audio','video'):
            with self.subTest(kind=kind):
                case,search=self.fixture(kind);original=case.index.store.connect;frames=search._frames;queries=[];products=[]
                @contextmanager
                def traced():
                    with original() as db:
                        db.set_trace_callback(lambda sql:queries.append(sql) if sql.upper().strip()=='PRAGMA DATA_VERSION' else None)
                        yield db
                def expanded(*args):
                    revision,values=frames(*args)
                    return revision,values*16
                def scored(left,right):products.append(1);return dot(left,right)
                with patch.object(case.index.store,'connect',side_effect=traced),patch.object(search,'_frames',side_effect=expanded),patch(kind+'_direct_similarity.dot',side_effect=scored):
                    result=search.similar(case.item)
                self.assertEqual(result['total'],1);self.assertEqual(len(products),1024)
                self.assertLess(len(queries),len(products)//8)
                self.assertEqual(list(case.stage.iterdir()),[])

    def test_external_commit_in_short_private_batch_never_reaches_result_sink(self):
        for kind in ('audio','video'):
            with self.subTest(kind=kind):
                case,search=self.fixture(kind);published=[];products=[]
                def changed(left,right):
                    products.append(1)
                    if len(products)==1:
                        with case.index.store.connect() as db:db.execute('UPDATE ai_'+kind+'_direct_sources SET total_frames=total_frames+1')
                    return dot(left,right)
                with patch(kind+'_direct_similarity.dot',side_effect=changed),self.assertRaises(AudioSearchChanged if kind=='audio' else VideoSearchChanged):
                    search.similar(case.item,result_sink=published.append)
                self.assertEqual(published,[]);self.assertTrue(products);self.assertLessEqual(len(products),4)
                self.assertEqual(list(case.stage.iterdir()),[])


if __name__=='__main__':unittest.main()
