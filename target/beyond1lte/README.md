# Galaxy S10 port

This target is under development. The installer intentionally aborts; a
successful host build is not permission to flash it.

## Fixed inputs and partition scope

Use S901B EUX GZH3 (Android 16) as the system donor, G973F AUT HWC1 as the
legacy vendor donor, and the pinned images under `kernel/`. Firmware names
are offline cache keys. The S10 build validates registrations before tool
setup and does not fall back to downloading another firmware version.

The `user-repartition-20260913` profile describes a measured repartitioned
beyond1lte, not a stock or universal SM-G973F/SM-G973N layout. Only boot, dtb,
dtbo, system, vendor and product may be written. ODM, prism, optics and
up_param remain preserved. Recovery checks the six write targets and their
exact sizes before writes; package validation also rejects reserved assets.

## Register local inputs

Prepare a complete read-only mounted donor export with numeric ownership,
SELinux labels and capability xattrs. Do not use an extraction tool that
silently omits compressed F2FS contents. Supply the following paths yourself:

```bash
python3 -B scripts/utils/s10_firmware.py import-tar "$DONOR_TAR" "$PWD/out/fw/SM-S901B_EUX"
python3 -B scripts/utils/s10_firmware.py import-hwc1 "$HWC1_REGISTERED_CACHE" "$PWD/out/fw/SM-G973F_AUT"
python3 -B scripts/utils/s10_apex_input.py register "$BT_PAYLOAD_TAR" "$BT_PAYLOAD_IMAGE" "$PWD/out/apex-inputs/gzh3-bluetooth"
```

The HWC1 importer accepts the existing verified registration and its proof
chain. Its product partition is identity-only; the ROM product comes from
GZH3. The Bluetooth archive must be a read-only export of the pinned GZH3
APEX payload, including ownership and security xattrs. Archive-to-image
association relies on that collection step. Registration detects subsequent
changes to files, links and builder metadata; it does not certify bootability.

Registration requires a new destination and never replaces an existing cache.
Android metadata is stored in sidecars, independently of host ownership.

## Build and validation

```bash
source buildenv.sh beyond1lte
run_cmd make_rom --no-target-files
python3 -B -m unittest discover -s scripts/tests
```

`run_cmd` writes logs outside the checkout, using `ARTISANROM_RECORDS_DIR`
when set or the sibling `ArtisanROM_records` directory otherwise.

The Exynos9820 modules provide legacy audio, vendor HALs, HRM, Bixby key,
camera dependencies and stock cover assets. Target modules provide initial USB
charging reapplication, the 32-bit product ABI list, software A2DP enforcement
and initial animation
defaults. Existing animation settings remain user-controlled.

Board API remains `none`; legacy VNDK 31 is selected separately. S10 inherits
shared ESSI source feature constants without modifying other ESSI targets.
Finalization runs after all modules, because QHD features replace SurfaceFlinger.
It applies the pinned QHD donor's legacy display-port fix and the HWC1 HDMI
output-flag fix, verifies the bounded GZH3 encoder patch, and checks complete
file ownership/label coverage. Unknown native inputs abort the build.
The Bluetooth payload importer also rejects unknown inputs.

The shared UN1CA framework/APEX pipeline must also finish successfully.
Final SELinux/VINTF validation, image and AVB checks, and on-device boot and
functional tests are still required for this donor combination. Do not infer
GZH3 runtime results from the earlier ArtisanROM donor. Keep the installer
abort until these checks and recovery prerequisites have been reviewed.
