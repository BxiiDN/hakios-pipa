// The UniXNU-pipa UFS root parser (drivers/ShengUfs/RootLayout.h, with hakios-pipa patch 0002) on GPTs built here:
// it finds the root partition by the name the board gives, never confuses it with Android's userdata, and reports
// "no manifest" for a userdata that holds Android's filesystem. Production code is included unchanged; only what the
// kernel provides (block reads, SHA-256, the diagnostic record) is supplied by this file.
//   c++ -std=c++17 -I UNIXNU-PIPA/drivers/ShengUfs root_layout_test.cpp -lcrypto
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <strings.h>
#include <vector>
#include <string>
#include <openssl/sha.h>
#include <zlib.h>

typedef int IOReturn;
enum { kIOReturnSuccess = 0, kIOReturnError = 1 };
enum { kDataMax = 131072 };
struct { const char *stage; uint64_t first, last; uint32_t magic0, magic1, manifest, windows; } gRootDiagnostic;

static std::vector<uint8_t> gDisk;   // LUN 0, 4096-byte blocks
static IOReturn hostRead4k (uint8_t lun, uint64_t lba, uint32_t blocks, void *dst)
{
  if (lun != 0 || (lba + blocks) * 4096 > gDisk.size ()) return kIOReturnError;
  memcpy (dst, gDisk.data () + lba * 4096, blocks * 4096ULL);
  return kIOReturnSuccess;
}

#include "RootLayout.h"

static int failures = 0, checks = 0;
#define CHECK(c) do { checks++; if (!(c)) { printf ("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static void put32 (uint8_t *p, uint32_t v) { for (int i = 0; i < 4; i++) p[i] = uint8_t (v >> (8 * i)); }
static void put64 (uint8_t *p, uint64_t v) { put32 (p, uint32_t (v)); put32 (p + 4, uint32_t (v >> 32)); }

struct Part { const char *name; uint64_t first, last; };
static const uint64_t kTotal = 4096;   // a 16 MiB "LUN"

static void makeDisk (const std::vector<Part> &parts)
{
  gDisk.assign (kTotal * 4096, 0);
  uint8_t *entries = gDisk.data () + 2 * 4096;
  for (size_t i = 0; i < parts.size (); i++) {
    uint8_t *e = entries + i * 128;
    e[0] = 0xaf; e[15] = 0x01;                         // any non-zero type GUID
    e[16] = uint8_t (i + 1);
    put64 (e + 32, parts[i].first); put64 (e + 40, parts[i].last);
    for (size_t c = 0; parts[i].name[c]; c++) e[56 + 2 * c] = uint8_t (parts[i].name[c]);
  }
  uint8_t *h = gDisk.data () + 4096;
  memcpy (h, "EFI PART", 8);
  put32 (h + 8, 0x00010000); put32 (h + 12, 92);
  put64 (h + 24, 1); put64 (h + 32, kTotal - 1); put64 (h + 40, 6); put64 (h + 48, kTotal - 6);
  put64 (h + 72, 2); put32 (h + 80, 128); put32 (h + 84, 128);
  put32 (h + 88, uint32_t (crc32 (0, entries, 128 * 128)));
  put32 (h + 16, 0);
  put32 (h + 16, uint32_t (crc32 (0, h, 92)));
}

static void writeManifest (uint64_t lba, uint64_t imageBytes)
{
  uint8_t *m = gDisk.data () + lba * 4096;
  memset (m, 0, 4096);
  memcpy (m, "SHNGROOT", 8);
  put32 (m + 8, 1); put32 (m + 12, 1); put64 (m + 16, imageBytes);
  uint8_t *w = m + 24;
  strcpy (reinterpret_cast<char *> (w), "OS");
  put64 (w + 32, 4096); put64 (w + 40, imageBytes - 4096); put32 (w + 48, 512); put32 (w + 52, 1);
  SHA256 (m, 4064, m + 4064);
}

int main ()
{
  const char *why = "";
  RootLayout layout;
  // Android's userdata (f2fs superblock magic at byte 1024) and iPadOS's own partition after it.
  makeDisk ({{"boot_a", 6, 99}, {"userdata", 100, 1999}, {"ipados", 2000, 3999}, {"ipados_b", 4000, 4089}});
  put32 (gDisk.data () + 100 * 4096 + 1024, 0xf2f52010);

  CHECK (rootPartitionIsAndroidUserdata ());                       // upstream default
  CHECK (findRootLayout (&layout, &why));
  CHECK (layout.userdataFirst == 100 && layout.manifestStatus == 1); // Android's filesystem: no manifest, no root, no store

  strlcpy (gRootPartitionName, "ipados", sizeof (gRootPartitionName));
  CHECK (!rootPartitionIsAndroidUserdata ());
  CHECK (findRootLayout (&layout, &why));
  CHECK (layout.userdataFirst == 2000 && layout.userdataLast == 3999);   // not userdata, not ipados_b
  CHECK (layout.manifestStatus == 1);

  writeManifest (2000, 16 * 4096);
  CHECK (findRootLayout (&layout, &why));
  CHECK (layout.manifestStatus == 0 && layout.windows == 1 && layout.imageBytes == 16 * 4096);

  // A manifest written into Android's userdata is not found when the root is ipados
  makeDisk ({{"userdata", 100, 1999}, {"ipados", 2000, 3999}});
  writeManifest (100, 16 * 4096);
  CHECK (findRootLayout (&layout, &why));
  CHECK (layout.userdataFirst == 2000 && layout.manifestStatus == 1);

  // No ipados partition: no root, stated plainly
  makeDisk ({{"userdata", 100, 3999}});
  CHECK (!findRootLayout (&layout, &why));
  CHECK (strcmp (why, "no root partition") == 0);

  // Only the exact name: "ipados_b" alone is not "ipados"
  makeDisk ({{"userdata", 100, 1999}, {"ipados_b", 2000, 3999}});
  CHECK (!findRootLayout (&layout, &why));

  if (failures) printf ("root_layout_test: %d of %d FAILED\n", failures, checks); else printf ("root_layout_test: PASS (%d checks)\n", checks);
  return failures != 0;
}
