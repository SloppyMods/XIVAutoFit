import bpy,sys,os
from mathutils import Vector
a=sys.argv[sys.argv.index("--")+1:]
src,out,scale=a[0],a[1],float(a[2])
M="/home/you/Documents/Meddle/"
OUT="/home/you/Projects/ffxiv-tools/XIVAutoFit/builds/"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=M+src)
arm=next(o for o in bpy.data.objects if o.type=="ARMATURE")
side={"mesh 1.0":"j_ude_b_l","mesh 1.4":"j_ude_b_l","mesh 1.5":"j_ude_b_r","mesh 1.8":"j_ude_b_r"}
for o in bpy.data.objects:
    if o.type=="MESH" and o.name in side:
        c=arm.data.bones[side[o.name]].head_local
        for v in o.data.vertices: v.co=c+(v.co-c)*scale
        o.data.update()
    if o.name.startswith("Icosphere"): bpy.data.objects.remove(o)
if len(a)>3 and a[3]=="elbows_only":
    for o in list(bpy.data.objects):
        if o.type=="MESH" and o.name.startswith("mesh 0."): bpy.data.objects.remove(o)
    el=sorted([o for o in bpy.data.objects if o.type=="MESH"],key=lambda o:[int(x) for x in o.name.split()[1].split(".")])
    for i,o in enumerate(el): o.name="tmp%d"%i
    for i,o in enumerate(el): o.name="mesh 0.%d"%i
bpy.ops.export_scene.gltf(filepath=OUT+out,export_format="GLB",export_extras=True)
print("scaled",scale)
