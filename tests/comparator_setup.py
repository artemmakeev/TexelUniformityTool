"""Install only inspected comparators into an explicit disposable Blender profile."""
import importlib
import json
import os
from pathlib import Path
import sys
import zipfile

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT.parent / 'comparators'
SANDBOX = (ROOT / 'artifacts/comparator-sandbox').resolve()

def setup(kind):
    for name in ('BLENDER_USER_CONFIG', 'BLENDER_USER_SCRIPTS', 'BLENDER_USER_EXTENSIONS'):
        path = Path(os.environ[name]).resolve()
        assert path.is_relative_to(SANDBOX), 'Refuse normal Blender profile'
        path.mkdir(parents=True, exist_ok=True)
    assert Path(bpy.utils.user_resource('CONFIG')).resolve() == Path(os.environ['BLENDER_USER_CONFIG']).resolve()
    if kind == 'python':
        assert bpy.app.version >= (4, 2, 0)
        folder = Path(os.environ['BLENDER_USER_EXTENSIONS']).resolve() / 'tdc_review'
        folder.mkdir(exist_ok=True)
        assert bpy.ops.preferences.extension_repo_add(name='TDC review', type='LOCAL',
            use_custom_directory=True, custom_directory=str(folder),
            use_sync_on_startup=False) == {'FINISHED'}
        repo = next(r for r in bpy.context.preferences.extensions.repos
                    if Path(r.directory).resolve() == folder)
        assert bpy.ops.extensions.package_install_files(
            filepath=str(COMP/'texel-density-checker-2026.1.1-official-extension.zip'),
            repo=repo.module, enable_on_install=True) == {'FINISHED'}
        name = f'bl_ext.{repo.module}.texel_density_checker'
        module = importlib.import_module(name)
    else:
        # This archive contains the unmodified official Python files plus our
        # MSVC /O2 build of inspected current tdcore.cpp; no shipped DLL is run.
        archive = COMP / 'texel-density-checker-2026.1.1-source-built.zip'
        assert bpy.ops.preferences.addon_install(filepath=str(archive), overwrite=True) == {'FINISHED'}
        module = addon_utils.enable('texel_density', default_set=True, persistent=False)
        assert module is not None
        name = 'texel_density'
    assert Path(module.__file__).resolve().is_relative_to(SANDBOX)
    # Headless scripts don't advance UI timers. Run the add-on's normal deferred
    # initialization once, outside measurements, then prevent late resets.
    if bpy.app.timers.is_registered(module.deferred_initialize):
        bpy.app.timers.unregister(module.deferred_initialize)
    module.deferred_initialize()
    prefs = bpy.context.preferences.addons[name].preferences
    prefs.automatic_recalc = False
    if hasattr(prefs, 'calculation_backend'):
        prefs.calculation_backend = 'CPP'
        test = module.cpp_interface.TDCoreWrapper()
        assert test.lib is not None, 'Native backend must not silently fall back'
        del test
    # Only dedicated temporary config writes are possible.
    assert Path(module.config_json.get_prefs_path()).resolve().is_relative_to(SANDBOX)
    return module

def parameters():
    td = bpy.context.scene.td
    # ID assignment avoids auto-recalculation while configuring the input.
    td['units'] = 0
    td.texture_size = '4096'
    td.units = '0'  # px/cm
    td.selected_faces = False
    td.density_set = '17.3'
    td.set_method = 'AVERAGE'
    td.rescale_anchor = 'UV_CENTER'
    return td

def view_context():
    window = bpy.context.window
    area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), window.screen.areas[0])
    area.type = 'VIEW_3D'
    region = next(r for r in area.regions if r.type == 'WINDOW')
    result={'window':window, 'area':area}
    if os.environ.get('TDC_BENCH_REGION','1')=='1':result['region']=region
    return result

if __name__ == '__main__':
    kind = sys.argv[sys.argv.index('--')+1]
    module = setup(kind)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_plane_add(size=1)
    obj = bpy.context.object
    obj.data.uv_layers.active.data[0].uv = (0,0)
    parameters()
    bpy.context.preferences.edit.use_global_undo = True
    bpy.ops.ed.undo_push(message='Comparator smoke baseline')
    with bpy.context.temp_override(**view_context()):
        result = bpy.ops.object.texel_density_set('EXEC_DEFAULT', True)
    assert result == {'FINISHED'}
    # Area and target independently measurable even if a tool uses different
    # aggregate density definitions on stretched meshes.
    obj.data.calc_loop_triangles()
    uv = obj.data.uv_layers.active.data
    area = 0.
    for t in obj.data.loop_triangles:
        a,b,c = [uv[i].uv for i in t.loops]
        area += abs((b.x-a.x)*(c.y-a.y)-(c.x-a.x)*(b.y-a.y))*.5
    actual = 40.96*area**.5
    assert abs(actual-17.3)/17.3 < 1e-4, actual
    if hasattr(module,'bl_info'):
        version=list(module.bl_info['version'])
    else:
        import tomllib
        version=tomllib.loads((Path(module.__file__).parent/'blender_manifest.toml').read_text())['version']
    print(json.dumps({'kind':kind,'version':version,
                      'blender':bpy.app.version_string,'density':actual,'passed':True}),flush=True)
