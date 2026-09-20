#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute the pinned original/patched ARM64 guard with Unicorn, using fake callees.
Usage: python3 -B scripts/tests/check_s10_display_port_arm64.py ORIGINAL_SURFACEFLINGER
Install unicorn separately outside the checkout. This is not an on-device test.
"""
import itertools
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'utils'))
from s10_display_port import patched, apply, EDITS, ORIGINAL_SHA256
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import *
import hashlib
import tempfile
import os


def run(image, general, has_data, duplicate, count, port):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, (len(image)+4095)&~4095)
    uc.mem_write(0, image)
    obj, stack, tls, stop = 0x2000000, 0x3000000, 0x4000000, 0x10000
    for base, size in ((obj,0x1000),(stack,0x20000),(tls,0x1000)):
        uc.mem_map(base,size)
    uc.mem_write(obj+0x148, bytes([general]))
    uc.mem_write(obj+0x128, struct.pack('<Q',count))
    uc.mem_write(tls+0x28, struct.pack('<Q',0x123456789abcdef))
    uc.reg_write(UC_ARM64_REG_TPIDR_EL0,tls)
    uc.reg_write(UC_ARM64_REG_SP,stack+0x10000)
    uc.reg_write(UC_ARM64_REG_X30,stop)
    uc.reg_write(UC_ARM64_REG_X0,obj)
    uc.reg_write(UC_ARM64_REG_X1,256)
    uc.reg_write(UC_ARM64_REG_W2,port)
    uc.reg_write(UC_ARM64_REG_W3,has_data)
    saved = {reg: 0xabc000+reg for reg in (UC_ARM64_REG_X19,UC_ARM64_REG_X20,
             UC_ARM64_REG_X21,UC_ARM64_REG_X22,UC_ARM64_REG_X23,UC_ARM64_REG_X29)}
    for reg,val in saved.items(): uc.reg_write(reg,val)
    calls=[]
    def hook(u,pc,size,unused):
        if pc==0x7dc470: raise AssertionError('stack canary failure')
        if pc not in (0x454b90,0x7d8110): return
        if pc==0x454b90:
            assert u.reg_read(UC_ARM64_REG_X0)==obj+0x30
            assert u.mem_read(u.reg_read(UC_ARM64_REG_X1),1)==bytes([port])
            calls.append('lookup')
            value=duplicate
        else:
            ptr=u.reg_read(UC_ARM64_REG_X2)
            text=bytes(u.mem_read(ptr,160)).split(b'\0')[0]
            if b'already in active use' in text:
                assert u.reg_read(UC_ARM64_REG_X3)==256
                assert u.reg_read(UC_ARM64_REG_W4)==port
            calls.append(text.decode())
            value=0
        # Called functions may destroy caller-saved registers.
        for reg in (UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3,UC_ARM64_REG_X8):
            u.reg_write(reg,0xdeadbeef)
        u.reg_write(UC_ARM64_REG_W0,int(value))
        u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_X30))
    uc.hook_add(UC_HOOK_CODE,hook)
    uc.emu_start(0x452608,stop,count=300)
    assert uc.reg_read(UC_ARM64_REG_PC)==stop
    assert uc.reg_read(UC_ARM64_REG_SP)==stack+0x10000
    for reg,val in saved.items(): assert uc.reg_read(reg)==val
    return uc.reg_read(UC_ARM64_REG_W0),calls


def main(path):
    original=Path(path).read_bytes()
    assert hashlib.sha256(original).hexdigest()==ORIGINAL_SHA256
    candidate=patched(original)
    assert patched(candidate)==candidate
    allowed={o+i for o,_,_ in EDITS for i in range(4)}
    assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(original,candidate)))
    assert len(original)==len(candidate)
    corrupted=bytearray(original)
    corrupted[0x45263c]^=1
    try:
        patched(bytes(corrupted))
    except ValueError:
        pass
    else:
        raise AssertionError('unknown binary accepted')
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'surfaceflinger'
        path.write_bytes(original)
        path.chmod(0o755)
        os.setxattr(path,'user.fixture',b'preserve')
        apply(path)
        apply(path)
        assert path.read_bytes()==candidate
        assert path.stat().st_mode & 0o777 == 0o755
        assert os.getxattr(path,'user.fixture')==b'preserve'
        link=Path(directory)/'link'
        link.symlink_to(path)
        try:
            apply(link)
        except ValueError:
            pass
        else:
            raise AssertionError('symlink accepted')
    cases=0
    for general,has_data,duplicate,count,port in itertools.product((0,1),(0,1),(0,1),(0,1,2),(0,4,129)):
        old,old_calls=run(original,general,has_data,duplicate,count,port)
        new,new_calls=run(candidate,general,has_data,duplicate,count,port)
        rest=(general and not has_data) or (not general and count==2)
        assert old==int(bool(duplicate or rest))
        assert new==int(bool((has_data and duplicate) or rest))
        assert ('lookup' in new_calls)==bool(has_data)
        if has_data: assert (old,old_calls)==(new,new_calls)
        cases+=1
    assert run(original,0,0,1,1,0)[0]==1
    assert run(candidate,0,0,1,1,0)[0]==0
    print(f'PASS: {cases} scenarios, original + patched ARM64; ABI/canary/duplicate and legacy limits checked')


if __name__=='__main__': main(sys.argv[1])
