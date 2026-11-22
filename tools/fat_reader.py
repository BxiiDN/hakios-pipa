#!/usr/bin/env python3
"""Read files out of a FAT12/16/32 volume image (the UniXNU payload volume is FAT), without mounting it and without
mtools. Read-only; 8.3 and long file names; enough to check what a built boot image will show and boot.

  fat_reader.py IMAGE            list every file with its size
  fat_reader.py IMAGE PATH       print one file (PATH like EFI/UniXNU/unixnu.toml)
"""
import struct
import sys


class FatError(Exception):
    pass


class Fat:
    def __init__(self, data):
        if len(data) < 512 or data[510:512] != b'\x55\xaa':
            raise FatError('no FAT boot sector signature')
        self.data = data
        (self.bps, self.spc, reserved, self.nfats, root_entries, total16, _, fat16_size, _, _, _,
         total32) = struct.unpack_from('<HBHBHHBHHHII', data, 11)
        if self.bps not in (512, 1024, 2048, 4096) or self.spc == 0 or self.nfats == 0:
            raise FatError('not a FAT volume (bad geometry)')
        fat_size = fat16_size or struct.unpack_from('<I', data, 36)[0]
        total = total16 or total32
        self.fat_start = reserved * self.bps
        root_sectors = (root_entries * 32 + self.bps - 1) // self.bps
        self.root_start = self.fat_start + self.nfats * fat_size * self.bps
        self.root_bytes = root_sectors * self.bps
        self.data_start = self.root_start + self.root_bytes
        clusters = (total - (self.data_start // self.bps)) // self.spc
        self.kind = 12 if clusters < 4085 else 16 if clusters < 65525 else 32
        self.root_cluster = struct.unpack_from('<I', data, 44)[0] if self.kind == 32 else None
        self.cluster_bytes = self.spc * self.bps

    def next_cluster(self, cluster):
        if self.kind == 16:
            value = struct.unpack_from('<H', self.data, self.fat_start + 2 * cluster)[0]
            return None if value >= 0xfff8 else value
        if self.kind == 32:
            value = struct.unpack_from('<I', self.data, self.fat_start + 4 * cluster)[0] & 0x0fffffff
            return None if value >= 0x0ffffff8 else value
        off = self.fat_start + cluster * 3 // 2
        pair = struct.unpack_from('<H', self.data, off)[0]
        value = pair >> 4 if cluster & 1 else pair & 0xfff
        return None if value >= 0xff8 else value

    def chain(self, cluster):
        out, seen = bytearray(), set()
        while cluster is not None and cluster >= 2:
            if cluster in seen:
                raise FatError('cluster chain loops')
            seen.add(cluster)
            start = self.data_start + (cluster - 2) * self.cluster_bytes
            out += self.data[start:start + self.cluster_bytes]
            cluster = self.next_cluster(cluster)
        return bytes(out)

    def entries(self, raw):
        lfn = {}
        for off in range(0, len(raw), 32):
            e = raw[off:off + 32]
            if len(e) < 32 or e[0] == 0:
                break
            if e[0] == 0xe5:
                lfn.clear()
                continue
            if e[11] == 0x0f:
                seq = e[0] & 0x1f
                part = (e[1:11] + e[14:26] + e[28:32]).decode('utf-16-le', 'ignore')
                lfn[seq] = part.split('\0')[0].split('￿')[0]
                continue
            if e[11] & 0x08:
                lfn.clear()
                continue
            short = e[0:8].decode('ascii', 'replace').rstrip() + ('.' + e[8:11].decode('ascii', 'replace').rstrip()
                                                                    if e[8:11].strip() else '')
            name = ''.join(lfn[k] for k in sorted(lfn)) if lfn else short
            lfn.clear()
            if name in ('.', '..'):
                continue
            cluster = struct.unpack_from('<H', e, 26)[0] | (struct.unpack_from('<H', e, 20)[0] << 16)
            yield name, bool(e[11] & 0x10), cluster, struct.unpack_from('<I', e, 28)[0]

    def walk(self, raw=None, prefix=''):
        if raw is None:
            raw = self.chain(self.root_cluster) if self.kind == 32 else \
                self.data[self.root_start:self.root_start + self.root_bytes]
        for name, is_dir, cluster, size in self.entries(raw):
            path = f'{prefix}{name}'
            if is_dir:
                yield from self.walk(self.chain(cluster), path + '/')
            else:
                yield path, cluster, size

    def files(self):
        return {path: size for path, _, size in self.walk()}

    def read(self, wanted):
        for path, cluster, size in self.walk():
            if path.lower() == wanted.lower():
                return self.chain(cluster)[:size]
        raise FatError(f'{wanted}: not in the volume')


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    fat = Fat(open(argv[1], 'rb').read())
    if len(argv) == 2:
        for path, size in fat.files().items():
            print(f'{size:>12} {path}')
    else:
        sys.stdout.buffer.write(fat.read(argv[2]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
