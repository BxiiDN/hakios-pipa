/* B5 entry shim, the decision (shim.h). Rules, fail-safe first (= tools/b5_shim_model.py decide()):
   1. not a flattened device tree (magic, version >= 16, blocks inside totalsize)   -> Android
   2. no /chosen or no /chosen/bootargs                                             -> Android
   3. bootargs has the word androidboot.mode=charger                                -> Android
   4. bootargs has the word androidboot.force_normal_boot=1 (ABL's normal boot)     -> Android
   5. recovery boot: linux,initrd-start and linux,initrd-end (4 or 8 bytes each) rewritten in place to the payload, whose
      length must be a whole number of 512-byte sectors; anything missing                -> Android      else -> menu */
#include "shim.h"

#define FDT_MAGIC 0xd00dfeedu
#define TOK_BEGIN 1u
#define TOK_END 2u
#define TOK_PROP 3u
#define TOK_NOP 4u
#define TOK_FINISH 9u

static u32 be32(const u8 *p) { return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3]; }
static void put_be32(u8 *p, u32 v) { p[0] = (u8)(v >> 24); p[1] = (u8)(v >> 16); p[2] = (u8)(v >> 8); p[3] = (u8)v; }

static int str_eq(const u8 *a, const char *b)
{
  while (*b) if (*a++ != (u8)*b++) return 0;
  return *a == 0;
}

/* a whole word of bootargs: bounded by start/end or a space */
static int has_word(const u8 *s, u32 len, const char *w)
{
  u32 n = 0, i, j;
  while (w[n]) n++;
  for (i = 0; i + n <= len; i++) {
    if (i > 0 && s[i - 1] != ' ') continue;
    for (j = 0; j < n && s[i + j] == (u8)w[j]; j++) {}
    if (j == n && (i + n == len || s[i + n] == ' ' || s[i + n] == 0)) return 1;
  }
  return 0;
}

int b5_decide(u8 *dtb, u64 payload_addr, u64 payload_bytes)
{
  u32 total, off_struct, off_strings, version, size_strings, size_struct, i, end, depth = 0, in_chosen = 0;
  u8 *bootargs = 0, *start = 0, *stop = 0;
  u32 bootargs_len = 0, start_len = 0, stop_len = 0;

  if (!dtb || be32(dtb) != FDT_MAGIC) return B5_ANDROID;
  total = be32(dtb + 4); off_struct = be32(dtb + 8); off_strings = be32(dtb + 12);
  version = be32(dtb + 20); size_strings = be32(dtb + 32); size_struct = be32(dtb + 36);
  if (version < 16 || total < 40 || off_struct > total || size_struct > total - off_struct ||
      off_strings > total || size_strings > total - off_strings)
    return B5_ANDROID;
  i = off_struct; end = off_struct + size_struct;
  while (i + 4 <= end) {
    u32 tok = be32(dtb + i);
    i += 4;
    if (tok == TOK_BEGIN) {
      const u8 *name = dtb + i;
      u32 n = 0;
      while (i + n < end && name[n]) n++;
      if (i + n >= end) return B5_ANDROID;
      depth++;
      if (depth == 2) in_chosen = str_eq(name, "chosen");
      i = (i + n + 1 + 3) & ~3u;
    } else if (tok == TOK_END) {
      if (depth == 0) return B5_ANDROID;
      if (depth == 2) in_chosen = 0;
      depth--;
    } else if (tok == TOK_PROP) {
      u32 len, nameoff;
      if (i + 8 > end) return B5_ANDROID;
      len = be32(dtb + i); nameoff = be32(dtb + i + 4);
      i += 8;
      if (nameoff >= size_strings || len > end - i) return B5_ANDROID;
      if (in_chosen && depth == 2) {
        const u8 *pname = dtb + off_strings + nameoff;
        if (str_eq(pname, "bootargs")) { bootargs = dtb + i; bootargs_len = len; }
        else if (str_eq(pname, "linux,initrd-start")) { start = dtb + i; start_len = len; }
        else if (str_eq(pname, "linux,initrd-end")) { stop = dtb + i; stop_len = len; }
      }
      i = (i + len + 3) & ~3u;
    } else if (tok == TOK_NOP) {
      continue;
    } else if (tok == TOK_FINISH) {
      break;
    } else {
      return B5_ANDROID;
    }
  }
  if (!bootargs) return B5_ANDROID;
  while (bootargs_len && bootargs[bootargs_len - 1] == 0) bootargs_len--;
  if (has_word(bootargs, bootargs_len, "androidboot.mode=charger")) return B5_ANDROID;
  if (has_word(bootargs, bootargs_len, "androidboot.force_normal_boot=1")) return B5_ANDROID;
  if (payload_bytes == 0 || (payload_bytes & 511) != 0) return B5_ANDROID;
  if (!start || !stop || (start_len != 4 && start_len != 8) || (stop_len != 4 && stop_len != 8)) return B5_ANDROID;
  if ((start_len == 4 && (payload_addr >> 32)) || (stop_len == 4 && ((payload_addr + payload_bytes) >> 32))) return B5_ANDROID;
  if (start_len == 8) { put_be32(start, (u32)(payload_addr >> 32)); put_be32(start + 4, (u32)payload_addr); }
  else put_be32(start, (u32)payload_addr);
  if (stop_len == 8) { put_be32(stop, (u32)((payload_addr + payload_bytes) >> 32)); put_be32(stop + 4, (u32)(payload_addr + payload_bytes)); }
  else put_be32(stop, (u32)(payload_addr + payload_bytes));
  return B5_MENU;
}
