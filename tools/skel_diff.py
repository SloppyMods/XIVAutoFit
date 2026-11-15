import bpy,sys
a=sys.argv[sys.argv.index("--")+1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
R=[]
for f in a:
    b=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=f); n=[o for o in bpy.data.objects if o not in b]
    ar=next(o for o in n if o.type=="ARMATURE"); R.append({x.name:x.head_local.copy() for x in ar.data.bones})
A,B=R; common=sorted(set(A)&set(B))
d=sorted(((A[k]-B[k]).length*1000,k) for k in common)
print("bones",len(A),len(B),"common",len(common),"median mm",round(d[len(d)//2][0],1),"p90",round(d[int(len(d)*.9)][0],1),"max",[(round(x,1),k) for x,k in d[-3:]])
hand=[x for x in d if any(t in x[1] for t in ("j_te","j_hito","j_naka","j_kusu","j_ko_","j_oya","n_hte","j_ude_b","n_hkata"))]
print("hand bones",len(hand),"median mm",round(hand[len(hand)//2][0],1) if hand else None,"max",round(max(x for x,_ in hand),1) if hand else None)
