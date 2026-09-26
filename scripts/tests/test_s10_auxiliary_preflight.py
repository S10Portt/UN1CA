"""Exercise empty/mounted auxiliary input and checked ext4 postprocessing."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]

class AuxiliaryPreflightTest(unittest.TestCase):
    def test_mounted_and_empty(self):
        source=(ROOT/'target/beyond1lte/installer/layout-preflight.sh').read_text()
        block=source[source.index('for part in odm prism optics; do'):]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for part in ('odm','prism','optics'): (root/part).touch()
            mounts=root/'mounts'
            block=block.replace('/proc/mounts',str(mounts))
            script='BLOCK_ROOT="$1"\nfail() { exit 1; }\n'+block
            for line, expected in [('',0),(f'{root}/odm /somewhere ext4 ro 0 0\n',1),('/dev/alias /prism ext4 ro 0 0\n',1)]:
                mounts.write_text(line)
                result=subprocess.run(['sh','-c',script,'fixture',d],capture_output=True)
                self.assertEqual(result.returncode,expected)

    def test_fsck_return_codes(self):
        source=(ROOT/'target/beyond1lte/installer/auxiliary-postinstall.sh').read_text()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for part in ('odm','prism','optics'): (root/part).touch()
            tool=root/'tool'; tool.write_text('#!/bin/sh\nexit "${TOOL_RC:-0}"\n'); tool.chmod(0o755)
            script=source.replace('/sbin/e2fsck',str(tool)).replace('/sbin/resize2fs','/bin/true')
            script=script.replace('/dev/block/by-name',d).replace('[ -b "$dev" ]','[ -f "$dev" ]').replace('/proc/mounts','/dev/null')
            for rc,expected in [(0,0),(1,0),(2,1),(4,1),(8,1)]:
                result=subprocess.run(['sh','-c',f'TOOL_RC={rc}; export TOOL_RC\n'+script],capture_output=True)
                self.assertEqual(result.returncode,expected)
            script=script.replace('RESIZE=/bin/true','RESIZE=/bin/false')
            self.assertNotEqual(subprocess.run(['sh','-c',script],capture_output=True).returncode,0)
