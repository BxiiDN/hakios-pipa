"""tools/payload_check.py: DarwinBoot's trust-cache rules, kernel span rules and the ADT reader."""
import importlib.util
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('payload_check', ROOT / 'tools/payload_check.py')
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


def module(hashes, kind=2):
    return struct.pack('<I16sI', 2, bytes(16), len(hashes)) + b''.join(h + bytes([kind, 0, 0, 0]) for h in hashes)


def bundle(*mods):
    starts, at = [], 4 + 4 * len(mods)
    for m in mods:
        starts.append(at)
        at += len(m)
    return struct.pack(f'<{1 + len(mods)}I', len(mods), *starts) + b''.join(mods)


def kernel(segments, entry):
    """A minimal arm64 MH_EXECUTE: LC_SEGMENT_64 per (vmaddr, vmsize, filesize, prot), then LC_UNIXTHREAD."""
    cmds = b''
    for vmaddr, vmsize, filesize, prot in segments:
        cmds += struct.pack('<2I16s4Q4I', 0x19, 72, b'S', vmaddr, vmsize, 0, filesize, prot, prot, 0, 0)
    thread = bytearray(288)
    struct.pack_into('<4I', thread, 0, 5, 288, 6, 68)
    struct.pack_into('<Q', thread, 272, entry)
    cmds += bytes(thread)
    head = struct.pack('<8I', 0xfeedfacf, 0x0100000c, 0, 2, len(segments) + 1, len(cmds), 0, 0)
    return head + cmds + bytes(0x4000)


class TrustRules(unittest.TestCase):
    def test_valid(self):
        hs = pc.valid_trust(bundle(module([b'\x01' * 20, b'\x02' * 20]), module([b'\x03' * 20])))
        self.assertEqual(len(hs), 3)

    def test_unsorted_refused(self):
        with self.assertRaisesRegex(ValueError, 'order'):
            pc.valid_trust(bundle(module([b'\x02' * 20, b'\x01' * 20])))

    def test_hash_type_refused(self):
        with self.assertRaisesRegex(ValueError, 'type'):
            pc.valid_trust(bundle(module([b'\x01' * 20], kind=9)))

    def test_length_refused(self):
        with self.assertRaises(ValueError):
            pc.valid_trust(bundle(module([b'\x01' * 20]))[:-4])


class KernelRules(unittest.TestCase):
    BASE = 0xfffffff007004000

    def test_span(self):
        k = kernel([(self.BASE, 0x100000, 0x1000, 5), (self.BASE + 0x100000, 0x200000, 0, 3)], self.BASE + 0x10)
        self.assertEqual(pc.kernel_span(k), (self.BASE, self.BASE + 0x300000, self.BASE + 0x10))

    def test_entry_not_executable(self):
        with self.assertRaisesRegex(ValueError, 'entry'):
            pc.kernel_span(kernel([(self.BASE, 0x100000, 0x1000, 3)], self.BASE + 0x10))

    def test_overlap(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            pc.kernel_span(kernel([(self.BASE, 0x200000, 0x1000, 5), (self.BASE + 0x100000, 0x100000, 0, 3)], self.BASE))

    def test_span_limit(self):
        with self.assertRaisesRegex(ValueError, 'span'):
            pc.kernel_span(kernel([(self.BASE, 0x1000, 0x1000, 5), (self.BASE + 0x10000000, 0x1000, 0, 3)], self.BASE))


class AdtReader(unittest.TestCase):
    def test_tree(self):
        import sys
        work = ROOT.parent / 'hakios-work/UniXNU/scripts'
        if not work.is_dir():
            self.skipTest('UniXNU tree not available')
        sys.path.insert(0, str(work))
        from unixnu.devicetree import node
        adt = node('device-tree', [('compatible', b'x\0')],
                   [node('chosen', [('dram-base', struct.pack('<Q', 0x80000000))], [node('memory-map', [('GpuAddon', bytes(16))])])])
        root = pc.adt_tree(adt)
        chosen = pc.child(root, 'chosen')
        self.assertEqual(struct.unpack('<Q', chosen[0]['dram-base'])[0], 0x80000000)
        self.assertEqual(pc.child(chosen, 'memory-map')[0]['GpuAddon'], bytes(16))
        with self.assertRaises(ValueError):
            pc.adt_tree(adt + b'\0\0\0\0')


if __name__ == '__main__':
    unittest.main()
