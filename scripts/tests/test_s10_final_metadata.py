# SPDX-License-Identifier: GPL-3.0-or-later
"""Final metadata must describe real output files, including literal regex names."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/utils'))
from s10_build_preflight import metadata


class FinalMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'configs').mkdir()
        for part in ('system', 'vendor', 'product'):
            (self.root/part).mkdir()
            (self.root/'configs'/('fs_config-'+part)).write_text(' 0 0 755 capabilities=0x0\n')
            (self.root/'configs'/('file_context-'+part)).write_text('/ u:object_r:rootfs:s0\n')
        # Target of this Android symlink need not exist on the build host.
        (self.root/'vendor/lib+test.so').symlink_to('/apex/example/lib.so')
        self.fs = self.root/'configs/fs_config-vendor'
        self.fc = self.root/'configs/file_context-vendor'
        self.fs.write_text(self.fs.read_text()+'vendor/lib+test.so 0 0 644 capabilities=0x0\n')
        self.fc.write_text(self.fc.read_text()+r'/vendor/lib\+test\.so u:object_r:vendor_file:s0'+'\n')

    def test_literal_label_and_android_symlink(self):
        metadata(self.root)

    def test_missing_ownership_is_rejected(self):
        self.fs.write_text(' 0 0 755 capabilities=0x0\n')
        with self.assertRaisesRegex(ValueError, 'missing ownership'):
            metadata(self.root)

    def test_missing_label_is_rejected(self):
        self.fc.write_text('/ u:object_r:rootfs:s0\n')
        with self.assertRaisesRegex(ValueError, 'missing labels'):
            metadata(self.root)

    def test_removed_file_cannot_leave_metadata(self):
        (self.root/'vendor/lib+test.so').unlink()
        with self.assertRaisesRegex(ValueError, 'stale ownership'):
            metadata(self.root)

    def test_duplicate_label_is_rejected(self):
        self.fc.write_text(self.fc.read_text()+r'/vendor/lib\+test\.so u:object_r:vendor_file:s0'+'\n')
        with self.assertRaisesRegex(ValueError, 'duplicate labels'):
            metadata(self.root)
