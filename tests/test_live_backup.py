"""Live snapshot/selection checks on generated catalogs, no GUI or model."""
from contextlib import contextmanager,closing
from dataclasses import replace
from pathlib import Path
import json,sqlite3,sys,tempfile,threading,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from live_backup import capture_live,BackupSelection
from storage_backup import backup,restore,RecoveryError
from storage_lease import storage_lease

class LiveBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.media=self.base/'media';self.media.mkdir();(self.media/'a.png').write_bytes(b'generated-only')
        self.cat=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.cat.close)
        self.root=self.cat.add_root(str(self.media));self.cat.index.scan(self.root);self.cat.sync_index();self.item=self.cat.search()['items'][0]['id']
        self.cat.update([self.item],{'tags':['before'],'favorite':True});self.cat.set_root_favorite(self.root,True)
        with self.cat.connect() as db:
            db.execute('INSERT INTO view_history VALUES(?,?,?)',(self.item,123,1))
            db.execute('INSERT INTO reader_progress VALUES(?,?,?,?)',(self.item,'a'*64,0,'single'))
        self.paused=False
    @contextmanager
    def quiesce(self,*,cancelled=None):
        self.assertFalse(self.paused);self.paused=True
        try:yield
        finally:self.paused=False
    def read(self,path,query):
        with closing(sqlite3.connect(path)) as db:return db.execute(query).fetchall()
    def test_live_snapshot_allows_reads_and_releases_writers_before_packing(self):
        writer=None;observed=[]
        def progress(value):
            nonlocal writer
            observed.append(value['stage'])
            if value['stage']=='capturing' and value['bytes_total'] is not None and writer is None:
                self.assertTrue(self.paused)
                self.assertEqual(self.cat.search(query='before')['total'],1)
                writer=threading.Thread(target=lambda:self.cat.update([self.item],{'tags':['after']}));writer.start()
            if value['stage']=='packing':
                self.assertFalse(self.paused);writer.join(5);self.assertFalse(writer.is_alive())
        # A live owner lease must not be reacquired as if the app were stopped.
        with storage_lease(self.cat.path):result=capture_live(self.cat,self.base/'bundle',quiesce=self.quiesce,progress=progress)
        if writer:writer.join(5)
        self.assertEqual(self.cat.get(self.item)['tags'],['after'])
        restored=self.base/'restored';restore(self.base/'bundle',restored)
        self.assertEqual(json.loads(self.read(restored/'catalog.sqlite','SELECT tags FROM items')[0][0]),['before'])
        self.assertTrue(result['selection']['history']);self.assertIn('packing',observed)
        self.assertEqual(list(self.base.glob('.aredoko-capture-*')),[])
    def test_excluding_history_position_changes_only_the_copy(self):
        capture_live(self.cat,self.base/'bundle',quiesce=self.quiesce,selection=BackupSelection(settings=False,history=False,reader_progress=False))
        restore(self.base/'bundle',self.base/'restored');destination=self.base/'restored/catalog.sqlite'
        self.assertEqual(self.read(destination,'SELECT count(*) FROM view_history'),[(0,)])
        self.assertEqual(self.read(destination,'SELECT count(*) FROM reader_progress'),[(0,)])
        self.assertEqual(self.read(self.cat.path,'SELECT count(*) FROM view_history'),[(1,)])
        self.assertEqual(self.read(self.cat.path,'SELECT count(*) FROM reader_progress'),[(1,)])
        self.assertEqual(self.read(destination,'SELECT favorite FROM registered_root_preferences'),[(1,)])
        missing=json.loads((self.base/'bundle/manifest.json').read_text())['not_included']
        self.assertTrue({'view_history','reader_progress'}<=set(missing))
    def test_cancel_and_rejected_publication_leave_no_completed_bundle(self):
        cancelled=threading.Event()
        def progress(value):
            if value['stage']=='capturing' and value['bytes_total'] is not None:cancelled.set()
        with self.assertRaises(InterruptedError):capture_live(self.cat,self.base/'cancelled',quiesce=self.quiesce,cancelled=cancelled.is_set,progress=progress)
        self.assertFalse((self.base/'cancelled').exists());self.assertEqual(list(self.base.glob('.aredoko-capture-*')),[])
        def reject(operation):raise InterruptedError('cancel won before manifest')
        with self.assertRaises(InterruptedError):capture_live(self.cat,self.base/'rejected',quiesce=self.quiesce,publish=reject)
        self.assertFalse((self.base/'rejected').exists());self.assertEqual(self.cat.get(self.item)['tags'],['before'])
    def test_viewer_settings_are_captured_as_bytes_or_omitted(self):
        settings=self.base/'viewer.json';raw=b'{"version":1,"wheel_up_advances":false,"theme":"dark"}';settings.write_bytes(raw)
        capture_live(self.cat,self.base/'with-settings',quiesce=self.quiesce,viewer_settings=settings)
        self.assertEqual((self.base/'with-settings/settings/viewer-settings.json').read_bytes(),raw)
        capture_live(self.cat,self.base/'without-settings',quiesce=self.quiesce,viewer_settings=settings,selection=BackupSelection(settings=False))
        self.assertFalse((self.base/'without-settings/settings').exists())
    def test_existing_output_missing_coordination_and_invalid_selection_are_rejected(self):
        with self.assertRaises(RecoveryError):BackupSelection(history=1)
        with self.assertRaises(RecoveryError):capture_live(self.cat,self.base/'bad',quiesce=None)
        destination=self.base/'exists';destination.mkdir();(destination/'keep').write_bytes(b'keep')
        with self.assertRaises(RecoveryError):capture_live(self.cat,destination,quiesce=self.quiesce)
        self.assertEqual((destination/'keep').read_bytes(),b'keep')

    def test_vector_db_and_catalog_are_captured_from_the_same_boundary(self):
        from ai_profiles import DEFAULT_PROFILE
        from ai_search import VectorStore
        from storage_backup import _profile_suffix
        profile=replace(DEFAULT_PROFILE,dimension=3)
        path=self.cat.path.with_name(self.cat.path.name+_profile_suffix(profile.key));store=VectorStore(path,profile)
        store.save_state({'state':'complete','processed':1})
        def progress(value):
            if value['stage']=='packing':
                self.cat.update([self.item],{'tags':['after']});store.save_state({'state':'complete','processed':2})
        capture_live(self.cat,self.base/'vectors',quiesce=self.quiesce,selection=BackupSelection(vectors=True),progress=progress)
        restore(self.base/'vectors',self.base/'restored-vectors')
        restored=self.base/'restored-vectors'/path.name
        self.assertEqual(json.loads(self.read(restored,'SELECT json FROM ai_state')[0][0])['processed'],1)
        self.assertEqual(store.state()['processed'],2)
        self.assertEqual(json.loads(self.read(self.base/'restored-vectors/catalog.sqlite','SELECT tags FROM items')[0][0]),['before'])
    def test_restore_rejects_a_false_omitted_history_declaration(self):
        backup(self.cat.path,self.base/'bundle',include_vectors=False)
        path=self.base/'bundle/manifest.json';manifest=json.loads(path.read_text());manifest['not_included'].append('view_history');path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(RecoveryError,'omitted'):restore(self.base/'bundle',self.base/'restored')
        self.assertFalse((self.base/'restored').exists())
