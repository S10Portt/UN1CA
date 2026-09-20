#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Register mounted donor archives and verify immutable offline build inputs.

Android ownership, modes, labels and capabilities live in builder sidecars;
extracted host files deliberately retain unprivileged ownership.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import tarfile
import tempfile

PARTITIONS = ('system', 'product', 'vendor', 'odm', 'vendor_dlkm')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(name):
    if not name or name.startswith('/') or '..' in name.split('/') or str(PurePosixPath(name)) != name:
        raise ValueError('noncanonical input path: ' + repr(name))
    if any(c.isspace() or ord(c) < 32 for c in name) or any(c in name for c in '\\^$?{}()|'):
        raise ValueError('unsupported metadata path: ' + repr(name))
    return name


def capabilities(value):
    if value is None:
        return 0
    raw = value.encode('utf-8', 'surrogateescape')
    if len(raw) != 20:
        raise ValueError('unsupported capability revision/size')
    flags, lo, ilo, hi, ihi = struct.unpack('<5I', raw)
    if flags != 0x02000001 or ilo or ihi:
        raise ValueError('capability cannot be represented by fs_config')
    return lo | (hi << 32)


def inventory(root):
    result = {}
    def failed(error):
        raise error
    for base, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        for name in sorted(dirs + files):
            path = Path(base) / name
            key = path.relative_to(root).as_posix()
            if key == '.s10-cache.json':
                continue
            if path.is_symlink():
                result[key] = {'link': os.readlink(path)}
            elif path.is_dir():
                result[key] = {'directory': True}
            elif path.is_file():
                result[key] = {'sha256': digest(path)}
            else:
                raise ValueError('unsupported inode: ' + key)
    return result


def prop(file, key, expected):
    values = [line.split('=', 1)[1].strip() for line in file.read_text().splitlines()
              if '=' in line and line.split('=', 1)[0].strip() == key]
    if values != [expected]:
        raise ValueError('firmware identity mismatch: ' + key)


def identity(root):
    if root.name == 'SM-S901B_EUX':
        prop(root / 'system/system/build.prop', 'ro.build.version.incremental', 'S901BXXSOGZH3')
        prop(root / 'system/system/build.prop', 'ro.build.version.sdk', '36')
        parts = PARTITIONS
    elif root.name == 'SM-G973F_AUT':
        prop(root / 'vendor/build.prop', 'ro.vendor.build.version.incremental', 'G973FXXSGHWC1')
        prop(root / 'system/system/build.prop', 'ro.build.version.incremental', 'G973FXXSGHWC1')
        parts = ('system', 'vendor')
    else:
        raise ValueError('unsupported offline firmware identity')
    for part in parts:
        for prefix in ('file_context-', 'fs_config-'):
            path = root / (prefix + part)
            if path.is_symlink() or not path.is_file() or not path.stat().st_size:
                raise ValueError('missing Android inode metadata: ' + path.name)


def register(root):
    identity(root)
    path = root / '.s10-cache.json'
    if path.exists() or path.is_symlink():
        raise ValueError('registration already exists')
    record = {'schema': 1, 'input_id': root.name, 'entries': inventory(root)}
    path.write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')


def verify(root):
    if root.is_symlink() or root.resolve() != root.absolute():
        raise ValueError('linked firmware cache or parent')
    marker = root / '.s10-cache.json'
    if marker.is_symlink():
        raise ValueError('linked registration')
    record = json.loads(marker.read_text())
    if record.get('schema') != 1 or record.get('input_id') != root.name:
        raise ValueError('invalid registration schema/identity')
    identity(root)
    if record.get('entries') != inventory(root):
        raise ValueError('offline cache contents changed since registration')


def import_tar(archive, destination):
    if destination.name != 'SM-S901B_EUX' or destination.exists() or destination.is_symlink():
        raise ValueError('destination must be a new SM-S901B_EUX cache')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.resolve() != destination.parent.absolute():
        raise ValueError('linked destination parent')
    stage = Path(tempfile.mkdtemp(prefix='.s10-import-', dir=destination.parent))
    try:
        metadata = {p: [[], []] for p in PARTITIONS}
        links = []
        seen = set()
        with tarfile.open(archive, 'r:') as tar:
            for item in tar:
                name = canonical(item.name.rstrip('/'))
                part, _, relative = name.partition('/')
                if part not in metadata or name in seen:
                    raise ValueError('duplicate/unexpected archive member: ' + name)
                seen.add(name)
                path = stage / name
                if any(p.is_symlink() for p in path.parents):
                    raise ValueError('linked archive parent')
                if not (item.isdir() or item.isreg() or item.issym()):
                    raise ValueError('unsupported archive inode: ' + name)
                label = item.pax_headers.get('SCHILY.xattr.security.selinux', '').rstrip('\0')
                if not re.fullmatch(r'[A-Za-z0-9_:,.-]+', label):
                    raise ValueError('missing/unsupported SELinux label: ' + name)
                cap = capabilities(item.pax_headers.get('SCHILY.xattr.security.capability'))
                key = relative if part == 'system' else name
                fskey = key if relative else ''
                context = '/' + key if key else '/'
                for char in '.+[]*':
                    context = context.replace(char, '\\' + char)
                metadata[part][0].append(f'{fskey} {item.uid} {item.gid} {item.mode:o} capabilities={cap:#x}\n')
                metadata[part][1].append(f'{context} {label}\n')
                path.parent.mkdir(parents=True, exist_ok=True)
                if item.isdir():
                    path.mkdir(exist_ok=True)
                elif item.issym():
                    links.append((path, item.linkname))
                else:
                    with tar.extractfile(item) as src, path.open('xb') as dst:
                        shutil.copyfileobj(src, dst)
        if not set(PARTITIONS) <= seen:
            raise ValueError('missing partition roots')
        for path, target in links:
            if path.exists() or path.is_symlink():
                raise ValueError('symlink overlaps archive descendants')
            path.symlink_to(target)
        for part, (fs, labels) in metadata.items():
            (stage / ('fs_config-' + part)).write_text(''.join(sorted(fs)))
            (stage / ('file_context-' + part)).write_text(''.join(sorted(labels)))
        # Rename only after all archive members and identity have been checked.
        prop(stage / 'system/system/build.prop', 'ro.build.version.incremental', 'S901BXXSOGZH3')
        stage.rename(destination)
        try:
            register(destination)
            verify(destination)
        except Exception:
            destination.rename(stage)
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def import_hwc1(source, destination):
    """Import the established HWC1 cache only after its proof chain matches."""
    if source.name != 'SM-G973F_AUT' or destination.name != source.name:
        raise ValueError('expected HWC1 registration')
    if source.resolve() != source.absolute() or destination.exists() or destination.is_symlink():
        raise ValueError('linked source or existing destination')
    record = json.loads((source / '.s10-input.json').read_text())
    if record.get('schema') != 1 or record.get('input_id') != source.name or set(record['partitions']) != {'system', 'vendor'}:
        raise ValueError('invalid HWC1 proof identity')
    observed = inventory(source)
    for part, hashes in record['partitions'].items():
        proof = source / '.s10-proofs' / part
        if set(hashes) != {'paths.json','verification.json','conversion.json'}:
            raise ValueError('unexpected HWC1 proof set')
        for name, sha in hashes.items():
            if observed.get('.s10-proofs/'+part+'/'+name) != {'sha256': sha}:
                raise ValueError('HWC1 proof changed')
        conversion = json.loads((proof/'conversion.json').read_text())
        verification = json.loads((proof/'verification.json').read_text())
        paths = json.loads((proof/'paths.json').read_text())
        if (conversion.get('metadata_conversion') != 'complete' or conversion['partition'] != part
                or verification.get('archive_metadata_match') is not True
                or verification['conversion_sha256'] != hashes['conversion.json']
                or conversion['output_sha256']['paths.json'] != hashes['paths.json']):
            raise ValueError('invalid HWC1 metadata proof chain')
        expected = {}
        for relative, entry in paths.items():
            key = part + ('/'+canonical(relative) if relative else '')
            if entry['type']=='d': expected[key]={'directory': True}
            elif entry['type']=='l': expected[key]={'link': entry['link']}
            elif entry['type']=='f': expected[key]={'sha256': verification['file_sha256'][relative]}
            else: raise ValueError('unsupported HWC1 inode')
        actual = {k:v for k,v in observed.items() if k==part or k.startswith(part+'/')}
        if expected != actual: raise ValueError('HWC1 tree content differs')
        for prefix in ('fs_config-','file_context-'):
            name=prefix+part
            if observed.get(name) != {'sha256': conversion['output_sha256'][name]}:
                raise ValueError('HWC1 sidecar changed')
    if set(record['identity_files']) != {'product/build.prop','avb/vbmeta.img'}:
        raise ValueError('unexpected HWC1 identity scope')
    for name, sha in record['identity_files'].items():
        if observed.get(name) != {'sha256': sha}: raise ValueError('HWC1 identity file changed')
    roots={k.split('/')[0] for k in observed}
    if roots != {'system','vendor','product','avb','.s10-input.json','.s10-proofs',
                 'fs_config-system','fs_config-vendor','file_context-system','file_context-vendor'}:
        raise ValueError('unexpected HWC1 cache entries')
    for directory in ('product','avb'):
        if {k for k in observed if k.startswith(directory+'/')} != {k for k in record['identity_files'] if k.startswith(directory+'/')}:
            raise ValueError('HWC1 identity-only directory has extra files')
    identity(source)
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.parent.resolve()!=destination.parent.absolute():raise ValueError('linked destination parent')
    stage=Path(tempfile.mkdtemp(prefix='.s10-hwc1-',dir=destination.parent))
    try:
        shutil.copytree(source,stage,symlinks=True,dirs_exist_ok=True)
        if inventory(stage)!=observed:raise ValueError('HWC1 copy differs')
        stage.rename(destination)
        try:
            register(destination)
            verify(destination)
        except Exception:
            destination.rename(stage)
            raise
    finally:
        if stage.exists():shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('import-tar')
    p.add_argument('archive', type=Path)
    p.add_argument('destination', type=Path)
    p = sub.add_parser('import-hwc1')
    p.add_argument('source', type=Path)
    p.add_argument('destination', type=Path)
    p = sub.add_parser('verify')
    p.add_argument('root', type=Path)
    args = parser.parse_args()
    if args.action == 'import-tar':
        import_tar(args.archive, args.destination)
    elif args.action == 'import-hwc1':
        import_hwc1(args.source, args.destination)
    else:
        verify(args.root)
    print('Offline firmware input verified')


if __name__ == '__main__':
    main()
