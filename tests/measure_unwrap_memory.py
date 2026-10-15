"""One cold unwrap in a fresh process; Windows lifetime peaks include setup."""
import argparse
import gc
import importlib.util
import json
from pathlib import Path
import sys
import time
import bpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from comparison_common import *

p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--scene',required=True);p.add_argument('--label',required=True)
args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);source=ROOT/args.source
spec=importlib.util.spec_from_file_location('memory_unwrap',source);tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool);tool.register()
scene=SCENES/(args.scene+'.blend');bpy.ops.wm.open_mainfile(filepath=str(scene),load_ui=False,use_scripts=False)
objects=list(bpy.context.selected_objects);active=bpy.context.active_object
before_geometry={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in objects}
bpy.context.scene.UVangle_limit=66;bpy.context.scene.UVisland_margin=.02
bpy.context.preferences.edit.use_global_undo=True;bpy.context.preferences.edit.undo_steps=2
gc.collect();bpy.ops.ed.undo_push(message='Cold unwrap memory baseline');before=memory()
start=time.perf_counter();result=bpy.ops.object.smart_uv_project_with_settings('EXEC_DEFAULT',True);bpy.context.view_layer.update();seconds=time.perf_counter()-start
after=memory()
assert result=={'FINISHED'} and bpy.context.mode=='OBJECT'
assert set(bpy.context.selected_objects)==set(objects) and bpy.context.active_object==active
for obj in objects:
    assert before_geometry[obj.name]==(len(obj.data.vertices),len(obj.data.polygons))
    assert np.isfinite(read_uv(obj.data)).all() and oracle_density(obj)>0
report={'blender':bpy.app.version_string,'source_version':list(tool.bl_info['version']),
        'source_sha256':hash_file(source),'scene':args.scene,'scene_sha256':hash_file(scene),
        'objects':len(objects),'seconds':seconds,'before_mib':before,'after_mib':after,
        'method':'one fresh-process cold registered unwrap with automatic undo and graph flush; lifetime memory peaks include startup/input load; numerical quality checked separately'}
out=ROOT/f'artifacts/unwrap-memory-{bpy.app.version[0]}.{bpy.app.version[1]}-{args.label}-{args.scene}.json'
out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
