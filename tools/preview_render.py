import bpy,sys,math
from mathutils import Vector
a=sys.argv[sys.argv.index("--")+1:]; src,png=a[0],a[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
cols={"DOLL":(0.9,0.1,0.1,1),"glv_a":(0.2,0.2,0.25,1),"_b":(0.85,0.7,0.55,1)}
ms=[o for o in bpy.data.objects if o.type=="MESH" and o.material_slots and o.material_slots[0].material]
for o in ms:
    n=o.material_slots[0].material.name
    o.color=next((c for k,c in cols.items() if k in n),(0.5,0.5,0.5,1))
    o.hide_render = ("Icosphere" in o.name)
sc=bpy.context.scene; sc.render.engine="BLENDER_WORKBENCH"
sc.display.shading.light="STUDIO"; sc.display.shading.color_type="OBJECT"
sc.render.resolution_x=1400; sc.render.resolution_y=700
sc.display.shading.show_cavity=False
pts=[v for o in ms for v in (o.matrix_world@Vector(c) for c in o.bound_box)]
# left hand region (x>0 in model) front view
c=Vector((sum(p.x for p in pts)/len(pts),sum(p.y for p in pts)/len(pts),sum(p.z for p in pts)/len(pts)))
cam=bpy.data.objects.new("c",bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera=cam
cam.data.type="ORTHO"; ext=max(max(p.x for p in pts)-min(p.x for p in pts),1e-3); cam.data.ortho_scale=0.30
cam.rotation_euler=(0,0,0)
hc=Vector((min(p.x for p in pts)+0.12,c.y,c.z))
for name,loc,rot in (("top",hc+Vector((0,0,2)),(0,0,0)),):
    cam.location=loc; cam.rotation_euler=rot; sc.render.filepath=png; bpy.ops.render.render(write_still=True)
print("rendered",png,[ (o.name,o.rotation_mode) for o in ms][:1])
