#!/sbin/sh
# Only the three packaged ext4 auxiliary images may be repaired/expanded.
fail() { echo "auxiliary-postinstall: FAIL: $1" >&2; exit 1; }
FSCK=/sbin/e2fsck
RESIZE=/sbin/resize2fs
[ -x "$FSCK" ] || FSCK=/bin/e2fsck
[ -x "$RESIZE" ] || RESIZE=/bin/resize2fs
[ -x "$FSCK" ] && [ -x "$RESIZE" ] || fail "required ext4 tools missing"
for part in odm prism optics; do
    dev="/dev/block/by-name/$part"
    [ -b "$dev" ] || fail "missing block target $part"
    real="$(readlink -f "$dev")" || fail "cannot resolve $part"
    while read -r source point remainder; do
        resolved="$(readlink -f "$source" 2>/dev/null)"
        [ "$resolved" != "$real" ] && [ "$point" != "/$part" ] || fail "mounted target $part"
    done < /proc/mounts
    "$FSCK" -f -p "$dev"
    rc=$?
    case "$rc" in 0|1) ;; *) fail "e2fsck $part returned $rc" ;; esac
    "$RESIZE" "$dev" || fail "resize2fs failed for $part"
done
exit 0
