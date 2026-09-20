# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify APK completion cannot concurrently rewrite S10 partition metadata."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]

class ApkSchedulingTests(unittest.TestCase):
    def test_s10_serializes_apk_processes(self):
        source=(ROOT/'scripts/make_rom.sh').read_text()
        function=re.search(r'(?ms)^BUILD_APKS\(\)\n\{.*?^\}',source).group()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'scripts').mkdir()
            mock=root/'scripts/apktool.sh'
            mock.write_text('''#!/bin/bash
set -e
mkdir "$COMPLETION_LOCK"
trap 'rmdir "$COMPLETION_LOCK"' EXIT
sleep 0.15
printf '%s\\n' "$*" >> "$CALLS"
''');mock.chmod(0o755)
            cache=root/'apktool'
            for name in ('first.jar','second.jar'):(cache/'system/framework'/name).mkdir(parents=True)
            shell='set -e\nLOG_STEP_IN() { :; }\nLOG_STEP_OUT() { :; }\n'+function+'\nBUILD_APKS\n'
            env=dict(os.environ,SRC_DIR=str(root),APKTOOL_DIR=str(cache),TARGET_CODENAME='beyond1lte',COMPLETION_LOCK=str(root/'lock'),CALLS=str(root/'calls'))
            result=subprocess.run(['bash','-c',shell],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(len((root/'calls').read_text().splitlines()),2)

if __name__=='__main__':unittest.main()
