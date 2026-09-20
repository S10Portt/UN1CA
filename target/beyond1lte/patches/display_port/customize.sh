# SPDX-License-Identifier: GPL-3.0-or-later
python3 "$SRC_DIR/scripts/utils/s10_display_port.py" "$WORK_DIR/system/system/bin/surfaceflinger" || ABORT "Unregistered S10 display donor"
