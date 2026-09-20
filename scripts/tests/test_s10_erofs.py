# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'utils'))
from s10_erofs import inspect

class ErofsContractTests(unittest.TestCase):
    def image(self):
        data=bytearray(4096)
        struct.pack_into('<I',data,1024,0xe0f5e1e2)
        data[1036]=12
        struct.pack_into('<I',data,1060,1)
        struct.pack_into('<I',data,1104,1)
        struct.pack_into('<H',data,1108,65535)
        return data

    def test_header_contract_and_unsupported_features(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'image';data=self.image();p.write_bytes(data)
            self.assertEqual(inspect(p)['filesystem_bytes'],4096)
            struct.pack_into('<I',data,1104,3);p.write_bytes(data)
            with self.assertRaises(ValueError):inspect(p)

    def test_rejects_truncation_and_oversized_filesystem(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'image';data=self.image();struct.pack_into('<I',data,1060,2);p.write_bytes(data)
            with self.assertRaises(ValueError):inspect(p)
            p.write_bytes(data[:1100])
            with self.assertRaises(ValueError):inspect(p)

if __name__=='__main__':unittest.main()
