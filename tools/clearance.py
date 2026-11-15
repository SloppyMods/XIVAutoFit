import bpy,bmesh,sys,numpy as np
from mathutils.bvhtree import BVHTree
f=sys.argv[sys.argv.index("--")+1]
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=f)
ms=[o for o in bpy.data.objects if o.type=="MESH" and o.name.startswith("mesh ")]
bm=bmesh.new()
for o in ms:
    if o.name.startswith("mesh 0."):
        t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); bm.from_mesh(me); t.free()
bm.verts.ensure_lookup_table(); bm.normal_update(); T=BVHTree.FromBMesh(bm)
for o in ms:
    if o.name.startswith("mesh 1."):
        d=[]
        for v in o.data.vertices:
            loc,nr,i,dist=T.find_nearest(v.co)
            if loc is not None and dist<0.03: d.append(((v.co-loc).dot(nr))*1000)
        d=np.array(d); print("CL",o.name,len(d),"signed mm p5/p25/p50/p75",np.percentile(d,[5,25,50,75]).round(1) if len(d) else "-")
