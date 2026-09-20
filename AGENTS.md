# Repository rules

## Source and records

Keep this repository limited to ROM source, build configuration, reusable tests,
licenses, maintained user/developer documentation, and required build inputs.

Do not write session transcripts, handoff notes, review reports, investigation
logs, device dumps, tombstones, disassembly output, or generated validation
reports anywhere inside the source checkout, including docs/, doc/, and ignored
folders. Do not paste personal identifiers or local absolute paths into source
comments, documentation, or commit messages.

Store such records outside the checkout. Use ARTISANROM_RECORDS_DIR when set;
otherwise use the sibling directory ../ArtisanROM_records. Resolve symlinks and
reject an output directory inside this checkout. Never commit that external
archive or a history backup. Temporary test fixtures belong in the OS temporary
directory. Build outputs/caches required by the build pipeline may remain in
out/; investigation and validation reports must use the external records directory.

The fixed partition layout inputs under target/beyond1lte/layouts/measurement
are an explicit exception: the build verifies their hashes and cross-checks
partition sizes. They are required source inputs, not a destination for new logs.

Before committing, inspect the staged path list and diff for accidental records
and personal data. Stage specific files rather than all untracked files.
