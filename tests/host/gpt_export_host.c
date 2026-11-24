// Host harness for GptExport.c (hakios-pipa tests/test_gpt_export.py): builds the container, envelope and every frame the
// firmware would show, from head and tail sector files. argv: head tail blocksize diskblocks frames-out envelope-out
#include <stdio.h>
#include <stdlib.h>
#include "GptExport.h"

static unsigned char *slurp(const char *p, long *n)
{
  FILE *f = fopen(p, "rb"); if (!f) return NULL;
  fseek(f, 0, SEEK_END); *n = ftell(f); fseek(f, 0, SEEK_SET);
  unsigned char *b = malloc((size_t)*n + 1);
  if (fread(b, 1, (size_t)*n, f) != (size_t)*n) { fclose(f); return NULL; }
  fclose(f); return b;
}

int main(int argc, char **argv)
{
  if (argc != 7) return 2;
  long hn, tn;
  unsigned char *h = slurp(argv[1], &hn), *t = slurp(argv[2], &tn);
  GS_U32 bs = (GS_U32)strtoul(argv[3], 0, 0);
  GS_U64 blocks = strtoull(argv[4], 0, 0);
  if (!h || !t) return 3;
  GS_U64 cap = 32 + (GS_U64)hn + (GS_U64)tn + 512;
  GS_U8 *c = malloc(cap), *e = malloc(cap);
  GS_U64 cl = GptExportContainer(bs, blocks, h, (GS_U32)(hn / bs), t, (GS_U32)(tn / bs), c, cap);
  GS_U64 el = GptExportEnvelope(c, cl, "pipa-lun0-gpt.hkgpt", "application/octet-stream", e, cap);
  if (!cl || !el) return 4;
  GS_U32 pc = GptExportCrc32(e, el), n = GptExportFrameCount(el);
  FILE *fo = fopen(argv[5], "wb"), *fe = fopen(argv[6], "wb");
  GS_U8 frame[GPT_EXPORT_FRAME_LENGTH];
  for (GS_U32 i = 0; i < n; i++) { GptExportFrame(e, el, i, 0x48474B31u ^ pc, pc, frame); fwrite(frame, 1, sizeof frame, fo); }
  fwrite(e, 1, (size_t)el, fe);
  fclose(fo); fclose(fe);
  printf("frames=%u envelope=%llu container=%llu\n", n, (unsigned long long)el, (unsigned long long)cl);
  return 0;
}
