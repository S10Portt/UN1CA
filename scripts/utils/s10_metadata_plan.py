#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pre-copy conflict guard. Does not certify SELinux resolution or mutate work.

Only accepts unchanged metadata or absent destination entries. A differing
source/work/module policy needs explicit review, not implicit precedence.
"""
import argparse
from pathlib import Path
import os
import re
import stat
import hashlib
import json


CONTEXT = re.compile(r"[A-Za-z0-9_]+:[A-Za-z0-9_]+:[A-Za-z0-9_]+:[A-Za-z0-9_:,.-]+")
TYPES = {'--', '-b', '-c', '-d', '-p', '-l', '-s'}


def item_kind(path, missing=False):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if missing:
            return None
        raise
    for check, name in ((stat.S_ISREG, 'file'), (stat.S_ISDIR, 'directory'), (stat.S_ISLNK, 'link')):
        if check(mode):
            return name
    raise ValueError(f'unsupported file kind: {path}')


def check_parents(path, missing=False):
    # Do not resolve Android links. Intermediate components must be real dirs.
    for parent in reversed(path.parents):
        kind = item_kind(parent, missing)
        if kind is not None and kind != 'directory':
            raise ValueError(f'intermediate path is not a real directory: {parent}')


def path_argument(value):
    if not value.startswith('/') or any(x in ('', '.', '..') for x in value.split('/')[1:]):
        raise ValueError(f'noncanonical absolute path: {value!r}')
    return Path(value)


def rows(path, kind):
    check_parents(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"invalid metadata file: {path}")
    result = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        fields = line.split()
        if kind == 'fs' and line[:1].isspace() and len(fields) == 4:
            fields.insert(0, '')
        key = fields[0]
        if kind == 'fs':
            if len(fields) != 5 or not all(re.fullmatch(r'[0-9]+', x) for x in fields[1:3]):
                raise ValueError(f"invalid fs row: {path}:{number}")
            if not re.fullmatch(r'[0-7]{1,4}', fields[3]) or not re.fullmatch(r'capabilities=0x[0-9a-fA-F]{1,16}', fields[4]):
                raise ValueError(f"invalid mode/capability: {path}:{number}")
            value = tuple(map(int, fields[1:3])) + (int(fields[3], 8), int(fields[4].split('=')[1], 16))
            if any(x > 0xffffffff for x in value[:2]):
                raise ValueError(f"invalid uid/gid: {path}:{number}")
        else:
            if len(fields) not in (2, 3):
                raise ValueError(f"invalid context: {path}:{number}")
            if (len(fields) == 3 and fields[1] not in TYPES) or not CONTEXT.fullmatch(fields[-1]):
                raise ValueError(f'invalid context/type: {path}:{number}')
            value = tuple(fields[1:])
        result.setdefault(key, []).append(value)
    return result


def context_key(path):
    if any(c.isspace() or c in r'\^$?{}()|' for c in path):
        raise ValueError(f"unsupported literal path: {path!r}")
    return '/' + ''.join('\\' + c if c in '.+[]*' else c for c in path)


def single(table, key, required):
    entries = table.get(key, [])
    if len(entries) > 1 or (required and not entries):
        raise ValueError(f"missing/ambiguous metadata key: {key!r}")
    return entries[0] if entries else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source'); p.add_argument('work'); p.add_argument('source_file'); p.add_argument('target_file')
    p.add_argument('--verify-result', action='store_true')
    p.add_argument('--policy', default='')
    p.add_argument('partition'); p.add_argument('uid'); p.add_argument('gid'); p.add_argument('mode'); p.add_argument('label')
    a = p.parse_args()
    selected_policy = None
    if a.policy:
        policy = json.loads(Path(__file__).with_name('s10_task_profile_policy.json').read_text())
        if a.policy != policy['id'] or a.partition != 'system':
            raise ValueError('unsupported explicit metadata policy')
        selected_policy = policy

    source, work = path_argument(a.source), path_argument(a.work)
    origin, destination = path_argument(a.source_file), path_argument(a.target_file)
    for root in (source, work):
        check_parents(root)
        if item_kind(root) != 'directory':
            raise ValueError(f'input root is not a real directory: {root}')
    check_parents(origin)
    check_parents(destination, missing=True)
    destination.relative_to(work / a.partition)
    source_partition = origin.relative_to(source).parts[0]
    if source_partition != a.partition:
        raise ValueError('cross-partition metadata remapping needs an explicit transfer policy')
    if origin == source / source_partition or destination == work / a.partition:
        raise ValueError('partition-root copy unsupported')
    if item_kind(origin, missing=True) is None:
        raise ValueError('missing or split source: no approved per-file metadata copy plan')
    source_tables = [rows(source / f'{prefix}-{source_partition}', kind) for prefix, kind in [('fs_config', 'fs'), ('file_context', 'context')]]
    work_tables = [rows(work / 'configs' / f'{prefix}-{a.partition}', kind) for prefix, kind in [('fs_config', 'fs'), ('file_context', 'context')]]
    def key(path, root, partition):
        value = path.relative_to(root).as_posix()
        if partition == 'system':
            value = value.removeprefix('system/')
        return value
    candidates = [(origin, destination)]
    if origin.is_dir() and not origin.is_symlink():
        def fail(error):
            raise error
        for parent, dirs, files in os.walk(origin, followlinks=False, onerror=fail):
            for name in dirs + files:
                path = Path(parent) / name
                candidates.append((path, destination / path.relative_to(origin)))
    # Include parents which ADD_TO_WORK_DIR may introduce metadata for.
    left, right = origin.parent, destination.parent
    while left != source / source_partition and right != work / a.partition:
        if left == source or right == work:
            raise ValueError('source/destination parent mapping mismatch')
        candidates.append((left, right)); left, right = left.parent, right.parent
    approved_keys = []
    for original, target in candidates:
        check_parents(original)
        check_parents(target, missing=True)
        original_kind = item_kind(original)
        target_kind = item_kind(target, missing=True)
        if target_kind is not None and target_kind != original_kind:
            raise ValueError(f'file-kind replacement needs explicit policy: {target}')
        src_key, dst_key = key(original, source, source_partition), key(target, work, a.partition)
        # Legacy ADD still consumes the same key for source and destination.
        if src_key != dst_key:
            raise ValueError(f'unsupported legacy key remapping: {src_key} -> {dst_key}')
        desired = single(source_tables[0], src_key, True)
        label = single(source_tables[1], context_key(src_key), True)
        if len(label) != 1:
            raise ValueError(f'typed source context needs policy: {src_key}')
        if original == origin:
            if selected_policy:
                rule = selected_policy['entries'].get(src_key)
                if rule is None or original_kind != 'file':
                    raise ValueError('metadata policy path/kind is outside approved scope')
                observed = {'uid': desired[0], 'gid': desired[1], 'mode': format(desired[2], 'o'),
                            'capabilities': hex(desired[3]), 'selinux': label[0]}
                with original.open('rb') as stream:
                    source_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if observed != rule['source'] or source_digest != rule['sha256']:
                    raise ValueError('metadata policy source content/metadata changed')
                if a.label != rule['target_label']:
                    raise ValueError('metadata policy requested label differs')
                label = (rule['target_label'],)
            provided = (a.uid, a.gid, a.mode)
            if any(provided) and not all(provided):
                raise ValueError('partial uid/gid/mode override is not supported')
            if all(provided):
                if desired[3] != 0:
                    raise ValueError(f'ADD override would erase source capability: {src_key}')
                if not re.fullmatch(r'[0-9]+', a.uid) or not re.fullmatch(r'[0-9]+', a.gid) or not re.fullmatch(r'[0-7]{1,4}', a.mode):
                    raise ValueError('invalid explicit uid/gid/mode')
                requested = (int(a.uid), int(a.gid), int(a.mode, 8), 0)
                if any(x > 0xffffffff for x in requested[:2]):
                    raise ValueError('explicit uid/gid outside 32-bit range')
                if requested != desired:
                    raise ValueError(f'new explicit field policy required: {src_key}')
            if a.label:
                if not CONTEXT.fullmatch(a.label):
                    raise ValueError('invalid explicit context')
                if (a.label,) != label:
                    raise ValueError(f'new explicit label policy required: {src_key}')
        for table, name, expected in [(work_tables[0], dst_key, desired), (work_tables[1], context_key(dst_key), label)]:
            current = single(table, name, False)
            if (target_kind is None) != (current is None):
                raise ValueError(f'file/metadata presence mismatch: {name}')
            if current is not None and current != expected:
                raise ValueError(f'source/work/module metadata conflict at {name}: explicit policy required')
        if a.verify_result:
            if target_kind != original_kind:
                raise ValueError(f'missing result or kind mismatch: {target}')
            if original_kind == 'link' and os.readlink(original) != os.readlink(target):
                raise ValueError(f'copied link target differs: {target}')
            if original_kind == 'file':
                def digest(path):
                    value = hashlib.sha256()
                    with path.open('rb') as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            value.update(block)
                    return value.digest()
                if digest(original) != digest(target):
                    raise ValueError(f'copied file content differs: {target}')
        approved_keys.append(dst_key)
    # Emitted only after ALL checks; ADD consumes this exact item/parent list.
    for name in dict.fromkeys(approved_keys):
        print(name)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f'S10 metadata copy plan rejected: {error}')
