"""Matched, output-verified current TDC comparison; undo/graph-inclusive timing."""
import argparse
from contextlib import nullcontext
import gc
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

import bpy
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from comparison_common import *
from comparator_setup import setup,parameters,view_context

parser=argparse.ArgumentParser()
parser.add_argument('--kind',choices=('python','native'),required=True)
parser.add_argument('--cases',default='all')
parser.add_argument('--trials',type=int,default=5)
parser.add_argument('--label',default='initial')
parser.add_argument('--memory-tool',choices=('ours','checker'))
parser.add_argument('--operations',default='set,calculate')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])

checker=setup(args.kind)
spec=importlib.util.spec_from_file_location('review_tool',ROOT/'TexelUniformityTool.py')
ours=importlib.util.module_from_spec(spec);spec.loader.exec_module(ours);ours.register()
manifest=json.loads((SCENES/'manifest.json').read_text())
cases=manifest['scenes'] if args.cases=='all' else [r for r in manifest['scenes'] if r['label'] in args.cases.split(',')]
report={'blender':bpy.app.version_string,'build':bpy.app.build_hash.decode(),
        'ours_version':list(ours.bl_info['version']),'ours_sha256':hash_file(ROOT/'TexelUniformityTool.py'),
        'comparator_version':'2026.1.1','comparator_kind':args.kind,
        'comparator_source_commit':'3737a8c9d87b29bffa670a79828f49c4cd656599',
        'native_backend':'locally compiled inspected MSVC /O2 source; not shipped binary' if args.kind=='native' else None,
        'machine':'AMD Ryzen 9 5900X, 12 cores/24 threads, 64 GiB RAM, Windows',
        'threads':2,'priority':'BelowNormal','automatic_undo':True,'undo_steps':2,
        'timed_scope':'registered operator with automatic undo plus view_layer.update; setup/reset/validation excluded',
        'settings':{'units':'px/cm','resolution':4096,'target':17.3,'set_method':'AVERAGE','anchor':'UV_CENTER','mode':'OBJECT',
                    'common_relative_density_tolerance':0.001},
        'samples_after_warmup':0 if args.memory_tool else args.trials,
        'cold_samples':1 if args.memory_tool else 0,
        'memory_tool':args.memory_tool,'operations':args.operations.split(','),'cases':[]}

def load_case(record):
    path=SCENES/(record['label']+'.blend')
    assert hash_file(path)==record['scene_sha256']
    bpy.ops.wm.open_mainfile(filepath=str(path),load_ui=False,use_scripts=False)
    parameters()
    bpy.context.scene.texture_resolution=4096
    bpy.context.scene.target_texel_density_px_cm=17.3
    bpy.context.preferences.edit.use_global_undo=True
    bpy.context.preferences.edit.undo_steps=2
    objects=sorted(bpy.context.selected_objects,key=lambda o:o.name)
    bpy.context.view_layer.objects.active=objects[0]
    bpy.context.view_layer.update()
    return objects

for record in cases:
    case={'input':record,'set':{},'calculate':{}}
    initial=load_case(record)
    expected={o.name:((read_uv(o.data).astype(np.float64)-.5)*(17.3/oracle_density(o))+.5).astype(np.float32) for o in initial}
    for operation in args.operations.split(','):
        assert operation in ('set','calculate')
        if operation=='calculate' and record['objects']!=1:continue
        names=[args.memory_tool] if args.memory_tool else ['ours','checker']
        samples={n:[] for n in names};errors={n:0. for n in names};density_errors={n:0. for n in names}
        state={n:True for n in names};mem={}
        trials=[0] if args.memory_tool else range(-1,args.trials)
        for trial in trials:
            order=names if trial%2==0 else list(reversed(names))
            for name in order:
                objects=load_case(record);active=objects[0].name
                before_matrices={o.name:np.array(o.matrix_world) for o in objects}
                before_uv={o.name:read_uv(o.data).copy() for o in objects} if operation=='calculate' else None
                gc.collect();bpy.ops.ed.undo_push(message='Matched comparison baseline')
                before=memory()
                # Our data-only operators need no editor override. In a fresh
                # headless window a synthetic area override can crash Blender's
                # redo HUD during automatic undo, after the Python code returns.
                scope = (bpy.context.temp_override(**view_context())
                         if name=='checker' and operation=='set' else nullcontext())
                with scope:
                    start=time.perf_counter()
                    if name=='ours':
                        result=(bpy.ops.object.set_target_texel_density('EXEC_DEFAULT',True) if operation=='set'
                                else bpy.ops.object.calculate_density('EXEC_DEFAULT',True))
                    else:
                        result=(bpy.ops.object.texel_density_set('EXEC_DEFAULT',True) if operation=='set'
                                else bpy.ops.object.texel_density_check('EXEC_DEFAULT',True))
                    bpy.context.view_layer.update()
                    elapsed=(time.perf_counter()-start)*1000
                after=memory()
                assert result=={'FINISHED'},result
                selected={o.name for o in bpy.context.selected_objects}
                state[name] &= selected==set(before_matrices) and bpy.context.active_object.name==active and bpy.context.mode=='OBJECT'
                for obj in objects:
                    np.testing.assert_array_equal(np.array(obj.matrix_world),before_matrices[obj.name])
                    if operation=='set':
                        error=float(np.max(np.abs(read_uv(obj.data)-expected[obj.name])))
                        errors[name]=max(errors[name],error)
                        rel=abs(oracle_density(obj)/17.3-1)
                        density_errors[name]=max(density_errors[name],float(rel))
                        # Current TDC rounds intermediate density to 3 decimals
                        # and accumulates float32 weighted means. Use an explicit
                        # common 0.1% contract and report every actual error.
                        assert rel<.001,(name,obj.name,rel)
                        np.testing.assert_allclose(read_uv(obj.data),expected[obj.name],rtol=0,atol=2e-4)
                    else:
                        np.testing.assert_array_equal(read_uv(obj.data),before_uv[obj.name])
                        actual=float(obj['texel_density']) if name=='ours' else float(bpy.context.scene.td.density)
                        rel=abs(actual/oracle_density(obj)-1)
                        density_errors[name]=max(density_errors[name],float(rel))
                        assert rel<.001,(name,obj.name,actual,rel)
                if trial>=0:samples[name].append(elapsed)
                mem[name]={'before_mib':before,'after_mib':after}
                print(json.dumps({'case':record['label'],'op':operation,'trial':trial,'tool':name,'ms':elapsed}),flush=True)
        for name in names:
            case[operation][name]={'median_ms':statistics.median(samples[name]),'range_ms':[min(samples[name]),max(samples[name])],
                                   'samples_ms':samples[name],'max_uv_coordinate_error':errors[name],
                                   'max_relative_density_error':density_errors[name],'object_selection_active_mode_preserved':state[name]}
            if args.memory_tool:case[operation][name]['memory']=mem[name]
        if not args.memory_tool:
            case[operation]['speedup_vs_checker']=case[operation]['checker']['median_ms']/case[operation]['ours']['median_ms']
    report['cases'].append(case)
    out=ROOT/f'artifacts/current-comparison-{args.kind}-{bpy.app.version[0]}.{bpy.app.version[1]}-{args.label}.json'
    out.write_text(json.dumps(report,indent=2))
print('COMPARISON COMPLETE',str(out.name),flush=True)
