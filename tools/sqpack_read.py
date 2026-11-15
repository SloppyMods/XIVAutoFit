# Minimal read-only SqPack reader. Finds a game file in the chara pack (040000) by its path, without any game tooling.
import struct,zlib,os
SQ=os.path.expanduser('~/.local/share/dev.goats.xivlauncher/ffxiv/game/sqpack/ffxiv/')
def _lookup(path,pack='040000'):
    h=(zlib.crc32(path.lower().encode())^0xFFFFFFFF)&0xFFFFFFFF
    b=open(SQ+pack+'.win32.index2','rb').read()
    hdr=struct.unpack('<I',b[0x0C:0x10])[0]
    off,size=struct.unpack('<II',b[hdr+8:hdr+16])
    for i in range(off,off+size,8):
        a,d=struct.unpack('<II',b[i:i+8])
        if a==h: return (d&0xE)>>1,(d&~0xF)*8
    return None
def exists(path): return _lookup(path) is not None
def read(path,pack='040000'):
    r=_lookup(path,pack)
    if r is None: return None
    dat,base=r
    with open(f'{SQ}{pack}.win32.dat{dat}','rb') as f:
        f.seek(base); h=f.read(0x18); hs,typ,raw,_,_,nb=struct.unpack('<IIIIII',h)
        assert typ==2,f'unsupported entry type {typ}'
        blocks=struct.unpack('<'+'IHH'*nb,f.read(8*nb)); out=b''
        for i in range(nb):
            o=blocks[i*3]; f.seek(base+hs+o); bh,_,c,u=struct.unpack('<IIII',f.read(16))
            f.seek(base+hs+o+bh)
            out+=f.read(u) if c==32000 else zlib.decompress(f.read(c),-15)
    assert len(out)==raw
    return out
