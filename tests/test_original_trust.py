"""tools/original_trust.py: IM4P unwrapping, the pinned digests, and the bundle layout."""
import hashlib
import importlib.util
import struct
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('original_trust', Path(__file__).resolve().parents[1] / 'tools/original_trust.py')
ot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ot)


def der(tag, body):
    n = len(body)
    if n < 128:
        return bytes([tag, n]) + body
    raw = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return bytes([tag, 0x80 | len(raw)]) + raw + body


def im4p(kind, payload):
    return der(0x30, der(0x16, b'IM4P') + der(0x16, kind) + der(0x16, b'x') + der(0x04, payload))


def module(entries):
    return struct.pack('<I16sI', 2, b'\0' * 16, entries) + b'\x11' * (24 * entries)


class OriginalTrust(unittest.TestCase):
    def test_unwrap(self):
        kind, payload = ot.im4p_payload(im4p(b'trcs', b'abc' * 100), 't')
        self.assertEqual((kind, payload), ('trcs', b'abc' * 100))

    def test_rejects_non_im4p(self):
        with self.assertRaises(ValueError):
            ot.im4p_payload(der(0x30, der(0x16, b'IMG4') + der(0x16, b't') + der(0x16, b'x') + der(0x04, b'')), 't')
        with self.assertRaises(ValueError):
            ot.im4p_payload(im4p(b'trst', b'x') + b'\0', 't')   # trailing bytes

    def test_module_shape(self):
        self.assertTrue(ot.module_ok(module(3)))
        self.assertFalse(ot.module_ok(module(3)[:-1]))
        self.assertFalse(ot.module_ok(b'\1' + module(3)[1:]))

    def test_digest_pinned(self):
        # a well-formed module that is not the original is refused
        with self.assertRaisesRegex(ValueError, 'pinned'):
            ot.build(im4p(b'trst', module(2)), im4p(b'trcs', module(1)))

    def test_layout(self):
        static, system = module(2), module(1)
        orig = ot.EXPECTED
        try:
            ot.EXPECTED = (hashlib.sha256(static).hexdigest(), hashlib.sha256(system).hexdigest())
            b = ot.build(im4p(b'trst', static), im4p(b'trcs', system))
        finally:
            ot.EXPECTED = orig
        self.assertEqual(struct.unpack_from('<3I', b), (2, 12, 12 + len(static)))
        self.assertEqual(b[12:12 + len(static)], static)
        self.assertEqual(b[12 + len(static):], system)


if __name__ == '__main__':
    unittest.main()
