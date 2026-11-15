import bpy,os,sys,re
from mathutils import Vector
a=sys.argv[sys.argv.index("--")+1:]
outfit,body,out=a[0],a[1],a[2]
OUT="/home/you/Projects/ffxiv-tools/XIVAutoFit/builds/"
if os.path.exists(OUT+out): sys.exit(f"refusing to overwrite {OUT+out}; pick a new name")
# Relative outfit/body/BODY2 paths resolve against EXPORTDIR. There is no fallback folder: the old default
# (~/Documents/Meddle) holds an unrelated old export, so a missing EXPORTDIR silently loaded the wrong file.
_rel=[p for p in (outfit,body,os.environ.get("BODY2","")) if p and not os.path.isabs(p)]
if _rel and not os.environ.get("EXPORTDIR"): sys.exit(f"EXPORTDIR is not set but these paths are relative: {_rel}; set EXPORTDIR or pass absolute paths")
M=os.environ.get("EXPORTDIR","")+"/"
bpy.ops.wm.read_factory_settings(use_empty=True)
def load(f):
    b=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=f if os.path.isabs(f) else M+f); return [o for o in bpy.data.objects if o not in b]
TOK=os.environ.get("JOINTMAT","DOLL").split(",")
def clean(n): return re.sub(r"(\.\d{3})+$","",n)
def isj(n): return any(t in n for t in TOK)
def mat(o): return o.material_slots[0].material.name if o.type=="MESH" and o.material_slots and o.material_slots[0].material else ""
O=load(outfit)
for o in list(bpy.data.objects):  # DROPMESH: remove source meshes by name, for two meshes that share one UNKNOWN material
    if o.type=="MESH" and o.name in os.environ.get("DROPMESH","").split(","): bpy.data.objects.remove(o)
for kv in [x for x in os.environ.get("MATFIX","").split(";") if "=" in x]:
    k,v=kv.split("=",1)
    for mm in bpy.data.materials:
        if mm.name==k: mm.name=v
for kv in [x for x in os.environ.get("GROUPMAT","").split(";") if "=" in x]:  # GROUPMAT="1=/mt_a.mtrl;2=/mt_b.mtrl": name by source group, for groups that share one UNKNOWN material
    g,v=kv.split("=",1); gm=bpy.data.materials.new(v)
    for o in bpy.data.objects:
        if o.type=="MESH" and o.name.startswith("mesh %s."%g): o.material_slots[0].material=gm
for o in list(bpy.data.objects):
    if o.type=="MESH" and (o.name.startswith("Icosphere") or (mat(o).startswith("/mt_c0201b0001_") and "piercings" not in mat(o))): bpy.data.objects.remove(o)
for o in list(bpy.data.objects):
    if o.type=="MESH" and any(t and t in mat(o) for t in os.environ.get("DROPMAT","").split(",")): bpy.data.objects.remove(o)
if os.environ.get("KEEP"):
    for o in list(bpy.data.objects):
        if o.type=="MESH" and o.name.startswith("mesh ") and int(o.name.split()[1].split(".")[0])>=int(os.environ["KEEP"]): bpy.data.objects.remove(o)
oa=next(o for o in bpy.data.objects if o.type=="ARMATURE")
cloth=[o for o in bpy.data.objects if o.type=="MESH"]
D=load(body)
da=next(o for o in D if o.type=="ARMATURE")
skin=[o for o in D if o.type=="MESH" and not isj(mat(o)) and clean(mat(o)).startswith("/mt_c0201b0001_b")]
joints=[o for o in D if o.type=="MESH" and isj(mat(o))]
if os.environ.get("NOJOINTS"): joints=[]

def merge_bones(oa,da):
    have={b.name for b in oa.data.bones}
    miss=[(b.name,b.head_local.copy(),b.tail_local.copy(),b.parent.name if b.parent else None) for b in da.data.bones if b.name not in have]
    if not miss: return 0
    bpy.context.view_layer.objects.active=oa
    bpy.ops.object.mode_set(mode="EDIT")
    eb=oa.data.edit_bones; todo=miss
    while todo:
        nxt=[]
        for n,h,t,p in todo:
            if p and p not in eb and any(x[0]==p for x in todo): nxt.append((n,h,t,p)); continue
            e=eb.new(n); e.head=h; e.tail=t if (t-h).length>1e-4 else h+Vector((0,0,0.01))
            if p and p in eb: e.parent=eb[p]
        if len(nxt)==len(todo): break
        todo=nxt
    bpy.ops.object.mode_set(mode="OBJECT")
    return len(miss)
if os.environ.get("BODY2"):
    D2=[o for o in load(os.environ["BODY2"]) if o.name in bpy.data.objects]
    s2=[o for o in D2 if o.type=="MESH" and not isj(mat(o)) and clean(mat(o)).startswith("/mt_c0201b0001_b")]
    j2=[o for o in D2 if o.type=="MESH" and isj(mat(o))]
    da2=next(o for o in D2 if o.type=="ARMATURE")
    print("body2 bones added to outfit armature:",merge_bones(oa,da2))
    for o in D2:
        if o.type=="MESH" and o not in s2 and o not in j2: bpy.data.objects.remove(o)
    bpy.data.objects.remove(da2)
    skin+=s2; joints+=j2
if os.environ.get("NIP"):
    def _bb(o): 
        zs=[v.co.z for v in o.data.vertices]; return len(zs),(min(zs)+max(zs))/2
    drop=[o for o in skin if _bb(o)[0]<=1000 and 1.20<_bb(o)[1]<1.30]
    print("dropped skin",[(o.name,_bb(o)[0]) for o in drop]); skin=[o for o in skin if o not in drop]
for o in list(D):
    if o.name in bpy.data.objects and o.type=="MESH" and o not in skin and o not in joints: bpy.data.objects.remove(o)
import re as _re
def gs(o):
    m=_re.match(r"mesh (\d+)\.(\d+)",o.name); return int(m.group(1)),m.group(2)
for i,o in enumerate(skin+joints): o.name="tmpd%d"%i
cg=sorted({gs(o)[0] for o in cloth})
for o in cloth: o.name="tmpc "+o.name
for o in cloth:
    g,sub=gs(type("x",(),{"name":o.name[5:]}))
    o.name="mesh %d.%s"%(cg.index(g)+1,sub)
cg=list(range(1,len(cg)+1))

EX=os.environ.get("EXTRAJ")
if EX:
    from mathutils.bvhtree import BVHTree
    import bmesh
    exf,exn=EX.split(":")
    bx=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath="/home/you/Projects/ffxiv-tools/XIVAutoFit/builds/"+exf)
    exo=[o for o in bpy.data.objects if o not in bx]
    ej=[o for o in exo if o.type=="MESH" and o.name==exn][0]
    dsk=[o for o in exo if o.type=="MESH" and o.name.startswith("mesh 0.")]
    def bt(objs):
        b=bmesh.new()
        for o in objs:
            t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); b.from_mesh(me); t.free()
        b.verts.ensure_lookup_table(); b.normal_update(); return BVHTree.FromBMesh(b)
    cx=sum(v.co.x for v in ej.data.vertices)/len(ej.data.vertices); cz=sum(v.co.z for v in ej.data.vertices)/len(ej.data.vertices)
    def front(objs):
        ys=[v.co.y for o in objs for v in o.data.vertices if abs(v.co.x-cx)<0.02 and abs(v.co.z-cz)<0.01]
        return min(ys) if ys else None
    yd=front(dsk); yg=front(skin)
    print("extra front y doll/golem",yd,yg)
    if yd is not None and yg is not None:
        sh=yg-yd
        for v in ej.data.vertices: v.co.y+=sh
        print("extra joint shifted y by",round(sh*1000,1),"mm")
    ej.data.update()
    cutg=[o for o in joints if "cut" in mat(o)]
    ej.name="tmpx"
    for sl in ej.material_slots:
        if sl.material: sl.material=cutg[0].material_slots[0].material
    ej.parent=oa; ej.modifiers["Armature"].object=oa
    joints.append(ej)
    for o in exo:
        if o is not ej and o.name in bpy.data.objects: bpy.data.objects.remove(o)
for o in skin+joints:
    for sl in o.material_slots:
        if sl.material: sl.material.name="tmpm_"+sl.material.name
mats=sorted({clean(mat(o).replace("tmpm_","")) for o in joints})
first=max(cg)+1
groups=[(0,skin)]+[(first+k,[o for o in joints if clean(mat(o).replace("tmpm_",""))==m]) for k,m in enumerate(mats)]
for g,l in groups:
    for i,o in enumerate(l): o.name="tmp%d_%d"%(g,i)
for g,l in groups:
    for i,o in enumerate(l):
        o.name="mesh %d.%d"%(g,i); o.parent=oa; o.modifiers["Armature"].object=oa
for me in list(bpy.data.meshes):
    if me.users==0: bpy.data.meshes.remove(me)
for m in list(bpy.data.materials):
    if m.users==0: bpy.data.materials.remove(m)
canon={}
for o in skin+joints:
    for sl in o.material_slots:
        if sl.material:
            c=clean(sl.material.name.replace("tmpm_","")); c=re.sub(r"_(characterscroll|character|skin)\.shpk$",".mtrl",c) if c.endswith(".shpk") else c
            if c not in canon: canon[c]=bpy.data.materials.new(c)
            sl.material=canon[c]
if os.environ.get("JOINTASMAT"):
    tok=os.environ["JOINTASMAT"]
    cm=next(sl.material for c in cloth for sl in c.material_slots if sl.material and tok in sl.material.name)
    for o in joints:
        for sl in o.material_slots: sl.material=cm
for m in list(bpy.data.materials):
    if m.users==0: bpy.data.materials.remove(m)

SCX=float(os.environ.get("SCX","1")); SCY=float(os.environ.get("SCY","1"))
if SCX!=1 or SCY!=1:
    cyv=[v.co.y for o in skin for v in o.data.vertices if 1.1<v.co.z<1.35 and abs(v.co.x)<0.15]
    cy=sum(cyv)/len(cyv)
    for o in [c for c in cloth if c.name in os.environ.get("SCMESH","mesh 1.0").split(",")]:
        for v in o.data.vertices: v.co=Vector((v.co.x*SCX,cy+(v.co.y-cy)*SCY,v.co.z))
        o.data.update(); print("scaled",o.name,SCX,SCY)

PUSH=float(os.environ.get("PUSH","0"))/1000
PX=float(os.environ.get("PUSHX","9"))
PZ=[float(x) for x in os.environ.get("PUSHZ","-9,9").split(",")]
if PUSH:
    import bmesh
    from mathutils.bvhtree import BVHTree
    sb=bmesh.new()
    for o in skin:
        t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); sb.from_mesh(me); t.free()
    sb.verts.ensure_lookup_table(); sb.normal_update(); tree=BVHTree.FromBMesh(sb)
    for o in [c for c in cloth if not os.environ.get('PUSHMESH') or c.name in os.environ['PUSHMESH'].split(',')]:
        b=bmesh.new(); b.from_mesh(o.data); b.verts.ensure_lookup_table(); d={}
        for v in b.verts:
            loc,n,i,dist=tree.find_nearest(v.co)
            if loc is not None and (v.co-loc).dot(n)<PUSH and PZ[0]<=v.co.z<=PZ[1] and abs(v.co.x)<=PX: d[v.index]=(loc+n*PUSH)-v.co
        for _ in range(2):
            nd=dict(d)
            for i in list(d):
                for e in b.verts[i].link_edges:
                    j=e.other_vert(b.verts[i]).index
                    if j not in d: nd[j]=Vector((0,0,0))
            for i in nd:
                nb=[nd.get(e.other_vert(b.verts[i]).index,Vector((0,0,0))) for e in b.verts[i].link_edges]
                nd[i]=(nd[i]+sum(nb,Vector((0,0,0)))*0.5/max(len(nb),1))/1.5 if False else max([nd[i]]+nb,key=lambda x:x.length) if nd[i].length<1e-9 else nd[i]
            d=nd
        grp={}
        for v in b.verts: grp.setdefault((round(v.co.x*1e4),round(v.co.y*1e4),round(v.co.z*1e4)),[]).append(v.index)
        for ids in grp.values():
            if len(ids)>1:
                vec=max((d.get(i,Vector((0,0,0))) for i in ids),key=lambda x:x.length)
                if vec.length>0:
                    for i in ids: d[i]=vec
        for i,vec in d.items(): b.verts[i].co+=vec
        print("push",o.name,len(d)); b.to_mesh(o.data); b.free()

HEM=float(os.environ.get("HEM","0"))/1000
if HEM:
    import bmesh
    from mathutils.bvhtree import BVHTree
    sb=bmesh.new()
    for o in skin:
        t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); sb.from_mesh(me); t.free()
    sb.verts.ensure_lookup_table(); sb.normal_update(); htree=BVHTree.FromBMesh(sb)
    F=Vector((0,-1,0))
    for o in [c for c in cloth if c.name in os.environ.get("HEMMESH","mesh 1.0").split(",")]*int(os.environ.get("HEMPASS","1")):
        b=bmesh.new(); b.from_mesh(o.data); b.verts.ensure_lookup_table(); d={}
        for v in b.verts:
            if v.co.z<float(os.environ.get("HEMZ","1.12")) and abs(v.co.x)<0.2:
                hit=htree.ray_cast(v.co,F,0.15)
                if hit[0] is not None: d[v.index]=(hit[0]+F*HEM)-v.co
        for _ in range(3):
            nd={}
            for i,vec in d.items():
                nd[i]=vec
                for e in b.verts[i].link_edges:
                    j=e.other_vert(b.verts[i]).index
                    if j not in d and j not in nd: nd[j]=vec*0.5
            d=nd
        for i,vec in d.items(): b.verts[i].co+=vec
        print("hem",o.name,len(d)); b.to_mesh(o.data); b.free()

FT=float(os.environ.get("FT","1")); FB=float(os.environ.get("FB","1"))
if FT!=1 or FB!=1:
    def ss(t): t=max(0,min(1,t)); return t*t*(3-2*t)
    cys=[v.co.y for o in skin for v in o.data.vertices if 0.5<v.co.z<1.0]
    cy=sum(cys)/len(cys)
    cxs={}
    for sg in (1,-1):
        xs=[v.co.x for o in skin for v in o.data.vertices if 0.5<v.co.z<0.9 and v.co.x*sg>0.02]
        cxs[sg]=sum(xs)/len(xs)
    for o in [c for c in cloth]:
        for v in o.data.vertices:
            z=v.co.z; w=ss((z-0.45)/0.25)*(1-ss((z-1.0)/0.1))
            if w<=0: continue
            sg=1 if v.co.x>=0 else -1
            f=1+(FT-1)*w
            x=cxs[sg]+(v.co.x-cxs[sg])*f; y=cy+(v.co.y-cy)*f
            if y>cy:
                wb=ss((z-0.78)/0.1)*(1-ss((z-1.0)/0.1)); y=cy+(y-cy)*(1+(FB-1)*wb)
            v.co=Vector((x,y,z))
        o.data.update()
    print("legscale",FT,FB)

if os.environ.get("WSYNC"):
    from mathutils.kdtree import KDTree
    zlo,zhi=float(os.environ.get("WZLO","0.3")),float(os.environ.get("WZHI","1.1"))
    bands=[(zlo,zhi,float(os.environ.get("WXMAX","9")))]+[tuple(float(x) for x in b.split(",")) for b in os.environ.get("WBANDS","").split(";") if b]  # WBANDS="zlo,zhi,xmax;...": extra bands, each with its own x limit
    wsrc=[x for x in os.environ.get("WSYNCSRC","").split(",") if x]  # WSYNCSRC="mesh 2.0": copy from these cloth meshes only, not from a sash or a hidden layer that happens to be nearer
    pts=[(o,v.index) for o in cloth for v in o.data.vertices if not wsrc or o.name in wsrc]
    kd=KDTree(len(pts))
    for k,(o,i) in enumerate(pts): kd.insert(o.data.vertices[i].co,k)
    kd.balance()
    def dom(o,i):
        g=o.data.vertices[i].groups
        return o.vertex_groups[max(g,key=lambda x:x.weight).group].name if g else None
    def corner_weights(co_o,ci): return [(co_o.vertex_groups[g.group].name,g.weight) for g in co_o.data.vertices[ci].groups]
    wtri=None
    if os.environ.get("WSYNCTRI"):  # WSYNCTRI=1: blend the corners of the nearest cloth triangle, so skin follows the cloth surface; one vertex's weights can differ from the surface on coarse cloth
        from mathutils.bvhtree import BVHTree
        tv=[];tf=[];towner=[]
        for c in [c for c in cloth if not wsrc or c.name in wsrc]:
            base=len(tv); tv+=[x.co.copy() for x in c.data.vertices]
            for p in c.data.polygons:
                for t in range(1,len(p.vertices)-1):
                    tf.append((base+p.vertices[0],base+p.vertices[t],base+p.vertices[t+1])); towner.append((c,p.vertices[0],p.vertices[t],p.vertices[t+1]))
        wtri=BVHTree.FromPolygons([tuple(x) for x in tv],tf)
    def blended(co):
        loc,_,fi,_=wtri.find_nearest(co); c,i0,i1,i2=towner[fi]
        a,b,e=(c.data.vertices[i].co for i in (i0,i1,i2)); v0,v1,v2=b-a,e-a,loc-a
        d00,d01,d11,d20,d21=v0.dot(v0),v0.dot(v1),v1.dot(v1),v2.dot(v0),v2.dot(v1); den=(d00*d11-d01*d01) or 1e-12
        u1,u2=(d11*d20-d01*d21)/den,(d00*d21-d01*d20)/den
        mix={}
        for share,ci in ((1-u1-u2,i0),(u1,i1),(u2,i2)):
            for nme,w in corner_weights(c,ci): mix[nme]=mix.get(nme,0)+max(share,0)*w
        top=sorted(mix.items(),key=lambda x:-x[1])[:4]; total=sum(w for _,w in top) or 1  # the game keeps 4 bones per vertex
        return [(nme,w/total) for nme,w in top if w>0]
    for o in (joints if os.environ.get('WSYNCJ') else skin+joints):
        ch=0;tot=0
        for v in o.data.vertices:
            if any(a<v.co.z<b and abs(v.co.x)<c for a,b,c in bands):
                tot+=1
                if wtri:
                    src=blended(v.co)
                    if dom(o,v.index)!=max(src,key=lambda x:x[1])[0]: ch+=1
                else:
                    co,k,d=kd.find(v.co); co_o,ci=pts[k]
                    if dom(o,v.index)!=dom(co_o,ci): ch+=1
                    src=corner_weights(co_o,ci)
                for g in list(v.groups): o.vertex_groups[g.group].remove([v.index])
                for nme,w in src:
                    vg=o.vertex_groups.get(nme) or o.vertex_groups.new(name=nme)
                    vg.add([v.index],w,"REPLACE")
        print("wsync",o.name,"verts",tot,"dominant-bone differed",ch)

H2=float(os.environ.get("HEM2","0"))/1000
if H2:
    import bmesh
    from mathutils.bvhtree import BVHTree
    from mathutils.kdtree import KDTree
    sb=bmesh.new()
    for o in skin:
        t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); sb.from_mesh(me); t.free()
    sb.verts.ensure_lookup_table(); sb.normal_update(); htree=BVHTree.FromBMesh(sb)
    F=Vector((0,-1,0)); R1=float(os.environ.get("HR1","0.02")); R2=float(os.environ.get("HR2","0.025")); hz=float(os.environ.get("HEMZ","1.12"))
    for o in [c for c in cloth if c.name in os.environ.get("HEMMESH","mesh 1.0").split(",")]:
        V=o.data.vertices; n=len(V); s=[0.0]*n
        for v in V:
            if v.co.z<hz and abs(v.co.x)<0.2:
                hit=htree.ray_cast(v.co,F,0.15)
                if hit[0] is not None: s[v.index]=(hit[0]-v.co).length+H2
        kd=KDTree(n)
        for v in V: kd.insert(v.co,v.index)
        kd.balance()
        s1=[max([s[j] for _,j,d in kd.find_range(v.co,R1)]+[0]) for v in V]
        s2=[]
        for v in V:
            num=den=0.0
            for _,j,d in kd.find_range(v.co,R2):
                w=1-d/R2; num+=w*s1[j]; den+=w
            s2.append(num/den if den else 0)
        m=0
        for v in V:
            if s2[v.index]>1e-6: v.co=v.co+F*s2[v.index]; m+=1
        o.data.update(); print("hem2",o.name,m)

FF=float(os.environ.get("FITFAST","0"))/1000
if FF:
    import bmesh, numpy as np
    from mathutils.bvhtree import BVHTree
    refs=list(skin)
    if os.environ.get("FITREF"):
        bx=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=os.environ["FITREF"])
        rx=[o for o in bpy.data.objects if o not in bx]
        refs+=[o for o in rx if o.type=="MESH" and o.material_slots and o.material_slots[0].material and clean(o.material_slots[0].material.name).startswith("/mt_c0201b0001_b") and "DOLL" not in o.material_slots[0].material.name]
    sb=bmesh.new()
    for o in refs:
        t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); sb.from_mesh(me); t.free()
    sb.verts.ensure_lookup_table(); sb.normal_update(); ftr=BVHTree.FromBMesh(sb)
    CELL=float(os.environ.get("FITCELL","0.01")); RD=int(os.environ.get("FITRD","2")); RB=int(os.environ.get("FITRB","3"))
    LAYF=float(os.environ.get("FITLAYER","0.02")); SMAXF=float(os.environ.get("FITSMAX","0.08"))
    names=lambda k:[x for x in os.environ.get(k,"").split(",") if x]
    appn=names("FITMESH"); srcn=names("FITSRC") or appn
    def key(p): return (int(np.floor(p[0]/CELL)),int(np.floor(p[1]/CELL)),int(np.floor(p[2]/CELL)))
    best={}; pS={}; pC={}
    PULL=[float(x) for x in os.environ["FITPULL"].split(",")] if os.environ.get("FITPULL") else None
    PMAX=float(os.environ.get("FITPULLMAX","40"))/1000
    for o in [c for c in cloth if c.name in srcn]:
        for v in o.data.vertices:
            loc,nr,i,d=ftr.find_nearest(v.co)
            if loc is None: continue
            sd=(v.co-loc).dot(nr)
            if -SMAXF<sd<FF and sd<LAYF:
                vec=np.array(nr)*(FF-sd); k=key(v.co)
                if k not in best or np.linalg.norm(vec)>np.linalg.norm(best[k]): best[k]=vec
            elif PULL and FF<=sd<PMAX:
                t=max(0.0,min(1.0,(v.co.z-PULL[0])/(PULL[1]-PULL[0]))); t=t*t*(3-2*t)
                if t>0:
                    k=key(v.co); pS[k]=pS.get(k,0)+np.array(nr)*(FF-sd)*t; pC[k]=pC.get(k,0)+1
    offs=[(a,b,c) for a in range(-RD,RD+1) for b in range(-RD,RD+1) for c in range(-RD,RD+1)]
    dil={}
    for k,vec in best.items():
        for a,b,c in offs:
            kk=(k[0]+a,k[1]+b,k[2]+c)
            if kk not in dil or np.linalg.norm(vec)>np.linalg.norm(dil[kk]): dil[kk]=vec
    offb=[(a,b,c,max(0.0,1-np.sqrt(a*a+b*b+c*c)/(RB+1))) for a in range(-RB,RB+1) for b in range(-RB,RB+1) for c in range(-RB,RB+1)]
    S={};C={}
    for k,vec in dil.items():
        for a,b,c,w in offb:
            if w<=0: continue
            kk=(k[0]+a,k[1]+b,k[2]+c); S[kk]=S.get(kk,0)+vec*w; C[kk]=C.get(kk,0)+w
    field={k:S[k]/C[k] for k in S}
    pf={}
    if pS:
        PS={};PC={}
        for k,vec in pS.items():
            av=vec/pC[k]
            for a,b,c,w in offb:
                if w<=0: continue
                kk=(k[0]+a,k[1]+b,k[2]+c); PS[kk]=PS.get(kk,0)+av*w; PC[kk]=PC.get(kk,0)+w
        pf={k:PS[k]/PC[k] for k in PS}
    for o in [c for c in cloth if c.name in appn]:
        m=0
        for v in o.data.vertices:
            kk=key(v.co); f=field.get(kk)
            if f is None or np.linalg.norm(f)<1e-5: f=pf.get(kk)
            if f is not None: v.co=v.co+Vector(f); m+=1
        o.data.update(); print("fitfast",o.name,m,"of",len(o.data.vertices))
    if os.environ.get("FITREF"):
        for o in rx:
            if o.name in bpy.data.objects: bpy.data.objects.remove(o)
        for me in list(bpy.data.meshes):
            if me.users==0: bpy.data.meshes.remove(me)

FITM=float(os.environ.get("FIT","0"))/1000
if FITM:
    import bmesh
    from mathutils.bvhtree import BVHTree
    from mathutils.kdtree import KDTree
    sb=bmesh.new()
    for o in skin:
        t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); sb.from_mesh(me); t.free()
    sb.verts.ensure_lookup_table(); sb.normal_update(); ftree=BVHTree.FromBMesh(sb)
    R1=float(os.environ.get("FITR1","0.03")); R2=float(os.environ.get("FITR2","0.03")); SMAX=float(os.environ.get("FITSMAX","0.05"))
    for o in [c for c in cloth if c.name in os.environ.get("FITMESH","mesh 1.0").split(",")]:
        V=o.data.vertices; n=len(V); need=[Vector((0,0,0))]*n; layer=[False]*n
        LAY=float(os.environ.get("FITLAYER","0.012"))
        for v in V:
            loc,nr,i,d=ftree.find_nearest(v.co)
            if loc is None: continue
            sd=(v.co-loc).dot(nr)
            if -SMAX<sd<LAY: layer[v.index]=True
            if -SMAX<sd<FITM: need[v.index]=nr*(FITM-sd)
        kd=KDTree(n)
        for v in V:
            if layer[v.index]: kd.insert(v.co,v.index)
        kd.balance()
        dil=[Vector((0,0,0))]*n
        for v in V:
            if not layer[v.index]: continue
            best=Vector((0,0,0))
            for _,j,d in kd.find_range(v.co,R1):
                if need[j].length>best.length: best=need[j]
            dil[v.index]=best
        outv=[Vector((0,0,0))]*n
        for v in V:
            if not layer[v.index]: continue
            num=Vector((0,0,0)); den=0.0
            for _,j,d in kd.find_range(v.co,R2):
                w=1-d/R2; num+=dil[j]*w; den+=w
            outv[v.index]=num/den if den else num
        m=0
        skpts=[(so,vv.index) for so in skin for vv in so.data.vertices]
        skkd=KDTree(len(skpts))
        for k,(so,i2) in enumerate(skpts): skkd.insert(so.data.vertices[i2].co,k)
        skkd.balance()
        sdv=[9.0]*n
        for v in V:
            loc,nr,i,d=ftree.find_nearest(v.co)
            if loc is not None: sdv[v.index]=abs((v.co-loc).dot(nr))
        foll=[c for c in cloth if c.name in [x for x in os.environ.get("FITFOLLOW","").split(",") if x]]
        if foll:
            from mathutils.geometry import barycentric_transform
            bmf=bmesh.new(); bmf.from_mesh(o.data); bmesh.ops.triangulate(bmf,faces=bmf.faces)
            bmf.verts.ensure_lookup_table(); bmf.faces.ensure_lookup_table(); bmf.normal_update()
            ft_m=BVHTree.FromBMesh(bmf); fverts=[[vv.index for vv in f.verts] for f in bmf.faces]; vco0=[vv.co.copy() for vv in o.data.vertices]; bmf.free()
        disp=[Vector((0,0,0))]*n
        for v in V:
            X0=float(os.environ.get("FITX0","9")); X1=float(os.environ.get("FITX1","9.1")); Z0=float(os.environ.get("FITZ0","9")); Z1=float(os.environ.get("FITZ1","9.1"))
            if os.environ.get("FITBZ0"):
                tb=max(0.0,min(1.0,(v.co.y-(-0.01))/0.04)); BZ0=float(os.environ["FITBZ0"]); BZ1=float(os.environ.get("FITBZ1",BZ0+0.02))
                Z0=Z0*(1-tb)+BZ0*tb; Z1=Z1*(1-tb)+BZ1*tb
            HZ=float(os.environ.get("FITHZ","0")); 
            if v.co.z<HZ: X0=float(os.environ.get("FITHX0",X0)); X1=float(os.environ.get("FITHX1",X1))
            wx=1-max(0,min(1,(abs(v.co.x)-X0)/(X1-X0))); wz=1-max(0,min(1,(v.co.z-Z0)/(Z1-Z0)))
            wgt=wx*wx*(3-2*wx)*wz*wz*(3-2*wz)
            if layer[v.index] and outv[v.index].length*wgt>1e-6: disp[v.index]=outv[v.index]*wgt; v.co=v.co+disp[v.index]; m+=1
            if os.environ.get("FITWSYNC") and layer[v.index] and wgt>0.01 and sdv[v.index]<0.03:
                co2,k2,d2=skkd.find(v.co); so,si=skpts[k2]
                new={}
                for g in so.data.vertices[si].groups: new[so.vertex_groups[g.group].name]=g.weight*wgt
                for g in v.groups: nm=o.vertex_groups[g.group].name; new[nm]=new.get(nm,0)+g.weight*(1-wgt)
                tot=sum(new.values()) or 1
                for g in list(v.groups): o.vertex_groups[g.group].remove([v.index])
                for nm,w in new.items():
                    if w>1e-4: (o.vertex_groups.get(nm) or o.vertex_groups.new(name=nm)).add([v.index],w/tot,"REPLACE")
        o.data.update(); print("fit",o.name,m)
        for fo in foll:
            fm=0
            for fv in fo.data.vertices:
                loc,nr,fi,dist=ft_m.find_nearest(fv.co)
                if loc is None: continue
                i0,i1,i2=fverts[fi]; d0,d1,d2=disp[i0],disp[i1],disp[i2]
                if d0.length==0 and d1.length==0 and d2.length==0: continue
                a0,b0,c0=vco0[i0],vco0[i1],vco0[i2]
                dv=barycentric_transform(loc,a0,b0,c0,a0+d0,b0+d1,c0+d2)-loc
                if dv.length>1e-6: fv.co=fv.co+dv; fm+=1
            fo.data.update(); print("fitfollow",fo.name,fm)

SB=float(os.environ.get("SKINBACK","0"))/1000
if SB:
    zlo=float(os.environ.get("SBZ0","1.0")); zr=float(os.environ.get("SBZR","0.03")); zhi=float(os.environ.get("SBZMAX","1.2")); xm=float(os.environ.get("SBX","0.17"))
    for o in skin:
        o.data.update(); nmv=0
        for v in o.data.vertices:
            z=v.co.z
            if zlo<z<zhi and abs(v.co.x)<xm and v.normal.y<-0.2:
                t=max(0,min(1,(z-zlo)/zr)); t=t*t*(3-2*t)
                v.co=v.co-v.normal*SB*t; nmv+=1
        o.data.update(); print("skinback",o.name,nmv)

JSX=float(os.environ.get("JSX","1"))
if JSX!=1:
    for o in [j for j in joints if j.name in os.environ.get("JSMESH","mesh 6.0").split(",")]:
        for v in o.data.vertices: v.co.x*=JSX
        o.data.update(); print("jscale",o.name,JSX)
for o in [j for j in joints if j.name in os.environ.get("DROPJ","").split(",")]:
    print("dropjoint",o.name); joints.remove(o); bpy.data.objects.remove(o)
SC=float(os.environ.get("SKINCARVE","0"))/1000
if SC:
    import bmesh
    from mathutils.bvhtree import BVHTree
    cb=bmesh.new()
    for o in cloth:
        t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); cb.from_mesh(me); t.free()
    cb.verts.ensure_lookup_table(); cb.normal_update(); ctree=BVHTree.FromBMesh(cb)
    zlo,zhi,xm,dm=float(os.environ.get("ZLO","1.0")),float(os.environ.get("ZHI","1.42")),float(os.environ.get("XMAX","0.2")),float(os.environ.get("DMAX","0.03"))
    for o in skin:
        o.data.calc_normals() if hasattr(o.data,"calc_normals") else None
        n=0
        for v in o.data.vertices:
            if zlo<v.co.z<zhi and abs(v.co.x)<xm:
                loc,nr,i,d=ctree.find_nearest(v.co,dm)
                if loc is None: continue
                pen=-((loc-v.co).dot(v.normal))
                if pen>-SC: v.co-=v.normal*min(pen+SC,0.03); n+=1
        o.data.update(); print("skincarve",o.name,n)
SI=float(os.environ.get("SHRINKIN","0"))/1000
if SI:
    import bmesh
    from mathutils.bvhtree import BVHTree
    cb=bmesh.new()
    for o in cloth:
        t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); cb.from_mesh(me); t.free()
    cb.verts.ensure_lookup_table(); cb.normal_update(); ctree=BVHTree.FromBMesh(cb)
    zlo,zhi=float(os.environ.get("ZLO","0.3")),float(os.environ.get("ZHI","1.03"))
    for o in (joints if os.environ.get('SHRINKJ') else skin+joints):
        if o.name=='tmpx': continue
        n=0
        for v in o.data.vertices:
            if zlo<v.co.z<zhi and abs(v.co.x)<float(os.environ.get("XMAX","9")):
                loc,nr,i,d=ctree.find_nearest(v.co,float(os.environ.get("DMAX","0.04")))
                if loc is not None and (v.co-loc).dot(nr)>-0.002: v.co=loc-nr*SI; n+=1
        o.data.update(); print("shrinkin",o.name,n)
PY=float(os.environ.get("PIERCEY","0"))/1000
if PY:
    for o in [c for c in cloth if "piercings" in mat(c)]:
        for v in o.data.vertices: v.co.y-=PY
        o.data.update(); print("piercey",o.name,PY)
CLEAR=float(os.environ.get("CLEAR","0"))/1000
if CLEAR:
    # final pass: any vertex of CLEARMESH closer than CLEAR to the skin (or inside it) is moved out to CLEAR, same test as fitcheck.py
    import bmesh
    from mathutils.bvhtree import BVHTree
    sb=bmesh.new()
    for o in skin+(joints if os.environ.get("CLEARJ") else []):
        t=bmesh.new(); t.from_mesh(o.data); me=bpy.data.meshes.new("t"); t.to_mesh(me); sb.from_mesh(me); t.free()
    sb.verts.ensure_lookup_table(); sb.normal_update(); ctree=BVHTree.FromBMesh(sb)
    for o in [c for c in cloth if c.name in os.environ.get("CLEARMESH","mesh 1.0").split(",")]:
        n=0
        for _ in range(3):
            for v in o.data.vertices:
                loc,nr,i,d=ctree.find_nearest(v.co,0.05)
                if loc is not None and (v.co-loc).dot(nr)<CLEAR: v.co=loc+nr*CLEAR; n+=1
        o.data.update(); print("clear",o.name,n)
bpy.data.objects.remove(da)
print([(o.name,mat(o),len(o.data.vertices),sorted(k for k in o.keys() if k.startswith("atr_"))) for o in bpy.data.objects if o.type=="MESH"])
bpy.ops.export_scene.gltf(filepath=OUT+out,export_format="GLB",export_extras=True)
