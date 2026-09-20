#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Add the measured-layout preflight to the generated S10 installer."""
from pathlib import Path
import re
import shutil
import sys
from s10_installer_guard import ABORT, PREFLIGHT, check


def prepare(repo,stage):
    script=stage/'META-INF/com/google/android/updater-script'
    text=script.read_text()
    if text.splitlines()[0].strip()!=ABORT:
        raise ValueError('S10 installer must retain its unconditional abort')
    if 'layout-preflight.sh' in text:
        raise ValueError('preflight already present')
    # Transform only the three exact pinned kernel write destinations.
    for image in ('boot','dtb','dtbo'):
        pattern=r'^package_extract_file\("'+image+r'\.img", "/dev/block/by-name/'+image+r'"\);$'
        text,count=re.subn(pattern,lambda m:'assert('+m.group()[:-1]+');',text,flags=re.M)
        if count!=1:raise ValueError('missing/duplicate kernel write: '+image)
    lines=text.splitlines()
    lines[1:1]=list(PREFLIGHT)
    script.write_text('\n'.join(lines)+'\n')
    shutil.copyfile(repo/'target/beyond1lte/installer/layout-preflight.sh',stage/'layout-preflight.sh')
    check(repo,stage)

if __name__=='__main__':prepare(*(Path(p) for p in sys.argv[1:]))
