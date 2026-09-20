# SPDX-License-Identifier: GPL-3.0-or-later
"""Host checks for the incomplete S10 port's configuration and fail-closed gates."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

class S10FoundationTests(unittest.TestCase):
    def config(self, root, target, output):
        env = dict(os.environ, SRC_DIR=str(root), OUT_DIR=str(output), ROM_BUILD_TIMESTAMP='1')
        return subprocess.run(['bash', str(root/'scripts/internal/gen_config_file.sh'), target],
                              env=env, capture_output=True, text=True)

    def test_measured_static_limits_and_legacy_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.config(ROOT, 'beyond1lte', tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = dict(re.findall(r'^(\w+)="(.*)"$', (Path(tmp)/'config.sh').read_text(), re.M))
            expected = {'SOURCE_FIRMWARE': 'SM-S901B/EUX', 'TARGET_FIRMWARE': 'SM-G973F/AUT',
                        'TARGET_BOARD_API_LEVEL': 'none', 'TARGET_LEGACY_VNDK_VERSION': '31',
                        'TARGET_OS_SINGLE_SYSTEM_IMAGE': 'essi', 'SOURCE_LCD_CONFIG_HFR_MODE': '2',
                        'TARGET_USE_DYNAMIC_PARTITIONS': 'false',
                        'TARGET_SYSTEM_PARTITION_SIZE': '7340032000',
                        'TARGET_VENDOR_PARTITION_SIZE': '1572864000',
                        'TARGET_PRODUCT_PARTITION_SIZE': '1572864000',
                        'TARGET_BOOT_PARTITION_SIZE': '57671680',
                        'TARGET_DTB_PARTITION_SIZE': '8388608', 'TARGET_DTBO_PARTITION_SIZE': '8388608'}
            for name, value in expected.items():self.assertEqual(data[name], value, name)

    def test_tampered_measurement_prevents_config_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'repo';out=Path(tmp)/'out';out.mkdir()
            for path in ['scripts/internal','scripts/utils','unica/configs','platform/exynos9820']:
                shutil.copytree(ROOT/path, root/path)
            (root/'target/beyond1lte').mkdir(parents=True)
            shutil.copy(ROOT/'target/beyond1lte/config.sh',root/'target/beyond1lte/config.sh')
            shutil.copytree(ROOT/'target/beyond1lte/layouts',root/'target/beyond1lte/layouts')
            p=root/'target/beyond1lte/layouts/measurement/s10-partition-bytes.txt'
            p.write_text(p.read_text()+'\n')
            self.assertNotEqual(self.config(root,'beyond1lte',out).returncode,0)
            self.assertFalse((out/'config.sh').exists())

    def test_kernel_set_matches_pinned_hashes(self):
        root=ROOT/'target/beyond1lte/kernel'
        expected={name:digest for digest,name in (l.split() for l in (root/'SHA256SUMS').read_text().splitlines())}
        self.assertEqual(set(expected),{'boot.img','dtb.img','dtbo.img'})
        for name,digest in expected.items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)

    def test_kernel_git_attributes_preserve_bytes(self):
        paths=['target/beyond1lte/kernel/'+n for n in ['boot.img','dtb.img','dtbo.img']]
        result=subprocess.run(['git','check-attr','text','--',*paths],cwd=ROOT,capture_output=True,text=True,check=True)
        self.assertEqual(len(result.stdout.splitlines()),3)
        self.assertTrue(all(line.endswith(': text: unset') for line in result.stdout.splitlines()))

    def test_legacy_vndk_does_not_require_board_api(self):
        script='''set -e
SOURCE_BOARD_API_LEVEL=31
TARGET_BOARD_API_LEVEL=none
TARGET_LEGACY_VNDK_VERSION=31
LOG() { :; }
ABORT() { echo "$*" >&2; exit 9; }
source "$1"
test "$TARGET_BOARD_API_LEVEL" = none
'''
        p=subprocess.run(['bash','-c',script,'test',str(ROOT/'unica/patches/vndk/customize.sh')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)

    def test_unknown_vndk_rejected(self):
        p=subprocess.run(['bash','-c','''SOURCE_BOARD_API_LEVEL=31
TARGET_BOARD_API_LEVEL=none
ABORT() { exit 9; }
source "$1"
''','test',str(ROOT/'unica/patches/vndk/customize.sh')],capture_output=True)
        self.assertEqual(p.returncode,9)

    def test_make_rom_stops_before_tools_or_downloads(self):
        p=subprocess.run(['bash',str(ROOT/'scripts/make_rom.sh')],env=dict(os.environ,SRC_DIR=str(ROOT),TARGET_CODENAME='beyond1lte'),capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('S10 preflight:',p.stderr+p.stdout)

    def test_installation_remains_disabled(self):
        p=ROOT/'target/beyond1lte/installer/assertions.edify'
        self.assertEqual(p.read_text().strip(),'abort("UN1CA S10 port is incomplete; installation is disabled.");')

if __name__=='__main__':unittest.main()
