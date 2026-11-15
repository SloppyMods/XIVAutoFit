import bpy,sys,math
# usage: blender -b -P render_views.py -- <glb> <out_prefix> [zc] [scale] [cyan]
# front/back/side/chest ortho renders. skin tan (or cyan with 5th arg), cloth by group, joints red.
a=sys.argv[sys.argv.index("--")+1:]; src,prefix=a[0],a[1]
zc=float(a[2]) if len(a)>2 else 1.15; osc=float(a[3]) if len(a)>3 else 0.62; cyan=len(a)>4
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
def mat(o): return o.material_slots[0].material.name if o.material_slots and o.material_slots[0].material else ""
for o in [x for x in bpy.data.objects if x.type=="MESH" and mat(x)]:
    m=mat(o)
    if "DOLL" in m: o.color=(0.9,0.15,0.12,1)
    elif m.startswith("/mt_c0201b0001_"): o.color=(0,1,1,1) if cyan else (0.85,0.72,0.58,1)
    else:
        g=int(o.name.split()[1].split(".")[0])
        o.color=[(0.35,0.4,0.5,1),(0.3,0.5,0.4,1),(0.5,0.45,0.3,1),(0.45,0.35,0.5,1)][(g-1)%4]
sc=bpy.context.scene; sc.render.engine="BLENDER_WORKBENCH"
sc.display.shading.light="STUDIO"; sc.display.shading.color_type="OBJECT"; sc.display.shading.show_cavity=True
sc.render.resolution_x=sc.render.resolution_y=1000
cam=bpy.data.objects.new("c",bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera=cam
cam.data.type="ORTHO"
r=math.radians
for n,(loc,rot,s) in {"front":((0,-3,zc),(r(90),0,0),osc),"back":((0,3,zc),(r(90),0,r(180)),osc),
    "side":((3,0,zc),(r(90),0,r(90)),osc),"chest":((0.9,-1.2,zc+0.18),(r(90),0,r(37)),0.30)}.items():
    cam.location=loc; cam.rotation_euler=rot; cam.data.ortho_scale=s
    sc.render.filepath=f"{prefix}_{n}.png"; bpy.ops.render.render(write_still=True)
