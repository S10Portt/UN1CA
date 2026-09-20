# DELETE_FROM_WORK_DIR rewrites shared partition metadata files. S10 must
# serialize these read/modify/write operations, including sibling paths.
DEBLOAT_JOBS="$(nproc)" || return 1
if [[ "$TARGET_CODENAME" == "beyond1lte" ]]; then
    DEBLOAT_JOBS=1
fi

# Dexpreopt
find "$WORK_DIR/product" -type d -name "oat" -print0 | xargs -0 -I "{}" -P "$DEBLOAT_JOBS" \
    bash -c 'source "$SRC_DIR/scripts/utils/module_utils.sh" || exit 1; DELETE_FROM_WORK_DIR "product" "${1//$WORK_DIR\/product\//}"' "bash" "{}"
if [[ "$TARGET_CODENAME" == "beyond1lte" && "${PIPESTATUS[*]}" =~ [1-9] ]]; then
    LOGE "S10 debloat enumeration/deletion/logging pipeline failed"
    return 1
fi
find "$WORK_DIR/system" -type d -name "oat" -print0 | xargs -0 -I "{}" -P "$DEBLOAT_JOBS" \
    bash -c 'source "$SRC_DIR/scripts/utils/module_utils.sh" || exit 1; DELETE_FROM_WORK_DIR "system" "${1//$WORK_DIR\/system\//}"' "bash" "{}"
if [[ "$TARGET_CODENAME" == "beyond1lte" && "${PIPESTATUS[*]}" =~ [1-9] ]]; then
    LOGE "S10 debloat enumeration/deletion/logging pipeline failed"
    return 1
fi
DELETE_FROM_WORK_DIR "system" "system/etc/boot-image.bprof" || return 1
DELETE_FROM_WORK_DIR "system" "system/etc/boot-image.prof" || return 1
DELETE_FROM_WORK_DIR "system" "system/framework/arm" || return 1
DELETE_FROM_WORK_DIR "system" "system/framework/arm64" || return 1
find "$WORK_DIR/system/system/framework" -type f -name "*.vdex" -print0 | xargs -0 -I "{}" -P "$DEBLOAT_JOBS" \
    bash -c 'source "$SRC_DIR/scripts/utils/module_utils.sh" || exit 1; DELETE_FROM_WORK_DIR "system" "${1//$WORK_DIR\/system\//}"' "bash" "{}"
if [[ "$TARGET_CODENAME" == "beyond1lte" && "${PIPESTATUS[*]}" =~ [1-9] ]]; then
    LOGE "S10 debloat enumeration/deletion/logging pipeline failed"
    return 1
fi
if $TARGET_OS_BUILD_SYSTEM_EXT_PARTITION; then
    find "$WORK_DIR/system_ext" -type d -name "oat" -print0 | xargs -0 -I "{}" -P "$DEBLOAT_JOBS" \
        bash -c 'source "$SRC_DIR/scripts/utils/module_utils.sh" || exit 1; DELETE_FROM_WORK_DIR "system_ext" "${1//$WORK_DIR\/system_ext\//}"' "bash" "{}"
    if [[ "$TARGET_CODENAME" == "beyond1lte" && "${PIPESTATUS[*]}" =~ [1-9] ]]; then
        LOGE "S10 debloat enumeration/deletion/logging pipeline failed"
        return 1
    fi
fi

# ROM & device-specific debloat list
if [ -f "$SRC_DIR/unica/debloat.sh" ]; then
    source "$SRC_DIR/unica/debloat.sh"
fi
if [ -f "$SRC_DIR/platform/$TARGET_PLATFORM/debloat.sh" ]; then
    source "$SRC_DIR/platform/$TARGET_PLATFORM/debloat.sh"
fi
if [ -f "$SRC_DIR/target/$TARGET_CODENAME/debloat.sh" ]; then
    source "$SRC_DIR/target/$TARGET_CODENAME/debloat.sh"
fi

ODM_DEBLOAT="$(sed "/^$/d" <<< "$ODM_DEBLOAT" | sort)"
PRODUCT_DEBLOAT="$(sed "/^$/d" <<< "$PRODUCT_DEBLOAT" | sort)"
SYSTEM_DEBLOAT="$(sed "/^$/d" <<< "$SYSTEM_DEBLOAT" | sort)"
SYSTEM_EXT_DEBLOAT="$(sed "/^$/d" <<< "$SYSTEM_EXT_DEBLOAT" | sort)"
VENDOR_DEBLOAT="$(sed "/^$/d" <<< "$VENDOR_DEBLOAT" | sort)"

if [ "$ODM_DEBLOAT" ]; then
    xargs -I "{}" -P "$DEBLOAT_JOBS" \
        bash -c 'source "$SRC_DIR/scripts/utils/module_utils.sh" || exit 1; DELETE_FROM_WORK_DIR "odm" "$1"' "bash" "{}" \
        <<< "$ODM_DEBLOAT" 2>&1 | sed "/File not found/d"
    if [[ "$TARGET_CODENAME" == "beyond1lte" && "${PIPESTATUS[*]}" =~ [1-9] ]]; then
        LOGE "S10 debloat enumeration/deletion/logging pipeline failed"
        return 1
    fi
fi
if [ "$PRODUCT_DEBLOAT" ]; then
    xargs -I "{}" -P "$DEBLOAT_JOBS" \
        bash -c 'source "$SRC_DIR/scripts/utils/module_utils.sh" || exit 1; DELETE_FROM_WORK_DIR "product" "$1"' "bash" "{}" \
        <<< "$PRODUCT_DEBLOAT" 2>&1 | sed "/File not found/d"
    if [[ "$TARGET_CODENAME" == "beyond1lte" && "${PIPESTATUS[*]}" =~ [1-9] ]]; then
        LOGE "S10 debloat enumeration/deletion/logging pipeline failed"
        return 1
    fi
fi
if [ "$SYSTEM_DEBLOAT" ]; then
    xargs -I "{}" -P "$DEBLOAT_JOBS" \
        bash -c 'source "$SRC_DIR/scripts/utils/module_utils.sh" || exit 1; DELETE_FROM_WORK_DIR "system" "$1"' "bash" "{}" \
        <<< "$SYSTEM_DEBLOAT" 2>&1 | sed "/File not found/d"
    if [[ "$TARGET_CODENAME" == "beyond1lte" && "${PIPESTATUS[*]}" =~ [1-9] ]]; then
        LOGE "S10 debloat enumeration/deletion/logging pipeline failed"
        return 1
    fi
fi
if [ "$SYSTEM_EXT_DEBLOAT" ]; then
    xargs -I "{}" -P "$DEBLOAT_JOBS" \
        bash -c 'source "$SRC_DIR/scripts/utils/module_utils.sh" || exit 1; DELETE_FROM_WORK_DIR "system_ext" "$1"' "bash" "{}" \
        <<< "$SYSTEM_EXT_DEBLOAT" 2>&1 | sed "/File not found/d"
    if [[ "$TARGET_CODENAME" == "beyond1lte" && "${PIPESTATUS[*]}" =~ [1-9] ]]; then
        LOGE "S10 debloat enumeration/deletion/logging pipeline failed"
        return 1
    fi
fi
if [ "$VENDOR_DEBLOAT" ]; then
    xargs -I "{}" -P "$DEBLOAT_JOBS" \
        bash -c 'source "$SRC_DIR/scripts/utils/module_utils.sh" || exit 1; DELETE_FROM_WORK_DIR "vendor" "$1"' "bash" "{}" \
        <<< "$VENDOR_DEBLOAT" 2>&1 | sed "/File not found/d"
    if [[ "$TARGET_CODENAME" == "beyond1lte" && "${PIPESTATUS[*]}" =~ [1-9] ]]; then
        LOGE "S10 debloat enumeration/deletion/logging pipeline failed"
        return 1
    fi
fi

unset ODM_DEBLOAT PRODUCT_DEBLOAT SYSTEM_DEBLOAT SYSTEM_EXT_DEBLOAT VENDOR_DEBLOAT DEBLOAT_JOBS
