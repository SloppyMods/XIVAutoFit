import bpy,bmesh
from collections import Counter
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath="/home/you/Documents/Meddle/c0201e0000_glv.glb")
for o in [o for o in bpy.data.objects if o.type=="MESH" and o.name.startswith("mesh") and any(s.material and "DOLL" in s.material.name for s in o.material_slots)]:
    vg={g.index:g.name for g in o.vertex_groups}
    bm=bmesh.new(); bm.from_mesh(o.data); bm.verts.ensure_lookup_table()
    seen=set(); comps=[]
    for v in bm.verts:
        if v.index in seen: continue
        st=[v]; c=[]; seen.add(v.index)
        while st:
            x=st.pop(); c.append(x)
            for e in x.link_edges:
                y=e.other_vert(x)
                if y.index not in seen: seen.add(y.index); st.append(y)
        comps.append(c)
    print("##",o.name,len(bm.verts),"components",len(comps))
    dl=o.data.vertices
    for c in sorted(comps,key=lambda c:sum(v.co.x for v in c)/len(c)):
        cnt=Counter()
        for v in c:
            w=max(dl[v.index].groups,key=lambda g:g.weight) if dl[v.index].groups else None
            if w: cnt[vg[w.group]]+=1
        ctr=[sum(v.co[i] for v in c)/len(c) for i in range(3)]
        print(" n",len(c),"ctr",[round(x,3) for x in ctr],cnt.most_common(2))
