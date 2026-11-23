"""tools/storage_abi_transfer.py on a synthetic flat 'kernel' with a fake Mach-O reader: the record transfers only
when the original class sits at the recorded addresses with the same dispatch. No Apple file is used."""
import hashlib
import importlib.util
import struct
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('sat', Path(__file__).resolve().parents[1] / 'tools/storage_abi_transfer.py')
sat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sat)

BASE = 0x1000
TEXT, CONST = (BASE, 0x1000), (BASE + 0x1000, 0x1000)
VT = CONST[0] + 0x100


class FakeNP:
    def __init__(self, exports):
        self._exports = exports

    def macho(self, kernel):
        return {'segments': []}

    def exports(self, kernel, image):
        return self._exports

    def backed_offset(self, segments, va, length, size):
        return va - BASE


def build(original_shift=0):
    kernel = bytearray(0x2000)
    natives = {TEXT[0] + 0x800 + 4 * i: [f'__native{i}'] for i in range(176)}
    pointers = [TEXT[0] + 0x10 + 4 * i for i in range(14)] + sorted(natives)
    struct.pack_into('<190Q', kernel, VT + 16 - BASE, *pointers)
    methods = [dict(slot=i, reference_name=f'm{i}', candidate_target=hex(p + (original_shift if i == 3 else 0)),
                    kernel_names=natives.get(p, [])) for i, p in enumerate(pointers)]
    audit = dict(live_native_4k=True, method_slots=190, abstract_complete_destructors_trap=True,
                 live_instance_sizes={'IOBlockStorageDevice': 0x90, 'IOService': 0x88}, kernel_bindings=176,
                 vtable=hex(VT), original_protected_constructor=hex(TEXT[0] + 0x40), original_base_destructor=hex(TEXT[0] + 0x44),
                 original_metaclass=hex(CONST[0] + 0x10), methods=methods)
    text = bytes(kernel[TEXT[0] - BASE:TEXT[0] - BASE + TEXT[1]])
    plan = dict(original_sha256=sat.KERNELCACHE, candidate_sha256=hashlib.sha256(bytes(kernel)).hexdigest(),
                extents=[dict(module=sat.MODULE, segment='__TEXT_EXEC', va=TEXT[0], size=TEXT[1]),
                         dict(module=sat.MODULE, segment='__DATA_CONST', va=CONST[0], size=CONST[1])],
                original_executable_sha256={sat.MODULE: hashlib.sha256(text).hexdigest()})
    return audit, bytes(kernel), plan, FakeNP(natives)


class Transfer(unittest.TestCase):
    def verdict(self, audit, kernel, plan, np):
        return all(r['pass'] for r in sat.check(audit, kernel, plan, np))

    def test_same_class_transfers(self):
        self.assertTrue(self.verdict(*build()))

    def test_original_slot_moved_fails(self):
        self.assertFalse(self.verdict(*build(original_shift=8)))

    def test_changed_original_code_fails(self):
        audit, kernel, plan, np = build()
        plan['original_executable_sha256'][sat.MODULE] = '0' * 64
        self.assertFalse(self.verdict(audit, kernel, plan, np))

    def test_other_kernelcache_fails(self):
        audit, kernel, plan, np = build()
        plan['original_sha256'] = '1' * 64
        self.assertFalse(self.verdict(audit, kernel, plan, np))

    def test_record_without_live_4k_fails(self):
        audit, kernel, plan, np = build()
        audit['live_native_4k'] = False
        self.assertFalse(self.verdict(audit, kernel, plan, np))
