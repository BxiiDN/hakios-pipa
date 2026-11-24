// Host harness for package/b5-shim/shim.c (tests/test_b5_shim_qemu.py): argv dtb-in dtb-out payload-addr payload-bytes;
// prints 0 (Android) or 1 (menu) and writes the device tree as the shim left it.
#include <stdio.h>
#include <stdlib.h>
#include "shim.h"
int main(int argc, char **argv)
{
  if (argc != 5) return 2;
  FILE *f = fopen(argv[1], "rb"); if (!f) return 3;
  fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
  u8 *b = malloc((size_t)n + 1);
  if (fread(b, 1, (size_t)n, f) != (size_t)n) return 4;
  fclose(f);
  int r = b5_decide(b, strtoull(argv[3], 0, 0), strtoull(argv[4], 0, 0));
  FILE *o = fopen(argv[2], "wb"); fwrite(b, 1, (size_t)n, o); fclose(o);
  printf("%d\n", r);
  return 0;
}
