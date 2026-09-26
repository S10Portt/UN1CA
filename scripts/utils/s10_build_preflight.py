#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail closed before tool setup, downloads, or S10 partition packaging."""
import argparse
import os
from pathlib import Path
import subprocess
from s10_firmware import verify, digest
from s10_auxiliary_images import verify as verify_auxiliary
from s10_apex_input import verify as verify_apex
from s10_metadata_plan import rows, context_key, item_kind


def kernel(repo):
    root = repo / 'target/beyond1lte/kernel'
    rows = [line.split() for line in (root / 'SHA256SUMS').read_text().splitlines()]
    if len(rows) != 3 or any(len(row) != 2 for row in rows):
        raise ValueError('invalid kernel checksum manifest')
    if {row[1] for row in rows} != {'boot.img', 'dtb.img', 'dtbo.img'}:
        raise ValueError('unexpected kernel image set')
    for sha, name in rows:
        path = root / name
        if path.is_symlink() or digest(path) != sha:
            raise ValueError('kernel checksum mismatch: ' + name)


def inputs(repo, fw):
    expected = {'SOURCE_FIRMWARE': 'SM-S901B/EUX', 'TARGET_FIRMWARE': 'SM-G973F/AUT',
                'SOURCE_FIRMWARE_OFFLINE': 'true', 'TARGET_FIRMWARE_OFFLINE': 'true',
                'SOURCE_EXTRA_FIRMWARES': '', 'TARGET_EXTRA_FIRMWARES': '',
                'TARGET_OS_FILE_SYSTEM_TYPE': 'erofs', 'TARGET_USE_DYNAMIC_PARTITIONS': 'false'}
    for key, value in expected.items():
        if os.environ.get(key, '') != value:
            raise ValueError('invalid S10 configuration: ' + key)
    profile = os.environ.get('TARGET_LAYOUT_PROFILE', '')
    keys = ('SYSTEM', 'VENDOR', 'PRODUCT', 'BOOT', 'DTB', 'DTBO')
    subprocess.run(['python3', str(repo / 'scripts/utils/s10_layout.py'), str(repo), profile, '--check',
                    *[f'TARGET_{k}_PARTITION_SIZE='+os.environ.get(f'TARGET_{k}_PARTITION_SIZE','') for k in keys]], check=True)
    kernel(repo)
    verify_auxiliary(Path(os.environ["OUT_DIR"]) / "inputs/s10-auxiliary", repo)
    for name in ('SM-S901B_EUX', 'SM-G973F_AUT'):
        verify(fw / name)
    verify_apex(fw.parent / 'apex-inputs/gzh3-bluetooth')


def work(root):
    partitions = {'system', 'vendor', 'product'}
    allowed = partitions | {'kernel', 'configs', '.completed'}
    if not partitions <= {p.name for p in root.iterdir()}:
        raise ValueError('incomplete S10 work tree')
    if any(p.name not in allowed for p in root.iterdir()):
        raise ValueError('unexpected auxiliary partition or artifact in work tree')
    if {p.name for p in (root/'kernel').iterdir()} != {'boot.img','dtb.img','dtbo.img'}:
        raise ValueError('unexpected packaged kernel set')
    for part in partitions:
        if (root/part).is_symlink():
            raise ValueError('linked work partition')
        for prefix in ('fs_config-', 'file_context-'):
            if not (root/'configs'/(prefix+part)).is_file():
                raise ValueError('missing work metadata')
    metadata(root)


def metadata(root):
    """Check complete final-tree metadata, after APK/RRO output creation."""
    for part in ('system', 'vendor', 'product'):
        fs = rows(root/'configs'/('fs_config-'+part), 'fs')
        fc = rows(root/'configs'/('file_context-'+part), 'context')
        paths = set()
        for parent, dirs, files in os.walk(root/part, followlinks=False):
            for name in dirs + files:
                path = Path(parent)/name
                item_kind(path)  # Refuse unsupported special inodes.
                relative = path.relative_to(root/part).as_posix()
                paths.add(relative if part == 'system' else part+'/'+relative)
        expected_contexts = {context_key(path) for path in paths}
        problems = {
            'missing ownership': paths - fs.keys(),
            'missing labels': expected_contexts - fc.keys(),
            'stale ownership': fs.keys() - paths - {'', part},
            'stale labels': fc.keys() - expected_contexts - {'/', '/'+part},
            'duplicate ownership': {key for key, values in fs.items() if len(values) != 1},
            'duplicate labels': {key for key, values in fc.items() if len(values) != 1},
        }
        for reason, keys in problems.items():
            if keys:
                raise ValueError(part + ': ' + reason + ': ' + ', '.join(sorted(keys)[:10]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('kernel','inputs','work','metadata'))
    p.add_argument('root',type=Path)
    p.add_argument('firmware',type=Path,nargs='?')
    a=p.parse_args()
    if a.action=='inputs':
        if a.firmware is None:raise ValueError('firmware root is required')
        inputs(a.root,a.firmware)
    elif a.action=='kernel':kernel(a.root)
    elif a.action=='metadata':metadata(a.root)
    else:work(a.root)

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as e:
        raise SystemExit('S10 preflight: '+str(e))
