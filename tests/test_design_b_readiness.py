"""tools/design_b_readiness.py: NOT READY today; each item turns PASS only on its own evidence; the committed plan keeps
consent BLOCKED."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import design_b_readiness as r  # noqa: E402
import gpt_export_decode as dec  # noqa: E402


class Readiness(unittest.TestCase):
    def test_not_ready_today(self):
        self.assertEqual(r.main([]), 1)
        self.assertEqual(r.check_consent(ROOT / 'plans/ipados-shrink-userdata.json')[0], 'BLOCKED')
        self.assertEqual(r.check_writer()[0], 'MISSING')
        for f in (r.check_backup, r.check_restore, r.check_gpt):
            self.assertEqual(f(None)[0], 'MISSING')
        self.assertEqual(r.check_rom(None, None, None, None)[0], 'MISSING')

    def test_restore_record(self):
        d = Path(tempfile.mkdtemp())
        (d / 'ok.txt').write_text('2026-11-25 restored WhatsApp from backup\nresult: OK\n')
        (d / 'no.txt').write_text('tried\n')
        self.assertEqual(r.check_restore(d / 'ok.txt')[0], 'PASS')
        self.assertEqual(r.check_restore(d / 'no.txt')[0], 'FAIL')

    def test_rom_package_needs_every_image(self):
        d = Path(tempfile.mkdtemp())
        (d / 'boot.img').write_bytes(b'x')
        level, text = r.check_rom(d, None, None, None)
        self.assertEqual(level, 'FAIL')
        self.assertIn('vendor_boot.img', text)

    def test_gpt_dump_from_the_exporter(self):
        from test_gpt_export import Export
        Export.setUpClass()
        t = Export('test_round_trip_is_byte_exact')
        frames, _, _ = t.export()
        scan = Export.tmp / 'scan.bin'
        scan.write_bytes(frames)
        out = Export.tmp / 'dump'
        self.assertEqual(dec.main([str(scan), '--out', str(out)]), 0)
        self.assertEqual(r.check_gpt(out)[0], 'PASS')
        (out / 'head.bin').write_bytes(b'tampered')
        self.assertEqual(r.check_gpt(out)[0], 'FAIL')


if __name__ == '__main__':
    unittest.main()
