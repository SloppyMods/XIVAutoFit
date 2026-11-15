import bpy,bmesh,sys
from mathutils.bvhtree import BVHTree
a=sys.argv[sys.argv.index("--")+1:]
out,ref,names=a[0],a[1],a[2].split(",")
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=out)
cl=[o for o in bpy.data.objects if o.type=="MESH" and o.name in names]
b=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=ref)
rf=[o for o in bpy.data.objects if o not in b and o.type=="MESH" and o.material_slots and o.material_slots[0].material and "DOLL" not in o.material_slots[0].material.name and o.material_slots[0].material.name.startswith("/mt_c0201b0001_b")]
bm=bmesh.new()
for o in rf:
    t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); bm.from_mesh(me); t.free()
bm.verts.ensure_lookup_table(); bm.normal_update(); tr=BVHTree.FromBMesh(bm)
bands={}
for o in cl:
    for v in o.data.vertices:
        loc,n,i,d=tr.find_nearest(v.co,0.1)
        if loc is not None: bands.setdefault(round(v.co.z/0.05)*0.05,[]).append((v.co-loc).dot(n)*1000)
ins=sum(1 for l in bands.values() for x in l if x<2); neg=sum(1 for l in bands.values() for x in l if x<0); deep=sum(1 for l in bands.values() for x in l if x<-3); print("inside<0:",neg,"deeper than 3mm:",deep,"of",sum(len(l) for l in bands.values()))
print("inside<2mm",ins,"min",round(min(min(l) for l in bands.values()),1))
for z in sorted(bands):
    if 0.25<=z<=0.7: l=sorted(bands[z]); print("z",round(z,2),"min/med/p90",round(l[0],1),round(l[len(l)//2],1),round(l[int(len(l)*.9)],1))
