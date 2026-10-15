"""Check each density definition on independently Smart-UV-unwrapped mixed props."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comparison_common import ROOT, SCENES, hash_file, oracle_density, read_uv, set_uv
from comparator_setup import setup, parameters, view_context

parser = argparse.ArgumentParser()
parser.add_argument('--kind', choices=('python','native'), required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
checker = setup(args.kind)
spec = importlib.util.spec_from_file_location('reviewed', ROOT/'TexelUniformityTool.py')
ours = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ours)
ours.register()


def weighted_face_oracle(obj):
    """TDC AVERAGE on these triangulated inputs, using float64 world edges."""
    densities, weights = [], []
    mesh = obj.data
    uv = read_uv(mesh).astype(np.float64)
    matrix = np.asarray(obj.matrix_world, dtype=np.float64)[:3,:3]
    for face in mesh.polygons:
        assert len(face.vertices) == 3
        co = [np.array(mesh.vertices[i].co, dtype=np.float64) for i in face.vertices]
        world = np.linalg.norm(np.cross(matrix@(co[1]-co[0]), matrix@(co[2]-co[0])))*.5
        points = uv[list(face.loop_indices)]
        a, b = points[1]-points[0], points[2]-points[0]
        area = abs(a[0]*b[1]-a[1]*b[0])*.5
        assert world > 0 and area > 0
        densities.append(4096*math.sqrt(area/world)/100)
        weights.append(area)
    return float(np.dot(densities,weights)/sum(weights))


scene = SCENES/'props64.blend'
bpy.ops.wm.open_mainfile(filepath=str(scene),load_ui=False,use_scripts=False)
objects = sorted(bpy.context.selected_objects,key=lambda o:o.name)
for obj in objects[24:]:bpy.data.objects.remove(obj,do_unlink=True)
objects = objects[:24]
for obj in objects:obj.select_set(False)
for obj in objects:
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(False)
before_uv = {obj.name:read_uv(obj.data).copy() for obj in objects}
before_matrix = {obj.name:np.array(obj.matrix_world) for obj in objects}
report = {'blender':bpy.app.version_string,'build':bpy.app.build_hash.decode(),
          'source_sha256':hash_file(ROOT/'TexelUniformityTool.py'),
          'comparator_version':'2026.1.1','comparator_kind':args.kind,
          'geometry_scene_sha256':hash_file(scene),'objects':len(objects),
          'method':'Native solo Smart UV Project per object, 66 degrees / margin .02; original nonuniform world transforms retained. Each tool is validated against its own independently computed density definition. No timing comparison.',
          'target':17.3,'relative_tolerance':.001,'results':{}}
for name in ('ours','checker'):
    parameters()
    bpy.context.scene.texture_resolution = 4096
    bpy.context.scene.target_texel_density_px_cm = 17.3
    for obj in objects:
        obj.select_set(False)
        set_uv(obj.data,before_uv[obj.name])
    oracle = oracle_density if name=='ours' else weighted_face_oracle
    calculate_error = 0.
    for obj in objects:
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        if name=='ours':
            actual = ours.calculate_texel_density(obj,4096)
        else:
            assert bpy.ops.object.texel_density_check() == {'FINISHED'}
            actual = float(bpy.context.scene.td.density)
        calculate_error = max(calculate_error,abs(actual/oracle(obj)-1))
        np.testing.assert_array_equal(read_uv(obj.data),before_uv[obj.name])
        obj.select_set(False)
    for obj in objects:obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.context.preferences.edit.use_global_undo = True
    bpy.ops.ed.undo_push(message='Smart UV accuracy baseline')
    if name=='ours':
        result = bpy.ops.object.set_target_texel_density('EXEC_DEFAULT',True)
    else:
        with bpy.context.temp_override(**view_context()):
            result = bpy.ops.object.texel_density_set('EXEC_DEFAULT',True)
    assert result == {'FINISHED'}
    bpy.context.view_layer.update()
    errors = [abs(oracle(obj)/17.3-1) for obj in objects]
    assert max(errors) < .001 and calculate_error < .001
    assert bpy.context.mode == 'OBJECT' and bpy.context.active_object == objects[0]
    assert set(bpy.context.selected_objects) == set(objects)
    for obj in objects:np.testing.assert_array_equal(np.array(obj.matrix_world),before_matrix[obj.name])
    report['results'][name] = {
        'definition':'sqrt(total UV area / total world area)' if name=='ours' else 'UV-area-weighted mean of face densities',
        'max_relative_calculate_error':calculate_error,
        'max_relative_target_error':max(errors),
        'output_area_average_range':[min(oracle_density(o) for o in objects),max(oracle_density(o) for o in objects)],
        'output_weighted_face_average_range':[min(weighted_face_oracle(o) for o in objects),max(weighted_face_oracle(o) for o in objects)],
        'state_preserved':True}
report['passed'] = True
out = ROOT/f'artifacts/astra-current-accuracy-{args.kind}-{bpy.app.version[0]}.{bpy.app.version[1]}.json'
out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
