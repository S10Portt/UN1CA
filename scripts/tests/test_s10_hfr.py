# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]

class HfrTests(unittest.TestCase):
    def test_ns_replacement_does_not_erase_selected_rate(self):
        text=(ROOT/'unica/patches/product_feature/customize.sh').read_text()
        start=text.index('# S10 RATE becomes')
        end=text.index('unset -f APPLY_HFR_NS_CONFIG',start)+len('unset -f APPLY_HFR_NS_CONFIG')
        with tempfile.TemporaryDirectory() as temp:
            fixture=Path(temp)/'method';fixture.write_text('RATE="24,10,30,48,60,96,120"\nNS="60"\n')
            script='''set -e
TARGET_CODENAME=beyond1lte
SOURCE_LCD_CONFIG_HFR_SUPPORTED_REFRESH_RATE=24,10,30,48,60,96,120
TARGET_LCD_CONFIG_HFR_SUPPORTED_REFRESH_RATE=60
SOURCE_LCD_CONFIG_HFR_SUPPORTED_REFRESH_RATE_NS=60
TARGET_LCD_CONFIG_HFR_SUPPORTED_REFRESH_RATE_NS=none
SET_FLOATING_FEATURE_CONFIG() { :; }
SMALI_PATCH() {
    if [[ "$5" == getMainInstance* ]]; then
        python3 -B - "$FIXTURE" "$6" "$7" <<'P'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text()
old='"'+sys.argv[2]+'"'
new='"'+sys.argv[3]+'"'
assert old in s
p.write_text(s.replace(old,new))
P
    fi
}
'''+text[start:end]
            result=subprocess.run(['bash','-c',script],env=dict(os.environ,FIXTURE=str(fixture)),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(fixture.read_text(),'RATE="60"\nNS=""\n')

if __name__=='__main__':unittest.main()
