# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate replacement input before removing the existing MIDAS directory."""
import hashlib
import json
from pathlib import Path
import sys
from s10_metadata_plan import rows, context_key, check_parents, item_kind


def verify(root):
    policy = json.loads(Path(__file__).with_suffix('.json').read_text())
    fs = rows(root/'fs_config-vendor', 'fs')
    fc = rows(root/'file_context-vendor', 'context')
    tree = root/'vendor/etc/midas'
    check_parents(tree)
    if item_kind(tree) != 'directory': raise ValueError('invalid MIDAS root')
    observed = {p.relative_to(root).as_posix() for p in [tree, *tree.rglob('*')]}
    if observed != {e['key'] for e in policy['entries']}:
        raise ValueError('MIDAS asset path coverage changed')
    for e in policy['entries']:
        path = root/e['key']; check_parents(path)
        if item_kind(path) != e['kind']:
            raise ValueError('MIDAS asset type changed: ' + e['key'])
        if e['kind'] == 'file' and hashlib.sha256(path.read_bytes()).hexdigest() != e['sha256']:
            raise ValueError('MIDAS asset changed: ' + e['key'])
        if fs.get(e['key']) != [tuple(e['fs'])] or fc.get(context_key(e['key'])) != [tuple(e['context'])]:
            raise ValueError('MIDAS asset metadata changed: ' + e['key'])


if __name__ == '__main__':
    try:
        verify(Path(sys.argv[1]).absolute())
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        raise SystemExit('S10 MIDAS input failed before deletion: ' + str(error))
