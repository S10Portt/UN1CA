# Galaxy S10 port foundation

This target is incomplete and must not be installed. The normal ROM build and
installer both stop intentionally until the hardware port is integrated.

The selected layout is a measured repartitioned beyond1lte layout, not a stock
or universal SM-G973F/SM-G973N layout. Its hashed measurements are required
build inputs. Only boot, dtb, dtbo, system, vendor and product may be written;
odm, prism, optics and up_param must remain preserved.

Use the registered S901B EUX GZH3 system donor, G973F AUT HWC1 vendor and the
pinned Exynos9820 kernel set. Firmware identifiers here are offline cache keys,
not downloader identifiers. Offline registration and downloader bypass are
not implemented yet; do not add invented identifiers to make downloads work.

Board API is unknown and remains `none`; legacy VNDK 31 is selected separately.
The SSI profile inherits shared S901B feature constants without changing other
essi targets. The display patch only accepts the registered GZH3 binary. USB
patch assembly validation does not establish runtime compatibility.

Remaining integration: firmware metadata registration, kernel/work-tree setup,
legacy hardware modules and ABI dependencies, software A2DP policy, fixed-layout
installer preflight and package guard, and final policy/APEX/image verification.
Remove neither build nor installation stops until these contracts are wired
and verified. Record investigations outside this checkout as described in AGENTS.md.
