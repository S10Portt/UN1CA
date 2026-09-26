#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare and stage pinned raw ext4 inputs; never rebuild auxiliary filesystems."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[2]
MANIFEST = 'target/beyond1lte/auxiliary/artisan311.json'
NAMES = ('odm', 'prism', 'optics')


def manifest(repo=REPO):
    data = json.loads((repo/MANIFEST).read_text())
    if set(data['partitions']) != set(NAMES):
        raise ValueError('unexpected auxiliary partition set')
    sizes = json.loads((repo/'target/beyond1lte/layouts/measurement/layout.json').read_text())['partition_bytes']
    for name, spec in data['partitions'].items():
        if spec['filesystem'] != 'ext4' or spec['partition_bytes'] != sizes[name] or not 0 < spec['image_bytes'] <= sizes[name]:
            raise ValueError('invalid auxiliary geometry: '+name)
    return data


def digest(stream):
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024*1024), b''):
        h.update(chunk)
    return h.hexdigest()


def validate_stream(stream, spec):
    h = hashlib.sha256(); size = 0; header = b''
    for chunk in iter(lambda: stream.read(1024*1024), b''):
        if not size: header = chunk[:4096]
        size += len(chunk); h.update(chunk)
    if size != spec['image_bytes'] or h.hexdigest() != spec['sha256'] or header[1080:1082] != b'\x53\xef':
        raise ValueError('auxiliary image size/hash/ext4 mismatch')


def verify(root, repo=REPO):
    data = manifest(repo)
    for part, spec in data['partitions'].items():
        path = root/(part+'.img')
        if path.is_symlink() or not path.is_file(): raise ValueError('missing regular auxiliary input: '+part)
        with path.open('rb') as stream: validate_stream(stream, spec)
    return data


def ranges(text, limit):
    lines = text.decode('ascii').splitlines()
    if len(lines) < 5 or lines[0] != '4' or lines[2:4] != ['0', '0']: raise ValueError('unsupported transfer format')
    end = 0
    for line in lines[4:]:
        op, raw = line.split(); a = list(map(int, raw.split(',')))
        if op != 'new' or a[0] != len(a)-1 or a[0] <= 0 or a[0] % 2: raise ValueError('invalid full-image range')
        for start, stop in zip(a[1::2], a[2::2]):
            if start != end or not start < stop <= limit//4096: raise ValueError('noncontiguous/oversized range')
            end = stop
    if int(lines[1]) != end: raise ValueError('transfer block count mismatch')
    return end*4096


def prepare(source, output, repo=REPO):
    data = manifest(repo)
    if output.exists() or output.is_symlink(): raise ValueError('prepare requires a new output directory')
    with source.open('rb') as stream:
        if digest(stream) != data['source']['sha256']: raise ValueError('source ZIP hash mismatch')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.s10-aux-', dir=output.parent) as tmp, zipfile.ZipFile(source) as z:
        temp = Path(tmp); dest = temp/'images'; dest.mkdir()
        if len(z.namelist()) != len(set(z.namelist())): raise ValueError('duplicate ZIP entries')
        for part, spec in data['partitions'].items():
            if ranges(z.read(part+'.transfer.list'), spec['partition_bytes']) != spec['image_bytes']: raise ValueError('unexpected raw size')
            packed = temp/(part+'.br')
            with z.open(part+'.new.dat.br') as inp, packed.open('wb') as out: shutil.copyfileobj(inp, out)
            # Cap decompression at the approved image size.
            with (dest/(part+'.img')).open('wb') as out:
                proc = subprocess.Popen(['brotli','-dc',str(packed)], stdout=subprocess.PIPE)
                try:
                    left = spec['image_bytes']
                    while left:
                        chunk = proc.stdout.read(min(left, 1024*1024))
                        if not chunk: raise ValueError('truncated auxiliary image')
                        out.write(chunk); left -= len(chunk)
                    if proc.stdout.read(1): raise ValueError('oversized auxiliary image')
                    if proc.wait(): raise ValueError('brotli failed')
                finally:
                    if proc.poll() is None: proc.kill()
                    proc.wait(); proc.stdout.close()
        verify(dest, repo)
        if output.exists(): raise ValueError('output appeared during preparation')
        dest.rename(output)


def stage(source, output, repo=REPO):
    verify(source, repo)
    for part in NAMES:
        with (source/(part+'.img')).open('rb') as inp, (output/(part+'.img')).open('xb') as out: shutil.copyfileobj(inp,out)
    verify(output, repo)
    with (output/'auxiliary-source.json').open('xb') as out: out.write((repo/MANIFEST).read_bytes())


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['prepare','stage','verify'])
    p.add_argument('source',type=Path); p.add_argument('output',type=Path,nargs='?')
    a = p.parse_args()
    if a.operation != 'verify' and a.output is None: p.error('output required')
    if a.operation == 'prepare': prepare(a.source,a.output)
    elif a.operation == 'stage': stage(a.source,a.output)
    else: verify(a.source)
