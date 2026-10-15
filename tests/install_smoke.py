"""Install the actual release ZIP into an explicitly isolated user scripts path."""
import json
import os
from pathlib import Path
import sys

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = (ROOT/'artifacts').resolve()
scripts = Path(os.environ['BLENDER_USER_SCRIPTS']).resolve()
config = Path(os.environ['BLENDER_USER_CONFIG']).resolve()
assert scripts.is_relative_to(SANDBOX) and config.is_relative_to(SANDBOX), 'Refuse to touch real user preferences'
scripts.mkdir(parents=True, exist_ok=True)
config.mkdir(parents=True, exist_ok=True)
assert Path(bpy.utils.user_resource('SCRIPTS')).resolve() == scripts
assert Path(bpy.utils.user_resource('CONFIG')).resolve() == config
release = json.loads((ROOT/'dist/manifest.json').read_text())
result = bpy.ops.preferences.addon_install(filepath=str(ROOT/'dist'/release['addon']['file']), overwrite=True)
assert result == {'FINISHED'}, result
module = addon_utils.enable('TexelUniformityTool', default_set=False, persistent=False)
assert module is not None
assert Path(module.__file__).resolve().is_relative_to(SANDBOX)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_plane_add(size=1)
obj = bpy.context.object
obj.scale=(2,3,1)
bpy.context.view_layer.update()
bpy.context.scene.texture_resolution=1024
bpy.context.scene.target_texel_density_px_cm=15
assert bpy.ops.object.calculate_density() == {'FINISHED'}
assert abs(obj['texel_density']-1024/(100*6**.5))<1e-5
assert bpy.ops.object.set_target_texel_density() == {'FINISHED'}
assert abs(module.calculate_texel_density(obj,1024)-15)<1e-4
assert bpy.ops.object.smart_uv_project_with_settings() == {'FINISHED'}
addon_utils.disable('TexelUniformityTool',default_set=False)
assert not hasattr(bpy.types.Scene,'texture_resolution')
summary = {'blender':bpy.app.version_string,'passed':True,'version':list(module.bl_info['version']),
           'zip_sha256':release['addon']['sha256'],'installed_module':str(module.__file__),
           'operations':['install ZIP','enable','calculate','set','unwrap','disable'],
           'preferences_saved':False}
(ROOT/f'artifacts/install-{bpy.app.version[0]}.{bpy.app.version[1]}.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
