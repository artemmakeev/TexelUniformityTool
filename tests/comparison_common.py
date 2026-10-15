"""Deterministic synthetic input and independent validation for comparisons."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
from pathlib import Path

import bmesh
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCENES = ROOT / 'artifacts/comparator-scenes'

def clear():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if not mesh.users:
            bpy.data.meshes.remove(mesh)

def read_uv(mesh):
    a = np.empty(len(mesh.loops)*2, np.float32)
    mesh.uv_layers.active.uv.foreach_get('vector', a)
    return a.reshape(-1,2)

def set_uv(mesh, a):
    # Generic attribute accessor detaches implicit sharing on 4.x as well.
    mesh.attributes[mesh.uv_layers.active.name].data.foreach_set('vector', a.ravel())
    mesh.update()

def scalar_density(obj, resolution=4096):
    mesh = obj.data
    mesh.calc_loop_triangles()
    uv = mesh.uv_layers.active.data
    matrix = np.array(obj.matrix_world, dtype=np.float64)[:3,:3]
    area, uv_area = 0., 0.
    for tri in mesh.loop_triangles:
        co = [np.array(mesh.vertices[i].co, dtype=np.float64) for i in tri.vertices]
        a,b = matrix@(co[1]-co[0]), matrix@(co[2]-co[0])
        ar = np.linalg.norm(np.cross(a,b))*.5
        if ar <= 0: continue
        points = [uv[i].uv for i in tri.loops]
        a,b = points[1]-points[0],points[2]-points[0]
        uv_area += abs(a.x*b.y-a.y*b.x)*.5
        area += ar
    return resolution*math.sqrt(uv_area/area)/(100*bpy.context.scene.unit_settings.scale_length) if area else 0.

def oracle_density(obj, resolution=4096):
    """Independent bulk oracle: transformed vertex edges, no production area normals."""
    mesh=obj.data;mesh.calc_loop_triangles();n=len(mesh.loop_triangles)
    vertices=np.empty(len(mesh.vertices)*3,np.float32);mesh.vertices.foreach_get('co',vertices)
    indices=np.empty(n*3,np.int32);mesh.loop_triangles.foreach_get('vertices',indices)
    points=vertices.reshape(-1,3).astype(np.float64)[indices.reshape(-1,3)]
    matrix=np.array(obj.matrix_world,dtype=np.float64)[:3,:3]
    a=(points[:,1]-points[:,0])@matrix.T;b=(points[:,2]-points[:,0])@matrix.T
    areas=np.linalg.norm(np.cross(a,b),axis=1)*.5;valid=areas>0
    mesh.loop_triangles.foreach_get('loops',indices)
    points=read_uv(mesh).astype(np.float64)[indices.reshape(-1,3)]
    a=points[:,1]-points[:,0];b=points[:,2]-points[:,0]
    uv_area=(np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])*.5)[valid].sum()
    return resolution*np.sqrt(uv_area/areas.sum())/(100*bpy.context.scene.unit_settings.scale_length)

def uniform_triangle_uv(obj, index=0, count=1):
    """Each face has the same world UV-area ratio, so both TD definitions agree."""
    mesh=obj.data
    if not mesh.uv_layers: mesh.uv_layers.new()
    uv=np.empty((len(mesh.loops),2),np.float64)
    matrix=np.array(obj.matrix_world,dtype=np.float64)[:3,:3]
    for face in mesh.polygons:
        assert face.loop_total==3
        co=[np.array(mesh.vertices[i].co,dtype=np.float64) for i in face.vertices]
        a,b=matrix@(co[1]-co[0]),matrix@(co[2]-co[0])
        length=np.linalg.norm(a); x=np.dot(a,b)/length
        points=np.array(((0.,0.),(length,0.),(x,math.sqrt(max(0,np.dot(b,b)-x*x)))))
        uv[list(face.loop_indices)]=points
    scale=np.array((.65+.7*index/count,1.35-.3*index/count))
    uv=uv*scale+(index%4,index%3)
    set_uv(mesh,uv.astype(np.float32))

def prop_mesh(kind, variant=0):
    bm=bmesh.new()
    if kind=='crate':
        bmesh.ops.create_cube(bm,size=1)
        bmesh.ops.bevel(bm,geom=list(bm.edges),offset=.06,segments=2,affect='EDGES')
    elif kind=='pipe':
        bmesh.ops.create_cone(bm,cap_ends=True,cap_tris=True,segments=24,
                             radius1=.35,radius2=.35,depth=1.4)
    elif kind=='bracket':
        profile=[(0,0),(1.5,0),(1.5,.2),(.2,.2),(.2,1.2),(0,1.2)]
        verts=[bm.verts.new((x,y,z)) for z in (0,.3) for x,y in profile]
        bm.faces.new(tuple(reversed(verts[:6])));bm.faces.new(verts[6:])
        for i in range(6):bm.faces.new((verts[i],verts[(i+1)%6],verts[(i+1)%6+6],verts[i+6]))
    else: bmesh.ops.create_cube(bm,size=1)
    for v in bm.verts:
        v.co.x*=.8+.07*variant;v.co.y*=1+.04*(variant%3)
    bmesh.ops.triangulate(bm,faces=list(bm.faces))
    mesh=bpy.data.meshes.new(kind);bm.to_mesh(mesh);bm.free();mesh.update()
    return mesh

class MemoryCounters(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(x,ctypes.c_size_t) for x in
        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]

def memory():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);api=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    api.GetProcessMemoryInfo.argtypes=(wintypes.HANDLE,ctypes.POINTER(MemoryCounters),wintypes.DWORD)
    c=MemoryCounters();c.cb=ctypes.sizeof(c)
    if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(c),c.cb):raise ctypes.WinError(ctypes.get_last_error())
    return {k:getattr(c,k)/(1024**2) for k in ('WorkingSetSize','PeakWorkingSetSize','PrivateUsage','PeakPagefileUsage')}

def hash_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
