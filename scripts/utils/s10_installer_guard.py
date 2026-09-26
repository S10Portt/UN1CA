# SPDX-License-Identifier: GPL-3.0-or-later
"""Require the current unconditional S10 abort (or an explicitly, narrowly
authorized abort-removed state) and the original installer executable."""
import hashlib
import json
import re
import zipfile
from pathlib import Path
import sys
from s10_copy_properties import read

ABORT = 'abort("UN1CA S10 port is incomplete; installation is disabled.");'

# assertions.edify has exactly two accepted states:
#   1. safe/default: its only executable line is exactly ABORT.
#   2. deliberate test state: it contains at least one nonblank line and every
#      nonblank line is a comment (there is no executable Edify content).
#
# An empty/whitespace-only file is NOT accepted. A different abort, partially
# edited statement, or any other executable content still fails the build.
# This keeps abort removal explicit in the repository while preserving all
# unrelated installer guards below.

# Only up_param remains forbidden; auxiliaries require exact payload validation.
RESERVED_PARTITIONS = ('up_param',)
RESERVED_PATTERN = re.compile(r'(?:^|[^A-Za-z0-9_])up_param(?:[^A-Za-z0-9_]|$)')
from s10_auxiliary_contract import check as check_auxiliary, check_zip as check_auxiliary_zip

POSTINSTALL = (
    'assert(package_extract_file("auxiliary-postinstall.sh", "/tmp/auxiliary-postinstall.sh"));',
    'set_metadata("/tmp/auxiliary-postinstall.sh", "uid", 0, "gid", 0, "mode", 0755);',
    'assert(run_program("/tmp/auxiliary-postinstall.sh") == "0");',
)


def code(data):
    return [line.strip() for line in data.decode('utf-8').splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def _nonblank_lines(data):
    return [line.strip() for line in data.decode('utf-8').splitlines()
            if line.strip()]


def _assertions_abort_present(data):
    """Return True for the safe ABORT state, False for a documented comment-only state."""
    lines = _nonblank_lines(data)
    executable = code(data)

    if executable == [ABORT]:
        return True

    # Abort removal is allowed only when the file is non-empty and consists
    # entirely of comments. Empty/whitespace-only files are rejected.
    if not executable and lines and all(line.lstrip().startswith('#') for line in lines):
        return False

    raise ValueError(
        'S10 assertions must contain exactly the required abort, or be a '
        'non-empty comment-only file documenting deliberate abort removal'
    )


OS_PARTITIONS = ('system', 'vendor', 'product')
KERNEL_PARTITIONS = ('boot', 'dtb', 'dtbo')
AUX_PARTITIONS = ('odm', 'prism', 'optics')
PARTITIONS = OS_PARTITIONS + KERNEL_PARTITIONS + AUX_PARTITIONS
PREFLIGHT = (
    'assert(package_extract_file("layout-preflight.sh", "/tmp/layout-preflight.sh"));',
    'set_metadata("/tmp/layout-preflight.sh", "uid", 0, "gid", 0, "dmode", 0755, "fmode", 0755);',
    'assert(run_program("/tmp/layout-preflight.sh") == "0");',
)


def check_preflight(repo, script, packaged):
    source = read(repo/'target/beyond1lte/installer/layout-preflight.sh')
    if packaged != source:
        raise ValueError('packaged preflight differs from source')
    measurement = json.loads(read(repo/'target/beyond1lte/layouts/measurement/layout.json'))
    sizes = dict(re.findall(r'^check_partition "(\w+)"\s+(\d+)$',
                            source.decode(), re.M))
    if set(sizes) != set(PARTITIONS) or any(
            int(sizes[p]) * 512 != measurement['partition_bytes'][p]
            for p in PARTITIONS):
        raise ValueError('preflight sizes differ from measured layout')
    positions = []
    for statement in PREFLIGHT:
        if script.count(statement) != 1:
            raise ValueError('installer requires exactly one: ' + statement)
        positions.append(script.index(statement))
    if positions != sorted(positions):
        raise ValueError('preflight extraction/setup/execution out of order')
    allowed = {
        **{f'block_image_update("/dev/block/by-name/{p}", package_extract_file("{p}.transfer.list"), "{p}.new.dat.br", "{p}.patch.dat") ||': p
           for p in PARTITIONS[:3]},
        **{f'assert(package_extract_file("{p}.img", "/dev/block/by-name/{p}"));': p
           for p in PARTITIONS[3:]},
    }
    found = []
    for i, line in enumerate(script):
        if line in allowed:
            if i <= positions[-1]:
                raise ValueError('partition write before preflight')
            found.append(allowed[line])
        elif ('/dev/block/' in line or 'block_image_update(' in line
              or 'write_raw_image(' in line or 'format(' in line
              or 'mount(' in line or 'run_program(' in line
              or 'package_extract_dir(' in line
              or 'package_extract_file(' in line) and line not in PREFLIGHT + POSTINSTALL:
            raise ValueError('unexpected installer operation: ' + line)
    if sorted(found) != sorted(PARTITIONS):
        raise ValueError('installer must write exactly the nine approved partitions')


    post = []
    for statement in POSTINSTALL:
        if script.count(statement) != 1: raise ValueError('missing/duplicate auxiliary postinstall')
        post.append(script.index(statement))
    if post != sorted(post): raise ValueError('postinstall order')
    writes = {allowed[line]: i for i,line in enumerate(script) if line in allowed}
    if not max(writes[p] for p in OS_PARTITIONS) < min(writes[p] for p in AUX_PARTITIONS):
        raise ValueError('auxiliary writes must follow OS writes')
    if not max(writes[p] for p in AUX_PARTITIONS) < post[0] < post[-1] < min(writes[p] for p in KERNEL_PARTITIONS):
        raise ValueError('auxiliary postinstall must precede kernel writes')


def check_postinstall(repo, read_file):
    if read_file('auxiliary-postinstall.sh') != read(repo/'target/beyond1lte/installer/auxiliary-postinstall.sh'):
        raise ValueError('modified auxiliary postinstall script')


def check_transfer(data, limit):
    """Validate this full-OTA format; incremental/stash operations are not supported."""
    lines = data.decode('ascii').splitlines()
    if len(lines) < 5 or lines[0] != '4' or lines[2:4] != ['0', '0']:
        raise ValueError('expected version-4 full transfer list without stashes')
    if not lines[1].isdigit() or not 0 < int(lines[1]) <= limit:
        raise ValueError('invalid transfer block count')
    writes, erases = [], []
    for line in lines[4:]:
        fields = line.split()
        if len(fields) != 2 or fields[0] not in ('new', 'zero', 'erase'):
            raise ValueError('unexpected transfer command: ' + line)
        tokens = fields[1].split(',')
        if not all(t.isdigit() for t in tokens):
            raise ValueError('invalid transfer range')
        values = list(map(int, tokens))
        if values[0] != len(values)-1 or values[0] == 0 or values[0] % 2:
            raise ValueError('invalid range endpoint count')
        ranges = erases if fields[0] == 'erase' else writes
        for start, end in zip(values[1::2], values[2::2]):
            if not 0 <= start < end <= limit:
                raise ValueError('transfer range exceeds partition or is empty')
            ranges.append((start, end))
    # Erase may precede writes to the same blocks; it is a separate operation.
    for ranges in (writes, erases):
        ordered = sorted(ranges)
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ValueError('overlapping transfer ranges')



def check_transfers(repo, read_file):
    sizes = json.loads(read(repo/'target/beyond1lte/layouts/measurement/layout.json'))['partition_bytes']
    for part in PARTITIONS[:3]:
        check_transfer(read_file(part+'.transfer.list'), sizes[part]//4096)


def check_zip(repo, path):
    # Stream auxiliary payload hashes without extracting firmware images to disk.
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate ZIP entries')
        for name in names:
            base = Path(name).name
            if any(base == p or base.startswith(p + '.') for p in RESERVED_PARTITIONS):
                raise ValueError('reserved partition asset in ZIP: ' + name)
        script = code(archive.read('META-INF/com/google/android/updater-script'))
        validate_script(repo, script, archive.read('META-INF/com/google/android/update-binary'))
        check_preflight(repo, script, archive.read('layout-preflight.sh'))
        check_transfers(repo, archive.read)
        check_postinstall(repo, archive.read)
        check_auxiliary_zip(archive, repo)


def validate_script(repo, script, binary):
    abort_present = _assertions_abort_present(read(repo/'target/beyond1lte/installer/assertions.edify'))
    if not script:
        raise ValueError('empty installer')
    if abort_present:
        if script[0] != ABORT or script.count(ABORT) != 1:
            raise ValueError('required abort must be first')
    elif ABORT in script:
        raise ValueError('stale abort in installer')
    expected = (repo/'prebuilts/bootable/deprecated-ota/updater').read_bytes()
    if hashlib.sha256(binary).digest() != hashlib.sha256(expected).digest():
        raise ValueError('update-binary differs from required input')
    if any(RESERVED_PATTERN.search(line) for line in script):
        raise ValueError('reserved partition referenced in installer')


def check(repo, stage=None):
    _assertions_abort_present(read(repo/'target/beyond1lte/installer/assertions.edify'))
    if stage is None:
        return
    if stage.is_file():
        check_zip(repo, stage)
        return
    script = code(read(stage/'META-INF/com/google/android/updater-script'))
    validate_script(repo, script, (stage/'META-INF/com/google/android/update-binary').read_bytes())
    check_preflight(repo, script, read(stage/'layout-preflight.sh'))
    check_transfers(repo, lambda name: read(stage/name))
    check_postinstall(repo, lambda name: read(stage/name))
    check_auxiliary(stage, 'package', repo)
    for path in stage.rglob('*'):
        if path.is_file() and any(path.name == p or path.name.startswith(p + '.')
                                  for p in RESERVED_PARTITIONS):
            raise ValueError('reserved partition asset: ' + path.name)


if __name__ == '__main__':
    try:
        if len(sys.argv) not in (2,3): raise ValueError('usage: s10_installer_guard.py REPO [STAGE_OR_ZIP]')
        check(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv)==3 else None)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        print(f'S10 installer: {exc}',file=sys.stderr)
        sys.exit(1)
