# Parser for human.pbd, the game's bone-deformer file: per race, a 3x4 matrix per bone.
import struct
import numpy as np
def parse(b):
    n=struct.unpack('<i',b[:4])[0]; heads=[]; p=4
    for i in range(n):
        rid,did,off,sc=struct.unpack('<HHif',b[p:p+12]); heads.append((rid,did,off,sc)); p+=12
    links=[]
    for i in range(n):
        links.append(struct.unpack('<hhhH',b[p:p+8])); p+=8
    out={}
    for k,(rid,did,off,sc) in enumerate(heads):
        if off<=0: out[rid]={'scale':sc,'bones':{},'idx':k,'deformer':did}; continue
        cnt=struct.unpack('<i',b[off:off+4])[0]
        no=struct.unpack(f'<{cnt}h',b[off+4:off+4+2*cnt])
        names=[]
        for x in no:
            e=b.index(b'\0',off+x); names.append(b[off+x:e].decode())
        start=off+((4+2*cnt+3)&~3)  # matrices come right after the name-offset table, names after them
        M=np.frombuffer(b,dtype='<f4',count=12*cnt,offset=start).reshape(-1,3,4).astype(float)
        out[rid]={'scale':sc,'bones':dict(zip(names,M)),'idx':k,'deformer':did}
    return out,heads,links
