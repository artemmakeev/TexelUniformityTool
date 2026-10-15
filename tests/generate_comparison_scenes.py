"""Generate disposable matched .blend files in Blender 4.0, readable by both builds."""
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix

sys.path.insert(0,str(Path(__file__).resolve().parent))
from comparison_common import *
from benchmark import grid

SCENES.mkdir(exist_ok=True)
existing={}
if (SCENES/'manifest.json').exists():
    existing={r['label']:r for r in json.loads((SCENES/'manifest.json').read_text())['scenes']}
records=[]
for label,kind,count in [('grid64','grid8',1),('grid65536','grid256',1),
                         ('props64','props',64),('cubes16','cube',16),('cubes128','cube',128),('cubes512','cube',512),
                         ('cubes1024','cube',1024),('props1024','props',1024)]:
    if label in existing and hash_file(SCENES/(label+'.blend'))==existing[label]['scene_sha256']:
        records.append(existing[label]);continue
    clear();bpy.context.scene.unit_settings.scale_length=1.
    if kind.startswith('grid'):
        objects,uv=grid(int(kind[4:]),count)
        for i,obj in enumerate(objects):set_uv(obj.data,uv.reshape(-1,2)*np.array((.7,1.3),np.float32))
    else:
        templates=[prop_mesh(x,i%4) for i,x in enumerate(('crate','pipe','bracket','cube') if kind=='props' else ('cube',))]
        objects=[]
        for i in range(count):
            mesh=templates[i%len(templates)].copy();obj=bpy.data.objects.new(f'Prop{i:04}',mesh)
            bpy.context.collection.objects.link(obj);obj.select_set(True)
            if kind=='props':
                obj.matrix_world=Matrix.Rotation((i%5)*.23,4,'Z')@Matrix.Diagonal((.8+.1*(i%4),1.3,.9,1))
            objects.append(obj)
        bpy.context.view_layer.objects.active=objects[0];bpy.context.view_layer.update()
        for i,obj in enumerate(objects):uniform_triangle_uv(obj,i,count)
    bpy.context.view_layer.objects.active=objects[0]
    bpy.context.view_layer.update()
    record={'label':label,'objects':count,'polygons':sum(len(o.data.polygons) for o in objects),
            'vertices':sum(len(o.data.vertices) for o in objects),'loops':sum(len(o.data.loops) for o in objects),
            'scale_length':1.,'texture_resolution':4096,'target_density_px_cm':17.3,
            'geometry':kind,'uniform_density_within_each_object':True}
    path=SCENES/(label+'.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=False)
    record['scene_sha256']=hash_file(path);records.append(record)
    print(json.dumps(record),flush=True)
(SCENES/'manifest.json').write_text(json.dumps({'generated_blender':bpy.app.version_string,'scenes':records},indent=2))
