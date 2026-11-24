// Host harness for UniXNUPkg/Driver/GptViewDxe/GptScan.c (hakios-pipa tests/test_gpt_view.py): the same file the firmware
// builds, fed from a dump: argv[1] = file with LBA 0.. end of the entry array, argv[2] = the backup header block (or "-"),
// argv[3] = block size, argv[4] = disk blocks, argv[5] = bytes needed. Prints key=value fields, then the display lines.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "GptScan.h"

static GS_U32 crc32_ieee(const void *data, GS_U64 n)
{
  const unsigned char *p = data;
  GS_U32 c = 0xffffffffu;
  for (GS_U64 i = 0; i < n; i++) {
    c ^= p[i];
    for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1)));
  }
  return c ^ 0xffffffffu;
}

static unsigned char *slurp(const char *path, long *len)
{
  FILE *f = fopen(path, "rb");
  if (!f) return NULL;
  fseek(f, 0, SEEK_END); *len = ftell(f); fseek(f, 0, SEEK_SET);
  unsigned char *b = malloc((size_t)*len + 1);
  if (fread(b, 1, (size_t)*len, f) != (size_t)*len) { fclose(f); return NULL; }
  fclose(f);
  return b;
}

int main(int argc, char **argv)
{
  if (argc != 6) return 2;
  long hl = 0, bl = 0;
  unsigned char *head = slurp(argv[1], &hl);
  unsigned char *backup = strcmp(argv[2], "-") ? slurp(argv[2], &bl) : NULL;
  GS_U32 bs = (GS_U32)strtoul(argv[3], 0, 0);
  GS_U64 blocks = strtoull(argv[4], 0, 0), need = strtoull(argv[5], 0, 0);
  GPT_SCAN_SUMMARY s;
  if (!head || hl < 2L * bs) return 3;
  GptScanHeader(head + bs, bs, blocks, crc32_ieee, &s);
  if (!(s.Flags & (GPT_SCAN_NO_SIGNATURE | GPT_SCAN_BAD_HEADER))) {
    GS_U64 at = s.EntriesLba * bs, bytes = (GS_U64)hl > at ? (GS_U64)hl - at : 0;
    GptScanEntries(head + at, bytes, backup, crc32_ieee, &s);
  }
  printf("flags=%u\npartitions=%u\nuserdata=%d\nipados=%d\nfree=%llu\nlargest=%llu\nlargest_first=%llu\nranges=%u\nlast=%s\nlast_end=%llu\n",
         s.Flags, s.Partitions, s.HasUserdata, s.HasIpados, (unsigned long long)s.FreeBlocks,
         (unsigned long long)s.LargestFreeBlocks, (unsigned long long)s.LargestFreeFirst, s.FreeRanges, s.LastPartitionName,
         (unsigned long long)s.LastPartitionEnd);
  char line[160];
  for (unsigned i = 0; GptScanLine(&s, need, i, line, sizeof line); i++) printf("line=%s\n", line);
  return 0;
}
