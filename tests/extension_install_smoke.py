"""Install and enable the actual Extensions ZIP using only isolated directories."""
import importlib
import json
import os
from pathlib import Path

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = (ROOT / 'artifacts').resolve()
for name in ('BLENDER_USER_CONFIG', 'BLENDER_USER_SCRIPTS', 'BLENDER_USER_EXTENSIONS'):
    destination = Path(os.environ[name]).resolve()
    assert destination.is_relative_to(SANDBOX), 'Refuse real user settings'
    destination.mkdir(parents=True, exist_ok=True)
assert Path(bpy.utils.user_resource('EXTENSIONS')).resolve() == Path(os.environ['BLENDER_USER_EXTENSIONS']).resolve()
directory = Path(os.environ['BLENDER_USER_EXTENSIONS']).resolve() / 'texel_review'
directory.mkdir(exist_ok=True)
assert bpy.ops.preferences.extension_repo_add(name='Texel review', type='LOCAL',
    use_custom_directory=True, custom_directory=str(directory),
    use_sync_on_startup=False) == {'FINISHED'}
repo = next(repo for repo in bpy.context.preferences.extensions.repos
            if Path(repo.directory).resolve() == directory)
assert not repo.remote_url
release = json.loads((ROOT/'dist/manifest.json').read_text())
result = bpy.ops.extensions.package_install_files(
    filepath=str(ROOT / 'dist'/release['extension_candidate']['file']),
    repo=repo.module, enable_on_install=True)
assert result == {'FINISHED'}, result
name = f'bl_ext.{repo.module}.texel_uniformity_tool'
assert name in bpy.context.preferences.addons
module = importlib.import_module(name)
assert Path(module.__file__).resolve().is_relative_to(directory)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_plane_add(size=1)
obj = bpy.context.object
obj.scale = (2, 3, 1)
bpy.context.view_layer.update()
bpy.context.scene.texture_resolution = 1024
bpy.context.scene.target_texel_density_px_cm = 15
assert bpy.ops.object.calculate_density() == {'FINISHED'}
assert abs(obj['texel_density'] - 1024 / (100 * 6**.5)) < 1e-5
assert bpy.ops.object.set_target_texel_density() == {'FINISHED'}
assert abs(module.calculate_texel_density(obj, 1024) - 15) < 1e-4
assert bpy.ops.object.smart_uv_project_with_settings() == {'FINISHED'}
addon_utils.disable(name, default_set=False)
assert not hasattr(bpy.types.Scene, 'texture_resolution')
report = {'blender': bpy.app.version_string, 'passed': True,
          'version':release['version'],'zip_sha256':release['extension_candidate']['sha256'],
          'operations': ['local extension repository', 'install ZIP', 'enable',
                         'calculate', 'set', 'unwrap', 'disable'],
          'preferences_saved': False, 'network_used': False,
          'license': 'GPL-3.0-or-later'}
(ROOT / f'artifacts/extension-install-{bpy.app.version[0]}.{bpy.app.version[1]}.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
