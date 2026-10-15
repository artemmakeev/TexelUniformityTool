"""Fresh-process million-quad benchmark with Windows process memory evidence."""
import argparse
import ctypes
from ctypes import wintypes
import gc
import hashlib
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from benchmark import ROOT,clear,load
import bpy
import numpy as np

class MemoryCounters(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
psapi=ctypes.WinDLL('psapi',use_last_error=True)
kernel.GetCurrentProcess.restype=wintypes.HANDLE
psapi.GetProcessMemoryInfo.argtypes=(wintypes.HANDLE,ctypes.POINTER(MemoryCounters),wintypes.DWORD)
def memory():
    counters=MemoryCounters()
    counters.cb=ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {name:getattr(counters,name)/(1024*1024) for name in
            ('WorkingSetSize','PeakWorkingSetSize','PrivateUsage','PeakPagefileUsage')}

parser=argparse.ArgumentParser()
parser.add_argument('--kind',choices=['original','reviewed'],required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
path=ROOT/('tests/upstream_v1_1.py' if args.kind=='original' else 'TexelUniformityTool.py')
module=load(path,args.kind)
module.register()
clear()
n=1024
y,x=np.mgrid[0:n+1,0:n+1]
coords=np.column_stack((x.ravel()/n,y.ravel()/n,np.zeros((n+1)**2))).astype(np.float32)
y,x=np.mgrid[0:n,0:n]
p=(y*(n+1)+x).ravel()
corners=np.column_stack((p,p+1,p+n+2,p+n+1)).astype(np.int32).ravel()
mesh=bpy.data.meshes.new('MillionQuads')
mesh.vertices.add(len(coords))
mesh.vertices.foreach_set('co',coords.ravel())
mesh.loops.add(len(corners))
mesh.loops.foreach_set('vertex_index',corners)
mesh.polygons.add(n*n)
mesh.polygons.foreach_set('loop_start',np.arange(n*n,dtype=np.int32)*4)
mesh.polygons.foreach_set('loop_total',np.full(n*n,4,dtype=np.int32))
mesh.update(calc_edges=True)
uv=coords[corners,:2].copy()
mesh.uv_layers.new().uv.foreach_set('vector',uv.ravel())
obj=bpy.data.objects.new('MillionQuads',mesh)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active=obj
bpy.context.scene.texture_resolution=4096
bpy.context.scene.target_texel_density_px_cm=20.48
bpy.context.preferences.edit.use_global_undo=True
bpy.context.preferences.edit.undo_steps=2
bpy.context.view_layer.update()
del x,y,p,coords,corners
gc.collect()
bpy.ops.ed.undo_push(message='Million quad baseline')
before=memory()
print('MEASUREMENT START',args.kind,flush=True)
start=time.perf_counter()
result=bpy.ops.object.set_target_texel_density('EXEC_DEFAULT',True)
bpy.context.view_layer.update()
seconds=time.perf_counter()-start
after=memory()  # Before verification allocations.
assert result=={'FINISHED'}
actual=np.empty(uv.size,np.float32)
mesh.uv_layers.active.uv.foreach_get('vector',actual)
expected=(uv*.5+.25).ravel()
error=float(np.max(np.abs(actual-expected)))
assert error<2e-6,error
report={'blender':bpy.app.version_string,'build':bpy.app.build_hash.decode(),'kind':args.kind,
        'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'quads':n*n,'triangles':2*n*n,'vertices':(n+1)**2,'loops':4*n*n,
        'seconds':seconds,'before_mib':before,'after_mib':after,'max_uv_error':error,
        'method':'fresh process; cold Set operator with automatic undo and dependency-graph flush; all output UVs checked; lifetime process peaks include startup and mesh generation'}
out=ROOT/f'artifacts/astra-large-{args.kind}-{bpy.app.version[0]}.{bpy.app.version[1]}.json'
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
module.unregister()
