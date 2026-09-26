# Galaxy S10 port

This target is under development. Controlled test installation is enabled for
the measured layout below; this is not a general-release build or a stock-layout installer.

## Fixed inputs and partition scope

Use S901B EUX GZH3 (Android 16) as the system donor, G973F AUT HWC1 as the
legacy vendor donor, and the pinned images under `kernel/`. Firmware names
are offline cache keys. The S10 build validates registrations before tool
setup and does not fall back to downloading another firmware version.

The `user-repartition-20260913` profile describes a measured repartitioned
beyond1lte, not a stock or universal SM-G973F/SM-G973N layout. The installer
writes boot, dtb, dtbo, system, vendor, product, ODM, prism and optics. Data,
EFS and up_param are not written. Recovery checks all nine paths and exact
sizes before any write, rejects mounted auxiliary partitions, and requires
e2fsck and resize2fs. All installations replace the three auxiliary contents,
including updates; existing carrier customizations there are not preserved.

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
Validate the final package before installation and confirm recovery prerequisites.
On-device boot and functional tests remain required for this donor combination.
Do not infer GZH3 runtime results from the earlier ArtisanROM donor. Kernel-inclusive
VINTF checks currently fail because the donor matrices have no 4.14 kernel entry;
this is distinct from the kernel-disabled boot compatibility check.
The unconditional development abort has been removed for controlled testing;
exact partition-size checks and the pinned auxiliary payload guards remain enforced.

## Pinned auxiliary filesystems

Prepare the verified ArtisanROM 3.1.1 input once (Python 3 and brotli required):

```sh
python3 -B scripts/utils/s10_auxiliary_images.py prepare /path/to/ArtisanROM_OFFICIAL_3.1.1_20260428_beyond1lte-sign.zip out/inputs/s10-auxiliary
```

Substitute the configured OUT_DIR for `out` if customized. The source ZIP,
raw image hashes, lengths and capacities are pinned in auxiliary/artisan311.json.
Preparation requires a new destination; use `verify` to check an existing cache.
The raw ext4 images stay outside WORK_DIR and are not rebuilt or AVB-signed.

UN1CA target-files contains them under S10_AUXILIARY, with the source manifest.
The full OTA builder verifies that bundle and stages it at the root only after
OS image conversion. Older S10 target-files lacking the bundle must be rebuilt.
S10 incremental OTAs are rejected; other targets keep their existing pipeline.
The final signed ZIP is checked again against the manifest and nine-write contract.

Installation writes OS partitions, then the three auxiliaries, checks e2fsck
(exit 0/1 only) and resize2fs, and finally writes the kernel. Resizing changes
on-device filesystem bytes; the ZIP retains the pinned raw hashes.

The intended clean path is Repartition → Cleaner → new integrated ROM → normal
clean-install data setup → boot. Never run Cleaner after ROM installation.
No automatic data wipe or separate auxiliary seed installation is added.

**Integrated clean boot is not yet verified for UN1CA GZH3.** This ports the
auxiliary provisioning approach from ArtisanROM; its runtime outcome is not
proof for this donor. Earlier successful installs may have relied on existing
auxiliary or first-boot data/EFS/OMR state. The pinned 3.1.1 ODM intentionally
retains its donor identity. A complete build and clean-install device test,
including CSC, telephony, SELinux, USB and DeX regression checks, remain required.
