# SPDX-License-Identifier: GPL-3.0-or-later
"""Guard the explicitly selected destination-retention policies before asset copying."""
import hashlib
import json
from pathlib import Path
import sys
from s10_metadata_plan import rows, context_key, item_kind, check_parents


def verify(module, work, source):
    rel = module.relative_to(source).as_posix()
    policy = json.loads((Path(__file__).with_suffix('.json')).read_text())
    entries = [e for e in policy['entries'] if e['module'] == rel]
    if not entries:
        raise ValueError('missing platform asset retention policy: ' + rel)
    tables = {}
    for e in entries:
        key = e['key']; part = key.split('/')[0]
        for root, config, essi_root in ((module, module, False), (work, work/'configs', True)):
            # ESSI merges system/vendor/product/odm into one system image; the
            # "system" partition's real content sits one level deeper than the
            # fs_config key implies. Mirrors ADD_TO_WORK_DIR in common_utils.sh.
            if essi_root and part == 'system':
                path = root/'system'/'system'/key.replace('system/', '')
            else:
                path = root/key
            check_parents(path)
            if item_kind(path) != e['kind']:
                raise ValueError('asset/destination type differs: ' + str(path))
            for prefix, kind, expected, lookup in (
                    ('fs_config-', 'fs', tuple(e['expected_fs']), key),
                    ('file_context-', 'context', tuple(e['expected_context']), context_key(key))):
                file = config/(prefix+part)
                if file not in tables: tables[file] = rows(file, kind)
                if tables[file].get(lookup) != [expected]:
                    raise ValueError('unapproved metadata policy: ' + str(file) + ':' + key)
        if e['kind'] == 'file' and hashlib.sha256((module/key).read_bytes()).hexdigest() != e['asset_sha256']:
            raise ValueError('replacement asset changed: ' + key)


if __name__ == '__main__':
    try:
        verify(*(Path(p).absolute() for p in sys.argv[1:4]))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit('S10 asset policy failed: ' + str(error))
