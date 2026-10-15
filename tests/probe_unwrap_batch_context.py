"""Disposable proof: does a single Edit session support independent per-object Smart UV?"""
import json
from pathlib import Path
import sys
import time
import bpy
import bmesh
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from comparison_common import *

clear();objects=[]
for i in range(4):
    obj=bpy.data.objects.new('Proof'+str(i),prop_mesh(('crate','pipe','bracket','cube')[i],i))
    bpy.context.collection.objects.link(obj);obj.select_set(True);obj.data.uv_layers.new();objects.append(obj)
bpy.context.view_layer.objects.active=objects[0]
expected={}
for obj in objects:obj.select_set(False)
for obj in objects:
    obj.select_set(True);bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.02)
    bpy.ops.object.mode_set(mode='OBJECT');expected[obj.name]=read_uv(obj.data).copy()
    set_uv(obj.data,np.zeros_like(expected[obj.name]));obj.select_set(False)
for obj in objects:obj.select_set(True)
bpy.context.view_layer.objects.active=objects[0]
faces_only='--faces' in sys.argv
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='DESELECT' if faces_only else 'SELECT')
for obj in objects:
    if faces_only:
        bm=bmesh.from_edit_mesh(obj.data)
        for face in bm.faces:face.select_set(True)
        bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
    with bpy.context.temp_override(object=obj,active_object=obj,edit_object=obj,
            selected_objects=[obj],selected_editable_objects=[obj],objects_in_mode=[obj],
            objects_in_mode_unique_data=[obj]):
        bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.02)
    if faces_only:
        for face in bm.faces:face.select_set(False)
        bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
bpy.ops.object.mode_set(mode='OBJECT')
errors={obj.name:float(np.max(np.abs(read_uv(obj.data)-expected[obj.name]))) for obj in objects}
report={'blender':bpy.app.version_string,'faces_only':faces_only,'per_object_max_uv_error':errors,'equivalent':max(errors.values())<2e-6}
(ROOT/f'artifacts/unwrap-context-proof-{bpy.app.version[0]}.{bpy.app.version[1]}{"-faces" if faces_only else ""}.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
