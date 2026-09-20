LOG "- Setting key code 703 to VOICE_ASSIST"
KEYLAYOUT="$WORK_DIR/system/system/usr/keylayout/Generic_internal.kl"
if grep -q -E '^key[[:space:]]+703[[:space:]]+WINK([[:space:]]|$)' "$KEYLAYOUT"; then
    sed -i -E '/^key[[:space:]]+703[[:space:]]+WINK([[:space:]]|$)/s/WINK/VOICE_ASSIST/' "$KEYLAYOUT"
elif ! grep -q -E '^key[[:space:]]+703[[:space:]]+VOICE_ASSIST([[:space:]]|$)' "$KEYLAYOUT"; then
    ABORT "Key 703 does not match the Exynos 9820 reference"
    return 1
fi
unset KEYLAYOUT
