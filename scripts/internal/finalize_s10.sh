#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -e
[[ "$TARGET_CODENAME" == "beyond1lte" ]] || exit 0
# QHD features replace SurfaceFlinger; validate and patch the final selected donor.
python3 -B "$SRC_DIR/scripts/utils/s10_display_port.py" \
    "$WORK_DIR/system/system/bin/surfaceflinger"
python3 -B "$SRC_DIR/scripts/utils/s10_hdmi_audio.py" \
    "$WORK_DIR/vendor/lib/hw/audio.primary.exynos9820.so"
python3 -B "$SRC_DIR/unica/patches/camera/s10_stagefright.py" \
    "$WORK_DIR/system/system/lib64/libstagefright.so"
python3 -B "$SRC_DIR/scripts/utils/s10_build_preflight.py" work "$WORK_DIR"
