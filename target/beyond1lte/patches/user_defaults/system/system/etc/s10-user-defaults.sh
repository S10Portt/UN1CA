#!/system/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# One-time Settings migration for clean installs and data-preserving upgrades.
# Later user animation preferences survive reboot. Retry after failure next boot.
MARKER=artisanrom_s10_animation_defaults_version
if [ "$(settings get global "$MARKER")" = "1" ]; then
    exit 0
fi

for KEY in window_animation_scale transition_animation_scale animator_duration_scale; do
    settings put global "$KEY" 0.5 || exit 1
    VALUE="$(settings get global "$KEY")" || exit 1
    case "$VALUE" in
        0.5|0.50|0.500) ;;
        *) exit 1 ;;
    esac
done
settings put global "$MARKER" 1
