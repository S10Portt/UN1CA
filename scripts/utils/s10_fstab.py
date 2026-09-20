#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""S10 OS fstab update; preserves data and unresolved auxiliary mount entries.

Only ext4/EROFS system/vendor/product policies are implemented. A successful
update does not certify fs_mgr flags, auxiliary mounts, or installed images.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

OS_MOUNTS = {'/system': 'system', '/vendor': 'vendor', '/product': 'product'}


def transform(text, filesystem):
    if filesystem not in {'ext4', 'erofs'}:
        raise ValueError('S10 fstab supports only ext4 or erofs OS policy')
    result, changes, seen = [], [], {}
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        body = line.split('#', 1)[0]
        fields = body.split()
        if not fields:
            result.append(line)
            continue
        if len(fields) < 2:
            raise ValueError(f'malformed fstab row {number}')
        partition = OS_MOUNTS.get(fields[1])
        if fields[1] == '/' and fields[0].rsplit('/', 1)[-1] == 'system':
            partition = 'system'
        if partition is None:
            result.append(line)  # /data, ODM, prism/optics and other rows are byte-preserved.
            continue
        if len(fields) != 5:
            raise ValueError(f'expected five fields at OS row {number}')
        if fields[0].rsplit('/', 1)[-1] != partition or '/by-name/' not in fields[0]:
            raise ValueError(f'unsupported S10 OS block path at row {number}')
        if fields[2] not in {'ext4', 'f2fs', 'erofs'}:
            raise ValueError(f'unsupported OS filesystem at row {number}')
        flags = fields[4].split(',')
        if any(flag.split('=', 1)[0] in {'logical', 'slotselect', 'slotselect_other'} for flag in flags):
            raise ValueError(f'dynamic/A-B fs_mgr flags in static S10 row {number}')
        rewritten = fields[:]
        rewritten[2:4] = [filesystem, 'ro']
        key = fields[1]
        if key in seen:
            # Alternative filesystem rows can collapse only when every final field agrees.
            if seen[key] != rewritten:
                raise ValueError(f'conflicting OS mount rows for {key}')
            changes.append({'line': number, 'mount': key, 'action': 'remove-equivalent-alternative'})
            continue
        seen[key] = rewritten
        if rewritten == fields:
            result.append(line)
        else:
            comment = (' #' + line.split('#', 1)[1].rstrip('\r\n')) if '#' in line else ''
            result.append('\t'.join(rewritten) + comment + ('\n' if line.endswith('\n') else ''))
            changes.append({'line': number, 'mount': key, 'before': fields, 'after': rewritten})
    return ''.join(result), changes, sorted(seen)


def prepare(root, filesystem):
    root = Path(os.path.abspath(root))
    for part in [*reversed(root.parents), root]:
        if part.is_symlink() or not part.is_dir():
            raise ValueError('unsupported input directory: ' + str(part))
    plans = []
    def fail(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        for name in sorted(files + dirs):
            if not name.startswith('fstab.') or name.endswith(('emmc', 'ramplus')):
                continue
            path = Path(directory) / name
            if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError('unsupported fstab entry: ' + str(path))
            before = path.read_bytes()
            after, changes, mounts = transform(before.decode('utf-8'), filesystem)
            plans.append((path, before, after.encode('utf-8'), changes, mounts))
    if not plans or not any(item[4] for item in plans):
        raise ValueError('no OS fstab entries found; refusing an empty successful plan')
    return plans


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--os-fs', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    plans = prepare(args.root, args.os_fs)  # Parse every input before modifying any file.
    reports = []
    for path, before, after, changes, mounts in plans:
        if args.apply and before != after:
            if path.read_bytes() != before:
                raise ValueError('fstab changed after planning: ' + str(path))
            fd, temp = tempfile.mkstemp(prefix='.s10-fstab-', dir=path.parent)
            os.close(fd)
            try:
                shutil.copy2(path, temp)
                Path(temp).write_bytes(after)
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        reports.append({'path': str(path), 'sha256_before': hashlib.sha256(before).hexdigest(),
                        'sha256_planned': hashlib.sha256(after).hexdigest(),
                        'os_mounts': mounts, 'changes': changes})
    print(json.dumps({'apply_requested': args.apply, 'files': reports,
                      'scope': 'OS fstab transformation only; auxiliary mount compatibility unverified'}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, UnicodeError, ValueError) as error:
        raise SystemExit('S10 fstab: ' + str(error))
