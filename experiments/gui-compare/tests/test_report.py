import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from report import summarize


class ReportTests(unittest.TestCase):
    def row(self, timestamp, component, pid, private, working, trial=1):
        return dict(timestamp=timestamp, component=component, pid=pid, private_bytes=private,
                    working_set_bytes=working, variant='Tauri', phase='Idle', trial=str(trial))

    def test_aggregates_child_processes_once_per_timestamp(self):
        m = 1048576
        rows = [self.row('t1','ui-tree',1,100*m,80*m), self.row('t1','ui-tree',2,50*m,35*m),
                self.row('t2','ui-tree',1,120*m,90*m), self.row('t1','python',3,20*m,15*m)]
        report = summarize(rows)
        ui = next(x for x in report if x['component']=='ui-tree')
        python = next(x for x in report if x['component']=='python')
        self.assertEqual(ui['median_private_mib'], 135.0)
        self.assertEqual(ui['max_private_mib'], 150.0)
        self.assertEqual(python['median_private_mib'], 20.0)
        self.assertEqual(ui['samples'], 2)

    def test_invalid_samples_rejected(self):
        with self.assertRaises(ValueError): summarize([self.row('t1','ui-tree',1,-1,10)])
        with self.assertRaises(ValueError): summarize([dict(timestamp='t1')])

if __name__ == '__main__': unittest.main()
