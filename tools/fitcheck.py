import bpy,bmesh,sys,numpy as np
from mathutils.bvhtree import BVHTree
# usage: blender -b -P fitcheck.py -- <glb>
# per cloth mesh: signed mm to skin (group 0). negative = cloth inside skin. also where the negatives sit.
f=sys.argv[sys.argv.index("--")+1]
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=f)
ms=[o for o in bpy.data.objects if o.type=="MESH" and o.name.startswith("mesh ")]
G=lambda o:int(o.name.split()[1].split(".")[0])
def mat(o): return o.material_slots[0].material.name if o.material_slots and o.material_slots[0].material else ""
skin=[o for o in ms if G(o)==0]; cloth=[o for o in ms if G(o)>=1 and "DOLL" not in mat(o)]
bm=bmesh.new()
for o in skin:
    t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); bm.from_mesh(me); t.free()
bm.verts.ensure_lookup_table(); bm.normal_update(); T=BVHTree.FromBMesh(bm)
for o in sorted(cloth,key=lambda x:x.name):
    d=[];neg=[]
    for v in o.data.vertices:
        loc,nr,i,dist=T.find_nearest(v.co)
        if loc is None or dist>0.05: continue
        s=(v.co-loc).dot(nr)*1000; d.append(s)
        if s<-1: neg.append((v.co.z,v.co.y))
    d=np.array(d)
    if not len(d): print("CLOTH",o.name,"no skin within 5cm"); continue
    where=""
    if neg:
        z=np.array([n[0] for n in neg]); y=np.array([n[1] for n in neg])
        where=f" neg<-1mm: {len(neg)} z[{z.min():.2f},{z.max():.2f}] front={int((y<0).sum())} back={int((y>=0).sum())}"
    print("CLOTH",o.name,len(d),"p1/p5/p50",np.percentile(d,[1,5,50]).round(1),where)
