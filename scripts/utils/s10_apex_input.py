#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Import a read-only mounted Bluetooth payload export for offline S10 builds.

The archive-to-image association relies on the operator's read-only collection.
Subsequent stages verify the pinned image and every registered payload entry.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
from s10_firmware import canonical, capabilities, digest, inventory

PAYLOAD_SHA256 = '54ce72bdcde6a08113a507a09dcbf17b9951c03cc73365882cdf3cd07dadf529'


def register(archive, image, destination):
    if digest(image) != PAYLOAD_SHA256:
        raise ValueError('unknown GZH3 Bluetooth payload')
    if destination.exists() or destination.is_symlink():
        raise ValueError('cache destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.resolve() != destination.parent.absolute():
        raise ValueError('linked destination parent')
    stage=Path(tempfile.mkdtemp(prefix='.s10-apex-',dir=destination.parent))
    try:
        payload=stage/'apex_payload';payload.mkdir()
        fs=[];contexts=[];seen=set();links=[]
        with tarfile.open(archive,'r:') as tar:
            for item in tar:
                key=item.name
                if key=='.':key=''
                elif key.startswith('./'):key=canonical(key[2:])
                else:key=canonical(key)
                if key in seen:raise ValueError('duplicate archive path')
                seen.add(key)
                if key=='lost+found' or key.startswith('lost+found/'):continue
                if not (item.isdir() or item.isreg() or item.issym()):raise ValueError('unsupported archive inode')
                if not key and not item.isdir():raise ValueError('invalid payload root')
                label=item.pax_headers.get('SCHILY.xattr.security.selinux','').rstrip('\0')
                if not re.fullmatch(r'[A-Za-z0-9_:,.-]+',label):raise ValueError('missing SELinux label')
                cap=capabilities(item.pax_headers.get('SCHILY.xattr.security.capability'))
                fs.append(f'{key} {item.uid} {item.gid} {item.mode:o} capabilities={cap:#x}\n')
                context='/'+key
                for char in '.+[]*':context=context.replace(char,'\\'+char)
                contexts.append(f'{context} {label}\n')
                path=payload/key
                path.parent.mkdir(parents=True,exist_ok=True)
                if item.isdir():path.mkdir(exist_ok=True)
                elif item.issym():links.append((path,item.linkname))
                else:
                    with tar.extractfile(item) as src,path.open('xb') as dst:shutil.copyfileobj(src,dst)
        for path,target in links:
            if path.exists() or path.is_symlink():raise ValueError('link overlaps archive descendants')
            path.symlink_to(target)
        expected={k for k in seen if k and k!='lost+found' and not k.startswith('lost+found/')}
        if '' not in seen or set(inventory(payload))!=expected:raise ValueError('archive inode coverage differs')
        (stage/'fs_config-apex_payload').write_text(''.join(sorted(fs)))
        (stage/'file_context-apex_payload').write_text(''.join(sorted(contexts)))
        record={'schema':1,'payload_sha256':PAYLOAD_SHA256,'archive_sha256':digest(archive),'entries':inventory(stage)}
        (stage/'.s10-cache.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
        stage.rename(destination)
    finally:
        if stage.exists():shutil.rmtree(stage)


def verify(cache):
    if cache.resolve()!=cache.absolute() or (cache/'.s10-cache.json').is_symlink():
        raise ValueError('linked payload cache')
    record=json.loads((cache/'.s10-cache.json').read_text())
    if record.get('schema')!=1 or record.get('payload_sha256')!=PAYLOAD_SHA256:
        raise ValueError('unexpected registered GZH3 payload')
    if record['entries']!=inventory(cache):raise ValueError('registered payload changed')


def stage(cache, image, destination):
    verify(cache)
    if digest(image)!=PAYLOAD_SHA256:raise ValueError('payload image differs')
    for name in ('apex_payload','fs_config-apex_payload','file_context-apex_payload'):
        if (destination/name).exists() or (destination/name).is_symlink():raise ValueError('payload destination already exists')
    shutil.copytree(cache/'apex_payload',destination/'apex_payload',symlinks=True)
    for name in ('fs_config-apex_payload','file_context-apex_payload'):shutil.copyfile(cache/name,destination/name)
    image.unlink()


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('register')
    for name in ('archive','image','destination'):a.add_argument(name,type=Path)
    a=sub.add_parser('stage')
    for name in ('cache','image','destination'):a.add_argument(name,type=Path)
    a=p.parse_args()
    if a.action=='register':register(a.archive,a.image,a.destination)
    else:stage(a.cache,a.image,a.destination)

if __name__=='__main__':main()
