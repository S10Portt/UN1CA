# SPDX-License-Identifier: GPL-3.0-or-later
import io
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/utils'))
import s10_firmware as fw
import s10_installer_guard as guard
from s10_installer_stage import prepare

class FirmwareTests(unittest.TestCase):
    def archive(self,path,extra=None):
        with tarfile.open(path,'w') as tar:
            for part in fw.PARTITIONS:
                entry=tarfile.TarInfo(part);entry.type=tarfile.DIRTYPE;entry.mode=0o755
                entry.pax_headers={'SCHILY.xattr.security.selinux':'u:object_r:system_file:s0'};tar.addfile(entry)
            data=b'ro.build.version.incremental=S901BXXSOGZH3\nro.build.version.sdk=36\n'
            entry=tarfile.TarInfo('system/system/build.prop');entry.size=len(data);entry.mode=0o644
            entry.pax_headers={'SCHILY.xattr.security.selinux':'u:object_r:system_file:s0'};tar.addfile(entry,io.BytesIO(data))
            if extra:
                entry=tarfile.TarInfo(extra);entry.mode=0o644
                entry.pax_headers={'SCHILY.xattr.security.selinux':'u:object_r:system_file:s0'};tar.addfile(entry)

    def test_import_and_detect_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.archive(root/'input.tar')
            cache=root/'SM-S901B_EUX';fw.import_tar(root/'input.tar',cache);fw.verify(cache)
            p=cache/'system/system/build.prop';p.write_text(p.read_text()+'unexpected=value\n')
            with self.assertRaisesRegex(ValueError,'changed'):fw.verify(cache)

    def test_reject_traversal_and_duplicate_members(self):
        for entry in ('system/../../escaped','system/system/build.prop'):
            with self.subTest(entry=entry),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.archive(root/'input.tar',entry)
                with self.assertRaises(ValueError):fw.import_tar(root/'input.tar',root/'SM-S901B_EUX')
                self.assertFalse((root/'SM-S901B_EUX').exists())

    def test_capability_conversion_refuses_loss(self):
        import struct
        cap=struct.pack('<5I',0x02000001,0xc0,0,0,0).decode('utf-8','surrogateescape')
        self.assertEqual(fw.capabilities(cap),0xc0)
        with self.assertRaises(ValueError):fw.capabilities('invalid')

def auxiliary_fixture(repo, stage):
    for name in ('target/beyond1lte/installer/layout-preflight.sh',
                 'target/beyond1lte/installer/auxiliary-postinstall.sh',
                 'target/beyond1lte/layouts/measurement/layout.json',
                 'prebuilts/bootable/deprecated-ota/updater'):
        path=repo/name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((ROOT/name).read_bytes())
    data=json.loads((ROOT/'target/beyond1lte/auxiliary/artisan311.json').read_text())
    for part,spec in data['partitions'].items():
        blob=bytearray(4096); blob[1080:1082]=b'\x53\xef'
        (stage/(part+'.img')).write_bytes(blob)
        spec['image_bytes']=len(blob);spec['sha256']=hashlib.sha256(blob).hexdigest()
    path=repo/'target/beyond1lte/auxiliary/artisan311.json'
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))
    (stage/'auxiliary-source.json').write_bytes(path.read_bytes())

class InstallerStageTests(unittest.TestCase):
    def test_generated_writes_are_guarded_and_abort_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp);script=stage/'META-INF/com/google/android/updater-script';script.parent.mkdir(parents=True)
            (script.parent/'update-binary').write_bytes((ROOT/'prebuilts/bootable/deprecated-ota/updater').read_bytes())
            lines=[guard.ABORT]
            for part in ('system','vendor','product'):
                lines += [f'block_image_update("/dev/block/by-name/{part}", package_extract_file("{part}.transfer.list"), "{part}.new.dat.br", "{part}.patch.dat") ||','abort("failed");']
                (stage/(part+'.transfer.list')).write_text('4\n1\n0\n0\nnew 2,0,1\n')
            for part in ('dtb','dtbo','boot'):
                lines.append(f'package_extract_file("{part}.img", "/dev/block/by-name/{part}");')
            repo=stage/'fixture-repo'
            for name in ('target/beyond1lte/installer/layout-preflight.sh',
                         'target/beyond1lte/layouts/measurement/layout.json',
                         'prebuilts/bootable/deprecated-ota/updater'):
                p=repo/name;p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes((ROOT/name).read_bytes())
            (repo/'target/beyond1lte/installer/assertions.edify').write_text(guard.ABORT+'\n')
            auxiliary_fixture(repo,stage)
            script.write_text('\n'.join(lines)+'\n');prepare(repo,stage)
            self.assertEqual(script.read_text().splitlines()[0],guard.ABORT)
            guard.check(repo,stage)
            with self.assertRaises(ValueError):prepare(repo,stage)

    def test_actual_ota_generator_matches_installer_guard(self):
        import os
        import re
        import subprocess
        def function(path,name):
            match=re.search(r'^'+name+r'\(\)\n\{\n.*?^\}',path.read_text(),re.M|re.S)
            self.assertIsNotNone(match,name)
            return match.group()
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp);script=stage/'META-INF/com/google/android/updater-script';script.parent.mkdir(parents=True)
            (script.parent/'update-binary').write_bytes((ROOT/'prebuilts/bootable/deprecated-ota/updater').read_bytes())
            for part in ('system','vendor','product'):
                (stage/(part+'.transfer.list')).write_text('4\n1\n0\n0\nnew 2,0,1\n')
                (stage/(part+'.new.dat.br')).touch()
            for part in ('boot','dtb','dtbo'):(stage/(part+'.img')).touch()
            install=ROOT/'scripts/utils/install_utils.sh'
            shell='''set -e
_CHECK_NON_EMPTY_PARAM() { test -n "$2"; }
PRINT_HEADER() { :; }
PRINT_SEPARATOR() { :; }
BUILD_INFO=$'device=beyond1lte\\nmodel=SM-G973F;SM-G973N'
KERNEL_BINS="dt dtb dtbo init_boot vendor_boot"
PARTITIONS_LIST="system vendor product system_ext odm vendor_dlkm odm_dlkm system_dlkm"
'''
            for name in ('GET_DEVICE_FROM_MOUNTPOINT','PRINT_ASSERTIONS'):shell+=function(install,name)+'\n'
            shell+=function(ROOT/'scripts/internal/build_full_ota_zip.sh','GENERATE_UPDATER_SCRIPT')+'\nGENERATE_UPDATER_SCRIPT\n'
            result=subprocess.run(['bash','-c',shell],env=dict(os.environ,SRC_DIR=str(ROOT),TMP_DIR=str(stage),TARGET_CODENAME='beyond1lte',TARGET_USE_DYNAMIC_PARTITIONS='false'),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            repo=stage/'fixture-repo';auxiliary_fixture(repo,stage)
            (repo/'target/beyond1lte/installer/assertions.edify').write_bytes((ROOT/'target/beyond1lte/installer/assertions.edify').read_bytes())
            prepare(repo,stage)
            guard.check(repo,stage)

if __name__=='__main__':unittest.main()
