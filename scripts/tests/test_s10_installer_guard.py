"""Host regression fixtures. Run: python3 -B -m unittest discover -s scripts/tests."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/utils'))
import s10_installer_guard as guard


class InstallerGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)/'repo'
        self.stage = Path(self.tmp.name)/'stage'
        for name in ('target/beyond1lte/installer/layout-preflight.sh',
                     'target/beyond1lte/layouts/measurement/layout.json',
                     'target/beyond1lte/installer/auxiliary-postinstall.sh'):
            p = self.repo/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((ROOT/name).read_bytes())
        (self.repo/'target/beyond1lte/installer/assertions.edify').write_text('# approved fixture\n')
        p = self.repo/'prebuilts/bootable/deprecated-ota/updater'
        p.parent.mkdir(parents=True)
        p.write_bytes(b'fixture updater')
        self.script = self.stage/'META-INF/com/google/android/updater-script'
        self.script.parent.mkdir(parents=True)
        (self.script.parent/'update-binary').write_bytes(p.read_bytes())
        (self.stage/'layout-preflight.sh').write_bytes(
            (self.repo/'target/beyond1lte/installer/layout-preflight.sh').read_bytes())
        data = json.loads((ROOT/'target/beyond1lte/auxiliary/artisan311.json').read_text())
        for part,spec in data['partitions'].items():
            blob = bytearray(4096); blob[1080:1082] = b'\x53\xef'
            (self.stage/(part+'.img')).write_bytes(blob)
            spec['image_bytes'] = len(blob)
            spec['sha256'] = hashlib.sha256(blob).hexdigest()
        manifest = self.repo/'target/beyond1lte/auxiliary/artisan311.json'
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps(data))
        (self.stage/'auxiliary-source.json').write_bytes(manifest.read_bytes())
        (self.stage/'auxiliary-postinstall.sh').write_bytes((ROOT/'target/beyond1lte/installer/auxiliary-postinstall.sh').read_bytes())
        self.lines = list(guard.PREFLIGHT)
        for p in ('system', 'vendor', 'product'):
            self.lines += [f'block_image_update("/dev/block/by-name/{p}", package_extract_file("{p}.transfer.list"), "{p}.new.dat.br", "{p}.patch.dat") ||',
                           'abort("write failed");']
        for p in guard.AUX_PARTITIONS:
            self.lines.append(f'assert(package_extract_file("{p}.img", "/dev/block/by-name/{p}"));')
        self.lines += list(guard.POSTINSTALL)
        for p in ('dtb', 'dtbo', 'boot'):
            self.lines.append(f'assert(package_extract_file("{p}.img", "/dev/block/by-name/{p}"));')
        self.save()
        for p in guard.PARTITIONS[:3]:
            (self.stage/(p+".transfer.list")).write_text("4\n1\n0\n0\nnew 2,0,1\n")

    def save(self):
        self.script.write_text('\n'.join(self.lines)+'\n')

    def rejected(self):
        self.save()
        with self.assertRaises((ValueError, OSError)):
            guard.check(self.repo, self.stage)

    def test_valid_stage_and_zip(self):
        guard.check(self.repo, self.stage)
        path = Path(self.tmp.name)/'rom.zip'
        with zipfile.ZipFile(path, 'w') as z:
            for p in self.stage.rglob('*'):
                if p.is_file():
                    z.write(p, p.relative_to(self.stage).as_posix())
        guard.check(self.repo, path)

    def test_missing_preflight(self):
        self.lines = self.lines[3:]
        (self.stage/'layout-preflight.sh').unlink()
        self.rejected()

    def test_modified_preflight(self):
        (self.stage/'layout-preflight.sh').write_text('exit 0\n')
        self.rejected()

    def test_unchecked_extraction(self):
        self.lines[0] = 'package_extract_file("layout-preflight.sh", "/tmp/layout-preflight.sh");'
        self.rejected()

    def test_late_or_duplicate_preflight(self):
        original = self.lines[:]
        self.lines = original[3:] + original[:3]
        self.rejected()
        self.lines = original[:3] + original
        self.rejected()

    def test_wrong_or_missing_write_target(self):
        original = self.lines[:]
        self.lines = [s.replace('/by-name/system', '/by-name/userdata') for s in original]
        self.rejected()
        self.lines = original[:-1]
        self.rejected()

    def test_size_drift(self):
        for base in (self.stage, self.repo/'target/beyond1lte/installer'):
            p = base/'layout-preflight.sh'
            p.write_text(p.read_text().replace('14336000', '1'))
        self.rejected()

    def test_auxiliary_payload(self):
        (self.stage/'odm.img').write_bytes(b'bad')
        self.rejected()


    def test_auxiliary_missing_or_altered(self):
        for name in ('odm.img','prism.img','optics.img'):
            with self.subTest(name=name):
                path = self.stage/name; data = path.read_bytes(); path.unlink()
                self.rejected(); path.write_bytes(data)
        path = self.stage/'prism.img'; data = path.read_bytes()
        path.write_bytes(b'X'+data[1:]); self.rejected()

    def test_forbidden_auxiliary_forms(self):
        for name in ('prism.new.dat.br','up_param.bin','nested/odm.img'):
            path = self.stage/name; path.parent.mkdir(exist_ok=True)
            path.write_bytes(b'bad'); self.rejected(); path.unlink()

    def test_duplicate_early_and_unknown_writes(self):
        original = self.lines[:]
        odm = 'assert(package_extract_file("odm.img", "/dev/block/by-name/odm"));'
        for lines in ([odm]+original, original+[odm], original+['format("ext4", "EMMC", "/dev/block/by-name/efs", "0", "/efs");']):
            self.lines = lines; self.rejected()
        self.lines = original

    def test_modified_or_missing_postinstall(self):
        path = self.stage/'auxiliary-postinstall.sh'
        path.write_text('exit 0'); self.rejected()
        path.unlink(); self.rejected()

    def test_final_zip_rejects_modified_auxiliary(self):
        path = Path(self.tmp.name)/'tampered.zip'
        with zipfile.ZipFile(path,'w') as z:
            for p in self.stage.rglob('*'):
                if p.is_file():
                    data=p.read_bytes()
                    if p.name=='optics.img': data=data[:-1]+b'X'
                    z.writestr(p.relative_to(self.stage).as_posix(),data)
        with self.assertRaises(ValueError): guard.check(self.repo,path)

    def test_auxiliary_size_drift(self):
        for base in (self.stage,self.repo/'target/beyond1lte/installer'):
            p=base/'layout-preflight.sh'
            p.write_text(p.read_text().replace('check_partition "odm" 8192','check_partition "odm" 8191'))
        self.rejected()


class TransferTest(unittest.TestCase):
    def test_full_ranges(self):
        guard.check_transfer(b'4\n5\n0\n0\nerase 2,0,5\nnew 2,0,4\nzero 2,4,5\n', 5)

    def test_bad_ranges(self):
        for operation in ('new 2,0,6', 'new 2,3,3', 'new 2,-1,2',
                          'new 4,0,3', 'new 4,0,3,2,4',
                          'new 2,0,3\nzero 2,2,4', 'move 2,0,3'):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                guard.check_transfer(('4\n5\n0\n0\n'+operation+'\n').encode(), 5)


class LayoutTest(unittest.TestCase):
    def test_exact_write_path(self):
        source = (ROOT/'target/beyond1lte/installer/layout-preflight.sh').read_text()
        self.assertIn('[ -b "$link" ]', source)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            writes = root/'by-name'
            alt = root/'alternate'
            sysfs = root/'sys'
            for p in (writes, alt, sysfs):
                p.mkdir()
            sizes = json.loads((ROOT/'target/beyond1lte/layouts/measurement/layout.json').read_text())['partition_bytes']
            for name in guard.PARTITIONS:
                node = root/('node-'+name)
                node.touch()
                (writes/name).symlink_to(node)
                (alt/name).symlink_to(node)
                (sysfs/node.name).mkdir()
                (sysfs/node.name/'size').write_text(str(sizes[name]//512))
            # Host fixture uses regular files; production retains mandatory -b.
            script = source.replace('BLOCK_ROOT=/dev/block/by-name', f'BLOCK_ROOT="{writes}"')
            script = script.replace('SYS_CLASS_BLOCK=/sys/class/block', f'SYS_CLASS_BLOCK="{sysfs}"')
            script = script.replace('[ -b "$link" ]', '[ -e "$link" ]')
            path = root/'preflight.sh'
            # Recovery tool availability is covered in the auxiliary fixture.
            script = script.replace('[ -x /sbin/e2fsck ]', 'true').replace('[ -x /sbin/resize2fs ]', 'true')
            path.write_text(script)
            def run():
                return subprocess.run(['sh', str(path)], capture_output=True).returncode
            self.assertEqual(run(), 0)
            (sysfs/'node-system/size').write_text('1')
            self.assertNotEqual(run(), 0)
            (sysfs/'node-system/size').write_text(str(sizes['system']//512))
            (writes/'system').unlink()
            # Alternate alias remains valid, but cannot substitute for write path.
            self.assertTrue((alt/'system').exists())
            self.assertNotEqual(run(), 0)


if __name__ == '__main__':
    unittest.main()
