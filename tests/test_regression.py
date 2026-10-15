"""Synthetic Blender regression suite. Run in factory-startup background Blender."""
import json
import hashlib
import math
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark import ROOT, clear, load

tool_source = ROOT / (sys.argv[sys.argv.index('--source')+1] if '--source' in sys.argv else 'TexelUniformityTool.py')
assert tool_source.resolve().is_relative_to(ROOT)
tool = load(tool_source, 'tool')
original = load(ROOT/'tests/upstream_v1_1.py', 'original')

def make(name='Mesh', vertices=None, faces=None, uvs=True):
    vertices = vertices if vertices is not None else [(0,0,0),(1,0,0),(1,1,0),(0,1,0)]
    faces = faces if faces is not None else [(0,1,2,3)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    if uvs:
        layer = mesh.uv_layers.new()
        for loop in mesh.loops:
            layer.data[loop.index].uv = vertices[loop.vertex_index][:2]
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj

def update():
    bpy.context.view_layer.update()

def uv_buffer(obj):
    return tool._read_uv(obj.data.uv_layers.active, len(obj.data.loops)).copy()

def oracle(obj, resolution=1024, units=1):
    """Independent scalar oracle: explicitly transform triangle vertex positions."""
    mesh = obj.data
    if not mesh.uv_layers.active:
        return 0
    mesh.calc_loop_triangles()
    area_3d = area_uv = 0.0
    for tri in mesh.loop_triangles:
        # Double-precision Python math avoids relying on the optimized normals.
        coords = [tuple(mesh.vertices[i].co) for i in tri.vertices]
        linear = [tuple(row[:3]) for row in obj.matrix_world][:3]
        def transformed_edge(a, b):
            edge = [a[i]-b[i] for i in range(3)]
            return [sum(row[i]*edge[i] for i in range(3)) for row in linear]
        a, b = transformed_edge(coords[1], coords[0]), transformed_edge(coords[2], coords[0])
        cross = [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
        area = math.sqrt(sum(v*v for v in cross))/2
        if area <= 0:
            continue
        area_3d += area
        uv = [tuple(mesh.uv_layers.active.data[i].uv) for i in tri.loops]
        ax, ay = uv[1][0]-uv[0][0], uv[1][1]-uv[0][1]
        bx, by = uv[2][0]-uv[0][0], uv[2][1]-uv[0][1]
        area_uv += abs(ax*by-ay*bx)/2
    return resolution * math.sqrt(area_uv/area_3d)/(100*units) if area_3d else 0


class Regression(unittest.TestCase):
    def setUp(self):
        clear()
        bpy.context.scene.unit_settings.scale_length = 1
        bpy.context.scene.texture_resolution = 1024

    def assertDensity(self, obj, expected=None, units=1):
        update()
        actual = tool.calculate_texel_density(obj, 1024, units)
        expected = oracle(obj, units=units) if expected is None else expected
        self.assertAlmostEqual(actual, expected, delta=max(1e-6, abs(expected)*2e-6))
        return actual

    def test_identity_and_uniform_scale(self):
        obj = make()
        self.assertDensity(obj, 10.24)
        obj.scale = (3,3,3)
        self.assertDensity(obj, 10.24/3)

    def test_nonuniform_negative_and_singular_scale(self):
        obj = make()
        for scale, expected in [((2,3,1),10.24/math.sqrt(6)),
                                ((-2,3,4),10.24/math.sqrt(6)),
                                ((2,3,0),10.24/math.sqrt(6)), ((0,3,4),0)]:
            obj.scale = scale
            self.assertDensity(obj, expected)

    def test_parent_shear_rotation_and_translation(self):
        obj = make(vertices=[(0,0,0),(1,0,1),(1,1,1),(0,1,0)])
        parent = bpy.data.objects.new('Parent', None)
        bpy.context.collection.objects.link(parent)
        parent.scale = (2,3,1)
        obj.parent = parent
        obj.rotation_euler = (.3,.5,.7)
        obj.location = (500, -200, 100)
        obj.scale = (1,.5,2)
        self.assertDensity(obj)

    def test_units(self):
        obj = make()
        bpy.context.scene.unit_settings.scale_length = .01
        self.assertAlmostEqual(tool.calculate_texel_density(obj, 1024), 1024, places=3)
        tool.scale_uv_to_target_density(obj, 256, 1024)
        self.assertDensity(obj, 256, units=.01)

    def test_mirrored_islands_do_not_cancel(self):
        obj = make(vertices=[(0,0,0),(1,0,0),(1,1,0),(0,1,0),
                             (2,0,0),(3,0,0),(3,1,0),(2,1,0)],
                   faces=[(0,1,2,3),(4,5,6,7)])
        layer = obj.data.uv_layers.active
        for i in range(4,8):
            layer.data[i].uv.x = -layer.data[i].uv.x
        self.assertDensity(obj, 10.24)
        self.assertEqual(original.calculate_texel_density(obj, 1024), 0)
        tool.scale_uv_to_target_density(obj, 5.12, 1024)
        self.assertDensity(obj, 5.12)

    def test_issue3_applied_boolean_uv_area_does_not_cancel(self):
        bpy.ops.mesh.primitive_cube_add(size=2)
        obj = bpy.context.object
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=.6, depth=3,
                                           location=(.4,.2,0))
        cutter = bpy.context.object
        bpy.context.view_layer.objects.active = obj
        modifier = obj.modifiers.new('Issue3Boolean', 'BOOLEAN')
        modifier.operation = 'DIFFERENCE'
        modifier.solver = 'EXACT'
        modifier.object = cutter
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.data.objects.remove(cutter, do_unlink=True)
        self.assertGreater(len(obj.data.polygons), 6)
        expected = oracle(obj)
        current = tool.calculate_texel_density(obj, 1024)
        self.assertAlmostEqual(current, expected, places=5)
        old = original.calculate_texel_density(obj, 1024)
        self.assertGreater(abs(old-expected), .1*expected)
        before = uv_buffer(obj)
        tool.scale_uv_to_target_density(obj, 3.7, 1024)
        self.assertDensity(obj, 3.7)
        self.assertTrue(np.isfinite(uv_buffer(obj)).all())
        self.assertFalse(np.array_equal(before, uv_buffer(obj)))

    def test_scale_to_bounds_toggle_reaches_native_projection(self):
        obj = make(vertices=[(0,0,0),(3,0,0),(3,1,0),(0,1,0)])
        other = make('OtherBounds',vertices=[(0,0,0),(2,0,0),(2,1,0),(0,1,0)])
        self.assertTrue(bpy.context.scene.UVscale_to_bounds)
        flags = []
        for enabled in (True, False):
            bpy.context.scene.UVscale_to_bounds = enabled
            with patch.object(tool, 'smart_uv_project_unwrap_with_settings',
                              wraps=tool.smart_uv_project_unwrap_with_settings) as call:
                self.assertEqual(bpy.ops.object.smart_uv_project_with_settings(), {'FINISHED'})
                flags.append(call.call_args.kwargs['scale_to_bounds'])
            actual = uv_buffer(obj)
            tool.smart_uv_project_unwrap_with_settings(math.radians(66), 0,
                                                       scale_to_bounds=enabled)
            np.testing.assert_allclose(uv_buffer(obj), actual, rtol=0, atol=2e-6)
            if enabled:
                np.testing.assert_allclose(actual.min(axis=0), [0,0], atol=2e-6)
                np.testing.assert_allclose(actual.max(axis=0), [1,1], atol=2e-6)
                np.testing.assert_allclose(uv_buffer(other).min(axis=0), [0,0], atol=2e-6)
                np.testing.assert_allclose(uv_buffer(other).max(axis=0), [1,1], atol=2e-6)
            else:
                self.assertLess(np.min(np.ptp(actual, axis=0)), .9)
        self.assertEqual(flags, [True, False])
        bpy.context.scene.UVscale_to_bounds = True

    def test_unwrap_progress_counts_successes_and_skips(self):
        valid = make('ProgressValid')
        empty = make('ProgressEmpty', vertices=[], faces=[])
        calls = []
        self.assertEqual(tool.smart_uv_project_unwrap_with_settings(1.15, 0,
            progress=lambda done, name: calls.append((done, name)))[0], 1)
        self.assertEqual(calls[-1][0], 2)
        self.assertEqual(sorted(n for n,_ in calls), [n for n,_ in calls])
        self.assertEqual(set(bpy.context.selected_objects), {valid,empty})

    def test_set_progress_counts_successes_and_skips(self):
        valid = make('ProgressValid')
        make('ProgressEmpty', vertices=[], faces=[])
        calls = []
        class Progress:
            def __init__(self, context, action, total):
                self.enabled = True
                self.total = total
            def __enter__(self): return self
            def __exit__(self, *args): calls.append(('end',self.total))
            def update(self, done, name): calls.append((done,name))
        with patch.object(tool, '_BatchProgress', Progress):
            self.assertEqual(bpy.ops.object.set_target_texel_density(), {'FINISHED'})
        self.assertEqual([entry[0] for entry in calls], [1,2,'end'])
        self.assertEqual(calls[-1][1], 2)
        self.assertDensity(valid, bpy.context.scene.target_texel_density_px_cm)

    def test_progress_ui_cleanup_on_unexpected_failure(self):
        events = []
        manager = types.SimpleNamespace(
            progress_begin=lambda *a:events.append(('begin',a)),
            progress_update=lambda n:events.append(('update',n)),
            progress_end=lambda:events.append(('end',)),
            texel_uniformity_progress=0)
        context = types.SimpleNamespace(window=object(), window_manager=manager,
            workspace=types.SimpleNamespace(status_text_set=lambda text:events.append(('status',text))),
            screen=types.SimpleNamespace(areas=[types.SimpleNamespace(tag_redraw=lambda:None)]))
        fake_bpy = types.SimpleNamespace(app=types.SimpleNamespace(background=False),
            ops=types.SimpleNamespace(wm=types.SimpleNamespace(redraw_timer=lambda **kw:None)))
        with patch.object(tool,'bpy',fake_bpy):
            with self.assertRaisesRegex(RuntimeError,'injected'):
                with tool._BatchProgress(context,'Test operation',3) as progress:
                    progress.update(1,'Mesh')
                    self.assertIsNotNone(tool._BATCH_PROGRESS)
                    raise RuntimeError('injected')
        self.assertIsNone(tool._BATCH_PROGRESS)
        self.assertEqual(manager.texel_uniformity_progress,0)
        self.assertEqual(events[0],('begin',(0,3)))
        self.assertEqual(events[-2:],[('status',None),('end',)])

    def test_concave_ngon_and_nonplanar_surface(self):
        obj = make(vertices=[(0,0,0),(2,0,0),(2,2,0),(1,1,0),(0,2,0)], faces=[(0,1,2,3,4)])
        self.assertDensity(obj, 10.24)
        obj.data.vertices[2].co.z = 1
        obj.data.update()
        obj.scale = (1,2,.5)
        self.assertDensity(obj)

    def test_triangles_random_affine_and_uvs(self):
        rng = np.random.default_rng(73)
        coords = rng.uniform(-2, 2, (300,3))
        obj = make(vertices=coords.tolist(), faces=np.arange(300).reshape(-1,3).tolist())
        values = rng.uniform(-4, 4, (300,2)).astype(np.float32)
        obj.data.uv_layers.active.uv.foreach_set('vector', values.ravel())
        # Explicit shear is lost by object matrix decomposition; parent supplies it.
        parent = bpy.data.objects.new('Parent', None)
        bpy.context.collection.objects.link(parent)
        obj.parent = parent
        for _ in range(12):
            parent.scale = rng.uniform(.1, 4, 3)
            obj.rotation_euler = rng.uniform(-3,3,3)
            obj.scale = rng.uniform(-3,3,3)
            self.assertDensity(obj)

    def test_missing_empty_and_collapsed_uv_do_not_mutate(self):
        for obj in [make('Missing', uvs=False), make('Empty', vertices=[], faces=[]), make('Collapsed')]:
            if obj.name.startswith('Collapsed'):
                obj.data.uv_layers.active.uv.foreach_set('vector', np.zeros(8, np.float32))
            count = len(obj.data.uv_layers)
            self.assertDensity(obj, 0)
            with self.assertRaises(ValueError):
                tool.scale_uv_to_target_density(obj, 10, 1024)
            self.assertEqual(len(obj.data.uv_layers), count)

    def test_degenerate_triangles_excluded(self):
        obj = make(vertices=[(0,0,0),(1,0,0),(0,1,0), (0,0,0),(0,0,0),(0,0,0)],
                   faces=[(0,1,2),(3,4,5)])
        for item, co in zip(obj.data.uv_layers.active.data[3:], [(0,0),(10,0),(0,10)]):
            item.uv = co
        self.assertDensity(obj, 10.24)

    def test_read_only_calculation_preserves_state(self):
        a, b = make('A'), make('B')
        b.select_set(False)
        bpy.context.view_layer.objects.active = a
        uv = uv_buffer(a)
        self.assertDensity(b, 10.24)
        self.assertIs(bpy.context.active_object, a)
        self.assertEqual(list(bpy.context.selected_objects), [a])
        np.testing.assert_array_equal(uv_buffer(a), uv)
        self.assertEqual(a.mode, 'OBJECT')

    def test_set_preserves_state_materials_and_other_uv_layers(self):
        a, b = make('A'), make('B')
        material = bpy.data.materials.new('SharedMaterial')
        a.data.materials.append(material)
        b.data.materials.append(material)
        layer = a.data.uv_layers.new(name='Other', do_init=True)
        a.data.uv_layers.active_index = 0
        other_uv = tool._read_uv(layer, len(a.data.loops)).copy()
        before = uv_buffer(a)
        bpy.context.view_layer.objects.active = a
        self.assertEqual(bpy.ops.object.set_target_texel_density(), {'FINISHED'})
        for obj in (a,b):
            self.assertDensity(obj, bpy.context.scene.target_texel_density_px_cm)
            self.assertIn('texel_density', obj)
            self.assertIs(obj.data.materials[0], material)
        self.assertIs(bpy.context.active_object, a)
        self.assertEqual(set(bpy.context.selected_objects), {a,b})
        np.testing.assert_array_equal(tool._read_uv(a.data.uv_layers['Other'], 4), other_uv)
        factor = bpy.context.scene.target_texel_density_px_cm/10.24
        np.testing.assert_allclose(uv_buffer(a), (before-.5)*factor+.5, atol=1e-6)

    def test_shared_meshes_with_different_scales_preserve_unselected(self):
        a = make('A')
        b = bpy.data.objects.new('B', a.data)
        c = bpy.data.objects.new('Unselected', a.data)
        for obj in (b,c):
            bpy.context.collection.objects.link(obj)
        b.select_set(True)
        b.scale = (2,3,1)
        before = uv_buffer(c)
        update()
        self.assertEqual(bpy.ops.object.set_target_texel_density(), {'FINISHED'})
        self.assertDensity(a, bpy.context.scene.target_texel_density_px_cm)
        self.assertDensity(b, bpy.context.scene.target_texel_density_px_cm)
        np.testing.assert_array_equal(uv_buffer(c), before)
        self.assertIsNot(a.data, c.data)
        self.assertIsNot(a.data, b.data)

    def test_edit_mode_rejected_without_leaving_it(self):
        obj = make()
        bpy.ops.object.mode_set(mode='EDIT')
        for operator in (bpy.ops.object.calculate_density, bpy.ops.object.set_target_texel_density,
                         bpy.ops.object.smart_uv_project_with_settings):
            self.assertFalse(operator.poll())
        with self.assertRaises(ValueError):
            tool.calculate_texel_density(obj, 1024)
        self.assertEqual(obj.mode, 'EDIT')

    def test_empty_and_nonmesh_selection_operator_poll(self):
        self.assertFalse(bpy.ops.object.set_target_texel_density.poll())
        obj = bpy.data.objects.new('EmptyObject', None)
        bpy.context.collection.objects.link(obj)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        self.assertFalse(bpy.ops.object.smart_uv_project_with_settings.poll())
        self.assertFalse(bpy.ops.object.set_target_texel_density.poll())
        self.assertFalse(bpy.ops.object.calculate_density.poll())

    def test_invalid_inputs(self):
        obj = make()
        before = uv_buffer(obj)
        for value in [0, -1, float('inf'), float('nan')]:
            with self.assertRaises(ValueError):
                tool.scale_uv_to_target_density(obj, value, 1024)
            with self.assertRaises(ValueError):
                tool.calculate_texel_density(obj, value)
            with self.assertRaises(ValueError):
                tool.calculate_texel_density(obj, 1024, value)
        np.testing.assert_array_equal(uv_buffer(obj), before)

    def test_unrepresentable_target_rejected_without_collapsing_uvs(self):
        obj = make(vertices=[(0,0,0),(1e-6,0,0),(1e-6,1e-6,0),(0,1e-6,0)])
        obj.data.uv_layers.active.uv.foreach_set('vector', np.array([0,0,1,0,1,1,0,1],np.float32))
        before=uv_buffer(obj)
        with self.assertRaisesRegex(ValueError, 'float32'):
            tool.scale_uv_to_target_density(obj,.01,4096)
        np.testing.assert_array_equal(uv_buffer(obj),before)

    def test_precision_guard_checks_separate_islands(self):
        obj=make(vertices=[(0,0,0),(1e-6,0,0),(1e-6,1e-6,0),(0,1e-6,0),
                           (2e-6,0,0),(3e-6,0,0),(3e-6,1e-6,0),(2e-6,1e-6,0)],
                 faces=[(0,1,2,3),(4,5,6,7)])
        # Two tiny resulting islands land at different representable points.
        # A bounding-box-only collapse check would miss this failure.
        uv=np.array([(0,0),(1,0),(1,1),(0,1),(1e8,0),(1e8+16,0),(1e8+16,16),(1e8,16)],np.float32)
        obj.data.uv_layers.active.uv.foreach_set('vector',uv.ravel())
        before=uv_buffer(obj)
        with self.assertRaisesRegex(ValueError,'float32'):
            tool.scale_uv_to_target_density(obj,.01,4096)
        np.testing.assert_array_equal(uv_buffer(obj),before)

    def test_operator_automatic_undo_redo(self):
        obj=make('AutomaticUndo')
        other=bpy.data.objects.new('LinkedUser',obj.data)
        bpy.context.collection.objects.link(other)
        before=uv_buffer(obj)
        bpy.context.preferences.edit.use_global_undo=True
        bpy.ops.ed.undo_push(message='Baseline automatic undo')
        self.assertEqual(bpy.ops.object.set_target_texel_density('EXEC_DEFAULT',True),{'FINISHED'})
        # No manual checkpoint after the operator: exercise its actual UNDO flag.
        self.assertEqual(bpy.ops.ed.undo(),{'FINISHED'})
        obj=bpy.data.objects['AutomaticUndo']
        np.testing.assert_array_equal(uv_buffer(obj),before)
        self.assertIs(obj.data,bpy.data.objects['LinkedUser'].data)
        self.assertEqual(bpy.ops.ed.redo(),{'FINISHED'})
        obj=bpy.data.objects['AutomaticUndo']
        self.assertDensity(obj,bpy.context.scene.target_texel_density_px_cm)
        self.assertIsNot(obj.data,bpy.data.objects['LinkedUser'].data)

    def test_unwrap_operator_automatic_undo_redo(self):
        obj=make('UnwrapUndo')
        obj.data.uv_layers.active.uv.foreach_set('vector',np.array([0,0,3,0,3,2,0,2],np.float32))
        before=uv_buffer(obj)
        bpy.context.preferences.edit.use_global_undo=True
        bpy.ops.ed.undo_push(message='Baseline unwrap undo')
        self.assertEqual(bpy.ops.object.smart_uv_project_with_settings('EXEC_DEFAULT',True),{'FINISHED'})
        after=uv_buffer(obj)
        self.assertFalse(np.array_equal(before,after))
        self.assertEqual(bpy.ops.ed.undo(),{'FINISHED'})
        obj=bpy.data.objects['UnwrapUndo']
        np.testing.assert_array_equal(uv_buffer(obj),before)
        self.assertEqual(bpy.context.mode,'OBJECT')
        self.assertEqual(bpy.ops.ed.redo(),{'FINISHED'})
        np.testing.assert_array_equal(uv_buffer(bpy.data.objects['UnwrapUndo']),after)

    def test_batch_skips_invalid_and_updates_all_displays(self):
        a, b, missing = make('A'), make('B'), make('Missing', uvs=False)
        self.assertEqual(bpy.ops.object.set_target_texel_density(), {'FINISHED'})
        for obj in (a,b):
            self.assertIn('texel_density', obj)
        self.assertEqual(len(missing.data.uv_layers), 0)

    def test_unwrap_restores_selection_hidden_flags_and_active(self):
        a, b = make('A'), make('B', uvs=False)
        obj = bpy.data.objects.new('Empty', None)
        bpy.context.collection.objects.link(obj)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        a.data.polygons[0].hide = True
        a.data.polygons[0].select = False
        a.data.vertices[1].select = False
        selection = tool._selection_flags(a.data, 'select')
        hidden = tool._selection_flags(a.data, 'hide')
        count, failures = tool.smart_uv_project_unwrap_with_settings(math.radians(66), .02)
        self.assertEqual((count,failures), (2,[]))
        self.assertEqual(set(bpy.context.selected_objects), {a,b,obj})
        self.assertIs(bpy.context.active_object, obj)
        self.assertEqual(bpy.context.mode, 'OBJECT')
        for before, after in zip(selection, tool._selection_flags(a.data, 'select')):
            np.testing.assert_array_equal(before, after)
        for before, after in zip(hidden, tool._selection_flags(a.data, 'hide')):
            np.testing.assert_array_equal(before, after)
        self.assertGreater(self.assertDensity(a), 0)
        self.assertGreater(self.assertDensity(b), 0)

    def test_unwrap_with_no_active_object(self):
        a = make()
        bpy.context.view_layer.objects.active = None
        count, failures = tool.smart_uv_project_unwrap_with_settings(1.15, 0)
        self.assertEqual((count, failures), (1, []))
        self.assertIsNone(bpy.context.active_object)
        self.assertEqual(list(bpy.context.selected_objects), [a])

    def test_unwrap_batch_matches_solo_with_pins_materials_and_layers(self):
        baseline = load(ROOT/'tests/fixtures/texel_uniformity_v1_2_0.py', 'unwrap_reference')
        objects = [make('BatchA'),make('BatchB',vertices=[(0,0,0),(3,0,0),(3,2,0),(0,2,0)])]
        before = {}
        uv_selection = {}
        for i,obj in enumerate(objects):
            obj.scale=(1+i,.7+i,1)
            obj.data.uv_layers.new(name='OtherUV')
            obj.data.uv_layers.active_index=i
            layer=obj.data.uv_layers.active
            layer.data.foreach_set('pin_uv',np.array([True,False,True,False],np.bool_))
            if hasattr(layer.data[0],'select'):
                layer.data.foreach_set('select',np.array([False,True,True,False],np.bool_))
            else:
                for name,domain,values in (
                        ('.uv_select_vert','CORNER',[False,True,True,False]),
                        ('.uv_select_edge','CORNER',[True,False,False,True]),
                        ('.uv_select_face','FACE',[True])):
                    attr=obj.data.attributes.get(name) or obj.data.attributes.new(name,'BOOLEAN',domain)
                    attr.data.foreach_set('value',np.array(values,np.bool_))
                    uv_selection[(obj.name,name)]=np.array(values,np.bool_)
            before[obj.name]=uv_buffer(obj).copy()
            mat=bpy.data.materials.new('AspectMaterial');mat.use_nodes=True
            node=mat.node_tree.nodes.new('ShaderNodeTexImage')
            node.image=bpy.data.images.new('AspectImage',width=32*(i+1),height=32)
            mat.node_tree.nodes.active=node;obj.data.materials.append(mat)
        bpy.context.view_layer.update()
        self.assertEqual(baseline.smart_uv_project_unwrap_with_settings(1.15,.02),(2,[]))
        expected={o.name:uv_buffer(o).copy() for o in objects}
        for obj in objects:tool._set_uv(obj.data,before[obj.name].reshape(-1,2))
        for (obj_name,name),values in uv_selection.items():
            bpy.data.objects[obj_name].data.attributes[name].data.foreach_set('value',values)
        self.assertEqual(tool.smart_uv_project_unwrap_with_settings(1.15,.02),(2,[]))
        for obj in objects:np.testing.assert_allclose(uv_buffer(obj),expected[obj.name],rtol=0,atol=2e-6)
        for (obj_name,name),values in uv_selection.items():
            actual=np.empty(len(values),np.bool_)
            bpy.data.objects[obj_name].data.attributes[name].data.foreach_get('value',actual)
            np.testing.assert_array_equal(actual,values)

    def test_unwrap_batch_matches_solo_with_selection_sync_and_modes(self):
        from comparison_common import prop_mesh
        baseline = load(ROOT/'tests/fixtures/texel_uniformity_v1_2_0.py', 'sync_reference')
        settings = bpy.context.scene.tool_settings
        previous = settings.use_uv_select_sync, tuple(settings.mesh_select_mode)
        try:
            for sync in (False, True):
                for mode in ((True,False,False),(False,True,False),(False,False,True)):
                    with self.subTest(sync=sync, mode=mode):
                        clear()
                        settings.use_uv_select_sync = sync
                        settings.mesh_select_mode = mode
                        objects = []
                        for i,kind in enumerate(('crate','pipe','bracket')):
                            mesh = prop_mesh(kind, i)
                            mesh.uv_layers.new(name='Untouched')
                            mesh.uv_layers.new(name='Active')
                            mesh.uv_layers.active_index = 1
                            obj = bpy.data.objects.new(kind,mesh)
                            bpy.context.collection.objects.link(obj)
                            obj.select_set(True)
                            objects.append(obj)
                        bpy.context.view_layer.objects.active = objects[-1]
                        before = {o.name:uv_buffer(o) for o in objects}
                        untouched = {o.name:tool._read_uv(o.data.uv_layers[0],len(o.data.loops)).copy() for o in objects}
                        self.assertEqual(baseline.smart_uv_project_unwrap_with_settings(1.15,.02),(3,[]))
                        expected = {o.name:uv_buffer(o) for o in objects}
                        for obj in objects:tool._set_uv(obj.data,before[obj.name])
                        self.assertEqual(tool.smart_uv_project_unwrap_with_settings(1.15,.02),(3,[]))
                        for obj in objects:
                            np.testing.assert_array_equal(uv_buffer(obj),expected[obj.name])
                            np.testing.assert_array_equal(tool._read_uv(obj.data.uv_layers[0],len(obj.data.loops)),untouched[obj.name])
                        self.assertEqual((settings.use_uv_select_sync,tuple(settings.mesh_select_mode)),(sync,mode))
                        self.assertEqual(set(bpy.context.selected_objects),set(objects))
                        self.assertIs(bpy.context.active_object,objects[-1])
        finally:
            settings.use_uv_select_sync, settings.mesh_select_mode = previous

    def test_unwrap_batch_failure_preserves_successful_neighbors(self):
        import bmesh
        baseline = load(ROOT/'tests/fixtures/texel_uniformity_v1_2_0.py', 'failure_reference')
        objects = [make('First'),make('Fail'),make('Last')]
        before = {o.name:uv_buffer(o) for o in objects}
        self.assertEqual(baseline.smart_uv_project_unwrap_with_settings(1.15,.02),(3,[]))
        expected = {o.name:uv_buffer(o) for o in objects}
        for obj in objects:tool._set_uv(obj.data,before[obj.name])
        original_smart = bpy.ops.uv.smart_project
        def fail_middle(**kwargs):
            obj = bpy.context.active_object
            if obj.name == 'Fail':
                bm = bmesh.from_edit_mesh(obj.data)
                layer = bm.loops.layers.uv.active
                bm.faces.ensure_lookup_table()
                bm.faces[0].loops[0][layer].uv = (99,99)
                raise RuntimeError('Injected middle-of-batch failure')
            return original_smart(**kwargs)
        with patch.object(bpy.ops,'uv',types.SimpleNamespace(smart_project=fail_middle)):
            count,failures = tool.smart_uv_project_unwrap_with_settings(1.15,.02)
        self.assertEqual(count,2)
        self.assertEqual([name for name,_ in failures],['Fail'])
        for obj in objects:
            np.testing.assert_array_equal(uv_buffer(obj),before[obj.name] if obj.name=='Fail' else expected[obj.name])
        self.assertEqual(set(bpy.context.selected_objects),set(objects))
        self.assertIs(bpy.context.active_object,objects[-1])
        self.assertEqual(bpy.context.mode,'OBJECT')

    def test_unwrap_shared_failure_does_not_change_failed_users_uv(self):
        import bmesh
        a=make('FailedShared');b=bpy.data.objects.new('SuccessfulShared',a.data)
        bpy.context.collection.objects.link(b);b.select_set(True)
        before=uv_buffer(a);native=bpy.ops.uv.smart_project
        def maybe_fail(**kw):
            if bpy.context.active_object.name==a.name:
                bm=bmesh.from_edit_mesh(a.data);layer=bm.loops.layers.uv.active
                bm.faces.ensure_lookup_table();bm.faces[0].loops[0][layer].uv=(99,99)
                raise RuntimeError('Injected shared-user failure')
            return native(**kw)
        with patch.object(bpy.ops,'uv',types.SimpleNamespace(smart_project=maybe_fail)):
            count,failures=tool.smart_uv_project_unwrap_with_settings(1.15,.02)
        self.assertEqual(count,1);self.assertEqual(len(failures),1)
        np.testing.assert_array_equal(uv_buffer(a),before)
        self.assertIsNot(a.data,b.data)

    def test_unwrap_across_batch_boundary_matches_independent_results(self):
        baseline=load(ROOT/'tests/fixtures/texel_uniformity_v1_2_0.py','boundary_reference')
        objects=[make('Many'+str(i)) for i in range(65)]
        before={o.name:uv_buffer(o).copy() for o in objects}
        self.assertEqual(baseline.smart_uv_project_unwrap_with_settings(1.15,.02),(65,[]))
        expected={o.name:uv_buffer(o).copy() for o in objects}
        for obj in objects:tool._set_uv(obj.data,before[obj.name].reshape(-1,2))
        self.assertEqual(tool.smart_uv_project_unwrap_with_settings(1.15,.02),(65,[]))
        for obj in objects:np.testing.assert_allclose(uv_buffer(obj),expected[obj.name],rtol=0,atol=2e-6)

    def test_unwrap_multiple_batches_automatic_undo_restores_linked_users(self):
        objects=[make('UndoBatch'+str(i)) for i in range(65)]
        linked=bpy.data.objects.new('UndoBatchLinked',objects[0].data)
        bpy.context.collection.objects.link(linked);linked.select_set(True);objects.append(linked)
        before={o.name:uv_buffer(o).copy() for o in objects}
        first_name=objects[0].name
        bpy.context.preferences.edit.use_global_undo=True
        bpy.ops.ed.undo_push(message='Multiple unwrap batches baseline')
        self.assertEqual(bpy.ops.object.smart_uv_project_with_settings('EXEC_DEFAULT',True),{'FINISHED'})
        after={o.name:uv_buffer(o).copy() for o in objects}
        self.assertIsNot(bpy.data.objects[first_name].data,bpy.data.objects['UndoBatchLinked'].data)
        self.assertEqual(bpy.ops.ed.undo(),{'FINISHED'})
        self.assertIs(bpy.data.objects[first_name].data,bpy.data.objects['UndoBatchLinked'].data)
        for name,values in before.items():np.testing.assert_array_equal(uv_buffer(bpy.data.objects[name]),values)
        self.assertEqual(bpy.ops.ed.redo(),{'FINISHED'})
        for name,values in after.items():np.testing.assert_array_equal(uv_buffer(bpy.data.objects[name]),values)

    def test_unwrap_preserves_uv_pins_and_selection(self):
        obj = make()
        layer = obj.data.uv_layers.active
        properties = [name for name in ('pin_uv', 'select', 'select_edge') if hasattr(layer.data[0], name)]
        before = {}
        for name in properties:
            values = np.array([True,False,True,False], dtype=np.bool_)
            layer.data.foreach_set(name, values)
            before[name] = values
        count, failures = tool.smart_uv_project_unwrap_with_settings(1.15, .03)
        self.assertEqual((count, failures), (1, []))
        for name, values in before.items():
            after = np.empty(4, dtype=np.bool_)
            obj.data.uv_layers.active.data.foreach_get(name, after)
            np.testing.assert_array_equal(after, values)

    def test_unwrap_shared_mesh_protects_unselected(self):
        a = make()
        b = bpy.data.objects.new('Unselected', a.data)
        bpy.context.collection.objects.link(b)
        before = uv_buffer(b)
        count, failures = tool.smart_uv_project_unwrap_with_settings(1.15, .03)
        self.assertEqual((count,failures), (1,[]))
        self.assertIsNot(a.data, b.data)
        np.testing.assert_array_equal(uv_buffer(b), before)

    def test_unwrap_failure_recovers_uv_mesh_mode_selection(self):
        a = make()
        b = bpy.data.objects.new('Unselected', a.data)
        bpy.context.collection.objects.link(b)
        original_mesh, before = a.data, uv_buffer(a)
        # Inject failure after entering Edit Mode, including a partially written UV.
        import bmesh
        def fail(**kwargs):
            mesh = bmesh.from_edit_mesh(a.data)
            layer = mesh.loops.layers.uv.active
            mesh.faces.ensure_lookup_table()
            mesh.faces[0].loops[0][layer].uv = (99,99)
            raise RuntimeError('injected unwrap failure')
        with patch.object(bpy.ops, 'uv', types.SimpleNamespace(smart_project=fail)):
            count, failures = tool.smart_uv_project_unwrap_with_settings(1.15, 0)
        self.assertEqual(count, 0)
        self.assertEqual(len(failures), 1)
        self.assertIs(a.data, original_mesh)
        self.assertEqual(bpy.context.mode, 'OBJECT')
        self.assertEqual(list(bpy.context.selected_objects), [a])
        self.assertIs(bpy.context.active_object, a)
        np.testing.assert_array_equal(uv_buffer(a), before)

    def test_modifiers_excluded_and_not_applied(self):
        obj = make()
        obj.modifiers.new('Solidify', 'SOLIDIFY').thickness = 1
        self.assertDensity(obj, 10.24)
        self.assertEqual(len(obj.modifiers), 1)

    def test_single_mesh_unwrap_failure_restores_uvs(self):
        obj = make()
        before = uv_buffer(obj)
        import bmesh
        def fail(**kwargs):
            bm = bmesh.from_edit_mesh(obj.data)
            layer = bm.loops.layers.uv.active
            bm.faces.ensure_lookup_table()
            bm.faces[0].loops[0][layer].uv = (33,44)
            raise RuntimeError('injected failure')
        with patch.object(bpy.ops, 'uv', types.SimpleNamespace(smart_project=fail)):
            count, failures = tool.smart_uv_project_unwrap_with_settings(1.15, 0)
        self.assertEqual(count, 0)
        self.assertEqual(len(failures), 1)
        np.testing.assert_array_equal(uv_buffer(obj), before)
        self.assertEqual(obj.mode, 'OBJECT')

    def test_linked_library_mesh_becomes_local_without_editing_library(self):
        obj = make('LibraryFixture')
        fixture = ROOT/f'artifacts/link-fixture-{bpy.app.version[0]}.blend'
        bpy.data.libraries.write(str(fixture), {obj.data})
        with bpy.data.libraries.load(str(fixture), link=True) as (source, dest):
            dest.meshes = [source.meshes[0]]
        obj.data = dest.meshes[0]
        self.assertIsNotNone(obj.data.library)
        before = uv_buffer(obj)
        library_mesh = obj.data
        tool.scale_uv_to_target_density(obj, 20.48, 1024)
        self.assertIsNone(obj.data.library)
        self.assertDensity(obj, 20.48)
        np.testing.assert_array_equal(tool._read_uv(library_mesh.uv_layers.active, 4), before)

    def test_uv_overlap_and_distant_tiles_count_per_surface(self):
        obj = make(vertices=[(0,0,0),(1,0,0),(1,1,0),(0,1,0),
                             (2,0,0),(3,0,0),(3,1,0),(2,1,0)],
                   faces=[(0,1,2,3),(4,5,6,7)])
        # Two overlapping islands each count; this is density, not unique coverage.
        values = np.array([(20,40),(21,40),(21,41),(20,41)]*2,np.float32)
        obj.data.uv_layers.active.uv.foreach_set('vector', values.ravel())
        self.assertDensity(obj, 10.24)

    def test_undo_redo_uv_and_linked_data(self):
        obj = make('UndoObject')
        duplicate = bpy.data.objects.new('Unselected', obj.data)
        bpy.context.collection.objects.link(duplicate)
        before = uv_buffer(obj)
        bpy.context.preferences.edit.use_global_undo = True
        # Explicit checkpoints are needed in background scripts, whose Python
        # operators do not get the interactive window manager's automatic pushes.
        bpy.ops.ed.undo_push(message='Before texel test')
        self.assertEqual(bpy.ops.object.set_target_texel_density(), {'FINISHED'})
        bpy.ops.ed.undo_push(message='After texel test')
        self.assertEqual(bpy.ops.ed.undo(), {'FINISHED'})
        obj = bpy.data.objects['UndoObject']  # Undo invalidates previous RNA refs.
        duplicate = bpy.data.objects['Unselected']
        np.testing.assert_array_equal(uv_buffer(obj), before)
        self.assertIs(obj.data, duplicate.data)
        self.assertEqual(bpy.ops.ed.redo(), {'FINISHED'})
        obj = bpy.data.objects['UndoObject']
        self.assertDensity(obj, bpy.context.scene.target_texel_density_px_cm)
        self.assertIsNot(obj.data, bpy.data.objects['Unselected'].data)


if __name__ == '__main__':
    tool.register()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Regression)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    tool.unregister()
    tool.register()  # Enabling/disabling/re-enabling must work cleanly.
    tool.unregister()
    summary = {'blender': bpy.app.version_string, 'tests': result.testsRun,
               'source':tool_source.relative_to(ROOT).as_posix(),
               'source_sha256':hashlib.sha256(tool_source.read_bytes()).hexdigest(),
               'tool_version':list(tool.bl_info['version']),
               'failures': [(str(t), e) for t,e in result.failures],
               'errors': [(str(t), e) for t,e in result.errors],
               'skipped': [(str(t), e) for t,e in result.skipped], 'passed': result.wasSuccessful()}
    (ROOT/f'artifacts/regression-{bpy.app.version[0]}.{bpy.app.version[1]}.json').write_text(json.dumps(summary, indent=2))
    if not result.wasSuccessful():
        raise SystemExit(1)
