"""Render real progress UI in a fresh isolated Blender window, then quit.

Run without --background, with isolated BLENDER_USER_* paths under artifacts.
Test-only redraw forcing captures the intermediate bar even on fast hardware.
No user scenes, preferences, input automation or external services are used.
"""
import importlib.util
import hashlib
import json
import os
import traceback
from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parents[1]
VERSION=f'{bpy.app.version[0]}.{bpy.app.version[1]}'
OUT=ROOT/'artifacts'
assert not bpy.app.background
for key in ('BLENDER_USER_CONFIG','BLENDER_USER_SCRIPTS','BLENDER_USER_EXTENSIONS'):
    assert Path(os.environ[key]).resolve().is_relative_to(OUT.resolve())
spec=importlib.util.spec_from_file_location('texel_ui_test',ROOT/'TexelUniformityTool.py')
tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

def run():
    report={'blender':bpy.app.version_string,'passed':False,'screenshots':[],
            'source_sha256':hashlib.sha256((ROOT/'TexelUniformityTool.py').read_bytes()).hexdigest(),
            'test_only_forced_redraw':True,'real_user_preferences_touched':False}
    try:
        tool.register()
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        objects=[]
        for index in range(72):
            bpy.ops.mesh.primitive_plane_add(size=1,location=(index%12,index//12,0))
            objects.append(bpy.context.object)
        for obj in objects: obj.select_set(True)
        bpy.context.view_layer.objects.active=objects[0]
        original=tool._BatchProgress.update
        captured=set()
        def capture(self,done,name):
            self.last_draw=float('-inf')  # Test-only: deterministically render every step.
            original(self,done,name)
            if 0<done<self.total and self.action not in captured:
                path=OUT/f'issues-ui-{self.action.replace(" ","-").lower()}-{VERSION}.png'
                assert tool._BATCH_PROGRESS['done']==done
                bpy.ops.screen.screenshot(filepath=str(path),check_existing=False)
                report['screenshots'].append({'action':self.action,'completed':done,
                    'total':self.total,'file':path.name})
                captured.add(self.action)
        tool._BatchProgress.update=capture
        assert bpy.ops.object.smart_uv_project_with_settings()=={'FINISHED'}
        assert tool._BATCH_PROGRESS is None
        assert bpy.context.window_manager.texel_uniformity_progress==0
        bpy.context.scene.target_texel_density_px_cm=2
        assert bpy.ops.object.set_target_texel_density()=={'FINISHED'}
        assert tool._BATCH_PROGRESS is None
        assert bpy.context.window_manager.texel_uniformity_progress==0
        assert captured=={'Smart UV Project','Set Density'},captured
        for obj in objects:
            assert abs(tool.calculate_texel_density(obj,4096)-2)<1e-4
        tool._BatchProgress.update=original
        tool.unregister()
        assert not hasattr(bpy.types.WindowManager,'texel_uniformity_progress')
        report['passed']=True
    except Exception:
        report['error']=traceback.format_exc()
    (OUT/f'issues-ui-{VERSION}.json').write_text(json.dumps(report,indent=2))
    print('REAL_UI_PROGRESS_RESULT',json.dumps(report),flush=True)
    bpy.ops.wm.quit_blender()
    return None

bpy.app.timers.register(run,first_interval=1.0)
