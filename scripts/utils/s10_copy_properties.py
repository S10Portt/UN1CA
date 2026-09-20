# SPDX-License-Identifier: GPL-3.0-or-later
"""Transfer known S10 source properties after partition copy; no generic prop editing."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from s10_metadata_plan import check_parents, item_kind


def read(path):
    check_parents(path)
    if item_kind(path) != 'file': raise ValueError('unsupported property input: ' + str(path))
    data = path.read_bytes()
    if not data or b'\0' in data: raise ValueError('empty/invalid property file')
    data.decode('utf-8')
    return data


def property_value(data, key, optional=False, nonempty=True):
    values = []
    for line in data.decode('utf-8').splitlines():
        if line.lstrip().startswith('#') or '=' not in line: continue
        name, value = line.split('=', 1)
        if name.strip() == key: values.append(value.strip())
    if not values and optional: return None
    if len(values) != 1 or (nonempty and not values[0]):
        raise ValueError('expected one valid property: ' + key)
    return values[0]


def replace(data, updates):
    # Validate all source/destination keys before producing any output.
    for key in updates: property_value(data, key, optional=True, nonempty=False)
    result = []; pending = dict(updates)
    for line in data.decode('utf-8').splitlines(keepends=True):
        if not line.lstrip().startswith('#') and '=' in line:
            key = line.split('=', 1)[0].strip()
            if key in pending:
                end = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
                result.append(key + '=' + pending.pop(key) + end)
                continue
        result.append(line)
    text = ''.join(result)
    for key, value in pending.items():
        if text and not text.endswith('\n'): text += '\n'
        text += key + '=' + value + '\n'
    after = text.encode('utf-8')
    for key, value in updates.items():
        if property_value(after, key, nonempty=False) != value: raise ValueError('output property mismatch')
    return after


def apply(stage, fw, work):
    source, target = fw/'SM-S908B_EUX', fw/'SM-G973F_AUT'
    snapshots = {}
    def snapshot(path):
        data = read(path); snapshots[path] = data; return data
    if stage == 'system':
        rel = 'system/system/build.prop'; original = source/rel
        updates = {'ro.product.device': property_value(snapshot(source/'odm/etc/build.prop'), 'ro.product.odm.device')}
    elif stage == 'vendor':
        rel = 'vendor/build.prop'; original = target/rel
        props = snapshot(source/rel)
        updates = {'ro.config.'+key: property_value(props, 'ro.config.'+key, nonempty=False) for key in
                   ('ringtone','notification_sound','alarm_alert','media_sound','ringtone_2','notification_sound_2')}
    elif stage == 'product':
        rel = 'product/etc/build.prop'; original = source/rel
        name = property_value(snapshot(target/'product/build.prop'), 'ro.product.product.name', optional=True)
        updates = {} if name is None else {'ro.product.product.name': name}
    else: raise ValueError('unsupported S10 property transfer stage')
    baseline = snapshot(original); planned = replace(baseline, updates)
    dest = work/rel; before = snapshot(dest)
    if before not in (baseline, planned): raise ValueError('destination differs from source-copy stage: ' + str(dest))
    for path, data in snapshots.items():
        if read(path) != data: raise ValueError('property input changed during planning')
    if before != planned:
        fd, name = tempfile.mkstemp(prefix='.s10-props-', dir=dest.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(planned); stream.flush(); os.fsync(stream.fileno())
            shutil.copymode(dest, name)
            if read(dest) != before: raise ValueError('destination changed before replacement')
            os.replace(name, dest)
        finally:
            if os.path.exists(name): os.unlink(name)
    if read(dest) != planned: raise ValueError('property result differs')
    return {'stage': stage, 'keys': list(updates), 'sha256_before': hashlib.sha256(before).hexdigest(),
            'sha256_after': hashlib.sha256(planned).hexdigest(),
            'scope': 'one property file transfer; Android metadata sidecars unchanged; no partition-copy transaction'}


if __name__ == '__main__':
    try:
        print(json.dumps(apply(sys.argv[1], Path(sys.argv[2]).absolute(), Path(sys.argv[3]).absolute())))
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        raise SystemExit('S10 property transfer failed: ' + str(error))
