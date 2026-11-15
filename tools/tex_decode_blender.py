# Run in Blender: decode each given .dds to a .npy RGBA array.
import bpy,sys,numpy as np
a=sys.argv[sys.argv.index('--')+1:]
for i in range(0,len(a),2):
    im=bpy.data.images.load(a[i]); im.colorspace_settings.name='Non-Color'
    w,h=im.size; px=np.empty(w*h*4,'f4'); im.pixels.foreach_get(px); px=px.reshape(h,w,4)[::-1]
    np.save(a[i+1],(np.clip(px,0,1)*255+.5).astype('u1')); print('decoded',a[i],w,h,px.mean((0,1)))
