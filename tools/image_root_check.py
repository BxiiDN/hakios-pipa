#!/usr/bin/env python3
"""The root a built image will mount, held to this tablet's GPT: the menu is read out of the image itself.

  image_root_check.py IMAGE GPT_DUMP...      exit 0: the root partition exists and is clear of userdata
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipa_gpt  # noqa: E402
import storage_safety  # noqa: E402
import verify_bootimg as vb  # noqa: E402


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    data = Path(argv[1]).read_bytes()
    fields, problems = vb.check(data)
    if problems:
        print('\n'.join(problems))
        return 1
    _, menu = vb.check_unixnu(data, fields)
    if menu is None:
        print('no menu in the image')
        return 1
    layouts = [t for path in argv[2:] for t in pipa_gpt.load_table(path)]
    verdict, hardware, findings = storage_safety.judge({'menu': menu, 'board': {}}, layouts)
    for level, text in findings:
        print(f'{level:7} {text}')
    return 0 if verdict == 'PASS' and hardware == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
