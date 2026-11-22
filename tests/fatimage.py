"""A minimal FAT32 image writer for tests (the UniXNU payload volume is FAT32: `mformat -F`). Long names, nested
directories, one cluster chain per file. Only for building fixtures; tools/fat_reader.py is what is under test."""
import struct

BPS, SPC, RESERVED, NFATS = 512, 1, 32, 2


def _short(index):
    return f'F{index:07d}'.encode() + b'BIN'


def _lfn_entries(name, short):
    checksum = 0
    for b in short:
        checksum = (((checksum & 1) << 7) | (checksum >> 1)) + b & 0xff
    units = list(name.encode('utf-16-le'))
    chars = [units[i:i + 2] for i in range(0, len(units), 2)] + [[0, 0]]
    while len(chars) % 13:
        chars.append([0xff, 0xff])
    out = []
    for seq in range(len(chars) // 13):
        part = chars[seq * 13:(seq + 1) * 13]
        flat = bytes(b for c in part for b in c)
        e = bytes([seq + 1 | (0x40 if seq == len(chars) // 13 - 1 else 0)]) + flat[0:10] + b'\x0f\x00' + bytes([checksum]) + \
            flat[10:22] + b'\x00\x00' + flat[22:26]
        out.append(e)
    return list(reversed(out))


def build(files, total_sectors=70000):
    """files: {'EFI/UniXNU/unixnu.toml': b'...'} -> bytes of a FAT32 volume."""
    fat_size = (total_sectors * 4 // BPS) + 1
    data_start = (RESERVED + NFATS * fat_size) * BPS
    image = bytearray(total_sectors * BPS)
    fat = [0x0ffffff8, 0x0fffffff]
    clusters = {}

    def alloc(payload):
        n = max(1, -(-len(payload) // (BPS * SPC)))
        first = len(fat)
        for i in range(n):
            fat.append(first + i + 1 if i < n - 1 else 0x0fffffff)
        off = data_start + (first - 2) * BPS * SPC
        image[off:off + len(payload)] = payload
        return first

    tree = {}
    for path, content in files.items():
        node = tree
        parts = path.split('/')
        for d in parts[:-1]:
            node = node.setdefault(d, {})
        node[parts[-1]] = content
    counter = [0]

    def write_dir(node, is_root=False):
        entries = bytearray()
        for name, value in node.items():
            counter[0] += 1
            short = _short(counter[0])
            if isinstance(value, dict):
                cluster, size, attr = write_dir(value), 0, 0x10
            else:
                cluster, size, attr = alloc(value), len(value), 0x20
            for lfn in _lfn_entries(name, short):
                entries += lfn
            entries += short + bytes([attr]) + b'\0' * 8 + struct.pack('<H', cluster >> 16) + b'\0' * 4 + \
                struct.pack('<HI', cluster & 0xffff, size)
        entries += b'\0' * 32
        return alloc(bytes(entries))

    root = write_dir(tree, True)
    bpb = struct.pack('<3s8sHBHBHHBHHHII', b'\xebX\x90', b'MSWIN4.1', BPS, SPC, RESERVED, NFATS, 0, 0, 0xf8, 0, 63, 255, 0,
                      total_sectors)
    bpb += struct.pack('<IHHIHH12sBBBI11s8s', fat_size, 0, 0, root, 1, 6, b'\0' * 12, 0x80, 0, 0x29, 0x53484e47,
                       b'PIPAESP    ', b'FAT32   ')
    image[0:len(bpb)] = bpb
    image[510:512] = b'\x55\xaa'
    table = struct.pack(f'<{len(fat)}I', *fat)
    for i in range(NFATS):
        off = (RESERVED + i * fat_size) * BPS
        image[off:off + len(table)] = table
    return bytes(image)
