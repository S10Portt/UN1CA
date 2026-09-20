# SPDX-License-Identifier: GPL-3.0-or-later
"""S10 portrait compatibility, invoked only by the camera module during a build.

Reference: sixteen fc385707, unica/patches/miscs/customize.sh.
Validate the entire six-library result before changing any file. An observed
post-patch hash is required even for a raw input; pattern presence is insufficient.
This script must not be executed during source-only porting review.
"""

import hashlib
import json
import os
from pathlib import Path
import sys


OLD = b"ro.product.name"
NEW = b"ro.unica.camera"
LIBRARIES = {
    f"vendor/{abi}/{name}"
    for abi in ("lib", "lib64")
    for name in (
        "libDualCamBokehCapture.camera.samsung.so",
        "liblivefocus_capture_engine.so",
        "liblivefocus_preview_engine.so",
    )
}


def read_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"not a supported regular file: {path}")
    data = path.read_bytes()
    if not data:
        raise ValueError(f"empty input: {path}")
    return data


def property_value(text, key):
    values = [
        line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if "=" in line and line.split("=", 1)[0].strip() == key
    ]
    if len(values) != 1 or not values[0]:
        raise ValueError(f"expected exactly one nonempty {key}")
    return values[0]


def property_lines(text, key, value, allow_change=False):
    lines = text.splitlines()
    positions = [
        i for i, line in enumerate(lines)
        if "=" in line and line.split("=", 1)[0].strip() == key
    ]
    if len(positions) > 1:
        raise ValueError(f"duplicate {key}")
    if positions:
        if not allow_change and property_value(text, key) != value:
            raise ValueError(f"conflicting {key}")
        lines[positions[0]] = f"{key}={value}"
    else:
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def replace_checked(path, before, after):
    # Preserve inode, ownership, mode and xattrs. Any failure aborts the module;
    # the multi-file operation is not a transaction and must not mark completion.
    if read_file(path) != before:
        raise ValueError(f"input changed during portrait preparation: {path}")
    if before == after:
        return
    with path.open("r+b") as stream:
        if stream.write(after) != len(after):
            raise OSError(f"short write: {path}")
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())
    if read_file(path) != after:
        raise ValueError(f"portrait write verification failed: {path}")


def prepare(work, stock, manifest):
    provenance = json.loads(read_file(manifest))
    hashes = provenance["sha256"]
    raw_hashes = provenance["raw_sha256"]
    counts = provenance["replacement_count"]
    if any(set(mapping) != LIBRARIES for mapping in (hashes, raw_hashes, counts)):
        raise ValueError("portrait manifest must describe exactly six raw/result libraries")
    pending = []
    states = set()
    for relative in sorted(LIBRARIES):
        path = work / relative
        data = read_file(path)
        # Reference miscs replaces all literal occurrences, including strings
        # that are not NUL-terminated property names. HWC1 has three per file.
        if counts[relative] != 3:
            raise ValueError(f"unexpected recorded replacement count: {relative}")
        if data.count(OLD) == 3 and data.count(NEW) == 0:
            if hashlib.sha256(data).hexdigest() != raw_hashes[relative]:
                raise ValueError(f"unverified raw portrait input: {relative}")
            result = data.replace(OLD, NEW)
            state = "raw"
        elif data.count(OLD) == 0 and data.count(NEW) == 3:
            result = data
            state = "patched"
        else:
            raise ValueError(f"unknown portrait property state: {relative}")
        if hashlib.sha256(result).hexdigest() != hashes[relative]:
            raise ValueError(f"unverified portrait library result: {relative}")
        pending.append((path, data, result))
        states.add(state)
    if len(states) != 1:
        raise ValueError("mixed raw/patched portrait library set")

    stock_props = read_file(stock / "system/system/build.prop").decode()
    if property_value(stock_props, "ro.product.system.name") != "beyond1ltexx":
        raise ValueError("portrait stock identity must be beyond1ltexx")
    flavor = property_value(stock_props, "ro.build.flavor")
    if flavor != "beyond1ltexx-user":
        raise ValueError("portrait stock flavor differs from observed working S10")
    prop_path = work / "system/system/build.prop"
    props = read_file(prop_path)
    result_props = property_lines(props.decode(), "ro.unica.camera", "beyond1ltexx")
    result_props = property_lines(result_props, "ro.build.flavor", flavor, allow_change=True)
    context_path = work / "system/system/etc/selinux/plat_property_contexts"
    contexts = read_file(context_path)
    lines = contexts.decode().splitlines()
    expected = "ro.unica.camera u:object_r:build_prop:s0 exact string"
    existing = [line.split() for line in lines if line.split()[:1] == ["ro.unica.camera"]]
    if existing and existing != [expected.split()]:
        raise ValueError("conflicting or duplicate portrait property context")
    result_contexts = contexts if existing else (contexts.decode().rstrip("\n") + "\n" + expected + "\n").encode()

    # All inputs are validated before the first mutation. System requirements
    # apply in both states, even when no vendor library needs rewriting.
    pending += [(prop_path, props, result_props.encode()), (context_path, contexts, result_contexts)]
    for path, before, after in pending:
        replace_checked(path, before, after)
    print(f"S10 portrait properties prepared (vendor input: {next(iter(states))})")


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4:
            raise ValueError("expected work root, stock root and portrait manifest")
        prepare(*(Path(arg) for arg in sys.argv[1:]))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"S10 portrait compatibility failed: {error}", file=sys.stderr)
        sys.exit(1)
