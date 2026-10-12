import hashlib,json,struct,sys,tempfile,unittest,zipfile,zlib
from pathlib import Path
from unittest.mock import patch
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'tools'))
from holdout_manifest import SUITES,load_suite
from create_holdout_fixture import create,COLORS

def pixels(data):
    offset=8;compressed=b''
    while offset<len(data):
        length=struct.unpack('>I',data[offset:offset+4])[0];kind=data[offset+4:offset+8];value=data[offset+8:offset+8+length]
        if kind==b'IDAT':compressed+=value
        offset+=length+12
    raw=zlib.decompress(compressed)
    return lambda x,y:tuple(raw[y*541+1+x*3:y*541+1+x*3+3])

class HoldoutTests(unittest.TestCase):
    def test_frozen_suites_and_independent_queries(self):
        raw,data=load_suite('holdout-v2');_,old=load_suite('baseline-v1')
        self.assertEqual(hashlib.sha256(raw).hexdigest(),SUITES['holdout-v2'][1])
        self.assertEqual(len(data['items']),30);self.assertEqual(len(data['cases']),30)
        self.assertTrue({c['query'] for c in data['cases']}.isdisjoint(c['query'] for c in old['cases']))
        self.assertTrue({i['file'] for i in data['items']}.isdisjoint(i['file'] for i in old['items']))
        self.assertEqual(sum(2*(1+len(c['sources'])) for c in data['cases']),220)
        self.assertEqual(sum(2*len(c['sources']) for c in data['cases']),160)
    def test_tampered_manifest_rejected_before_inference(self):
        with patch('holdout_manifest.Path.read_bytes',return_value=b'{"version":2}'):
            with self.assertRaisesRegex(ValueError,'SHA256'):load_suite('holdout-v2')
    def test_bad_qrels_rejected_even_with_matching_input_digest(self):
        raw,data=load_suite('holdout-v2');data['cases'][0]['relevance']={'unknown':2}
        modified=json.dumps(data).encode();digest=hashlib.sha256(modified).hexdigest()
        with patch.dict(SUITES,{'holdout-v2':(SUITES['holdout-v2'][0],digest)}),patch('holdout_manifest.Path.read_bytes',return_value=modified):
            with self.assertRaisesRegex(ValueError,'qrels'):load_suite('holdout-v2')
    def test_evidence_groups_no_answer_and_eligibility(self):
        _,data=load_suite('holdout-v2');items={i['key']:i for i in data['items']}
        expected={'metadata':12,'pixels':6,'agreement':4,'conflict-pixels':2,'conflict-metadata':2,'filename-control':2,'no-answer':2}
        for group,count in expected.items():self.assertEqual(sum(c['group']==group for c in data['cases']),count)
        for case in data['cases']:
            self.assertTrue(case['evidence'])
            self.assertTrue(all(items[key]['kind']==case['kind'] for key in case['relevance']))
            self.assertEqual(bool(case['relevance']),case['group']!='no-answer')
            if case['group']=='pixels':self.assertTrue(all(not items[key]['tags'] for key in case['relevance']))
    def test_real_pixels_label_conflicts_and_unique_covers(self):
        _,data=load_suite('holdout-v2')
        with tempfile.TemporaryDirectory() as tmp:
            folder=create(Path(tmp)/'new',data['items']);self.assertEqual(len(list(folder.iterdir())),30)
            at=pixels((folder/'h_p01.png').read_bytes());self.assertEqual(at(50,120),COLORS['orange']);self.assertEqual(at(130,120),COLORS['orange']);self.assertEqual(at(90,120),COLORS['white'])
            self.assertEqual(pixels((folder/'h_p11.png').read_bytes())(90,120),COLORS['red'])
            self.assertIn('青い三角形',next(i for i in data['items'] if i['key']=='h_p11')['tags'])
            self.assertEqual(pixels((folder/'h_p12.png').read_bytes())(90,120),COLORS['blue'])
            covers=[]
            for item in data['items']:
                if item['kind']=='image':covers.append((folder/item['file']).read_bytes())
                elif item['kind']=='book':
                    with zipfile.ZipFile(folder/item['file']) as z:self.assertEqual(z.namelist(),['page01.png']);covers.append(z.read('page01.png'))
            self.assertEqual(len(covers),18);self.assertEqual(len(set(covers)),18)
            with self.assertRaises(FileExistsError):create(folder,data['items'])

if __name__=='__main__':unittest.main()
