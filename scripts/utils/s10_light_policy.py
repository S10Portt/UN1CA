# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only pre/post validation of the S10 Light HAL destination policy."""
import hashlib
import json
from pathlib import Path
import sys
from s10_metadata_plan import rows, context_key, item_kind, check_parents


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(stage, assets, work):
    if stage not in ('pre', 'post'):
        raise ValueError('invalid Light policy stage')
    policy = json.loads(Path(__file__).with_suffix('.json').read_text())
    fs = rows(work/'configs/fs_config-vendor', 'fs')
    fc = rows(work/'configs/file_context-vendor', 'context')
    for e in policy['entries']:
        key = e['key']; source = assets/key; dest = work/key
        check_parents(source); check_parents(dest)
        if item_kind(source) != 'file' or digest(source) != e['sha256']:
            raise ValueError('unverified Light asset: ' + key)
        # All parents already exist; this transfer must not create parent policy.
        for parent in dest.parents:
            if parent == work: break
            if item_kind(parent) != 'directory': raise ValueError('invalid Light parent')
            parent_key = parent.relative_to(work).as_posix()
            if parent_key == 'vendor': continue
            if len(fs.get(parent_key, [])) != 1 or len(fc.get(context_key(parent_key), [])) != 1:
                raise ValueError('missing/ambiguous parent metadata: ' + parent_key)
        kind = item_kind(dest, missing=True)
        expected = [tuple(e['fs'])]; label = [(e['label'],)]
        if kind is None:
            if stage != 'pre' or e['expected_original_sha256'] is not None or key in fs or context_key(key) in fc:
                raise ValueError('unexpected absent Light destination: ' + key)
        else:
            if kind != 'file' or fs.get(key) != expected or fc.get(context_key(key)) != label:
                raise ValueError('Light destination metadata/type differs: ' + key)
            allowed = {e['sha256']}
            if stage == 'pre' and e['expected_original_sha256']:
                allowed.add(e['expected_original_sha256'])
            if digest(dest) not in allowed:
                raise ValueError('Light destination contents differ: ' + key)


if __name__ == '__main__':
    try:
        verify(sys.argv[1], Path(sys.argv[2]).absolute(), Path(sys.argv[3]).absolute())
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        raise SystemExit('S10 Light policy failed: ' + str(error))
