"""Exercise UN1CA's actual full-OTA shell pipeline using small fixture images."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/utils'))
from test_s10_integration import auxiliary_fixture
from s10_auxiliary_images import stage as stage_images
from s10_auxiliary_contract import check as check_payload
from s10_installer_guard import check


@unittest.skipUnless(all(shutil.which(t) for t in ('7z','brotli','bc','unzip')), 'OTA host tools required')
class AuxiliaryPipelineTest(unittest.TestCase):
    def test_target_files_to_final_zip_and_reject_old_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);repo=base/'repo';inputs=base/'inputs';inputs.mkdir()
            shutil.copytree(ROOT/'scripts', repo/'scripts')
            (repo/'external').mkdir()
            make=repo/'external/make.sh';make.write_text('#!/bin/sh\nexit 0\n');make.chmod(0o755)
            auxiliary_fixture(repo, inputs)
            shutil.copyfile(ROOT/"target/beyond1lte/config.sh",repo/"target/beyond1lte/config.sh")
            for name in ('assertions.edify','customize.sh','recovery.fstab'):
                shutil.copyfile(ROOT/'target/beyond1lte/installer'/name, repo/'target/beyond1lte/installer'/name)
            # Stand-ins isolate packaging from OS image generation and signing.
            tools=base/'tools';tools.mkdir()
            converter=tools/'img2sdat'
            converter.write_text('''#!/usr/bin/env python3
import sys
from pathlib import Path
out=Path(sys.argv[sys.argv.index('-o')+1]);part=Path(sys.argv[-1]).stem
with (out/'converted.txt').open('a') as f:f.write(part+'\\n')
(out/(part+'.transfer.list')).write_text('4\\n1\\n0\\n0\\nnew 2,0,1\\n')
(out/(part+'.new.dat')).write_bytes(bytes(4096))
(out/(part+'.patch.dat')).touch()
''');converter.chmod(0o755)
            signer=tools/'signapk';signer.write_text('#!/bin/sh\ncp "$4" "$5"\n');signer.chmod(0o755)
            target=base/'target';target.mkdir()
            for part in ('system','vendor','product','boot','dtb','dtbo'):
                (target/(part+'.img')).write_bytes(bytes(4096))
            info='device=beyond1lte\nmodel=SM-G973F\nname=Fixture\nversion=fixture\ntimestamp=1\nos_version=16\noneui_version=8\nbuild_incremental=fixture\nbuild_date=1\nsecurity_patch=2026-09-01\nsource_fingerprint=fixture\nuse_dynamic_partitions=false\n'
            (target/'build_info.txt').write_text(info)
            bundle=target/'S10_AUXILIARY';bundle.mkdir();stage_images(inputs,bundle,repo)
            check_payload(bundle,'package',repo)
            def archive(path, omit=False):
                with zipfile.ZipFile(path,'w') as z:
                    for p in target.rglob('*'):
                        if p.is_file() and not (omit and 'S10_AUXILIARY' in p.parts):
                            z.write(p,p.relative_to(target).as_posix())
            source=base/'target.zip';archive(source)
            output=base/'full.zip'
            env=dict(os.environ,SRC_DIR=str(repo),OUT_DIR=str(base/'out'),TARGET_CODENAME='beyond1lte',DEBUG='false',ROM_IS_OFFICIAL='false',PATH=str(tools)+os.pathsep+os.environ['PATH'])
            def build(input_zip):
                return subprocess.run(['bash',str(repo/'scripts/internal/build_full_ota_zip.sh'),str(input_zip),str(output)],env=env,capture_output=True,text=True)
            result=build(source)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            check(repo,output)
            with zipfile.ZipFile(output) as z:
                self.assertEqual(set(z.read('converted.txt').decode().splitlines()),{'system','vendor','product'})
                self.assertFalse(any(n.startswith('S10_AUXILIARY/') for n in z.namelist()))
                for part in ('odm','prism','optics'):
                    self.assertEqual(z.read(part+'.img'),(inputs/(part+'.img')).read_bytes())
            # A stale target-files archive must not silently preserve empty auxiliaries.
            old=base/'old.zip';archive(old,omit=True)
            self.assertNotEqual(build(old).returncode,0)
            # A root-level auxiliary must not enter generic img2sdat processing.
            (target/'odm.img').write_bytes(b'unexpected')
            archive(source)
            self.assertNotEqual(build(source).returncode,0)

    def test_incremental_s10_is_rejected(self):
        # Execute the real device gate without performing incremental image work.
        source=(ROOT/'scripts/internal/build_incremental_ota_zip.sh').read_text()
        start=source.index('if [[ "$TARGET_CODENAME" == "beyond1lte" ]]')
        gate=source[start:source.index('\nfi',start)+3]
        for target,expected in [('beyond1lte',1),('a52q',0)]:
            result=subprocess.run(['bash','-c','LOGE() { :; }; '+gate],env=dict(os.environ,TARGET_CODENAME=target))
            self.assertEqual(result.returncode,expected)
