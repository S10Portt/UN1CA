# Selected from the reference stock_blobs module; see target/beyond1lte/README.md
# Hotword and 32-bit WFD replacements still need base-specific validation.
LOG_STEP_IN "- Replacing GameDriver"
ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/priv-app/GameDriver-EX9820/GameDriver-EX9820.apk" 0 0 644 "u:object_r:system_file:s0"
ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/priv-app/DevGPUDriver-EX9820/DevGPUDriver-EX9820.apk" 0 0 644 "u:object_r:system_file:s0"
LOG_STEP_OUT

if [[ "$TARGET_CODENAME" == "beyond1lte" ]]; then
    # Match the SoundBooster library generation to HWC1 vendor parameter files.
    LOG_STEP_IN "- Replacing stock SoundBooster libs with the HWC1 (SM-G973F) donor's own matched version"
    ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/lib/lib_SoundBooster_ver1000.so" 0 0 644 "u:object_r:system_lib_file:s0"
    DELETE_FROM_WORK_DIR "system" "system/lib/lib_SoundBooster_ver1100.so"
    ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/lib/libsamsungSoundbooster_plus_legacy.so" 0 0 644 "u:object_r:system_lib_file:s0"
    ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/lib64/lib_SoundBooster_ver1000.so" 0 0 644 "u:object_r:system_lib_file:s0"
    DELETE_FROM_WORK_DIR "system" "system/lib64/lib_SoundBooster_ver1100.so"
    ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/lib64/libsamsungSoundbooster_plus_legacy.so" 0 0 644 "u:object_r:system_lib_file:s0"
    LOG_STEP_OUT

    # Restore legacy MFP libraries and system-side HIDL clients required by
    # the S10 camera nodes. Vendor copies are not visible in the app namespace.
    LOG_STEP_IN "- Adding HWC1 (SM-G973F) donor's own libMultiFrameProcessing{10,20,20Day}.camera.samsung.so (missing from GZD7, crashes stock Camera app's HIFI_LLS/LLHDR/MFHDR nodes)"
    for _MFP_VER in 10 20 20Day; do
        ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/lib/libMultiFrameProcessing${_MFP_VER}.camera.samsung.so" 0 0 644 "u:object_r:system_lib_file:s0"
        ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/lib64/libMultiFrameProcessing${_MFP_VER}.camera.samsung.so" 0 0 644 "u:object_r:system_lib_file:s0"
        if ! grep -qF "libMultiFrameProcessing${_MFP_VER}.camera.samsung.so" "$WORK_DIR/system/system/etc/public.libraries-camera.samsung.txt"; then
            EVAL "echo \"libMultiFrameProcessing${_MFP_VER}.camera.samsung.so\" >> \"$WORK_DIR/system/system/etc/public.libraries-camera.samsung.txt\""
        fi
    done
    unset _MFP_VER
    for _MFP_DEP in "vendor.samsung_slsi.hardware.iva@1.0.so" "vendor.samsung_slsi.hardware.MultiFrameProcessing20@1.0.so"; do
        ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/lib/${_MFP_DEP}" 0 0 644 "u:object_r:system_lib_file:s0"
        ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/lib64/${_MFP_DEP}" 0 0 644 "u:object_r:system_lib_file:s0"
    done
    unset _MFP_DEP
    LOG_STEP_OUT

    # GZD7 task profiles require sf and foreground-boost groups absent in HWC1.
    # Use HWC1 foreground/top-app CPU masks; root cpuset cpus is not writable.
    LOG_STEP_IN "- Restoring GZD7-expected 'sf'/'foreground-boost' cpuset groups in HWC1 (SM-G973F) vendor init (missing from stock S10, referenced by GZD7's task_profiles.json/surfaceflinger.rc)"
    _CPUSET_RC="$WORK_DIR/vendor/etc/init/init.exynos9820.rc"
    if [ ! -f "$_CPUSET_RC" ]; then
        LOGE "File not found: ${_CPUSET_RC//$WORK_DIR/}"
        return 1
    fi
    _CPUSET_BLOCK="$(
        {
            echo ""
            echo "# GZD7 compatibility cpusets (sf / foreground-boost) -- see target/beyond1lte/README.md"
            echo "on init"
            echo "    mkdir /dev/cpuset/sf"
            echo "    copy /dev/cpuset/cpus /dev/cpuset/sf/cpus"
            echo "    copy /dev/cpuset/mems /dev/cpuset/sf/mems"
            echo "    chown system system /dev/cpuset/sf/tasks"
            echo "    chown system system /dev/cpuset/sf/cgroup.procs"
            echo "    chown system system /dev/cpuset/sf/cpus"
            echo "    chmod 0664 /dev/cpuset/sf/cpus"
            echo "    write /dev/cpuset/sf/cpus 0-2,4-7"
            echo ""
            echo "    mkdir /dev/cpuset/foreground-boost"
            echo "    copy /dev/cpuset/cpus /dev/cpuset/foreground-boost/cpus"
            echo "    copy /dev/cpuset/mems /dev/cpuset/foreground-boost/mems"
            echo "    chown system system /dev/cpuset/foreground-boost"
            echo "    chown system system /dev/cpuset/foreground-boost/tasks"
            echo "    chown system system /dev/cpuset/foreground-boost/cgroup.procs"
            echo "    chown system system /dev/cpuset/foreground-boost/cpus"
            echo "    chmod 0664 /dev/cpuset/foreground-boost/tasks"
            echo "    chmod 0664 /dev/cpuset/foreground-boost/cgroup.procs"
            echo "    chmod 0664 /dev/cpuset/foreground-boost/cpus"
            echo "    write /dev/cpuset/foreground-boost/cpus 0-7"
        }
    )"
    if grep -qE '^[[:space:]]*mkdir /dev/cpuset/(sf|foreground-boost)([[:space:]]|$)' "$_CPUSET_RC"; then
        # A previous/partial patch must not silently suppress either group.
        while IFS= read -r _CPUSET_LINE; do
            [[ "$_CPUSET_LINE" == "    "* ]] || continue
            if ! grep -qxF "$_CPUSET_LINE" "$_CPUSET_RC"; then
                LOGE "Incomplete compatibility cpuset configuration: $_CPUSET_LINE"
                return 1
            fi
        done <<< "$_CPUSET_BLOCK"
    else
        printf '%s\n' "$_CPUSET_BLOCK" >> "$_CPUSET_RC"
    fi
    unset _CPUSET_RC _CPUSET_BLOCK _CPUSET_LINE
    LOG_STEP_OUT

    # Software A2DP default. The beyond1lte user_defaults module also restores
    # this after /data properties load, overriding a saved incompatible value.
    # Only SBC playback is validated; AAC/LDAC remain unverified.
    SET_PROP "system" "persist.bluetooth.a2dp_offload.disabled" "true"
fi

LOG_STEP_IN "- Adding stock NFC Case features"
ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/etc/permissions/com.sec.feature.cover.sview.xml" 0 0 644 "u:object_r:system_file:s0"
ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/etc/permissions/com.sec.feature.cover.xml" 0 0 644 "u:object_r:system_file:s0"
ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/etc/permissions/com.sec.feature.nfc_authentication_cover.xml" 0 0 644 "u:object_r:system_file:s0"
ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/etc/permissions/com.sec.feature.cover.clearcover.xml" 0 0 644 "u:object_r:system_file:s0"

if [[ "$TARGET_CODENAME" != "beyondx" ]]; then
    ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/etc/permissions/com.sec.feature.cover.flip.xml" 0 0 644 "u:object_r:system_file:s0"
    ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/etc/permissions/com.sec.feature.cover.ledbackcover.xml" 0 0 644 "u:object_r:system_file:s0"
    ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/etc/permissions/com.sec.feature.cover.nfcledcover.xml" 0 0 644 "u:object_r:system_file:s0"
fi

ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/priv-app/LedBackCoverAppBeyond/LedBackCoverAppBeyond.apk" 0 0 644 "u:object_r:system_file:s0"
ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "system/etc/permissions/privapp-permissions-com.samsung.android.app.ledbackcover.xml" 0 0 644 "u:object_r:system_file:s0"
LOG_STEP_OUT

LOG_STEP_IN "- Adding stock cutout assets"
DECODE_APK "system_ext" "priv-app/SystemUI/SystemUI.apk"
cp -a "$MODPATH/assets/"* "$APKTOOL_DIR/system_ext/priv-app/SystemUI/SystemUI.apk/assets/"
LOG_STEP_OUT
