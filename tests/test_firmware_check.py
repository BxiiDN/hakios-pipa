"""tools/firmware_check.py with synthetic files: format rules, pins, the split-ZAP case. No real firmware is used."""
import hashlib
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('firmware_check', ROOT / 'tools/firmware_check.py')
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)


def zap(machine=164):
    head = bytearray(b'\x7fELF\x01\x01\x01' + bytes(9))
    head += struct.pack('<HHI', 2, machine, 1) + bytes(52 - 24)
    return bytes(head)


def touch(ok=True):
    blob = bytearray(8192)
    blob[-4096], blob[-4095] = (0x7f, 0x80) if ok else (1, 1)
    return bytes(blob)


GOOD = {'gpu/a650_gmu.bin': bytes(64), 'gpu/a650_sqe.fw': bytes(32), 'gpu/a650_zap.elf': zap(),
        'touch/novatek_nt36532_m82_fw_csot.bin': touch()}


class FirmwareCheck(unittest.TestCase):
    def tree(self, files, pins=True):
        d = Path(tempfile.mkdtemp())
        for rel, blob in files.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_bytes(blob)
        pinfile = d / 'proprietary-files.txt'
        lines = ['# test pins']
        for rel, entry in fc.INPUTS.items():
            if pins and rel in GOOD:
                lines.append(f'{entry} | test | {hashlib.sha256(GOOD[rel]).hexdigest()} | test')
        pinfile.write_text('\n'.join(lines) + '\n')
        return d, fc.pins_of(pinfile)

    def verdicts(self, files, pins=True):
        d, p = self.tree(files, pins)
        return {r['input']: r for r in fc.check(d, p)}

    def test_all_pass(self):
        self.assertTrue(all(r['verdict'] == 'PASS' for r in self.verdicts(GOOD).values()))

    def test_missing(self):
        files = dict(GOOD)
        del files['gpu/a650_gmu.bin']
        self.assertEqual(self.verdicts(files)['gpu/a650_gmu.bin']['verdict'], 'MISSING')

    def test_renamed_file_is_not_a_zap(self):
        files = dict(GOOD, **{'gpu/a650_zap.elf': GOOD['gpu/a650_sqe.fw']})
        self.assertEqual(self.verdicts(files)['gpu/a650_zap.elf']['verdict'], 'FORMAT FAIL')

    def test_elf_machine_reported_not_judged(self):
        row = self.verdicts(dict(GOOD, **{'gpu/a650_zap.elf': zap(40)}))['gpu/a650_zap.elf']
        self.assertEqual((row['verdict'], row['elf_machine']), ('PIN MISMATCH', 40))

    def test_split_pil_is_reported(self):
        files = dict(GOOD)
        del files['gpu/a650_zap.elf']
        files['gpu/a650_zap.mdt'] = b'mdt'
        row = self.verdicts(files)['gpu/a650_zap.elf']
        self.assertEqual(row['verdict'], 'MISSING')
        self.assertIn('split PIL', row['note'])

    def test_touch_version_rule_and_pin(self):
        self.assertEqual(self.verdicts(dict(GOOD, **{'touch/novatek_nt36532_m82_fw_csot.bin': touch(False)}))[
            'touch/novatek_nt36532_m82_fw_csot.bin']['verdict'], 'FORMAT FAIL')
        self.assertEqual(self.verdicts(dict(GOOD, **{'gpu/a650_gmu.bin': bytes(128)}))['gpu/a650_gmu.bin']['verdict'],
                         'PIN MISMATCH')
        self.assertEqual(self.verdicts(GOOD, pins=False)['gpu/a650_sqe.fw']['verdict'], 'NO PIN')

    def test_port_pins_parse(self):
        port = ROOT.parent / 'hw/UniXNU-pipa/proprietary-files.txt'
        pins = fc.pins_of(port) if port.is_file() else {}
        if pins:
            for entry in fc.INPUTS.values():
                self.assertEqual(len(pins[entry]), 64, entry)


if __name__ == '__main__':
    unittest.main()
