"""Validate every object's UVs against solo Blender Smart UV; time scaling separately."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys
import time
import types
from unittest.mock import patch

import bpy
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from comparison_common import *

p=argparse.ArgumentParser();p.add_argument('--counts',default='1,16,128,512,1024')
p.add_argument('--trials',type=int,default=3);p.add_argument('--props',action='store_true')
p.add_argument('--paired',action='store_true');p.add_argument('--label',default='baseline')
p.add_argument('--candidate',default='TexelUniformityTool.py')
p.add_argument('--shared',action='store_true')
p.add_argument('--scene',default='')
p.add_argument('--variants',default='')
p.add_argument('--candidate-only',action='store_true')
args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
paths=[('v1_2_0',ROOT/'tests/fixtures/texel_uniformity_v1_2_0.py')]
if args.paired:paths.append(('current',ROOT/args.candidate))
if args.candidate_only:paths=[('current',ROOT/args.candidate)]
if args.variants:
    source=(ROOT/'tests/fixtures/candidate_batch64_verified.py').read_text(encoding='utf-8')
    paths=[]
    for size in map(int,args.variants.split(',')):
        assert size in (8,16,32,64)
        generated=ROOT/f'tests/fixtures/tuning_batch{size}.py'
        generated.write_bytes(source.replace('end-start < 64',f'end-start < {size}').encode())
        paths.append((f'batch{size}',generated))
modules=[]
for name,path in paths:
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);modules.append((name,m))
base=SCENES/((args.scene+'.blend') if args.scene else ('props1024.blend' if args.props else 'cubes1024.blend'))

def load(n):
    bpy.ops.wm.open_mainfile(filepath=str(base),load_ui=False,use_scripts=False)
    objects=sorted(bpy.context.selected_objects,key=lambda o:o.name)
    for obj in objects[n:]:bpy.data.objects.remove(obj,do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if not mesh.users:bpy.data.meshes.remove(mesh)
    objects=objects[:n]
    # Whole-object contract includes hidden faces and preserves prior mesh flags.
    for i,obj in enumerate(objects):
        for v in obj.data.vertices:v.select=v.index%3==0
        for f in obj.data.polygons:
            f.select=f.index%2==0
            f.hide=i%23==0 and f.index%5==0
        obj.select_set(True)
    if args.shared:
        source=objects[0].data
        for obj in objects[1:]:obj.data=source
        untouched=bpy.data.objects.new('UnselectedSharedMesh',source)
        bpy.context.collection.objects.link(untouched)
    marker=bpy.data.objects.new('NonMeshSelection',None);bpy.context.collection.objects.link(marker);marker.select_set(True)
    bpy.context.view_layer.objects.active=marker;bpy.context.view_layer.update()
    return objects,marker

def key(obj):
    co=np.empty(len(obj.data.vertices)*3,np.float32);obj.data.vertices.foreach_get('co',co)
    return hashlib.sha256(co.tobytes()+np.array(obj.matrix_world,dtype=np.float32)[:3,:3].tobytes()).hexdigest()

def flags(mesh):
    return [np.array([getattr(x,name) for x in items],dtype=bool)
            for name in ('select','hide') for items in (mesh.vertices,mesh.edges,mesh.polygons)]

def reference(obj):
    selected=list(bpy.context.selected_objects);active=bpy.context.view_layer.objects.active
    for x in selected:x.select_set(False)
    mesh=obj.data.copy();temp=bpy.data.objects.new('SoloReference',mesh);temp.matrix_world=obj.matrix_world.copy()
    bpy.context.collection.objects.link(temp);temp.select_set(True);bpy.context.view_layer.objects.active=temp
    for items in (mesh.vertices,mesh.edges,mesh.polygons):
        for x in items:x.hide=False
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.02)
    bpy.ops.object.mode_set(mode='OBJECT');result=read_uv(mesh).copy()
    bpy.data.objects.remove(temp,do_unlink=True);bpy.data.meshes.remove(mesh)
    for x in selected:x.select_set(True)
    bpy.context.view_layer.objects.active=active
    return result

report={'blender':bpy.app.version_string,'build':bpy.app.build_hash.decode(),'scene':base.name,'scene_sha256':hash_file(base),
        'sources':{name:{'version':list(m.bl_info['version']),'sha256':hash_file(path)} for (name,m),(_,path) in zip(modules,paths)},
        'method':f'every UV compared with solo Blender Smart UV; automatic undo and graph flush included; {args.trials} trials after warmup, version order rotated each trial',
        'angle_degrees':66,'island_margin':.02,'threads':2,'priority':'BelowNormal','shared_input':args.shared,'cases':[]}
for n in map(int,args.counts.split(',')):
    objects,marker=load(n);expected={}
    for obj in objects:
        k=key(obj)
        if k not in expected:expected[k]=reference(obj)
    case={'objects':n,'nonmesh_selected':1,'reference_geometries_and_transforms':len(expected),'results':{}}
    samples={name:[] for name,_ in modules};max_error={name:0. for name,_ in modules}
    for trial in range(-1,args.trials):
        offset=trial%len(modules)
        for name,module in modules[offset:]+modules[:offset]:
            objects,marker=load(n)
            before={o.name:flags(o.data) for o in objects};matrix={o.name:np.array(o.matrix_world) for o in objects}
            untouched=bpy.data.objects.get('UnselectedSharedMesh')
            untouched_uv=read_uv(untouched.data).copy() if untouched else None
            module.register();bpy.context.scene.UVangle_limit=66;bpy.context.scene.UVisland_margin=.02
            bpy.context.preferences.edit.use_global_undo=True;bpy.context.preferences.edit.undo_steps=2
            bpy.ops.ed.undo_push(message='Independent unwrap baseline')
            start=time.perf_counter();result=bpy.ops.object.smart_uv_project_with_settings('EXEC_DEFAULT',True)
            bpy.context.view_layer.update();elapsed=(time.perf_counter()-start)*1000
            assert result=={'FINISHED'}
            assert bpy.context.mode=='OBJECT' and bpy.context.active_object==marker
            assert set(bpy.context.selected_objects)==set(objects+[marker])
            for obj in objects:
                error=float(np.max(np.abs(read_uv(obj.data)-expected[key(obj)])));max_error[name]=max(max_error[name],error)
                assert error<3e-6,(name,obj.name,error)
                for a,b in zip(flags(obj.data),before[obj.name]):np.testing.assert_array_equal(a,b)
                np.testing.assert_array_equal(np.array(obj.matrix_world),matrix[obj.name])
            if untouched:
                np.testing.assert_array_equal(read_uv(untouched.data),untouched_uv)
                assert len({o.data.as_pointer() for o in objects})==len(objects)
                assert all(o.data!=untouched.data for o in objects)
            if trial>=0:samples[name].append(elapsed)
            module.unregister()
            print(json.dumps({'unwrap_objects':n,'tool':name,'trial':trial,'ms':elapsed,'max_uv_error':max_error[name]}),flush=True)
    for name in samples:
        case['results'][name]={'median_ms':statistics.median(samples[name]),'range_ms':[min(samples[name]),max(samples[name])],
                               'samples_ms':samples[name],'max_uv_error_vs_solo_blender':max_error[name],
                               'selection_hide_active_mode_transforms_preserved':True}
    # Separate instrumentation pass; excluded from reported timing samples.
    module=modules[-1][1];objects,marker=load(n);module.register()
    bpy.context.scene.UVangle_limit=66;bpy.context.scene.UVisland_margin=.02
    bpy.ops.ed.undo_push(message='Unwrap profiling baseline')
    operator=bpy.ops.object.smart_uv_project_with_settings
    original_mode=bpy.ops.object.mode_set;original_smart=bpy.ops.uv.smart_project;original_select=bpy.ops.mesh.select_all
    components={k:{'calls':0,'ms':0.} for k in ('mode_set','smart_project','mesh_select')}
    def measured(label,fn):
        def call(*a,**kw):
            start=time.perf_counter()
            try:return fn(*a,**kw)
            finally:components[label]['calls']+=1;components[label]['ms']+=(time.perf_counter()-start)*1000
        return call
    with patch.object(bpy.ops,'object',types.SimpleNamespace(mode_set=measured('mode_set',original_mode))),\
         patch.object(bpy.ops,'uv',types.SimpleNamespace(smart_project=measured('smart_project',original_smart))),\
         patch.object(bpy.ops,'mesh',types.SimpleNamespace(select_all=measured('mesh_select',original_select))):
        start=time.perf_counter();operator('EXEC_DEFAULT',True);bpy.context.view_layer.update();total=(time.perf_counter()-start)*1000
    case['profile_last_version']={'components':components,'total_ms':total}
    module.unregister();report['cases'].append(case)
    out=ROOT/f'artifacts/independent-unwrap-{bpy.app.version[0]}.{bpy.app.version[1]}-{args.label}{"-props" if args.props else ""}{"-shared" if args.shared else ""}.json'
    out.write_text(json.dumps(report,indent=2))
print('UNWRAP COMPLETE',out.name,flush=True)
