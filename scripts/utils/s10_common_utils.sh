# SPDX-License-Identifier: GPL-3.0-or-later
# Strict metadata handling for the measured S10 port only.

_MATCH_METADATA_LINE()
{
    if [[ "${STRICT_RAW_METADATA:-false}" == "true" ]]; then
        awk 'BEGIN { key=ARGV[1]; ARGV[1]="" }
            $1 == key { print; found++ }
            END { if (found != 1) exit 1 }' "$2" "$1"
    else
        grep -F "$2 " "$1"
    fi
}

_REMOVE_METADATA_KEY()
{
    local META="$1" KEY="$2" RECURSIVE="${3:-false}" COPY IS_CONTEXT=false
    [[ "$META" == */file_context-* ]] && IS_CONTEXT=true
    [[ -f "$META" && -r "$META" && ! -L "$META" ]] || return 1
    COPY=$(mktemp "${META}.edit.XXXXXX") || return 1
    cp -p -- "$META" "$COPY" || return 1
    awk 'function literal(value, i,c) {
            for (i=1;i<=length(value);i++) {
                c=substr(value,i,1)
                if (c=="\\") {
                    i++; if (i>length(value) || index(".+[]*",substr(value,i,1))==0) return 0
                } else if (index(".+[]*^$?{}()|",c)>0) return 0
            }
            return 1
        }
        BEGIN { key=ARGV[1]; recursive=ARGV[2]; context=ARGV[3]; ARGV[1]=""; ARGV[2]=""; ARGV[3]="" }
        /^[[:space:]]*#/ || NF==0 { print; next }
        context=="true" && !literal($1) { print; next }
        $1==key { next }
        recursive=="true" && index($1,key "/")==1 { next }
        { print }' "$KEY" "$RECURSIVE" "$IS_CONTEXT" "$META" > "$COPY" || return 1
    mv -f -- "$COPY" "$META" || return 1
}

ADD_TO_WORK_DIR()
{
    _CHECK_NON_EMPTY_PARAM "SOURCE" "$1" || return 1
    _CHECK_NON_EMPTY_PARAM "PARTITION" "$2" || return 1
    _CHECK_NON_EMPTY_PARAM "FILE" "$3" || return 1

    local SOURCE="$1"
    local PARTITION="$2"
    local FILE="$3"
    local METADATA_POLICY="${8:-}"
    local USER="$4"
    local GROUP="$5"
    local MODE="$6"
    local LABEL="$7"

    if [ ! -d "$SOURCE" ]; then
        if [ "$(cut -d "/" -f 2 -s <<< "$SOURCE")" ]; then
            SOURCE="$FW_DIR/$(cut -d "/" -f 1 <<< "$SOURCE")_$(cut -d "/" -f 2 <<< "$SOURCE")"
        else
            SOURCE="$SRC_DIR/prebuilts/samsung/$SOURCE"
        fi
    fi

    if [ ! -d "$SOURCE" ]; then
        LOGE "Folder not found: ${SOURCE//$SRC_DIR\//}"
        return 1
    fi

    if [[ "$TARGET_CODENAME" == "beyond1lte" && "$PARTITION" == "product" ]] &&
            { [[ "$SOURCE" == "$FW_DIR/SM-G973F_AUT" ]] ||
              [[ "$SOURCE/product" -ef "$FW_DIR/SM-G973F_AUT/product" ]]; }; then
        LOGE "HWC1 product is identity-only; copying it requires a separate metadata policy"
        return 1
    fi

    if ! IS_VALID_PARTITION_NAME "$PARTITION"; then
        LOGE "\"$PARTITION\" is not a valid partition name"
        return 1
    fi

    while [[ "${FILE:0:1}" == "/" ]]; do
        FILE="${FILE:1}"
    done

    local SOURCE_FILE="$SOURCE"
    local TARGET_FILE="$WORK_DIR"
    if [[ "$PARTITION" == "system_ext" ]]; then
        if [ -d "$SOURCE/system_ext" ]; then
            SOURCE_FILE+="/system_ext/$FILE"
        elif [ -d "$SOURCE/system/system/system_ext" ]; then
            SOURCE_FILE+="/system/system/system_ext/$FILE"
        else
            SOURCE_FILE+="/system/system_ext/$FILE"
        fi

        if $TARGET_OS_BUILD_SYSTEM_EXT_PARTITION; then
            TARGET_FILE+="/system_ext/$FILE"
        else
            PARTITION="system"
            FILE="system/system_ext/$FILE"
            TARGET_FILE+="/system/$FILE"
        fi
    elif [[ "$PARTITION" == "system" ]]; then
        if [ -d "$SOURCE/system/system" ]; then
            SOURCE_FILE+="/system/$FILE"
            TARGET_FILE+="/system/$FILE"
        else
            SOURCE_FILE+="/system/${FILE//system\//}"
            TARGET_FILE+="/system/system/${FILE//system\//}"
        fi
    else
        SOURCE_FILE+="/$PARTITION/$FILE"
        TARGET_FILE+="/$PARTITION/$FILE"
    fi

    if [[ -n "$METADATA_POLICY" && ( "$TARGET_CODENAME" != "beyond1lte" || "$SOURCE" != "$FW_DIR/"* ) ]]; then
        LOGE "S10 metadata policy requires a firmware input in the strict path"
        return 1
    fi
    # Firmware-derived S10 data must have unique, readable source/work metadata.
    # Explicit prebuilt assets retain the original interface.
    local STRICT_RAW_METADATA=false META_FILE S10_PLAN_FILE
    local SOURCE_IS_DIR=false
    [[ -d "$SOURCE_FILE" && ! -L "$SOURCE_FILE" ]] && SOURCE_IS_DIR=true
    if [[ "$TARGET_CODENAME" == "beyond1lte" && "$SOURCE" == "$FW_DIR/"* ]]; then
        STRICT_RAW_METADATA=true
        S10_PLAN_FILE=$(mktemp "$WORK_DIR/configs/.s10-plan.XXXXXX") || return 1
        python3 "$SRC_DIR/scripts/utils/s10_metadata_plan.py" --policy "$METADATA_POLICY" \
            "$SOURCE" "$WORK_DIR" "$SOURCE_FILE" "$TARGET_FILE" "$PARTITION" \
            "$USER" "$GROUP" "$MODE" "$LABEL" > "$S10_PLAN_FILE" || return 1
        for META_FILE in "$SOURCE/fs_config-$PARTITION" "$SOURCE/file_context-$PARTITION" \
            "$WORK_DIR/configs/fs_config-$PARTITION" "$WORK_DIR/configs/file_context-$PARTITION"; do
            [[ -f "$META_FILE" && -r "$META_FILE" && ! -L "$META_FILE" ]] || {
                LOGE "Missing readable S10 metadata: $META_FILE"
                return 1
            }
            local META_KIND="context" META_SCOPE="work"
            [[ "$META_FILE" == */fs_config-* ]] && META_KIND="fs"
            [[ "$META_FILE" == "$SOURCE/"* ]] && META_SCOPE="source"
            awk 'BEGIN { kind=ARGV[1]; scope=ARGV[2]; ARGV[1]=""; ARGV[2]="" }
                /^[[:space:]]*#/ || NF==0 { next }
                {
                    key=$1
                    if (kind=="fs") {
                        offset=0
                        if (NF==4 && $0~/^[[:space:]]/) { key=""; offset=-1 }
                        else if (NF!=5) exit 1
                        uid=$(2+offset); gid=$(3+offset); mode=$(4+offset); cap=$(5+offset)
                        if (uid!~/^[0-9]+$/ || gid!~/^[0-9]+$/ || uid>4294967295 || gid>4294967295 ||
                            mode!~/^[0-7]+$/ || length(mode)>4 || cap!~/^capabilities=0x[0-9a-fA-F]+$/ || length(cap)>31) exit 1
                    } else {
                        if (NF==2) context=$2
                        else if (scope=="work" && NF==3 && $2~/^-[bcdpls-]$/) {
                            key=key " " $2; context=$3
                        } else exit 1
                        if (context!~/^[^[:space:]:]+:[^[:space:]:]+:[^[:space:]:]+:[^[:space:]]+$/ && context!="<<none>>") exit 1
                    }
                    if (seen[key]++) exit 1
                }' "$META_KIND" "$META_SCOPE" "$META_FILE" || {
                LOGE "Invalid or duplicate S10 metadata: $META_FILE"
                return 1
            }
        done
    fi

    if [ ! -e "$SOURCE_FILE" ] && [ ! -L "$SOURCE_FILE" ]; then
        if [ -e "$SOURCE_FILE.00" ]; then
            LOG "- Adding $(sed -e "s|$WORK_DIR||" -e "s|/\.||" <<< "$TARGET_FILE") from ${SOURCE//$SRC_DIR\//}"
            mkdir -p "$(dirname "$TARGET_FILE")"
            EVAL "cat \"$SOURCE_FILE.\"[0-9][0-9] > \"$TARGET_FILE\"" || exit 1
        else
            LOGE "File not found: ${SOURCE_FILE//$SRC_DIR\//}"
            return 1
        fi
    else
        LOG "- Adding $(sed -e "s|$WORK_DIR||" -e "s|/\.||" <<< "$TARGET_FILE") from ${SOURCE//$SRC_DIR\//}"
        if "$SOURCE_IS_DIR"; then
            mkdir -p "$TARGET_FILE" || return 1
        else
            mkdir -p "$(dirname "$TARGET_FILE")" || return 1
        fi
        EVAL "cp -a -T \"$SOURCE_FILE\" \"$TARGET_FILE\"" || exit 1
    fi

    local ENTRY="${TARGET_FILE//$WORK_DIR\//}"
    [[ "$PARTITION" == "system" ]] && ENTRY="${ENTRY//system\/system\//system/}"
    ENTRY="${ENTRY%/.}"

    if ! _MATCH_METADATA_LINE "$WORK_DIR/configs/fs_config-$PARTITION" "$ENTRY" > /dev/null 2>&1; then
        if [ "$USER" ] && [ "$GROUP" ] && [ "$MODE" ]; then
            echo "$ENTRY $USER $GROUP $MODE capabilities=0x0" >> "$WORK_DIR/configs/fs_config-$PARTITION"
        elif _MATCH_METADATA_LINE "$SOURCE/fs_config-$PARTITION" "$ENTRY" > /dev/null 2>&1; then
            _MATCH_METADATA_LINE "$SOURCE/fs_config-$PARTITION" "$ENTRY" >> "$WORK_DIR/configs/fs_config-$PARTITION" || return 1
        else
            if "$STRICT_RAW_METADATA"; then
                LOGE "Required S10 metadata entry was not found; refusing defaults"
                return 1
            fi
            LOGW "No fs_config entry found for \"$ENTRY\" in \"${SOURCE//$SRC_DIR\//}\". Using default values"

            USER=0
            GROUP=0
            MODE=644
            if [ -d "$TARGET_FILE" ]; then
                [[ "$PARTITION" == "vendor" ]] && GROUP=2000
                MODE=755
            fi

            echo "$ENTRY $USER $GROUP $MODE capabilities=0x0" >> "$WORK_DIR/configs/fs_config-$PARTITION"
        fi
    fi

    if ! _MATCH_METADATA_LINE "$WORK_DIR/configs/file_context-$PARTITION" "/$(_HANDLE_SPECIAL_CHARS "$ENTRY")" > /dev/null 2>&1; then
        if [ "$LABEL" ]; then
            echo "/$(_HANDLE_SPECIAL_CHARS "$ENTRY") $LABEL" >> "$WORK_DIR/configs/file_context-$PARTITION"
        elif _MATCH_METADATA_LINE "$SOURCE/file_context-$PARTITION" "/$(_HANDLE_SPECIAL_CHARS "$ENTRY")" > /dev/null 2>&1; then
            _MATCH_METADATA_LINE "$SOURCE/file_context-$PARTITION" "/$(_HANDLE_SPECIAL_CHARS "$ENTRY")" >> "$WORK_DIR/configs/file_context-$PARTITION" || return 1
        else
            if "$STRICT_RAW_METADATA"; then
                LOGE "Required S10 metadata entry was not found; refusing defaults"
                return 1
            fi
            LOGW "No file_context entry found for \"$ENTRY\" in \"${SOURCE//$SRC_DIR\//}\". Using default value"

            LABEL="$(_GET_SELINUX_LABEL "$PARTITION" "/$ENTRY")"

            echo "/$(_HANDLE_SPECIAL_CHARS "$ENTRY") $LABEL" >> "$WORK_DIR/configs/file_context-$PARTITION"
        fi
    fi

    if "$STRICT_RAW_METADATA" || "$SOURCE_IS_DIR"; then
        local FILES
        if "$STRICT_RAW_METADATA"; then
            FILES=$(cat "$S10_PLAN_FILE") || return 1
        else
        FILES="$(find "${SOURCE_FILE%/.}")" || return 1
        FILES="${FILES//$SOURCE\//}"
        [[ "$PARTITION" == "system" ]] && FILES="${FILES//system\/system\//system/}"
        if ! $TARGET_OS_BUILD_SYSTEM_EXT_PARTITION; then
            FILES=$(sed -e 's|^system/system$|system|' -e 's|^system_ext/|system/system_ext/|' <<< "$FILES") || return 1
        fi

        fi

        while IFS= read -r f; do
            IS_VALID_PARTITION_NAME "$f" && continue

            if ! _MATCH_METADATA_LINE "$WORK_DIR/configs/fs_config-$PARTITION" "$f" > /dev/null 2>&1; then
                if _MATCH_METADATA_LINE "$SOURCE/fs_config-$PARTITION" "$f" > /dev/null 2>&1; then
                    _MATCH_METADATA_LINE "$SOURCE/fs_config-$PARTITION" "$f" >> "$WORK_DIR/configs/fs_config-$PARTITION" || return 1
                else
                    if "$STRICT_RAW_METADATA"; then
                        LOGE "Required S10 metadata entry was not found; refusing defaults"
                        return 1
                    fi
                    LOGW "No fs_config entry found for \"$f\" in \"${SOURCE//$SRC_DIR\//}\". Using default values"

                    USER=0
                    GROUP=0
                    MODE=644
                    if [ -d "$SOURCE/$f" ] || [ -d "$SOURCE/system/$f" ] || [ -d "$SOURCE/${f//system\//}" ]; then
                        [[ "$PARTITION" == "vendor" ]] && GROUP=2000
                        MODE=755
                    fi

                    echo "$f $USER $GROUP $MODE capabilities=0x0" >> "$WORK_DIR/configs/fs_config-$PARTITION"
                fi
            fi

            if ! _MATCH_METADATA_LINE "$WORK_DIR/configs/file_context-$PARTITION" "/$(_HANDLE_SPECIAL_CHARS "$f")" > /dev/null 2>&1; then
                if _MATCH_METADATA_LINE "$SOURCE/file_context-$PARTITION" "/$(_HANDLE_SPECIAL_CHARS "$f")" > /dev/null 2>&1; then
                    _MATCH_METADATA_LINE "$SOURCE/file_context-$PARTITION" "/$(_HANDLE_SPECIAL_CHARS "$f")" >> "$WORK_DIR/configs/file_context-$PARTITION" || return 1
                else
                    if "$STRICT_RAW_METADATA"; then
                        LOGE "Required S10 metadata entry was not found; refusing defaults"
                        return 1
                    fi
                    LOGW "No file_context entry found for \"$f\" in \"${SOURCE//$SRC_DIR\//}\". Using default value"

                    LABEL="$(_GET_SELINUX_LABEL "$PARTITION" "/$f")"

                    echo "/$(_HANDLE_SPECIAL_CHARS "$f") $LABEL" >> "$WORK_DIR/configs/file_context-$PARTITION"
                fi
            fi
        done <<< "$FILES"
    else
        local TMP="${TARGET_FILE%/.}"
        TMP="$(dirname "${TMP//$WORK_DIR\//}")"
        [[ "$PARTITION" == "system" ]] && TMP="${TMP//system\/system\//system/}"

        while [[ "$TMP" != "." ]]; do
            IS_VALID_PARTITION_NAME "$TMP" && break

            if ! _MATCH_METADATA_LINE "$WORK_DIR/configs/fs_config-$PARTITION" "$TMP" > /dev/null 2>&1; then
                if _MATCH_METADATA_LINE "$SOURCE/fs_config-$PARTITION" "$TMP" > /dev/null 2>&1; then
                    _MATCH_METADATA_LINE "$SOURCE/fs_config-$PARTITION" "$TMP" >> "$WORK_DIR/configs/fs_config-$PARTITION" || return 1
                else
                    if "$STRICT_RAW_METADATA"; then
                        LOGE "Required S10 metadata entry was not found; refusing defaults"
                        return 1
                    fi
                    LOGW "No fs_config entry found for \"$TMP\" in \"${SOURCE//$SRC_DIR\//}\". Using default values"

                    USER=0
                    GROUP=0
                    MODE=755
                    [[ "$PARTITION" == "vendor" ]] && GROUP=2000

                    echo "$TMP $USER $GROUP $MODE capabilities=0x0" >> "$WORK_DIR/configs/fs_config-$PARTITION"
                fi
            fi

            if ! _MATCH_METADATA_LINE "$WORK_DIR/configs/file_context-$PARTITION" "/$(_HANDLE_SPECIAL_CHARS "$TMP")" > /dev/null 2>&1; then
                if _MATCH_METADATA_LINE "$SOURCE/file_context-$PARTITION" "/$(_HANDLE_SPECIAL_CHARS "$TMP")" > /dev/null 2>&1; then
                    _MATCH_METADATA_LINE "$SOURCE/file_context-$PARTITION" "/$(_HANDLE_SPECIAL_CHARS "$TMP")" >> "$WORK_DIR/configs/file_context-$PARTITION" || return 1
                else
                    if "$STRICT_RAW_METADATA"; then
                        LOGE "Required S10 metadata entry was not found; refusing defaults"
                        return 1
                    fi
                    LOGW "No file_context entry found for \"$TMP\" in \"${SOURCE//$SRC_DIR\//}\". Using default value"

                    LABEL="$(_GET_SELINUX_LABEL "$PARTITION" "/$TMP")"

                    echo "/$(_HANDLE_SPECIAL_CHARS "$TMP") $LABEL" >> "$WORK_DIR/configs/file_context-$PARTITION"
                fi
            fi

            TMP="$(dirname "$TMP")"
        done
    fi

    if "$STRICT_RAW_METADATA"; then
        python3 "$SRC_DIR/scripts/utils/s10_metadata_plan.py" --verify-result --policy "$METADATA_POLICY" \
            "$SOURCE" "$WORK_DIR" "$SOURCE_FILE" "$TARGET_FILE" "$PARTITION" \
            "$USER" "$GROUP" "$MODE" "$LABEL" > /dev/null || return 1
        rm -f -- "$S10_PLAN_FILE" || return 1
    fi
    return 0
}

DELETE_FROM_WORK_DIR()
{
    _CHECK_NON_EMPTY_PARAM "PARTITION" "$1" || return 1
    _CHECK_NON_EMPTY_PARAM "FILE" "$2" || return 1

    local PARTITION="$1"
    local FILE="$2"

    if ! IS_VALID_PARTITION_NAME "$PARTITION"; then
        LOGE "\"$PARTITION\" is not a valid partition name"
        return 1
    fi

    while [[ "${FILE:0:1}" == "/" ]]; do
        FILE="${FILE:1}"
    done

    if ! $TARGET_OS_BUILD_SYSTEM_EXT_PARTITION && [[ "$PARTITION" == "system_ext" ]]; then
        PARTITION="system"
        FILE="system/system_ext/$FILE"
    fi

    local FILE_PATH="$WORK_DIR"
    case "$PARTITION" in
        "system_ext")
            if $TARGET_OS_BUILD_SYSTEM_EXT_PARTITION; then
                FILE_PATH+="/system_ext"
            else
                FILE_PATH+="/system/system/system_ext"
            fi
            ;;
        *)
            FILE_PATH+="/$PARTITION"
            ;;
    esac
    FILE_PATH+="/$FILE"

    if [ ! -e "$FILE_PATH" ] && [ ! -L "$FILE_PATH" ]; then
        LOGW "File not found: ${FILE_PATH//$WORK_DIR/}"
        return 0
    fi

    local IS_DIR=false
    [ -d "$FILE_PATH" ] && [ ! -L "$FILE_PATH" ] && IS_DIR=true

    LOG "- Deleting ${FILE_PATH//$WORK_DIR/}"
    rm -rf "$FILE_PATH" || return 1

    local KEY="$FILE"
    [[ "$PARTITION" != "system" ]] && KEY="$PARTITION/$KEY"
    _REMOVE_METADATA_KEY "$WORK_DIR/configs/fs_config-$PARTITION" "$KEY" "$IS_DIR" || return 1
    _REMOVE_METADATA_KEY "$WORK_DIR/configs/file_context-$PARTITION" \
        "/$(_HANDLE_SPECIAL_CHARS "$KEY")" "$IS_DIR" || return 1

    if [[ "$FILE" == *".so" ]]; then
        local LIB_LIST
        for LIB_LIST in "$WORK_DIR/system/system/etc/public.libraries"*.txt; do
            [[ -e "$LIB_LIST" || -L "$LIB_LIST" ]] || continue
            _REMOVE_METADATA_KEY "$LIB_LIST" "${FILE##*/}" || return 1
        done
    fi

    return 0
}
