# SPDX-License-Identifier: GPL-3.0-or-later
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'utils'))
import s10_apex_input as apex

class ApexInputTests(unittest.TestCase):
    def archive(self,path,bad=False):
        with tarfile.open(path,'w') as tar:
            for name in ('.','./lib64'):
                t=tarfile.TarInfo(name);t.type=tarfile.DIRTYPE;t.mode=0o755
                t.pax_headers={'SCHILY.xattr.security.selinux':'u:object_r:system_file:s0'};tar.addfile(t)
            t=tarfile.TarInfo('./lib64/libtest.so' if not bad else './lib64/../../outside')
            t.size=4;t.mode=0o644;t.uid=0;t.gid=2000
            t.pax_headers={'SCHILY.xattr.security.selinux':'u:object_r:system_lib_file:s0'};tar.addfile(t,io.BytesIO(b'test'))

    def test_stage_preserves_metadata_and_rejects_changed_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);image=root/'payload.img';image.write_bytes(b'image');archive=root/'payload.tar';self.archive(archive)
            with patch.object(apex,'PAYLOAD_SHA256',apex.digest(image)):
                cache=root/'cache';apex.register(archive,image,cache);apex.verify(cache)
                destination=root/'unknown';destination.mkdir();apex.stage(cache,image,destination)
                self.assertFalse(image.exists())
                self.assertIn('lib64/libtest.so 0 2000 644 capabilities=0x0', (destination/'fs_config-apex_payload').read_text())
                (cache/'apex_payload/lib64/libtest.so').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'changed'):apex.verify(cache)

    def test_rejects_unrelated_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);image=root/'payload.img';image.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'unknown'):apex.register(root/'absent.tar',image,root/'cache')

    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);image=root/'payload.img';image.write_bytes(b'image');archive=root/'payload.tar';self.archive(archive,True)
            with patch.object(apex,'PAYLOAD_SHA256',apex.digest(image)),self.assertRaises(ValueError):
                apex.register(archive,image,root/'cache')
            self.assertFalse((root/'cache').exists())

if __name__=='__main__':unittest.main()
