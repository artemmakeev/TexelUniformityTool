"""Record density-definition and linked-user differences, outside speed rankings."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import bpy
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from comparison_common import *
from comparator_setup import setup,parameters,view_context

parser=argparse.ArgumentParser();parser.add_argument('--kind',choices=('python','native'),required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);checker=setup(args.kind)
spec=importlib.util.spec_from_file_location('own_semantics',ROOT/'TexelUniformityTool.py')
ours=importlib.util.module_from_spec(spec);spec.loader.exec_module(ours);ours.register()
report={'blender':bpy.app.version_string,'comparator':'2026.1.1','kind':args.kind,'cases':{}}
for tool in ('ours','checker'):
    clear();parameters();bpy.context.scene.texture_resolution=4096;bpy.context.scene.target_texel_density_px_cm=17.3
    mesh=bpy.data.meshes.new('TwoTriangles');mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0),(2,0,0),(3,0,0),(2,1,0)],[],[(0,1,2),(3,4,5)])
    mesh.uv_layers.new();set_uv(mesh,np.array([(0,0),(1,0),(0,1),(2,0),(4,0),(2,2)],np.float32))
    obj=bpy.data.objects.new('Stretched',mesh);bpy.context.collection.objects.link(obj);obj.select_set(True)
    bpy.context.view_layer.objects.active=obj;bpy.context.view_layer.update()
    start=oracle_density(obj)
    with bpy.context.temp_override(**view_context()):
        if tool=='checker':
            bpy.ops.object.texel_density_check();reported=float(bpy.context.scene.td.density)
            bpy.ops.object.texel_density_set()
        else:
            reported=ours.calculate_texel_density(obj,4096);bpy.ops.object.set_target_texel_density()
    report['cases'][tool+'_stretched']={'input_area_average':start,'reported_input_density':reported,
                                      'output_area_average':float(oracle_density(obj)),'target':17.3}
    clear();parameters();bpy.context.scene.texture_resolution=4096;bpy.context.scene.target_texel_density_px_cm=17.3
    bpy.ops.mesh.primitive_plane_add(size=1);a=bpy.context.object;a.name='SelectedA';mesh=a.data
    b=bpy.data.objects.new('SelectedB',mesh);c=bpy.data.objects.new('Unselected',mesh)
    for x in (b,c):bpy.context.collection.objects.link(x)
    b.scale=(2,2,2);a.select_set(True);b.select_set(True);c.select_set(False)
    bpy.context.view_layer.objects.active=a;bpy.context.view_layer.update();before=read_uv(c.data).copy()
    with bpy.context.temp_override(**view_context()):
        (bpy.ops.object.set_target_texel_density() if tool=='ours' else bpy.ops.object.texel_density_set())
    report['cases'][tool+'_linked']={'selected_density':[float(oracle_density(x)) for x in (a,b)],
                                   'unselected_density':float(oracle_density(c)),
                                   'unselected_uv_unchanged':bool(np.array_equal(read_uv(c.data),before)),
                                   'selected_meshes_independent':a.data!=b.data}
    if tool=='ours':
        assert report['cases'][tool+'_linked']['unselected_uv_unchanged']
        assert all(abs(oracle_density(x)/17.3-1)<1e-4 for x in (a,b))
out=ROOT/f'artifacts/current-semantics-{args.kind}-{bpy.app.version[0]}.{bpy.app.version[1]}.json'
out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
