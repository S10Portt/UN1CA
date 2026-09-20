#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured user layout -> build limits. Does not authorize installation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys

PARTITIONS = ('system', 'vendor', 'product', 'boot', 'dtb', 'dtbo')
PROFILE = 'user-repartition-20260913'


def read(root, relative):
    path = Path(relative)
    if path.is_absolute() or any(p in ('..', '.') for p in path.parts):
        raise ValueError('noncanonical evidence path')
    current = root
    for component in path.parts:
        current = current / component
        if stat.S_ISLNK(current.lstat().st_mode):
            raise ValueError(f'evidence symlink: {current}')
    if not stat.S_ISREG(current.lstat().st_mode):
        raise ValueError(f'evidence is not a regular file: {current}')
    return current.read_bytes()


def load(root, selected):
    if selected != PROFILE:
        raise ValueError('select the measured user-repartition-20260913 profile explicitly')
    profile = json.loads(read(root, f'target/beyond1lte/layouts/{selected}.json'))
    if (profile['schema'] != 1 or profile['id'] != selected or
            profile['target'] != 'beyond1lte' or profile['installation_approved'] is not False or
            profile['auxiliary_policy'] != dict.fromkeys(('odm', 'prism', 'optics'), 'unresolved')):
        raise ValueError('unsupported profile/installation policy')
    raw = read(root, profile['measurement'])
    if hashlib.sha256(raw).hexdigest() != profile['measurement_sha256']:
        raise ValueError('layout measurement digest mismatch')
    measured = json.loads(raw)
    captures = {}
    for name, record in measured['files'].items():
        if Path(name).name != name:
            raise ValueError('invalid capture name')
        data = read(root, 'target/beyond1lte/layouts/measurement/' + name)
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError(f'capture digest mismatch: {name}')
        captures[name] = data.decode('utf-8')
    lines = captures['s10-partition-bytes.txt'].splitlines()
    if len(lines) % 2:
        raise ValueError('incomplete size capture')
    sizes = {}
    for name, value in zip(lines[::2], lines[1::2]):
        if name in sizes or not re.fullmatch(r'[1-9][0-9]*', value):
            raise ValueError('invalid/duplicate captured size')
        sizes[name] = int(value)
    links = {}
    for line in captures['s10-block-links-detail.txt'].splitlines():
        match = re.search(r' ([a-z0-9_]+) -> (/dev/block/[a-z0-9]+)$', line)
        if match:
            name, device = match.groups()
            if name in links:
                raise ValueError('duplicate captured link')
            links[name] = device
    blocks = {}
    for line in captures['s10-partitions.txt'].splitlines():
        fields = line.split()
        if len(fields) == 4 and all(x.isdecimal() for x in fields[:3]):
            if fields[3] in blocks:
                raise ValueError('duplicate proc partition')
            blocks[fields[3]] = int(fields[2]) * 1024
    for name, size in sizes.items():
        device = links[name]
        if (size != measured['partition_bytes'][name] or size % 512 or
                size != blocks[Path(device).name] or
                device != measured['by_name_entries'][name]):
            raise ValueError(f'inconsistent captured mapping: {name}')
    # ODM/prism/optics capacities are observations, not approved write targets.
    return {f'TARGET_{p.upper()}_PARTITION_SIZE': sizes[p] for p in PARTITIONS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('profile')
    parser.add_argument('--check', nargs='*', metavar='NAME=VALUE')
    args = parser.parse_args()
    expected = load(args.root, args.profile)
    if args.check is None:
        for name, value in expected.items():
            print(f'{name}\t{value}')
    else:
        actual = {}
        for entry in args.check:
            name, value = entry.split('=', 1)
            if name in actual:
                raise ValueError('duplicate effective size')
            actual[name] = value
        if actual != {k: str(v) for k, v in expected.items()}:
            raise ValueError('effective partition limits differ from selected layout; regenerate config')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'S10 layout: {exc}', file=sys.stderr)
        sys.exit(1)
