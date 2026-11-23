import sys
import unittest
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from report import summarize, write_html_report


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

    def test_estimates_cpu_usage_from_sampled_counters(self):
        a = self.row('2026-10-11T01:00:00+00:00', 'ui-tree', 11, 10, 10)
        b = self.row('2026-10-11T01:00:10+00:00', 'ui-tree', 11, 10, 10)
        c = self.row('2026-10-11T01:00:00+00:00', 'ui-tree', 12, 5, 5)
        d = self.row('2026-10-11T01:00:10+00:00', 'ui-tree', 12, 5, 5)
        for row, cpu in ((a, 4.0), (b, 6.0), (c, 1.0), (d, 2.0)):
            row['cpu_seconds'] = str(cpu)
        summary = summarize([a, b, c, d])[0]
        self.assertEqual(summary['avg_cpu_pct_one_core'], 30.0)
        self.assertIsNotNone(summary['avg_cpu_pct_machine'])

    def test_html_report_contains_both_variants_and_japanese_labels(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.html"
            self.assertIsNone(write_html_report([
                {'variant': 'Tauri', 'phase': 'Idle', 'component': 'ui-tree',
                 'median_private_mib': 220.0, 'median_sum_working_set_mib': 440.0,
                 'avg_cpu_pct_one_core': 8.0},
                {'variant': 'WinUI', 'phase': 'Idle', 'component': 'ui-tree',
                 'median_private_mib': 110.0, 'median_sum_working_set_mib': 155.0,
                 'avg_cpu_pct_one_core': 2.0}], str(path)))
            page = path.read_text(encoding='utf-8')
            self.assertIn("Tauri", page)
            self.assertIn("WinUI", page)
            self.assertIn("待機", page)
            self.assertIn("50.0%", page)
            self.assertIn("データなし", page)

    def test_rejects_invalid_cpu_counters(self):
        sample = self.row('2026-10-11T01:00:00+00:00','ui-tree',1,100,100)
        sample['cpu_seconds'] = 'nan'
        with self.assertRaises(ValueError):
            summarize([sample])

    def test_invalid_samples_rejected(self):
        with self.assertRaises(ValueError): summarize([self.row('t1','ui-tree',1,-1,10)])
        with self.assertRaises(ValueError): summarize([dict(timestamp='t1')])

if __name__ == '__main__': unittest.main()
