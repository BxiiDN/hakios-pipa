"""tools/candidate_provenance.py: the stage-A reference kernel is the prelinker's own output, or it is refused."""
import hashlib
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('candidate_provenance', ROOT / 'tools/candidate_provenance.py')
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

TEXT_VA = 0xfffffff007004000


def macho(symbols, cpu=0x100000c, text_va=TEXT_VA, filetype=2):
    """Executable with __TEXT and a symbol table exporting SYMBOLS (name -> address)."""
    strings = b'\0' + b''.join(name.encode() + b'\0' for name in symbols)
    ncmds, cmds_size = 2, 72 + 24
    symoff = 32 + cmds_size
    stroff = symoff + 16 * len(symbols)
    end = stroff + len(strings)
    seg = struct.pack('<2I16s4Q2I2I', 0x19, 72, b'__TEXT', text_va, 0x4000, 0, end, 5, 5, 0, 0)
    symtab = struct.pack('<6I', 0x2, 24, symoff, len(symbols), stroff, len(strings))
    table, strx = b'', 1
    for name, address in symbols.items():
        table += struct.pack('<IBBHQ', strx, 0x0f, 1, 0, address)
        strx += len(name) + 1
    header = struct.pack('<8I', 0xfeedfacf, cpu, 0, filetype, ncmds, cmds_size, 0, 0)
    return header + seg + symtab + table + strings


GOOD_EXPORTS = {name: TEXT_VA + 0x100 * (i + 1) for i, name in enumerate(cp.REQUIRED_EXPORTS)}


class Candidate(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def make(self, data=None, hid=cp.HID_TEXT_SHA, digest=None, extents=True, modified=False):
        data = macho(GOOD_EXPORTS) if data is None else data
        kernel = self.dir / 'kernel.macho'
        kernel.write_bytes(data)
        plan = {'candidate_sha256': digest or hashlib.sha256(data).hexdigest(), 'images_modified': modified,
                'original_executable_sha256': {'com.apple.iokit.IOHIDFamily': hid},
                'extents': [{'module': 'com.apple.iokit.IOHIDFamily', 'segment': '__TEXT_EXEC', 'va': 1, 'size': 1}]
                if extents else []}
        (self.dir / 'kernel.json').write_text(json.dumps(plan))
        return kernel, self.dir / 'kernel.json'

    def failures(self, *args, **kwargs):
        findings, _ = cp.check_candidate(*self.make(*args, **kwargs))
        return [text for verdict, text in findings if verdict == 'FAIL']

    def test_prelinker_output_passes_and_round_trips(self):
        kernel, plan = self.make()
        patch = self.dir / 'stage.patch'
        patch.write_text('stage a\n')
        prov = self.dir / 'provenance.json'
        self.assertEqual(cp.main(['record', '--kernel', str(kernel), '--plan', str(plan), '--stage-patch', str(patch),
                                  '--out', str(prov), '--commit', 'UniXNU=62f203c']), 0)
        self.assertFalse(json.loads(prov.read_text())['boot_candidate'])
        tree = self.dir / 'tree'
        self.assertEqual(cp.main(['install', '--candidate', str(kernel), '--plan', str(plan), '--provenance', str(prov),
                                  '--tree', str(tree)]), 0)
        installed = tree / 'build/xnu-prelink' / cp.INSTALLED_NAME
        self.assertEqual(installed.read_bytes(), kernel.read_bytes())
        self.assertTrue(installed.with_suffix('.json').is_file())

    def test_wrong_hash(self):
        self.assertTrue(any('prelinker recorded' in f for f in self.failures(digest='0' * 64)))

    def test_modified_after_prelink(self):
        kernel, plan = self.make()
        kernel.write_bytes(kernel.read_bytes() + b'\0')
        findings, _ = cp.check_candidate(kernel, plan)
        self.assertIn('FAIL', [v for v, _ in findings])

    def test_wrong_architecture(self):
        self.assertTrue(any('arm64' in f for f in self.failures(data=macho(GOOD_EXPORTS, cpu=0x1000007))))

    def test_unaligned_text_layout(self):
        self.assertTrue(any('aligned' in f for f in self.failures(data=macho(GOOD_EXPORTS, text_va=TEXT_VA + 0x1000))))

    def test_missing_symbol(self):
        exports = dict(GOOD_EXPORTS)
        del exports['__ZTV9IOService']
        self.assertTrue(any('__ZTV9IOService' in f for f in self.failures(data=macho(exports))))

    def test_other_iohidfamily(self):
        self.assertTrue(any('IOHIDFamily' in f for f in self.failures(hid='1' * 64)))
        self.assertTrue(any('extent' in f for f in self.failures(extents=False)))

    def test_images_modified(self):
        self.assertTrue(any('unmodified' in f for f in self.failures(modified=True)))

    def test_provenance_of_another_kernel(self):
        kernel, plan = self.make()
        prov = self.dir / 'p.json'
        prov.write_text(json.dumps({'stage': 'A', 'candidate_sha256': '0' * 64, 'plan_candidate_sha256': '0' * 64,
                                    'boot_candidate': False}))
        findings, _ = cp.check_candidate(kernel, plan, prov)
        self.assertTrue(any(v == 'FAIL' and 'provenance' in t for v, t in findings))

    def test_missing_inputs_fail(self):
        findings, _ = cp.check_candidate(self.dir / 'none.macho', self.dir / 'none.json')
        self.assertEqual(findings[0][0], 'FAIL')
        self.assertEqual(cp.report(findings), 1)


class Bindings(unittest.TestCase):
    AUDIT = {'reference_candidate_sha256': 'a' * 64, 'original_text_sha256': cp.HID_TEXT_SHA, 'original_slots': 207,
             'original_instance_size': 208, 'owned_slots': [0, 1, 7, 14, 86, 87, 111, 171, 173, 180],
             'bindings': {'__ZN11IOHIDDeviceC2EPK11OSMetaClass': 0xfffffff004ad94f8,
                          '__ZTV11IOHIDDevice': 0xfffffff005d045b0}}

    def compare(self, **changes):
        d = Path(tempfile.mkdtemp())
        final = json.loads(json.dumps(self.AUDIT))
        final['reference_candidate_sha256'] = 'b' * 64
        for key, value in changes.items():
            final[key] = value
        (d / 'b.json').write_text(json.dumps(self.AUDIT))
        (d / 'f.json').write_text(json.dumps(final))
        return [v for v, _ in cp.compare_bindings(d / 'b.json', d / 'f.json')]

    def test_same_bindings_pass(self):
        self.assertNotIn('FAIL', self.compare())

    def test_moved_binding_fails(self):
        moved = dict(self.AUDIT['bindings'], __ZTV11IOHIDDevice=0xfffffff005d045c0)
        self.assertIn('FAIL', self.compare(bindings=moved))

    def test_missing_binding_fails(self):
        self.assertIn('FAIL', self.compare(bindings={'__ZTV11IOHIDDevice': 0xfffffff005d045b0}))

    def test_other_layout_fails(self):
        self.assertIn('FAIL', self.compare(original_instance_size=216))
        self.assertIn('FAIL', self.compare(owned_slots=[0, 1]))

    def test_same_reference_is_not_a_recheck(self):
        self.assertIn('FAIL', self.compare(reference_candidate_sha256='a' * 64))


if __name__ == '__main__':
    unittest.main()
