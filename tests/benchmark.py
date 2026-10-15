"""Factory-startup synthetic benchmark; no user files or preferences are read/written.

Run with Blender --background --factory-startup --disable-autoexec -t 2
--python-exit-code 1 --python tests/benchmark.py -- --label baseline
"""
import argparse
import cProfile
import importlib.util
import io
import json
import platform
import pstats
import statistics
import sys
import time
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def clear():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if not mesh.users:
            bpy.data.meshes.remove(mesh)

def grid(n, count=1):
    """Identical planar quads, continuous UVs, identity transform, one material."""
    y, x = np.mgrid[0:n+1, 0:n+1]
    coords = np.column_stack((x.ravel()/n, y.ravel()/n, np.zeros((n+1)**2)))
    y, x = np.mgrid[0:n, 0:n]
    p = (y*(n+1)+x).ravel()
    faces = np.column_stack((p, p+1, p+n+2, p+n+1))
    mesh = bpy.data.meshes.new('Grid')
    mesh.from_pydata(coords.tolist(), [], faces.tolist())
    layer = mesh.uv_layers.new()
    loop_uv = np.asarray(coords[faces.ravel(), :2], dtype=np.float32).ravel()
    layer.uv.foreach_set('vector', loop_uv)
    objects = []
    for index in range(count):
        obj = bpy.data.objects.new('Grid', mesh if index == 0 else mesh.copy())
        bpy.context.collection.objects.link(obj)
        obj.select_set(True)
        objects.append(obj)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.context.view_layer.update()
    return objects, loop_uv

def timed(fn, reset, repeats=5):
    reset()
    fn()  # warm up Blender caches; excluded from timings
    samples = []
    for _ in range(repeats):
        reset()
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter()-start)
    return {'median_ms': statistics.median(samples)*1000,
            'samples_ms': [s*1000 for s in samples]}

def run(label):
    original = load(ROOT/'tests/upstream_v1_1.py', 'original')
    current = load(ROOT/'TexelUniformityTool.py', 'current')
    modules = [('original', original)] if label == 'baseline' else [('original', original), ('optimized', current)]
    results = {'blender': bpy.app.version_string, 'build': bpy.app.build_hash.decode(),
               'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform(),
               'threads': 2, 'repeats': 5, 'label': label, 'cases': []}
    for n, count in [(8, 1), (128, 1), (256, 1), (8, 128), (32, 32)]:
        clear()
        objects, uv = grid(n, count)
        def reset():
            for obj in objects:
                obj.data.uv_layers.active.uv.foreach_set('vector', uv)
                obj.data.update()
            bpy.context.view_layer.objects.active = objects[0]
            bpy.context.view_layer.update()
        case = {'grid_side': n, 'objects': count, 'quads_total': n*n*count, 'results': {}}
        for name, module in modules:
            # Reuse one registered add-on at a time, just as an installed version.
            module.register()
            bpy.context.scene.texture_resolution = 4096
            bpy.context.scene.target_texel_density_px_cm = 20.48
            calculate = lambda: [module.calculate_texel_density(o, 4096) for o in objects]
            scale = lambda: [module.scale_uv_to_target_density(o, 20.48, 4096) for o in objects]
            batch = lambda: bpy.ops.object.set_target_texel_density()
            case['results'][name] = {'calculate': timed(calculate, reset),
                                      'scale_helpers': timed(scale, reset),
                                      'set_operator': timed(batch, reset)}
            # The analytic answer is 40.96 px/cm before and 20.48 after scaling.
            densities = [module.calculate_texel_density(o, 4096) for o in objects]
            assert all(abs(d-20.48) < 1e-4 for d in densities), densities[:3]
            module.unregister()
        results['cases'].append(case)
        print(json.dumps(case), flush=True)
    clear()
    objects, uv = grid(128)
    profile = cProfile.Profile()
    profile.enable()
    for _ in range(3):
        original.calculate_texel_density(objects[0], 4096)
        original.scale_uv_to_target_density(objects[0], 20.48, 4096)
    profile.disable()
    stream = io.StringIO()
    pstats.Stats(profile, stream=stream).sort_stats('cumtime').print_stats(25)
    (ROOT/'artifacts/profile-original.txt').write_text(stream.getvalue())
    if label != 'baseline':
        profile = cProfile.Profile()
        profile.enable()
        for _ in range(3):
            current.calculate_texel_density(objects[0], 4096)
            current.scale_uv_to_target_density(objects[0], 20.48, 4096)
        profile.disable()
        stream = io.StringIO()
        pstats.Stats(profile, stream=stream).sort_stats('cumtime').print_stats(25)
        (ROOT/'artifacts/profile-optimized.txt').write_text(stream.getvalue())
    path = ROOT/f'artifacts/benchmark-{label}.json'
    path.write_text(json.dumps(results, indent=2))
    print('SAVED', path, flush=True)


def run_paired():
    """Alternate version order each trial to reduce drift on a shared machine."""
    original = load(ROOT/'tests/upstream_v1_1.py', 'original')
    optimized = load(ROOT/'TexelUniformityTool.py', 'optimized')
    versions = [('original', original), ('optimized', optimized)]
    result = {'blender': bpy.app.version_string, 'build': bpy.app.build_hash.decode(),
              'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform(),
              'threads': 2, 'repeats': 7, 'method': 'paired alternating order; warmup excluded; resets excluded',
              'cases': [], 'unwrap_cases': []}
    for n, count in [(8,1), (128,1), (256,1), (8,128), (32,32)]:
        clear()
        objects, uv = grid(n, count)
        case = {'grid_side': n, 'objects': count, 'quads_total': n*n*count,
                'results': {name: {op: [] for op in ('calculate','scale_helpers','set_operator')}
                            for name,_ in versions}}
        for trial in range(-1,7):
            order = versions if trial % 2 == 0 else list(reversed(versions))
            for name, module in order:
                module.register()
                bpy.context.scene.texture_resolution = 4096
                bpy.context.scene.target_texel_density_px_cm = 20.48
                functions = {
                    'calculate': lambda: [module.calculate_texel_density(o,4096) for o in objects],
                    'scale_helpers': lambda: [module.scale_uv_to_target_density(o,20.48,4096) for o in objects],
                    'set_operator': lambda: bpy.ops.object.set_target_texel_density(),
                }
                for op, fn in functions.items():
                    for obj in objects:
                        obj.data.uv_layers.active.uv.foreach_set('vector', uv)
                        obj.data.update()
                    bpy.context.view_layer.objects.active = objects[0]
                    bpy.context.view_layer.update()
                    start = time.perf_counter()
                    fn()
                    elapsed = (time.perf_counter()-start)*1000
                    if trial >= 0:
                        case['results'][name][op].append(elapsed)
                densities = [module.calculate_texel_density(o,4096) for o in objects]
                assert all(abs(d-20.48)<1e-4 for d in densities)
                module.unregister()
        for version in case['results'].values():
            for op, samples in list(version.items()):
                version[op] = {'median_ms': statistics.median(samples), 'samples_ms': samples}
        result['cases'].append(case)
        print(json.dumps(case), flush=True)
    # Unwrap still calls Blender's own per-object Smart Project; measure the
    # restoration cost honestly. Re-select original objects before every version.
    for n, count in [(1,1), (8,32), (32,8)]:
        clear()
        objects, uv = grid(n,count)
        case = {'grid_side':n,'objects':count,'quads_total':n*n*count,
                'results': {name: [] for name,_ in versions}}
        for trial in range(-1,5):
            for name,module in (versions if trial%2==0 else list(reversed(versions))):
                for obj in objects:
                    obj.select_set(True)
                    obj.data.uv_layers.active.uv.foreach_set('vector', uv)
                    obj.data.update()
                bpy.context.view_layer.objects.active = objects[0]
                bpy.context.view_layer.update()
                start = time.perf_counter()
                module.smart_uv_project_unwrap_with_settings(1.15, .01)
                elapsed = (time.perf_counter()-start)*1000
                if trial>=0:
                    case['results'][name].append(elapsed)
        for name,samples in list(case['results'].items()):
            case['results'][name] = {'median_ms':statistics.median(samples),'samples_ms':samples}
        result['unwrap_cases'].append(case)
        print(json.dumps(case),flush=True)
    path = ROOT/f'artifacts/benchmark-paired-{bpy.app.version[0]}.{bpy.app.version[1]}.json'
    path.write_text(json.dumps(result,indent=2))
    print('SAVED',path,flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='comparison')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if args.label == 'paired':
        run_paired()
    else:
        run(args.label)
