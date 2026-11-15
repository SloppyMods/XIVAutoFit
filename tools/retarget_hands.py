import bpy,sys,os
import numpy as np
from mathutils import Vector
a=sys.argv[sys.argv.index("--")+1:]
outfit,doll,out,keep=a[0],a[1],a[2],int(a[3])
OUT="/home/you/Projects/ffxiv-tools/XIVAutoFit/builds/"
bpy.ops.wm.read_factory_settings(use_empty=True)
def load(f):
    b=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=f); return [o for o in bpy.data.objects if o not in b]
O=load(outfit); D=load(doll)
oa=next(o for o in O if o.type=="ARMATURE"); da=next(o for o in D if o.type=="ARMATURE")
for o in [x for x in D if x.type=="MESH"]:
    if o.name in bpy.data.objects: bpy.data.objects.remove(o)
for o in list(O):
    if o.type=="MESH" and o.name.startswith("mesh ") and int(o.name.split()[1].split(".")[0])>=keep: bpy.data.objects.remove(o)
    elif o.type=="MESH" and o.name.startswith("Icosphere"): bpy.data.objects.remove(o)
O=[o for o in bpy.data.objects if o.type=="MESH" and o.name.startswith("mesh ")]
TOK=("j_te","j_hito","j_naka","j_kusu","j_ko_","j_oya","n_hte")
def fit(X,Y):
    mx,my=X.mean(0),Y.mean(0); Xc,Yc=X-mx,Y-my
    U,S,Vt=np.linalg.svd(Yc.T@Xc/len(X)); d=np.sign(np.linalg.det(U@Vt)); Dm=np.diag([1,1,d])
    R=U@Dm@Vt; s=(S*np.array([1,1,d])).sum()/((Xc**2).sum()/len(X)); t=my-s*R@mx
    return s,R,t
ob={b.name:np.array(b.head_local) for b in oa.data.bones}; db={b.name:np.array(b.head_local) for b in da.data.bones}
for o in O:
    if o.data.shape_keys: o.shape_key_clear()
for suf in ("_l","_r"):
    names=[n for n in ob if n.endswith(suf) and any(t in n for t in TOK) and n in db]
    X=np.array([ob[n] for n in names]); Y=np.array([db[n] for n in names])
    s,R,t=fit(X,Y); sign=1 if X[:,0].mean()>0 else -1
    res=np.linalg.norm((s*(R@X.T).T+t)-Y,axis=1)
    print("side",suf,"bones",len(names),"scale",round(s,3),"residual mm mean/max",round(res.mean()*1000,1),round(res.max()*1000,1))
    for o in O:
        if o.type!="MESH": continue
        me=o.data
        def tf(v): return Vector(s*(R@np.array(v))+t)
        sel=[v.index for v in me.vertices if (v.co.x*sign)>=0]
        if me.shape_keys:
            for kb in me.shape_keys.key_blocks:
                for i in sel: kb.data[i].co=tf(kb.data[i].co)
        for i in sel: me.vertices[i].co=tf(me.vertices[i].co)
        me.update()
dn={b.name for b in da.data.bones}
for o in O:
    miss=[g.name for g in o.vertex_groups if g.name not in dn]
    idx={g.name:g.index for g in o.vertex_groups}
    used=sum(1 for v in o.data.vertices for ge in v.groups if ge.weight>0 and o.vertex_groups[ge.group].name in miss)
    print("missing-bone weights used",o.name,used)
    for n in miss: o.vertex_groups.remove(o.vertex_groups[n])
    o.parent=da; o.matrix_parent_inverse=da.matrix_world.inverted()
    for m in o.modifiers:
        if m.type=="ARMATURE": m.object=da
bpy.data.objects.remove(oa)
bpy.ops.export_scene.gltf(filepath=OUT+out,export_format="GLB",export_extras=True)
print("done")
