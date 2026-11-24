// SPDX-License-Identifier: MIT
// hakios-pipa: copied from UniXNU-pipa package/linux-log/init.c (11cd2f8) for the GPT reader (build-gpt-reader.py, -DREADER_GPT):
// every UFS LUN's primary GPT (first 6 sectors), its backup GPT (last 5 sectors) and its size, read only, into LOG.BIN.
// pipa log reader init (see build-log-reader.py). The stock kernel reserves a 4 MiB ramoops area at 0xb0000000 (its built-in
// command line ramoops_memreserve=4M: 2 MiB console, 2 MiB pmsg, no ECC) and, when the memory survived the restart, shows what
// the previous system left there under /sys/fs/pstore. This program copies those files, this kernel's own log and its command
// line into LOG.BIN of the FAT image /log.img, writes a marker with this boot's id into pmsg and the kernel log, and offers the
// image read only as a USB mass storage disk; STATUS.TXT in the same image says what it did. When the host ejects the disk, or
// after TIMEOUT_S, it restarts into fastboot: a warm reset when the reader's device tree has qcom,force-warm-reboot, so the next
// reader finds this one's marker if the memory survives the way back. Static and libc-free; nothing on UFS is read or written.
// Adapted from the TB128FU reader (UniXNU-tb128fu package/linux-log/init.c).

// The host mounts and copies within about 15 s of boot. Some ejects were not seen (2026-10-24, twice: the LUN kept its file), and
// the tablet came back to fastboot 8.5 to 9 minutes after the reader started, so 300 rounds of this wait take far longer than
// 300 s; 60 rounds are enough.
#define TIMEOUT_S  60
#define BIG        (4 * 1024 * 1024)
#define GADGET     "/sys/kernel/config/usb_gadget/log"
#define LUN        GADGET "/functions/mass_storage.0/lun.0"
#define PSTORE     "/sys/fs/pstore"

enum {
  SysMknodat = 33, SysMkdirat = 34, SysSymlinkat = 36, SysMount = 40, SysOpenat = 56, SysClose = 57, SysGetdents64 = 61,
  SysRead = 63, SysWrite = 64, SysPwrite64 = 68, SysSync = 81, SysExit = 93, SysNanosleep = 101, SysSyslog = 116, SysReboot = 142,
};
enum { AtFdcwd = -100, ORdonly = 0, OWronly = 1, ORdwr = 2, SyslogReadAll = 3 };

static long sys(long n, long a, long b, long c, long d, long e)
{
  register long x8 __asm__("x8") = n, x0 __asm__("x0") = a, x1 __asm__("x1") = b, x2 __asm__("x2") = c,
                x3 __asm__("x3") = d, x4 __asm__("x4") = e;
  __asm__ volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4) : "memory");
  return x0;
}

// The compiler may emit calls to these; the volatile stores keep it from turning the loops back into calls.
void *memset(void *d, int c, unsigned long n)
{
  volatile unsigned char *p = d;
  while (n--) *p++ = (unsigned char)c;
  return d;
}
void *memcpy(void *d, const void *s, unsigned long n)
{
  volatile unsigned char *p = d;
  const unsigned char *q = s;
  while (n--) *p++ = *q++;
  return d;
}

static unsigned long slen(const char *s) { unsigned long n = 0; while (s[n]) ++n; return n; }
__attribute__((unused)) static int memcmp_eq(const void *a, const void *b, unsigned long n)
{
  const unsigned char *p = a, *q = b;
  while (n--) if (*p++ != *q++) return 0;
  return 1;
}

// Offset of NEEDLE in HAY, or -1.
static long find(const char *hay, unsigned long len, const char *needle)
{
  unsigned long n = slen(needle);
  for (unsigned long i = 0; i + n <= len; ++i) {
    unsigned long j = 0;
    while (j < n && hay[i + j] == needle[j]) ++j;
    if (j == n) return (long)i;
  }
  return -1;
}

static void sleep_s(long seconds) { long ts[2] = {seconds, 0}; sys(SysNanosleep, (long)ts, 0, 0, 0, 0); }

// STATUS.TXT: one line per step, rewritten into the image after every step.
static char status[4096];
static unsigned long status_len, status_off, status_cap;
static int image = -1;

static void put_n(const char *s, unsigned long n)
{
  if (status_len + n < sizeof(status)) { memcpy(status + status_len, s, n); status_len += n; }
}
static void put(const char *s) { put_n(s, slen(s)); }
static void put_num(unsigned long v)
{
  char b[24]; int i = 23; b[i] = 0;
  do { b[--i] = (char)('0' + v % 10); v /= 10; } while (v);
  put(b + i);
}
static void flush_status(void)
{
  if (image < 0 || !status_cap) return;
  static char page[4096];
  unsigned long n = status_cap < sizeof(page) ? status_cap : sizeof(page);
  memset(page, ' ', n);
  memcpy(page, status, status_len < n ? status_len : n);
  page[n - 1] = '\n';
  sys(SysPwrite64, image, (long)page, (long)n, (long)status_off, 0);
}
static void step(const char *what, long result)
{
  put(what); put(" = "); if (result < 0) { put("-"); put_num((unsigned long)-result); } else put_num((unsigned long)result);
  put("\n"); flush_status();
}

static long write_file(const char *path, const char *text)
{
  long fd = sys(SysOpenat, AtFdcwd, (long)path, OWronly, 0, 0);
  if (fd < 0) return fd;
  long r = sys(SysWrite, fd, (long)text, (long)slen(text), 0, 0);
  sys(SysClose, fd, 0, 0, 0, 0);
  return r;
}
static long read_file(const char *path, char *buf, unsigned long cap)
{
  long fd = sys(SysOpenat, AtFdcwd, (long)path, ORdonly, 0, 0);
  if (fd < 0) return fd;
  long r = sys(SysRead, fd, (long)buf, (long)cap - 1, 0, 0);
  sys(SysClose, fd, 0, 0, 0, 0);
  buf[r > 0 ? r : 0] = 0;
  return r;
}
// The whole file, up to CAP bytes (pstore files are read in pieces).
static long read_all(const char *path, char *buf, unsigned long cap)
{
  long fd = sys(SysOpenat, AtFdcwd, (long)path, ORdonly, 0, 0);
  if (fd < 0) return fd;
  unsigned long got = 0;
  while (got < cap) {
    long r = sys(SysRead, fd, (long)(buf + got), (long)(cap - got), 0, 0);
    if (r < 0) { sys(SysClose, fd, 0, 0, 0, 0); return r; }
    if (r == 0) break;
    got += (unsigned long)r;
  }
  sys(SysClose, fd, 0, 0, 0, 0);
  return (long)got;
}
static unsigned long parse_num(const char **p)
{
  unsigned long v = 0;
  while (**p == ' ' || **p == '\n') ++*p;
  while (**p >= '0' && **p <= '9') v = v * 10 + (unsigned long)(*(*p)++ - '0');
  return v;
}

static void join(char *out, const char *a, const char *b)
{
  unsigned long n = slen(a), m = slen(b);
  memcpy(out, a, n); memcpy(out + n, b, m + 1);
}

// The first entry of DIR (other than . and ..) copied into NAME; 1 if found.
static int first_entry(const char *dir, char *name, unsigned long cap)
{
  static char ents[4096];
  long fd = sys(SysOpenat, AtFdcwd, (long)dir, ORdonly, 0, 0);
  if (fd < 0) return 0;
  int found = 0;
  long n = sys(SysGetdents64, fd, (long)ents, sizeof(ents), 0, 0);
  for (long at = 0; at < n && !found;) {
    const char *entry = ents + at + 19;
    if (entry[0] != '.' && slen(entry) < cap) { memcpy(name, entry, slen(entry) + 1); found = 1; }
    at += *(unsigned short *)(ents + at + 16);
  }
  sys(SysClose, fd, 0, 0, 0, 0);
  return found;
}

// LOG.BIN: per item a 64-byte record header ("UXFILE01", the size or a negative errno as a signed 64-bit number, the name, zero
// padded), then the data padded to 8 bytes; "UXEND000" after the last (the FIRMWARE.BIN format of the TB128FU reader).
static unsigned long log_off, log_cap, log_at;
static long record(const char *name, const char *data, long size)
{
  char head[64];
  unsigned long n = slen(name);
  if (log_at + 64 + 8 > log_cap) return -27;
  if (size > 0 && log_at + 64 + (unsigned long)size + 8 > log_cap) size = -27;
  memset(head, 0, sizeof(head));
  memcpy(head, "UXFILE01", 8);
  for (int i = 0; i < 8; ++i) head[8 + i] = (char)((unsigned long)size >> (8 * i));
  memcpy(head + 16, name, n < 47 ? n : 47);
  sys(SysPwrite64, image, (long)head, 64, (long)(log_off + log_at), 0);
  if (size > 0) sys(SysPwrite64, image, (long)data, size, (long)(log_off + log_at + 64), 0);
  log_at += 64 + (size > 0 ? ((unsigned long)size + 7) / 8 * 8 : 0);
  sys(SysPwrite64, image, (long)"UXEND000", 8, (long)(log_off + log_at), 0);
  return size;
}

static char big[BIG];

// Every file pstore shows (console-ramoops-0, pmsg-ramoops-0, dmesg-ramoops-N: what the previous system left), one record each.
static long copy_pstore(void)
{
  static char ents[4096];
  long fd = sys(SysOpenat, AtFdcwd, (long)PSTORE, ORdonly, 0, 0);
  if (fd < 0) return fd;
  long n = sys(SysGetdents64, fd, (long)ents, sizeof(ents), 0, 0);
  sys(SysClose, fd, 0, 0, 0, 0);
  if (n < 0) return n;
  long count = 0;
  for (long at = 0; at < n;) {
    const char *entry = ents + at + 19;
    at += *(unsigned short *)(ents + at + 16);
    if (entry[0] == '.' || slen(entry) > 100) continue;
    char path[128];
    join(path, PSTORE "/", entry);
    long size = read_all(path, big, BIG);
    char name[64];
    join(name, "pstore/", entry);
    step(name, record(name, big, size));
    if (size > 0 && find(big, (unsigned long)size, "UNIXNU-PIPA-READER") >= 0) put("  holds a reader marker\n");
    ++count;
  }
  return count;
}

// /dev/pmsg0: the stock kernel has no devtmpfs, and pmsg's major is dynamic (252 under Android).
static long open_pmsg(void)
{
  static char devices[8192];
  long fd = sys(SysOpenat, AtFdcwd, (long)"/dev/pmsg0", OWronly, 0, 0);
  if (fd >= 0) return fd;
  long r = read_file("/proc/devices", devices, sizeof(devices));
  if (r <= 0) return r < 0 ? r : -2;
  long at = find(devices, (unsigned long)r, " pmsg\n");
  if (at < 0) return -2;
  long line = at;
  while (line > 0 && devices[line - 1] != '\n') --line;
  const char *p = devices + line;
  unsigned long major = parse_num(&p);
  put("pmsg_major="); put_num(major); put("\n");
  step("mknod.pmsg0", sys(SysMknodat, AtFdcwd, (long)"/dev/pmsg0", 020600, (long)(major << 8), 0));
  return sys(SysOpenat, AtFdcwd, (long)"/dev/pmsg0", OWronly, 0, 0);
}

// "UNIXNU-PIPA-READER boot_id=<this boot's id>" into pmsg (pmsg-ramoops-0 of the next boot) and the kernel log (its
// console-ramoops-0).
static long write_marker(void)
{
  char id[64], text[128];
  long r = read_file("/proc/sys/kernel/random/boot_id", id, sizeof(id));
  if (r <= 0) return r < 0 ? r : -5;
  if (id[r - 1] == '\n') id[r - 1] = 0;
  join(text, "UNIXNU-PIPA-READER boot_id=", id);
  join(text + slen(text), "", "\n");
  put("marker: "); put(text);
  long pmsg = open_pmsg();
  step("pmsg.open", pmsg);
  if (pmsg >= 0) { step("pmsg.write", sys(SysWrite, pmsg, (long)text, (long)slen(text), 0, 0)); sys(SysClose, pmsg, 0, 0, 0, 0); }
  long kmsg = sys(SysOpenat, AtFdcwd, (long)"/dev/kmsg", OWronly, 0, 0);
  if (kmsg < 0) {
    sys(SysMknodat, AtFdcwd, (long)"/dev/kmsg", 020600, (1 << 8) | 11, 0);
    kmsg = sys(SysOpenat, AtFdcwd, (long)"/dev/kmsg", OWronly, 0, 0);
  }
  step("kmsg.open", kmsg);
  if (kmsg >= 0) { step("kmsg.write", sys(SysWrite, kmsg, (long)text, (long)slen(text), 0, 0)); sys(SysClose, kmsg, 0, 0, 0, 0); }
  return pmsg < 0 ? pmsg : 0;
}

// This kernel's log as a record; the lines that tell how the tablet came up go to STATUS.TXT as well.
static long copy_dmesg(void)
{
  static const char *const needles[] = {"msm_reserve_ramoops_memory addr", "ramoops: attached", "pstore: ",
                                        "PMIC@SID0 Power-on reason", "PMIC@SID0: Power-off reason"};
  long n = sys(SysSyslog, SyslogReadAll, (long)big, BIG, 0, 0);
  if (n <= 0) return record("dmesg", big, n < 0 ? n : -61);
  for (unsigned i = 0; i < sizeof(needles) / sizeof(needles[0]); ++i) {
    long at = find(big, (unsigned long)n, needles[i]);
    if (at < 0) continue;
    long end = at;
    while (end < n && big[end] != '\n' && end - at < 200) ++end;
    put("  "); put_n(big + at, (unsigned long)(end - at)); put("\n");
  }
  return record("dmesg", big, n);
}

static long gadget(void)
{
  static const char *const dirs[] = {GADGET, GADGET "/strings/0x409", GADGET "/configs/c.1",
                                     GADGET "/configs/c.1/strings/0x409", GADGET "/functions/mass_storage.0"};
  for (unsigned i = 0; i < sizeof(dirs) / sizeof(dirs[0]); ++i) {
    long r = sys(SysMkdirat, AtFdcwd, (long)dirs[i], 0755, 0, 0);
    if (r < 0 && r != -17) return r;
  }
  write_file(GADGET "/idVendor", "0x1d6b");
  write_file(GADGET "/idProduct", "0x0104");
  write_file(GADGET "/strings/0x409/manufacturer", "UniXNU");
  write_file(GADGET "/strings/0x409/product", "pipa log reader");
  write_file(GADGET "/strings/0x409/serialnumber", "unixnulog");
  write_file(GADGET "/configs/c.1/strings/0x409/configuration", "log");
  // ro and removable before file: the attributes cannot change while a backing file is open.
  step("lun.removable", write_file(LUN "/removable", "1"));
  step("lun.ro", write_file(LUN "/ro", "1"));
  step("lun.file", write_file(LUN "/file", "/log.img"));
  long r = sys(SysSymlinkat, (long)(GADGET "/functions/mass_storage.0"), AtFdcwd, (long)(GADGET "/configs/c.1/mass_storage.0"), 0, 0);
  step("config.link", r);
  if (r < 0 && r != -17) return r;
  char udc[64];
  int found = 0;
  for (int i = 0; i < 20 && !found; ++i) { found = first_entry("/sys/class/udc", udc, sizeof(udc)); if (!found) sleep_s(1); }
  if (!found) return -19;
  put("udc="); put(udc); put("\n");
  r = write_file(GADGET "/UDC", udc);
  step("udc.bind", r);
  // dwc3-msm leaves peripheral mode to the charger's VBUS report; a forced mode covers a cable already present at boot.
  step("ssusb.mode", write_file("/sys/bus/platform/devices/a600000.ssusb/mode", "peripheral"));
  return r;
}

#ifdef READER_DATA
// The Data reader (build-log-reader.py --data, -DREADER_DATA): also copies the persistent Data overlay (drivers/RamBlock/
// PersistOverlay.h) out of userdata, read only, so the host can rebuild the Data volume over its own copy of the seed. Nothing is
// mounted; the partition is opened O_RDONLY and set read only in the block layer (BLKROSET) before the first read, and the copy
// stops if that does not hold. Window: the last RESERVE_BLOCKS of userdata are the log reserve, the window ends just below them
// (NativeUfs native_ufs_store_open), and is 1 + bitmap + pages 4096-byte blocks. DATA.BIN holds the header block, the bitmap blocks
// and then every present page in index order (its index follows from the bitmap).
#define DATA_PAGES      2097152UL                 // the 8 GiB seed (data.dbr logical size / 4096)
#define BITMAP_BLOCKS   ((DATA_PAGES + 32767) / 32768)
#define WINDOW_BLOCKS   (1 + BITMAP_BLOCKS + DATA_PAGES)
#define RESERVE_BLOCKS  262144UL                  // sheng-log-reserve default, 1024 MiB
enum { SysIoctl = 29, SysFtruncate = 46, SysPread64 = 67 };
#define BLKROSET     0x125dUL
#define BLKROGET     0x125eUL
#define BLKGETSIZE64 0x80081272UL
static unsigned long data_off, data_cap, image_bytes;
static unsigned char bitmap[BITMAP_BLOCKS * 4096];
static unsigned long fnv = 0xcbf29ce484222325UL;
static void hash(const unsigned char *p, unsigned long n) { while (n--) { fnv ^= *p++; fnv *= 0x100000001b3UL; } }
static void put_hex(unsigned long v) { char b[17]; for (int i = 15; i >= 0; --i) { b[i] = "0123456789abcdef"[v & 15]; v >>= 4; } b[16] = 0; put(b); }
static unsigned long get64le(const unsigned char *p) { unsigned long v = 0; for (int i = 7; i >= 0; --i) v = (v << 8) | p[i]; return v; }

// userdata's block device: the /sys/class/block entry whose uevent says PARTNAME=userdata.
static long open_userdata(void)
{
  static char ents[16384], text[512];
  long fd = sys(SysOpenat, AtFdcwd, (long)"/sys/class/block", ORdonly, 0, 0);
  if (fd < 0) return fd;
  long n = sys(SysGetdents64, fd, (long)ents, sizeof(ents), 0, 0);
  sys(SysClose, fd, 0, 0, 0, 0);
  for (long at = 0; at < n;) {
    const char *entry = ents + at + 19;
    at += *(unsigned short *)(ents + at + 16);
    if (entry[0] == '.' || slen(entry) > 32) continue;
    char path[96];
    join(path, "/sys/class/block/", entry);
    join(path + slen(path), "", "/uevent");
    long r = read_file(path, text, sizeof(text));
    if (r <= 0 || find(text, (unsigned long)r, "PARTNAME=userdata\n") < 0) continue;
    long mj = find(text, (unsigned long)r, "MAJOR="), mn = find(text, (unsigned long)r, "MINOR=");
    if (mj < 0 || mn < 0) return -22;
    const char *p = text + mj + 6; unsigned long major = parse_num(&p);
    p = text + mn + 6; unsigned long minor = parse_num(&p);
    put("userdata="); put(entry); put(" dev="); put_num(major); put(":"); put_num(minor); put("\n");
    unsigned long dev = (minor & 0xff) | (major << 8) | ((minor & ~0xffUL) << 12);
    step("mknod.userdata", sys(SysMknodat, AtFdcwd, (long)"/dev/userdata", 060400, (long)dev, 0));
    return sys(SysOpenat, AtFdcwd, (long)"/dev/userdata", ORdonly, 0, 0);
  }
  return -2;
}

static long copy_data(void)
{
  long ud = open_userdata();
  step("userdata.open", ud);
  if (ud < 0) return ud;
  int one = 1, ro = 0;
  step("userdata.blkroset", sys(SysIoctl, ud, (long)BLKROSET, (long)&one, 0, 0));
  step("userdata.blkroget", sys(SysIoctl, ud, (long)BLKROGET, (long)&ro, 0, 0));
  put("userdata.ro="); put_num((unsigned long)ro); put("\n");
  if (ro != 1) return -30;                               // EROFS: refuse to read without the block layer holding it read only
  unsigned long bytes = 0;
  step("userdata.size", sys(SysIoctl, ud, (long)BLKGETSIZE64, (long)&bytes, 0, 0));
  put("userdata.bytes="); put_num(bytes); put("\n");
  unsigned long blocks = bytes / 4096;
  if (blocks < RESERVE_BLOCKS + WINDOW_BLOCKS) return -28;
  unsigned long first = blocks - RESERVE_BLOCKS - WINDOW_BLOCKS;
  put("window.first_block="); put_num(first); put(" (partition-relative, 4096 B)\n");
  static unsigned char head[4096];
  long r = sys(SysPread64, ud, (long)head, 4096, (long)(first * 4096), 0);
  step("window.header", r);
  if (r != 4096) return r < 0 ? r : -5;
  int magic = memcmp_eq(head, "SHNGDATA", 8);
  put("window.magic="); put(magic ? "SHNGDATA" : "absent"); put(" pages="); put_num(get64le(head + 16));
  put(" generation="); put_num(head[56] | head[57] << 8 | head[58] << 16 | (unsigned long)head[59] << 24); put("\n");
  sys(SysPwrite64, image, (long)head, 4096, (long)data_off, 0);
  hash(head, 4096);
  if (!magic || get64le(head + 16) != DATA_PAGES) return -22;
  r = sys(SysPread64, ud, (long)bitmap, sizeof(bitmap), (long)((first + 1) * 4096), 0);
  step("window.bitmap", r);
  if (r != (long)sizeof(bitmap)) return r < 0 ? r : -5;
  sys(SysPwrite64, image, (long)bitmap, sizeof(bitmap), (long)(data_off + 4096), 0);
  hash(bitmap, sizeof(bitmap));
  unsigned long present = 0;
  for (unsigned long i = 0; i < DATA_PAGES; ++i) present += bitmap[i >> 3] >> (i & 7) & 1;
  put("window.present_pages="); put_num(present); put("\n");
  flush_status();
  unsigned long room = data_cap / 4096 - 1 - BITMAP_BLOCKS, out = 1 + BITMAP_BLOCKS, copied = 0;
  for (unsigned long i = 0; i < DATA_PAGES && copied < room;) {
    if (!(bitmap[i >> 3] >> (i & 7) & 1)) { ++i; continue; }
    unsigned long run = 1;
    while (i + run < DATA_PAGES && run < BIG / 4096 && copied + run < room && (bitmap[(i + run) >> 3] >> ((i + run) & 7) & 1)) ++run;
    r = sys(SysPread64, ud, (long)big, (long)(run * 4096), (long)((first + 1 + BITMAP_BLOCKS + i) * 4096), 0);
    if (r != (long)(run * 4096)) { step("window.page_read", r); return r < 0 ? r : -5; }
    sys(SysPwrite64, image, (long)big, (long)(run * 4096), (long)(data_off + out * 4096), 0);
    hash((unsigned char *)big, run * 4096);
    out += run; copied += run; i += run;
  }
  sys(SysClose, ud, 0, 0, 0, 0);
  put("window.copied_pages="); put_num(copied); put(copied == present ? " (all)" : " (TRUNCATED: DATA.BIN is full)"); put("\n");
  put("data.bin_bytes="); put_num(out * 4096); put(" fnv64="); put_hex(fnv); put("\n");
  return (long)copied;
}
#endif


#ifdef READER_GPT
// The GPT reader (-DREADER_GPT, hakios-pipa docs/IPADOS-PARTITION.md): for every whole UFS disk (/sys/class/block entry whose
// uevent says DEVTYPE=disk and DEVNAME=sd?), a read-only node is made, opened O_RDONLY and set read only in the block layer
// (BLKROSET) before the first read; a disk that does not read back BLKROGET=1 is skipped unread. Recorded per disk:
// gpt/<disk>.info (size in bytes and logical sector size, as text), gpt/<disk>.head (the first 6 sectors: protective MBR,
// primary header, 4 sectors of entries) and gpt/<disk>.tail (the last 5 sectors: backup entries and header). Nothing is written
// to any disk; nothing is mounted.
enum { SysIoctlG = 29, SysPread64G = 67 };
#define BLKROSET_G     0x125dUL
#define BLKROGET_G     0x125eUL
#define BLKSSZGET_G    0x1268UL
#define BLKGETSIZE64_G 0x80081272UL
static long copy_gpt(void)
{
  static char ents[16384], text[512];
  long fd = sys(SysOpenat, AtFdcwd, (long)"/sys/class/block", ORdonly, 0, 0);
  if (fd < 0) return fd;
  long n = sys(SysGetdents64, fd, (long)ents, sizeof(ents), 0, 0);
  sys(SysClose, fd, 0, 0, 0, 0);
  long disks = 0;
  for (long at = 0; at < n;) {
    const char *entry = ents + at + 19;
    at += *(unsigned short *)(ents + at + 16);
    if (entry[0] != 's' || entry[1] != 'd' || slen(entry) != 3) continue;
    char path[96];
    join(path, "/sys/class/block/", entry);
    join(path + slen(path), "", "/uevent");
    long r = read_file(path, text, sizeof(text));
    if (r <= 0 || find(text, (unsigned long)r, "DEVTYPE=disk\n") < 0) continue;
    long mj = find(text, (unsigned long)r, "MAJOR="), mn = find(text, (unsigned long)r, "MINOR=");
    if (mj < 0 || mn < 0) continue;
    const char *p = text + mj + 6; unsigned long major = parse_num(&p);
    p = text + mn + 6; unsigned long minor = parse_num(&p);
    unsigned long dev = (minor & 0xff) | (major << 8) | ((minor & ~0xffUL) << 12);
    char node[32], name[48];
    join(node, "/dev/gpt-", entry);
    step(node, sys(SysMknodat, AtFdcwd, (long)node, 060400, (long)dev, 0));
    long d = sys(SysOpenat, AtFdcwd, (long)node, ORdonly, 0, 0);
    step("  open", d);
    if (d < 0) continue;
    int one = 1, ro = 0;
    step("  blkroset", sys(SysIoctlG, d, (long)BLKROSET_G, (long)&one, 0, 0));
    step("  blkroget", sys(SysIoctlG, d, (long)BLKROGET_G, (long)&ro, 0, 0));
    if (ro != 1) { put("  not read only: skipped unread\n"); sys(SysClose, d, 0, 0, 0, 0); continue; }
    unsigned long bytes = 0; int ssz = 0;
    step("  size", sys(SysIoctlG, d, (long)BLKGETSIZE64_G, (long)&bytes, 0, 0));
    step("  sector", sys(SysIoctlG, d, (long)BLKSSZGET_G, (long)&ssz, 0, 0));
    if (ssz != 512 && ssz != 4096) { sys(SysClose, d, 0, 0, 0, 0); continue; }
    char info[96]; unsigned long il = 0;
    { char *q = info; const char *a = "bytes="; while (*a) q[il++] = *a++;
      char b[24]; int i = 23; b[i] = 0; unsigned long v = bytes; do { b[--i] = (char)('0' + v % 10); v /= 10; } while (v);
      for (const char *c = b + i; *c; ++c) q[il++] = *c;
      a = " sector="; while (*a) q[il++] = *a++;
      i = 23; v = (unsigned long)ssz; do { b[--i] = (char)('0' + v % 10); v /= 10; } while (v);
      for (const char *c = b + i; *c; ++c) q[il++] = *c;
      q[il++] = '\n'; }
    join(name, "gpt/", entry); join(name + slen(name), "", ".info");
    step(name, record(name, info, (long)il));
    unsigned long head = 6UL * (unsigned long)ssz, tail = 5UL * (unsigned long)ssz;
    if (bytes < head + tail) { sys(SysClose, d, 0, 0, 0, 0); continue; }
    r = sys(SysPread64G, d, (long)big, (long)head, 0, 0);
    join(name, "gpt/", entry); join(name + slen(name), "", ".head");
    step(name, record(name, big, r == (long)head ? r : (r < 0 ? r : -5)));
    r = sys(SysPread64G, d, (long)big, (long)tail, (long)(bytes - tail), 0);
    join(name, "gpt/", entry); join(name + slen(name), "", ".tail");
    step(name, record(name, big, r == (long)tail ? r : (r < 0 ? r : -5)));
    sys(SysClose, d, 0, 0, 0, 0);
    ++disks;
  }
  return disks;
}
#endif

__attribute__((unused)) static void reboot_bootloader(void)
{
  sys(SysSync, 0, 0, 0, 0, 0);
  sys(SysReboot, (long)0xfee1dead, 672274793, (long)0xa1b2c3d4, (long)"bootloader", 0);
}

// The power-off build (build-log-reader.py --poweroff, -DREADER_POWER_OFF): the stock kernel's power off, which drives the PMIC's
// shutdown (fastboot oem poweroff answers OKAY and does nothing on this tablet, and a long power press is a hard reset), for leaving
// it off after a session. It waits until the USB cable is out: with VBUS present the PMIC powered the tablet straight back on and the
// bootloader, finding no Android to charge under, went to recovery (2026-10-26). After POWER_OFF_WAIT_S it powers off anyway.
#if defined(READER_POWER_OFF) || defined(READER_GPT)
#define POWER_OFF_WAIT_S 600
// VBUS as the charger driver (qpnp-smb5) sees it: "present" follows the plug, "online" also wants a known charger type.
#define USB_PRESENT "/sys/class/power_supply/usb/present"
#define USB_ONLINE "/sys/class/power_supply/usb/online"
static void sleep_ms(long ms) { long ts[2] = {ms / 1000, (ms % 1000) * 1000000}; sys(SysNanosleep, (long)ts, 0, 0, 0, 0); }
static void power_off(void)
{
  sys(SysSync, 0, 0, 0, 0, 0);
  sys(SysReboot, (long)0xfee1dead, 672274793, (long)0x4321fedc, 0, 0);
}
static void power_off_unplugged(void)
{
  sys(SysMkdirat, AtFdcwd, (long)"/sys", 0755, 0, 0);
  sys(SysMount, (long)"sysfs", (long)"/sys", (long)"sysfs", 0, 0);
  char online[8];
  // Two reads of 0 in a row, half a second apart: the cable is out, not a moment of the charger's renegotiation.
  for (unsigned tick = 0, zeros = 0; tick < POWER_OFF_WAIT_S * 2; ++tick) {
    long n = read_file(USB_PRESENT, online, sizeof(online));
    if (n <= 0) n = read_file(USB_ONLINE, online, sizeof(online));
    zeros = n > 0 && online[0] == '0' ? zeros + 1 : 0;
    if (zeros >= 2) break;
    sleep_ms(500);
  }
  power_off();
}
#endif

__attribute__((noreturn)) void start(void)
{
#ifdef READER_POWER_OFF
  power_off_unplugged();
  for (;;) sys(SysExit, 1, 0, 0, 0, 0);
#endif
  sys(SysMkdirat, AtFdcwd, (long)"/dev", 0755, 0, 0);
  sys(SysMkdirat, AtFdcwd, (long)"/sys", 0755, 0, 0);
  sys(SysMkdirat, AtFdcwd, (long)"/proc", 0755, 0, 0);
  long devfs = sys(SysMount, (long)"devtmpfs", (long)"/dev", (long)"devtmpfs", 0, 0);
  long sysfs = sys(SysMount, (long)"sysfs", (long)"/sys", (long)"sysfs", 0, 0);
  long procfs = sys(SysMount, (long)"proc", (long)"/proc", (long)"proc", 0, 0);
  long cfs = sys(SysMount, (long)"configfs", (long)"/sys/kernel/config", (long)"configfs", 0, 0);
  long psfs = sys(SysMount, (long)"pstore", (long)PSTORE, (long)"pstore", 0, 0);

  // /log.offsets (build-log-reader.py): byte offset and size of LOG.BIN, then of STATUS.TXT inside /log.img.
  char spec[128];
  read_file("/log.offsets", spec, sizeof(spec));
  const char *p = spec;
  log_off = parse_num(&p); log_cap = parse_num(&p);
  status_off = parse_num(&p); status_cap = parse_num(&p);
  image = (int)sys(SysOpenat, AtFdcwd, (long)"/log.img", ORdwr, 0, 0);
#ifdef READER_DATA
  // DATA.BIN is the image's last file; the ramdisk carries the image only up to it, and it is grown here (sparse in tmpfs).
  data_off = parse_num(&p); data_cap = parse_num(&p); image_bytes = parse_num(&p);
  long grown = image >= 0 ? sys(SysFtruncate, image, (long)image_bytes, 0, 0, 0) : -9;
#endif

  char release[160];
  put("pipa log reader\n");
#ifdef READER_GPT
  put("mode: GPT reader (read only)\n");
#endif
  if (read_file("/proc/version", release, sizeof(release)) > 0) put(release);
  if (status_len && status[status_len - 1] != '\n') put("\n");
  step("mount.devtmpfs", devfs);
  step("mount.sysfs", sysfs);
  step("mount.proc", procfs);
  step("mount.configfs", cfs);
  step("mount.pstore", psfs);
  step("image.open", image);
  step("pstore.files", copy_pstore());
  step("marker", write_marker());
  long cmdline = read_all("/proc/cmdline", big, BIG);
  step("cmdline", record("cmdline", big, cmdline));
  step("dmesg", copy_dmesg());
#ifdef READER_GPT
  step("gpt.disks", copy_gpt());
#endif
#ifdef READER_DATA
  step("image.grow", grown);
  step("data", copy_data());
#define WAIT_S 1200
#else
#define WAIT_S TIMEOUT_S
#endif
  step("gadget", gadget());

  char file[128];
  long waited = 0;
  for (; waited < WAIT_S; ++waited) {
    sleep_s(1);
    long n = read_file(LUN "/file", file, sizeof(file));
    if (n >= 0 && (n == 0 || file[0] == '\n')) break;   // the host ejected the medium
  }
#ifdef READER_GPT
  // hakios-pipa: no restart into fastboot (a `fastboot reboot` on the installed port ROM stopped at the logo, 2026-11-24). The
  // tablet powers off once the USB cable is out (or after POWER_OFF_WAIT_S); the owner starts Android with the power key.
  put(waited < WAIT_S ? "ejected by the host" : "timeout"); put("; powering off when the USB cable is out\n");
  flush_status();
  power_off_unplugged();
#else
  put(waited < WAIT_S ? "ejected by the host" : "timeout"); put("; restarting into fastboot\n");
  flush_status();
  reboot_bootloader();
#endif
  for (;;) sys(SysExit, 1, 0, 0, 0, 0);
}
