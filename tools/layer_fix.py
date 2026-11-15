# blender -b -P layer_fix.py -- <gap> <sf> <dg> <dz> <bg> <bb> [in.glb] [out.glb]
# in/out are bare names in builds/ (default Bottoms6058_base.glb -> Bottoms6058_dollbody.glb). Still shaped for e6058:
# it needs "mesh 1.0" (outer+inner layers) and "mesh 1.3" (hem). An existing output is never overwritten.
import bpy,bmesh,os,sys
from mathutils.bvhtree import BVHTree
M="/home/you/Projects/ffxiv-tools/XIVAutoFit/builds/"
a=sys.argv[sys.argv.index("--")+1:]; GAP=float(a[0])/1000; SF=float(a[1]); DG=float(a[2])/1000; DZ=float(a[3]); BG=float(a[4])/1000; BB=float(a[5])/1000
SRC=a[6] if len(a)>6 else "Bottoms6058_base.glb"; DST=a[7] if len(a)>7 else "Bottoms6058_dollbody.glb"
if os.path.exists(M+DST): sys.exit(f"refusing to overwrite {M+DST}; pass a new output name as the 8th argument")
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=M+SRC)
if "mesh 1.0" not in bpy.data.objects or "mesh 1.3" not in bpy.data.objects: sys.exit(f"{SRC} has no 'mesh 1.0' and 'mesh 1.3'; layer_fix.py is shaped for e6058")
o=bpy.data.objects["mesh 1.0"]; h=bpy.data.objects["mesh 1.3"]
b=bmesh.new(); b.from_mesh(o.data); b.verts.ensure_lookup_table()
seen=set(); comps=[]
for v in b.verts:
    if v.index in seen: continue
    st=[v]; c=[]; seen.add(v.index)
    while st:
        x=st.pop(); c.append(x.index)
        for e in x.link_edges:
            w=e.other_vert(x)
            if w.index not in seen: seen.add(w.index); st.append(w)
    comps.append(c)
black=[c for c in comps if len(c)>250 and max(b.verts[i].co.z for i in c)<0.9]
bi={i for c in black for i in c}
t=bmesh.new(); mp={i:t.verts.new(b.verts[i].co) for i in sorted(bi)}
for f in b.faces:
    if all(v.index in bi for v in f.verts): t.faces.new([mp[v.index] for v in f.verts])
t.normal_update(); T=BVHTree.FromBMesh(t)
hb=bmesh.new(); hb.from_mesh(h.data); hb.verts.ensure_lookup_table(); n=0
for v in hb.verts:
    loc,nr,i,d=T.find_nearest(v.co)
    if loc is not None and d<0.05:
        sd=(v.co-loc).dot(nr)
        if sd<GAP: v.co+=nr*(GAP-sd); n+=1
print("hem pushed",n,"of",len(hb.verts)); hb.to_mesh(h.data)
dn=0
for v in b.verts:
    if v.index in bi or v.co.z>DZ: continue
    loc,nr,i,d=T.find_nearest(v.co)
    if loc is not None and d<0.05:
        sd=(v.co-loc).dot(nr)
        if sd<DG: v.co+=nr*(DG-sd); dn+=1
print("denim pushed",dn)
belt={q.index for c in comps if min(b.verts[i].co.z for i in c)>=0.93 for q in [b.verts[i] for i in c]}
print("belt verts",len(belt))
if SF!=1:
    ws=[v for v in b.verts if v.index not in bi and 0.97<v.co.z<1.0]; cy=sum(v.co.y for v in ws)/len(ws)
    for v in b.verts:
        if v.index in bi or v.index in belt: continue
        s=min(1,max(0,(v.co.z-0.90)/0.07)); s=s*s*(3-2*s); f=1+(SF-1)*s
        v.co.x*=f; v.co.y=cy+(v.co.y-cy)*f
    sk=bmesh.new()
    for ob in bpy.data.objects:
        if ob.type=="MESH" and ob.name.startswith("mesh 0."):
            q=bmesh.new(); q.from_mesh(ob.data); me=bpy.data.meshes.new("t"); q.to_mesh(me); sk.from_mesh(me); q.free()
    sk.verts.ensure_lookup_table(); sk.normal_update(); TS=BVHTree.FromBMesh(sk); nb=0
    for i in belt:
        v=b.verts[i]; loc,nr,_,d=TS.find_nearest(v.co)
        if loc is not None and d<0.05 and (v.co-loc).dot(nr)<BG: v.co+=nr*(BG-(v.co-loc).dot(nr)); nb+=1
    print("belt pushed",nb)
    body=[c for c in comps if len(c)>400][0]; bs=set(body)
    tb=bmesh.new(); mq={i:tb.verts.new(b.verts[i].co) for i in sorted(bs)}
    for f in b.faces:
        if all(v.index in bs for v in f.verts): tb.faces.new([mq[v.index] for v in f.verts])
    tb.normal_update(); TB=BVHTree.FromBMesh(tb); n2=0
    for i in belt:
        v=b.verts[i]; loc,nr,_,d=TB.find_nearest(v.co)
        if loc is not None and d<0.04 and (v.co-loc).dot(nr)<BB: v.co+=nr*(BB-(v.co-loc).dot(nr)); n2+=1
    print("belt off body",n2)
    b.to_mesh(o.data)
bpy.ops.export_scene.gltf(filepath=M+DST,export_format="GLB",export_extras=True)
