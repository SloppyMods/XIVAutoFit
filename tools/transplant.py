import bpy,os,sys
a=sys.argv[sys.argv.index("--")+1:]
outfit,joints,out=a[0],a[1],a[2]
THR=float(a[3]) if len(a)>3 else 0
KEEP=int(a[4]) if len(a)>4 else 99
bpy.ops.wm.read_factory_settings(use_empty=True)
M="/home/you/Documents/Meddle/"
OUT="/home/you/Projects/ffxiv-tools/XIVAutoFit/builds/"
os.makedirs(OUT,exist_ok=True)
def load(f):
    b=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=f if os.path.isabs(f) else M+f); return [o for o in bpy.data.objects if o not in b]
O=load(outfit)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"): bpy.data.objects.remove(o)
for o in list(bpy.data.objects):
    if o.type=="MESH" and o.name.startswith("mesh ") and int(o.name.split()[1].split(".")[0])>=KEEP: bpy.data.objects.remove(o)

import os as _os
if _os.environ.get("FIXL"):
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    gl=[o for o in bpy.data.objects if o.type=="MESH" and o.material_slots and o.material_slots[0].material and "glv_a" in o.material_slots[0].material.name][0]
    V=gl.data.vertices; R=[v for v in V if v.co.x<0]; idx={v.index:i for i,v in enumerate(R)}
    bm=[Vector((-v.co.x,v.co.y,v.co.z)) for v in R]
    tris=[]
    for p in gl.data.polygons:
        if all(i in idx for i in p.vertices):
            q=[idx[i] for i in p.vertices]; tris+= [(q[0],q[1],q[2])]+([(q[0],q[2],q[3])] if len(q)==4 else [])
    tree=BVHTree.FromPolygons(bm,tris); moved=0
    for v in V:
        if v.co.x>0:
            loc,n,i,d=tree.find_nearest(v.co)
            if loc is not None and d>0.0005: v.co=loc; moved+=1
    F=float(_os.environ.get("FATTEN","0"))/1000
    if F:
        gl.data.update()
        for v in V:
            if v.co.x>0.50: v.co=v.co+v.normal*F
    S=float(_os.environ.get("SHRINK","0"))/1000
    if S:
        for o in bpy.data.objects:
            if o.type=="MESH" and o.material_slots and o.material_slots[0].material and o.material_slots[0].material.name.endswith("b.mtrl") and "DOLL" not in o.material_slots[0].material.name:
                o.data.update()
                for v in o.data.vertices:
                    if 0.52<v.co.x<0.565: v.co=v.co-v.normal*S
                o.data.update()
    gl.data.update(); print("fixleft moved",moved,"fatten",F,"shrink",S)
omesh=[o for o in bpy.data.objects if o.type=="MESH" and o.name.startswith("mesh ")]
idx=1+max(int(o.name.split()[1].split(".")[0]) for o in omesh)
D=load(joints)
D=[o for o in D if o.name in bpy.data.objects]
oa=next(o for o in bpy.data.objects if o.type=="ARMATURE" and o not in D); da=next(o for o in D if o.type=="ARMATURE")
ob={b.name:b for b in oa.data.bones}; db={b.name:b for b in da.data.bones}
print("joint bones subset of outfit:",set(db)<=set(ob),len(db),len(ob))
J=[o for o in D if o.type=="MESH" and any(s.material and "DOLL" in s.material.name for s in o.material_slots)]
for o in list(D):
    if o.type!="ARMATURE" and o not in J and o.name in bpy.data.objects: bpy.data.objects.remove(o)
for i,o in enumerate(J): o.name="tmp%d"%i
for i,o in enumerate(J):
    o.name="mesh %d.%d"%(idx,i); o.parent=oa; o.modifiers["Armature"].object=oa
    for m in o.material_slots: m.material.name="/mt_c0201b0001_DOLL.mtrl" if m.material else ""


if THR<0:
    import bmesh,re
    from collections import Counter,defaultdict
    comps=[]
    for o in J:
        vg={g.index:g.name for g in o.vertex_groups}; dl=o.data.vertices
        b=bmesh.new(); b.from_mesh(o.data); b.verts.ensure_lookup_table(); seen=set()
        for v in b.verts:
            if v.index in seen: continue
            st=[v]; c=[]; seen.add(v.index)
            while st:
                x=st.pop(); c.append(x.index)
                for e in x.link_edges:
                    y=e.other_vert(x)
                    if y.index not in seen: seen.add(y.index); st.append(y)
            cnt=Counter()
            for i in c:
                if dl[i].groups:
                    w=max(dl[i].groups,key=lambda g:g.weight); cnt[vg[w.group]]+=1
            fam=[k for k,_ in cnt.most_common() if re.match(r"j_(naka|kusu|hito|ko)_a_[lr]$",k)]
            comps.append((o,b,c,fam[0] if fam else None,abs(sum(dl[i].co.x for i in c)/len(c))))
    groups=defaultdict(list)
    for t in comps:
        if t[3]: groups[t[3]].append(t)
    kill=defaultdict(list)
    for fam,l in groups.items():
        l.sort(key=lambda t:-t[4])
        for o,b,c,f,x in l[4:]: kill[id(b)]+=c
    for o,b,c,f,x in comps:
        if id(b) in kill and c and True:
            pass
    done=set()
    for o,b,c,f,x in comps:
        if id(b) in done: continue
        done.add(id(b)); b.verts.ensure_lookup_table()
        geom=[b.verts[i] for i in kill[id(b)]]
        n0=len(b.verts); bmesh.ops.delete(b,geom=geom,context="VERTS")
        print("caps",o.name,n0,"->",len(b.verts)); b.to_mesh(o.data); b.free()
if THR>0:
    import bmesh
    from mathutils.bvhtree import BVHTree
    cover=[o for o in omesh if any(s.material and "glv_a" in s.material.name or s.material and "_a.mtrl" in s.material.name for s in o.material_slots)] or [o for o in omesh if "_b" not in o.material_slots[0].material.name]
    bm=bmesh.new(); 
    for o in cover:
        t=bmesh.new(); t.from_mesh(o.data); t.transform(o.matrix_world); me=bpy.data.meshes.new("t"); t.to_mesh(me); bm.from_mesh(me); t.free()
    bm.verts.ensure_lookup_table(); tree=BVHTree.FromBMesh(bm)
    for o in J:
        b=bmesh.new(); b.from_mesh(o.data); n0=len(b.verts)
        kill=[v for v in b.verts if (tree.find_nearest(o.matrix_world@v.co)[3] or 9)<THR]
        bmesh.ops.delete(b,geom=kill,context="VERTS")
        loose=[v for v in b.verts if not v.link_faces]; bmesh.ops.delete(b,geom=loose,context="VERTS")
        print("trim",o.name,n0,"->",len(b.verts)); b.to_mesh(o.data); b.free()
bpy.data.objects.remove(da)
for m in list(bpy.data.materials):
    if m.users==0: bpy.data.materials.remove(m)
print([(o.name,[s.material.name for s in o.material_slots],len(o.data.vertices),sorted(k for k in o.keys() if k.startswith("atr_")),len(o.data.shape_keys.key_blocks) if o.data.shape_keys else 0) for o in bpy.data.objects if o.type=="MESH"])
bpy.ops.export_scene.gltf(filepath=OUT+out,export_format="GLB",export_extras=True)
