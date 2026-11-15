import bpy,bmesh,sys
from mathutils.bvhtree import BVHTree
f=sys.argv[sys.argv.index("--")+1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=f)
ms=[o for o in bpy.data.objects if o.type=="MESH" and o.name.startswith("mesh ")]
skin=[o for o in ms if o.name.startswith("mesh 0.")]
cloth=[o for o in ms if o.name.split()[1][0] not in "0" and o.material_slots and "DOLL" not in o.material_slots[0].material.name and not o.name.split()[1].startswith(("9.","8.")) or False]
cloth=[o for o in ms if not o.name.startswith("mesh 0.") and "DOLL" not in o.material_slots[0].material.name]
bm=bmesh.new()
for o in skin:
    t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); bm.from_mesh(me); t.free()
bm.verts.ensure_lookup_table(); bm.normal_update(); tr=BVHTree.FromBMesh(bm)
tot=0;inside=0;deep=0
for o in cloth:
    n=0;m=0;w=0
    for v in o.data.vertices:
        loc,nr,i,d=tr.find_nearest(v.co,0.06)
        if loc is None: continue
        sd=(v.co-loc).dot(nr); n+=1
        if sd<0.002: m+=1
        if sd<-0.003: w+=1
    tot+=n;inside+=m;deep+=w
    print(o.name,"near skin",n,"inside<2mm",m,"deeper than 3mm",w)
print("TOTAL near",tot,"inside<2mm",inside,"deeper3",deep)
