import bpy,numpy as np,sys
f=sys.argv[sys.argv.index("--")+1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=f)
for o in bpy.data.objects:
    if o.type=="MESH" and o.name.startswith("mesh"):
        v=np.array([x.co[:] for x in o.data.vertices])
        print("T",f.split("/")[-1][:14],o.name,len(v),[m.name for m in o.data.materials],"x",v[:,0].min().round(2),v[:,0].max().round(2),"y",v[:,1].min().round(2),v[:,1].max().round(2),"z",v[:,2].min().round(2),v[:,2].max().round(2),[k for k in o.keys()])
