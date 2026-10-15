"""Independent output-verified benchmark, with automatic undo and graph flush."""
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark import ROOT, clear, grid, load
import bpy
import numpy as np

versions = [('original',load(ROOT/'tests/upstream_v1_1.py','original')),
            ('reviewed',load(ROOT/'TexelUniformityTool.py','reviewed'))]
tool = versions[1][1]
bpy.context.preferences.edit.use_global_undo = True
bpy.context.preferences.edit.undo_steps = 2
report = {'blender':bpy.app.version_string,'build':bpy.app.build_hash.decode(),
          'source_sha256':hashlib.sha256((ROOT/'TexelUniformityTool.py').read_bytes()).hexdigest(),
          'method':'5 alternating paired trials; explicit automatic undo requested; view_layer.update included; every output UV checked analytically',
          'cases':[]}
for side,count in [(8,128),(256,1),(32,32)]:
    clear()
    objects,base_uv=grid(side,count)
    # Different UV density, aspect and tile for every object. All original
    # workloads have identity world transforms and nonmirrored UVs by design.
    inputs,expected=[],[]
    for i,obj in enumerate(objects):
        scale=np.array((.6+i/count,1.4-i/(2*count)))
        coords=(base_uv.reshape(-1,2)*scale+(i%4,i%3)).astype(np.float32)
        inputs.append(coords)
        factor=17.3/(40.96*np.sqrt(np.prod(scale)))
        expected.append(((coords.astype(np.float64)-.5)*factor+.5).astype(np.float32))
    case={'objects':count,'quads':side*side*count,'results':{name:[] for name,_ in versions},'max_uv_errors':{}}
    for trial in range(-1,5):
        for name,module in (versions if trial%2==0 else list(reversed(versions))):
            module.register()
            bpy.context.scene.texture_resolution=4096
            bpy.context.scene.target_texel_density_px_cm=17.3
            for obj,coords in zip(objects,inputs):
                tool._set_uv(obj.data,coords)
                obj.data.update()
                obj.select_set(True)
            bpy.context.view_layer.objects.active=objects[0]
            bpy.context.view_layer.update()
            bpy.ops.ed.undo_push(message='Independent benchmark input')
            start=time.perf_counter()
            result=bpy.ops.object.set_target_texel_density('EXEC_DEFAULT',True)
            bpy.context.view_layer.update()
            elapsed=(time.perf_counter()-start)*1000
            assert result=={'FINISHED'}
            if trial>=0:
                case['results'][name].append(elapsed)
            max_error=0.
            for obj,wanted in zip(objects,expected):
                actual=tool._read_uv(obj.data.uv_layers.active,len(obj.data.loops))
                max_error=max(max_error,float(np.max(np.abs(actual-wanted))))
                np.testing.assert_allclose(actual,wanted,rtol=0,atol=2e-5)
            case['max_uv_errors'][name]=max(case['max_uv_errors'].get(name,0),max_error)
            if name=='reviewed':
                assert bpy.context.active_object==objects[0]
                assert set(bpy.context.selected_objects)==set(objects)
            module.unregister()
    for name,samples in list(case['results'].items()):
        case['results'][name]={'median_ms':statistics.median(samples),'samples_ms':samples}
    case['speedup']=case['results']['original']['median_ms']/case['results']['reviewed']['median_ms']
    report['cases'].append(case)
    print(json.dumps(case),flush=True)
out=ROOT/f'artifacts/astra-benchmark-{bpy.app.version[0]}.{bpy.app.version[1]}.json'
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
