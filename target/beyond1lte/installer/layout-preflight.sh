#!/sbin/sh
# Pre-write partition layout guard for beyond1lte.
#
# This build assumes the user-measured repartition profile
# "user-repartition-20260913" (target/beyond1lte/layouts/user-repartition-20260913.json,
# expected byte sizes sourced from target/beyond1lte/layouts/measurement/layout.json,
# sha256 5b331c34ceef922602b0ff3d771dc4bf19ac2f32ed5b0d89c3d62a8eb711e4db).
# It is NOT a stock/universal G973F or G973N layout. Before any
# block_image_update() call writes to a partition, confirm the device
# actually attached at install time has the exact same byte size this
# build expects -- fail closed (nonzero exit -> assert() aborts the
# install) rather than let block_image_update discover a mismatch
# mid-write.
#
# Scope: only the 6 partitions this installer actually writes
# (system/vendor/product/boot/dtb/dtbo). odm/prism/optics/up_param are
# preserve-only (never written by this installer, see
# target/beyond1lte/README.md) and are guarded at
# build time by scripts/utils/s10_installer_guard.py instead -- this
# script does not touch them.

# Check precisely the paths written by updater-script. No alternate alias fallback.
BLOCK_ROOT=/dev/block/by-name
SYS_CLASS_BLOCK=/sys/class/block

fail() {
    echo "layout-preflight: FAIL: $1" 1>&2
    exit 1
}

sysfs_size_path() {
    # Prints a readable <SYS_CLASS_BLOCK>/*/size path for device node $1,
    # searching both the flat and nested (holder/parent) layouts different
    # kernels expose, or nothing if not found.
    local devnode="$1"
    if [ -r "$SYS_CLASS_BLOCK/$devnode/size" ]; then
        echo "$SYS_CLASS_BLOCK/$devnode/size"
        return 0
    fi
    local candidate
    for candidate in "$SYS_CLASS_BLOCK"/*/"$devnode"/size; do
        if [ -r "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

# bytes_to_string(): formats sectors*512 for a log message without doing the
# multiplication in shell arithmetic. Some recovery shells (observed: TWRP's
# on this exact device) implement $(( )) with 32-bit signed integers, and
# sectors*512 for anything past ~4.19M sectors (~2GiB) silently wraps to a
# negative number -- this bit real S10 hardware for the 7GB system partition
# (14336000 * 512 overflowed to -1249902592). awk uses floating point (>15
# significant digits, exact for integers this size), so it is used here
# purely for the human-readable log line; it is never used for the pass/fail
# decision below, which compares sector counts directly and never multiplies.
bytes_to_string() {
    if command -v awk >/dev/null 2>&1; then
        awk "BEGIN { printf \"%.0f\", $1 * 512 }"
    else
        echo "${1} sectors (x512)"
    fi
}

check_partition() {
    local name="$1"
    local expected_sectors="$2"

    local link
    link="$BLOCK_ROOT/$name"
    [ -b "$link" ] || fail "write target is not a block device: $link"

    local real
    real="$(readlink -f "$link" 2>/dev/null)" || fail "cannot resolve $link"
    [ -n "$real" ] || fail "empty resolved path for $link"
    local devnode
    devnode="$(basename "$real")"

    local sizepath
    sizepath="$(sysfs_size_path "$devnode")" || fail "cannot resolve /sys/class/block size for '$name' (device $devnode)"

    local sectors
    sectors="$(cat "$sizepath" 2>/dev/null)"
    case "$sectors" in
        ''|*[!0-9]*) fail "non-numeric block size reported for '$name': '$sectors'" ;;
    esac

    # Compare sector counts directly -- no multiplication, so this cannot
    # overflow regardless of the shell's integer width.
    if [ "$sectors" != "$expected_sectors" ]; then
        fail "'$name' size mismatch: this build expects ${expected_sectors} sectors / $(bytes_to_string "$expected_sectors") bytes (user-repartition-20260913), device reports ${sectors} sectors / $(bytes_to_string "$sectors") bytes (${link} -> ${real}). This is very likely NOT the measured device; refusing to write."
    fi
    echo "layout-preflight: OK: $name = ${sectors} sectors / $(bytes_to_string "$sectors") bytes (${link})"
}

# Expected sizes in 512-byte sectors (bytes / 512, all exact -- see
# target/beyond1lte/layouts/measurement/layout.json): system=7340032000, vendor=product=
# 1572864000, boot=57671680, dtb=dtbo=8388608.
check_partition "system"  14336000
check_partition "vendor"  3072000
check_partition "product" 3072000
check_partition "boot"    112640
check_partition "dtb"     16384
check_partition "dtbo"    16384

echo "layout-preflight: PASSED"
exit 0
