#!/usr/bin/env python3
"""Offline simulation of pipa's power-on paths with each boot-partition content (docs/MODE-B.md): stock, the MODE A
menu image placed in flash (B1 without a handoff -- the loop), and B5. Every step is a rule with its evidence; the
simulation follows them until a terminal state, a user input, or a repeated state (a loop). Nothing touches a device.

  mode_b_sim.py            print every scenario and its outcome; exit 1 if a forbidden outcome appears

Forbidden: a loop that needs no user input, except in EXPECTED_LOOPS -- the design rejected for it (the tablet would never reach Android by itself), and any scenario in
which fastboot (Vol- at power-on, ABL's own partition) is unreachable.
"""
import sys

# ABL rules (abl LinuxLoader of OS2.0.16, docs/MODE-B.md "ABL, dari biner"):
#   key at power-on: Vol- -> fastboot (ABL, never reads the boot partition); Vol+ -> recovery boot of boot_<slot>
#   (no androidboot.force_normal_boot=1); charger plugged while off -> androidboot.mode=charger; else normal boot.
#   An image larger than the partition or with a bad layout is refused; refused boots spend the slot's retries and
#   the slot is marked unbootable (2026-11-17 on this unit), then the other slot or fastboot.
# Image contents:
#   stock  : Linux + Android ramdisk: normal -> ANDROID; recovery -> RECOVERY; charger -> CHARGER
#   mode_a : BootShim + UEFI + payload (the RAM-boot image): every power-on -> MENU (the image cannot see the mode)
#   b5     : stock + shim (tools/b5_shim_model.py): normal/charger -> stock path; recovery -> MENU
# Menu (UniXNU dualboot.py + hakios 0001): timeout 10 s -> default entry Android = reset; iPadOS entry -> DarwinBoot.
# iPadOS without its root partition (native-ufs-root-part=ipados, absent on this GPT): panic -> pipa-panic-restart-after
# -> reset (board.toml kernel args).

TERMINAL = {'ANDROID', 'RECOVERY', 'CHARGER', 'FASTBOOT', 'IPADOS'}


def abl(image, key, charger, accepted=True):
    if key == 'vol-':
        return 'FASTBOOT'
    if not accepted:
        return 'FASTBOOT'          # retries spent, slot unbootable; the other slot is not assumed to boot
    mode = 'recovery' if key == 'vol+' else 'charger' if charger else 'normal'
    if image == 'stock':
        return {'normal': 'ANDROID', 'recovery': 'RECOVERY', 'charger': 'CHARGER'}[mode]
    if image == 'mode_a':
        return 'MENU'
    if image == 'b5':
        return 'MENU' if mode == 'recovery' else {'normal': 'ANDROID', 'charger': 'CHARGER'}[mode]
    raise ValueError(image)


def menu(choice, ipados_root):
    if choice == 'timeout' or choice == 'android':
        return 'RESET'
    if choice == 'ipados':
        return 'IPADOS' if ipados_root else 'PANIC'
    if choice == 'recovery':
        return 'RESET'             # MODE A recovery entry: a reset with a key held by the user
    raise ValueError(choice)


def run(image, first_key=None, charger=False, menu_choice='timeout', ipados_root=False, accepted=True, limit=8):
    """Follow power-on, then each reset with no key held, until terminal or a repeated state."""
    trace, key, seen = [], first_key, set()
    for _ in range(limit):
        state = abl(image, key, charger, accepted)
        trace.append(state)
        if state in TERMINAL:
            return trace, state
        if state == 'MENU':
            out = menu(menu_choice, ipados_root)
            trace.append(out)
            if out in TERMINAL:
                return trace, out
        sig = (state, key, menu_choice)
        if sig in seen:
            return trace, 'LOOP'
        seen.add(sig)
        key, charger = None, False   # after a reset nobody holds a key; the menu choice repeats (worst case: timeout)
        if menu_choice != 'timeout':
            menu_choice = 'timeout'
    return trace, 'LOOP'


# The MODE A image in flash: its Android entry is a reset back into itself (why MODE B needs a real handoff).
EXPECTED_LOOPS = {'mode_a in flash, power-on (rejected design)'}

SCENARIOS = [
    # (name, image, key, charger, menu choice, ipados root, accepted)
    ('stock, power-on', 'stock', None, False, 'timeout', False, True),
    ('mode_a in flash, power-on (rejected design)', 'mode_a', None, False, 'timeout', False, True),
    ('mode_a in flash, Vol- (fastboot)', 'mode_a', 'vol-', False, 'timeout', False, True),
    ('b5, power-on', 'b5', None, False, 'timeout', False, True),
    ('b5, charger while off', 'b5', None, True, 'timeout', False, True),
    ('b5, Vol+ -> menu, timeout', 'b5', 'vol+', False, 'timeout', False, True),
    ('b5, Vol+ -> menu, iPadOS without root partition', 'b5', 'vol+', False, 'ipados', False, True),
    ('b5, Vol+ -> menu, iPadOS with root partition', 'b5', 'vol+', False, 'ipados', True, True),
    ('b5, Vol+ -> menu, recovery entry', 'b5', 'vol+', False, 'recovery', False, True),
    ('b5 refused by ABL', 'b5', None, False, 'timeout', False, False),
    ('b5, Vol- (fastboot)', 'b5', 'vol-', False, 'timeout', False, True),
]


def main():
    bad = 0
    for name, image, key, charger, choice, root, accepted in SCENARIOS:
        trace, outcome = run(image, key, charger, choice, root, accepted)
        fastboot = abl(image, 'vol-', False, accepted) == 'FASTBOOT'
        if not fastboot:
            verdict = 'FORBIDDEN'
        elif outcome == 'LOOP':
            verdict = 'expected' if name in EXPECTED_LOOPS else 'FORBIDDEN'
        else:
            verdict = 'FORBIDDEN' if name in EXPECTED_LOOPS else 'ok'
        bad += verdict == 'FORBIDDEN'
        print(f'{verdict:9} {name:52} {" -> ".join(trace):60} => {outcome}')
    print('MODE B SIMULATION ' + ('FAIL' if bad else 'PASS') + f' ({bad} forbidden)')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
