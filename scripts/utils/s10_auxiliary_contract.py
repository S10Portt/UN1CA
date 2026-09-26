#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Only pinned raw auxiliary payloads may enter packages, never work trees."""
from pathlib import Path
import sys
import zipfile
from s10_auxiliary_images import MANIFEST, NAMES, REPO, manifest, validate_stream, verify


def approved_names(names):
    allowed = {p+'.img' for p in NAMES}
    for name in names:
        base = Path(name).name
        if any(base == p or base.startswith(p+'.') for p in (*NAMES,'up_param')) and name not in allowed:
            raise ValueError('unapproved auxiliary asset: '+name)
    if not allowed.issubset(names): raise ValueError('missing approved auxiliary image')


def check_zip(archive, repo=REPO):
    names = archive.namelist()
    if len(names) != len(set(names)): raise ValueError('duplicate ZIP entries')
    approved_names(names)
    data = manifest(repo)
    if archive.read('auxiliary-source.json') != (repo/MANIFEST).read_bytes(): raise ValueError('auxiliary provenance mismatch')
    for part,spec in data['partitions'].items():
        with archive.open(part+'.img') as stream: validate_stream(stream,spec)


def check(root, stage, repo=REPO):
    if root.is_symlink() or not root.is_dir(): raise ValueError('invalid S10 staging directory')
    names = [p.relative_to(root).as_posix() for p in root.rglob('*')]
    if stage == 'work':
        for name in names:
            if '/' not in name and any(name == p or name.startswith(p+'.') for p in (*NAMES,'up_param')):
                raise ValueError('auxiliary inputs must stay outside WORK_DIR')
    elif stage == 'package':
        approved_names(names); verify(root,repo)
        if (root/'auxiliary-source.json').read_bytes() != (repo/MANIFEST).read_bytes(): raise ValueError('auxiliary provenance mismatch')
    else: raise ValueError('unsupported stage')


if __name__ == '__main__':
    try:
        if len(sys.argv)!=3: raise ValueError('usage: s10_auxiliary_contract.py work|package ROOT')
        check(Path(sys.argv[2]),sys.argv[1])
    except (OSError,ValueError) as e: raise SystemExit(str(e))
