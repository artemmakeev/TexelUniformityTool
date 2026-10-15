# SPDX-License-Identifier: GPL-3.0-or-later
# TexelUniformityTool by Artem Makeev.
# Release 1.2.2 is licensed under GNU GPL version 3 or, at your option, any later version.
# See LICENSE.txt for the full license terms.
# Modified 2026-10-15: independent bulk unwrap batching, density and state fixes.
import math
import time

import bpy
import bmesh
import numpy as np  # Included with Blender; no additional installation required.

bl_info = {
    "name": "TexelUniformityTool",
    "author": "Artem Makeev",
    "version": (1, 2, 2),
    "blender": (4, 0, 0),
    "description": "Bulk Smart UV Project and uniform object texel density",
    "category": "Object",
    "location": "View3D > Sidebar > TexelUniformity",
}


def _check_object(obj):
    if obj is None or obj.type != 'MESH':
        raise ValueError("Select a mesh object")
    if obj.data.is_editmode or obj.mode != 'OBJECT':
        raise ValueError("Use Object Mode; operations affect the whole mesh")


def _editable(data):
    # ID.is_editable was added after Blender 4.0.
    return getattr(data, 'is_editable', data.library is None)


def _parameters(texture_resolution, unit_scale):
    if not math.isfinite(texture_resolution) or texture_resolution <= 0:
        raise ValueError("Texture resolution must be positive and finite")
    if not math.isfinite(unit_scale) or unit_scale <= 0:
        raise ValueError("Scene unit scale must be positive and finite")


def _read_uv(layer, count):
    values = np.empty(count * 2, dtype=np.float32)
    layer.uv.foreach_get('vector', values)
    return values.reshape(-1, 2)


def _set_uv(mesh, values):
    layer = mesh.uv_layers.active
    if bpy.app.version < (5, 0, 0):
        # MeshUVLoopLayer setters in 4.0 bypass implicit sharing after Mesh.copy().
        # The generic attribute accessor requests writable (detached) storage.
        mesh.attributes[layer.name].data.foreach_set('vector', values.ravel())
    else:
        layer.uv.foreach_set('vector', values.ravel())


def _density_data(obj, texture_resolution, unit_scale, for_scaling=False):
    """Area-average px/cm and the UV buffer, without changing Blender state.

    Absolute UV triangle areas prevent mirrored islands cancelling. Cofactor
    transforms of triangle area normals handle nonuniform scale, parent shear,
    reflections and singular transforms without evaluating/copying meshes.
    """
    _check_object(obj)
    _parameters(texture_resolution, unit_scale)
    mesh = obj.data
    layer = mesh.uv_layers.active
    if layer is None or not len(mesh.polygons):
        return 0.0, None, None
    uv = _read_uv(layer, len(mesh.loops))
    if not np.isfinite(uv).all():
        raise ValueError("UV coordinates contain non-finite values")
    mesh.calc_loop_triangles()
    triangles = mesh.loop_triangles
    count = len(triangles)
    areas = np.empty(count, dtype=np.float32)
    triangles.foreach_get('area', areas)
    linear = np.asarray(obj.matrix_world, dtype=np.float64)[:3, :3]
    if not np.isfinite(linear).all():
        raise ValueError("Object transform contains non-finite values")
    gram = linear.T @ linear
    uniform_squared = float(gram[0, 0])
    if np.allclose(gram, np.eye(3) * uniform_squared, rtol=1e-7, atol=0.0):
        world_areas = areas.astype(np.float64) * uniform_squared
    else:
        normals = np.empty(count * 3, dtype=np.float32)
        triangles.foreach_get('normal', normals)
        cofactor = np.column_stack((np.cross(linear[:, 1], linear[:, 2]),
                                    np.cross(linear[:, 2], linear[:, 0]),
                                    np.cross(linear[:, 0], linear[:, 1])))
        transformed = np.einsum('ij,kj->ki', cofactor, normals.reshape(-1, 3))
        world_areas = areas * np.linalg.norm(transformed, axis=1)
    surface_area = float(world_areas.sum(dtype=np.float64))
    if not math.isfinite(surface_area):
        raise ValueError("Mesh surface area is not finite")
    if surface_area <= 0:
        return 0.0, uv, None
    indices = np.empty(count * 3, dtype=np.int32)
    triangles.foreach_get('loops', indices)
    # Float64 differences keep small islands accurate on distant UDIM tiles.
    tri_uv = uv.astype(np.float64)[indices.reshape(-1, 3)]
    a = tri_uv[:, 1] - tri_uv[:, 0]
    b = tri_uv[:, 2] - tri_uv[:, 0]
    uv_areas = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) * 0.5
    # Collapsed 3D triangles must not inflate the UV area.
    valid = world_areas > 0
    uv_area = float(uv_areas[valid].sum(dtype=np.float64))
    density = texture_resolution * math.sqrt(uv_area / surface_area) / (100 * unit_scale)
    if not math.isfinite(density):
        raise ValueError("Calculated density is not finite")
    precision = None
    if for_scaling:
        # Bound how much float32 coordinate rounding can alter total UV area.
        # This uses edges already computed above, without a second mesh read.
        edge_sum = float((np.abs(a).sum(axis=1) + np.abs(b).sum(axis=1))[valid].sum())
        precision = (indices.reshape(-1, 3), valid, uv_area, edge_sum)
    return density, uv, precision


def calculate_texel_density(obj, texture_resolution, unit_scale=None):
    """Whole base mesh's active UV density in px/cm, including world transform.

    No selection, mode, UV layer, transform or material changes. Scene scale_length
    is meters per Blender unit (including when unit system is NONE).
    """
    if unit_scale is None:
        unit_scale = bpy.context.scene.unit_settings.scale_length
    return _density_data(obj, texture_resolution, unit_scale)[0]


def _write_uv(obj, values):
    # Selected linked duplicates may need different density. Preserve unselected
    # users and never repeatedly scale one shared UV buffer.
    old_mesh = obj.data
    copied = old_mesh.users > 1 or not _editable(old_mesh)
    mesh = old_mesh.copy() if copied else old_mesh
    try:
        _set_uv(mesh, values)
        mesh.update()
        if copied:
            obj.data = mesh
    except Exception:
        if copied and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise


def scale_uv_to_target_density(obj, target_density_px_cm, texture_resolution, unit_scale=None):
    """Scale all UVs around (0.5, 0.5), preserving relative island proportions."""
    _check_object(obj)
    if not _editable(obj):
        raise ValueError("Object is read-only")
    if not math.isfinite(target_density_px_cm) or target_density_px_cm <= 0:
        raise ValueError("Target density must be positive and finite")
    if unit_scale is None:
        unit_scale = bpy.context.scene.unit_settings.scale_length
    current, uv, precision = _density_data(obj, texture_resolution, unit_scale, for_scaling=True)
    if current <= 0 or uv is None:
        raise ValueError("Mesh needs nonzero surface area and an uncollapsed active UV map")
    # Read UVs once and calculate density once. No mode switches or BMeshes.
    factor = target_density_px_cm / current
    scaled = (uv.astype(np.float64) - 0.5) * factor + 0.5
    if not np.isfinite(scaled).all() or np.any(np.abs(scaled) > np.finfo(np.float32).max):
        raise ValueError("Target density exceeds UV coordinate limits")
    stored = scaled.astype(np.float32)
    indices, valid, uv_area, edge_sum = precision
    error = float(np.max(np.abs(stored.astype(np.float64) - scaled)))
    intended_area = uv_area * factor * factor
    # If coordinate error is <= e, each triangle's area error is bounded by
    # e * (|edge_a|_1 + |edge_b|_1) + 4e^2. The usual path needs no second pass.
    area_error = error * factor * edge_sum + 4 * error * error * int(valid.sum())
    actual_density = target_density_px_cm
    if intended_area <= 0 or area_error > intended_area * 1e-4:
        triangles = stored.astype(np.float64)[indices]
        a, b = triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
        actual_area = float((np.abs(a[:, 0]*b[:, 1] - a[:, 1]*b[:, 0]) * .5)[valid].sum())
        actual_density = current * math.sqrt(actual_area / uv_area)
        if not math.isfinite(actual_density) or abs(actual_density / target_density_px_cm - 1) > 1e-4:
            raise ValueError("Target density cannot be represented accurately in float32 UVs; increase it or resize/recenter the UV layout")
    _write_uv(obj, stored)
    return actual_density


def _selection_flags(mesh, attribute):
    snapshot = []
    for suffix, elements in zip(('vert', 'edge', 'poly'), (mesh.vertices, mesh.edges, mesh.polygons)):
        values = np.zeros(len(elements), dtype=np.bool_)
        data = mesh.attributes.get(f'.{attribute}_{suffix}')
        if data is not None:
            data.data.foreach_get('value', values)
        snapshot.append(values)
    return snapshot


def _restore_flags(mesh, attribute, snapshot):
    for suffix, domain, values in zip(('vert', 'edge', 'poly'), ('POINT', 'EDGE', 'FACE'), snapshot):
        name = f'.{attribute}_{suffix}'
        data = mesh.attributes.get(name)
        current = np.zeros(len(values), dtype=np.bool_)
        if data is not None:
            data.data.foreach_get('value', current)
        # Raw attribute buffers avoid slow per-element computed RNA properties.
        if not np.array_equal(current, values):
            if data is None:
                data = mesh.attributes.new(name, 'BOOLEAN', domain)
            data.data.foreach_set('value', values)


def smart_uv_project_unwrap_with_settings(radians_angle_limit, UIisland_margin, context=None,
                                        scale_to_bounds=False, progress=None):
    """Unwrap each mesh independently with bounded temporary Edit Mode storage."""
    context = context or bpy.context
    if context.mode != 'OBJECT':
        raise ValueError("Use Object Mode")
    if not math.isfinite(radians_angle_limit) or not 0 <= radians_angle_limit <= math.pi/2:
        raise ValueError("Angle limit must be between 0 and 90 degrees")
    if not math.isfinite(UIisland_margin) or not 0 <= UIisland_margin <= 1:
        raise ValueError("Island margin must be between 0 and 1")
    selected = list(context.selected_objects)
    active = context.view_layer.objects.active
    candidates, failures = [], []
    processed = 0
    for obj in selected:
        if obj.type == 'MESH':
            if not _editable(obj) or not len(obj.data.polygons):
                failures.append((obj.name, "empty or read-only mesh"))
            else:
                candidates.append(obj)
    if progress:
        progress(len(failures), "")
    try:
        for obj in selected:
            obj.select_set(False)
        start = 0
        while start < len(candidates):
            end, loops, sources = start, 0, set()
            # Bound BMesh/backup memory. Keep linked users in separate batches so
            # a failed user can regain its original mesh before the next copy.
            while end < len(candidates) and end-start < 64:
                mesh = candidates[end].data
                if end > start and (loops+len(mesh.loops) > 200000 or mesh in sources):
                    break
                sources.add(mesh)
                loops += len(mesh.loops)
                end += 1
            records = []
            try:
                for obj in candidates[start:end]:
                    original = obj.data
                    copied = original.users > 1 or not _editable(original)
                    if copied:
                        obj.data = original.copy()
                    mesh = obj.data
                    r = {'obj':obj, 'mesh':mesh, 'original':original, 'copied':copied,
                         'ready':False, 'ok':False, 'reported':False}
                    records.append(r)
                    r['selection'] = _selection_flags(mesh, 'select')
                    r['hidden'] = _selection_flags(mesh, 'hide')
                    r['uv_count'] = len(mesh.uv_layers)
                    r['uv_index'] = mesh.uv_layers.active_index
                    r['uv'] = _read_uv(mesh.uv_layers.active, len(mesh.loops)) if r['uv_count'] else None
                    r['ready'] = True
                    if any(v.any() for v in r['hidden']):
                        _restore_flags(mesh, 'hide', [np.zeros_like(v) for v in r['hidden']])
                    obj.select_set(True)
                context.view_layer.objects.active = records[0]['obj']
                bpy.ops.object.mode_set(mode='EDIT')
                multiple = len(records) > 1
                bpy.ops.mesh.select_all(action='DESELECT' if multiple else 'SELECT')
                for r in records:
                    obj, mesh = r['obj'], r['mesh']
                    if multiple:
                        bm = bmesh.from_edit_mesh(mesh)
                        for face in bm.faces:
                            face.select_set(True)
                        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
                    try:
                        # Native packing does not honor object overrides alone.
                        # Real face selection above isolates this one UV layout.
                        with context.temp_override(object=obj, active_object=obj, edit_object=obj,
                                selected_objects=[obj], selected_editable_objects=[obj],
                                objects_in_mode=[obj], objects_in_mode_unique_data=[obj]):
                            result = bpy.ops.uv.smart_project(angle_limit=radians_angle_limit,
                                island_margin=UIisland_margin, scale_to_bounds=scale_to_bounds)
                        if 'FINISHED' not in result:
                            raise RuntimeError("Smart UV Project cancelled")
                        r['ok'] = True
                        processed += 1
                    except (RuntimeError, ValueError) as exc:
                        failures.append((obj.name, str(exc)))
                        r['reported'] = True
                    finally:
                        if multiple:
                            for face in bm.faces:
                                face.select_set(False)
                            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
                        if progress:
                            progress(processed + len(failures), obj.name)
            except (RuntimeError, ValueError) as exc:
                for r in records:
                    if not r['ok'] and not r['reported']:
                        failures.append((r['obj'].name, str(exc)))
                        r['reported'] = True
            finally:
                if context.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
                for r in records:
                    obj, mesh = r['obj'], r['mesh']
                    if r['ready']:
                        _restore_flags(mesh, 'select', r['selection'])
                        _restore_flags(mesh, 'hide', r['hidden'])
                    if not r['ok']:
                        if r['copied']:
                            obj.data = r['original']
                            bpy.data.meshes.remove(mesh)
                        elif r['ready']:
                            while len(mesh.uv_layers) > r['uv_count']:
                                mesh.uv_layers.remove(mesh.uv_layers[-1])
                            if r['uv'] is not None:
                                mesh.uv_layers.active_index = r['uv_index']
                                _set_uv(mesh, r['uv'])
                    elif "texel_density" in obj:
                        del obj["texel_density"]
                    obj.select_set(False)
            start = end
    finally:
        for obj in selected:
            obj.select_set(True)
        context.view_layer.objects.active = active
    if progress:
        progress(processed + len(failures), "")
    return processed, failures


_BATCH_PROGRESS = None


def _draw_batch_progress(self, context):
    """A real progress bar in the status bar and the add-on panel."""
    state = _BATCH_PROGRESS
    if state is None:
        return
    label = f"{state['action']}: {state['done']}/{state['total']} meshes"
    row = self.layout.row()
    if context.region and context.region.type == 'HEADER':
        row.ui_units_x = 20
    if hasattr(row, 'progress'):
        row.progress(factor=state['done'] / max(1, state['total']), type='BAR', text=label)
    else:
        # Blender versions without UILayout.progress still get a read-only bar.
        row.enabled = False
        row.prop(context.window_manager, 'texel_uniformity_progress', text=label, slider=True)


class _BatchProgress:
    """Throttled foreground redraws; headless use retains the fast path."""
    def __init__(self, context, action, total):
        self.context, self.action, self.total = context, action, total
        self.enabled = not bpy.app.background and context.window is not None and total > 0
        self.last_draw = time.monotonic()

    def __enter__(self):
        global _BATCH_PROGRESS
        if self.enabled:
            self.context.window_manager.progress_begin(0, self.total)
            _BATCH_PROGRESS = {'action': self.action, 'done': 0, 'total': self.total}
            self.context.window_manager.texel_uniformity_progress = 0
            self.last_draw = -math.inf
            self.update(0, "")
        return self

    def update(self, completed, name):
        if not self.enabled:
            return
        _BATCH_PROGRESS['done'] = min(self.total, completed)
        manager = self.context.window_manager
        manager.progress_update(completed)
        manager.texel_uniformity_progress = 100 * completed / self.total
        text = f"{self.action}: {completed}/{self.total} meshes"
        if name:
            text += f" — {name}"
        self.context.workspace.status_text_set(text)
        now = time.monotonic()
        if now - self.last_draw >= .15:
            self.last_draw = now
            # Refresh the bar without dispatching input or changing the operator
            # into a modal job (which would change existing undo semantics).
            try:
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            except RuntimeError:
                pass  # A transient redraw failure must not affect mesh work.

    def __exit__(self, exc_type, exc, traceback):
        global _BATCH_PROGRESS
        if self.enabled:
            _BATCH_PROGRESS = None
            self.context.window_manager.texel_uniformity_progress = 0
            try:
                self.context.workspace.status_text_set(None)
            finally:
                self.context.window_manager.progress_end()
                for area in self.context.screen.areas:
                    area.tag_redraw()



def _mesh_poll(cls, context):
    return context.mode == 'OBJECT' and any(o.type == 'MESH' and _editable(o)
                                          for o in context.selected_objects)


def _report_batch(operator, count, failures, action):
    if failures:
        example = f"{failures[0][0]}: {failures[0][1]}"
        operator.report({'WARNING'}, f"{action}: {count} mesh(es); skipped {len(failures)}. {example}")
    elif count:
        operator.report({'INFO'}, f"{action}: {count} mesh(es)")
    else:
        operator.report({'WARNING'}, "Select an editable mesh object")
    return {'FINISHED'} if count else {'CANCELLED'}


class OBJECT_OT_smart_uv_project_with_settings(bpy.types.Operator):
    """Apply Smart UV Project separately to each selected mesh in Object Mode"""
    bl_idname = "object.smart_uv_project_with_settings"
    bl_label = "Smart UV Project"
    bl_options = {'REGISTER', 'UNDO'}
    poll = classmethod(_mesh_poll)

    def execute(self, context):
        try:
            total = sum(o.type == 'MESH' for o in context.selected_objects)
            with _BatchProgress(context, 'Smart UV Project', total) as progress:
                count, failures = smart_uv_project_unwrap_with_settings(
                    math.radians(context.scene.UVangle_limit), context.scene.UVisland_margin,
                    context, scale_to_bounds=context.scene.UVscale_to_bounds,
                    progress=progress.update if progress.enabled else None)
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        return _report_batch(self, count, failures, "Smart UV Project applied")


class OBJECT_OT_calculate_density(bpy.types.Operator):
    """Measure the whole base mesh's active UV map, including object scale"""
    bl_idname = "object.calculate_density"
    bl_label = "Calculate Density"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.mode == 'OBJECT' and obj is not None and obj.type == 'MESH' and _editable(obj)

    def execute(self, context):
        obj = context.active_object
        try:
            density = calculate_texel_density(obj, context.scene.texture_resolution,
                                              context.scene.unit_settings.scale_length)
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        obj["texel_density"] = density
        self.report({'INFO'}, f"Density: {density:.2f} px/cm")
        return {'FINISHED'}


class OBJECT_OT_scale_uv_to_target_density(bpy.types.Operator):
    """Set mesh average density; shared mesh users become independent"""
    bl_idname = "object.set_target_texel_density"
    bl_label = "Set Target Texel Density"
    bl_options = {'REGISTER', 'UNDO'}
    poll = classmethod(_mesh_poll)

    def execute(self, context):
        count, failures = 0, []
        scene = context.scene
        objects = [o for o in context.selected_objects if o.type == 'MESH']
        with _BatchProgress(context, 'Set Density', len(objects)) as progress:
            for index, obj in enumerate(objects, 1):
                try:
                    density = scale_uv_to_target_density(obj, scene.target_texel_density_px_cm,
                                                         scene.texture_resolution,
                                                         scene.unit_settings.scale_length)
                    obj["texel_density"] = density
                    count += 1
                except (ValueError, RuntimeError) as exc:
                    failures.append((obj.name, str(exc)))
                finally:
                    progress.update(index, obj.name)
        return _report_batch(self, count, failures, "Target density set")


class VIEW3D_PT_custom_texel_uniformity_panel(bpy.types.Panel):
    """The original compact N-panel workflow."""
    bl_label = "Texel Uniformity"
    bl_idname = "VIEW3D_PT_custom_texel_uniformity"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TexelUniformity'
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        layout.label(text="UV Section:")
        layout.prop(context.scene, "UVangle_limit", text="Angle Limit")
        layout.prop(context.scene, "UVisland_margin", text="Island Margin")
        layout.prop(context.scene, "UVscale_to_bounds", text="Scale to Bounds")
        layout.operator("object.smart_uv_project_with_settings", text="Bulk Apply Smart UV Project")
        layout.label(text="Texture Resolution:")
        row = layout.row(align=True)
        row.prop(context.scene, "texture_resolution", text="")
        row.label(text="px")
        obj = context.active_object
        if obj and "texel_density" in obj:
            layout.label(text=f"Last Density: {obj['texel_density']:.2f} px/cm")
        else:
            layout.label(text="Last Density: —")
        layout.operator("object.calculate_density", text="Calculate Density")
        layout.prop(context.scene, "target_texel_density_px_cm", text="Target Density")
        layout.operator("object.set_target_texel_density", text="Set Density")
        _draw_batch_progress(self, context)


CLASSES = (OBJECT_OT_calculate_density, OBJECT_OT_scale_uv_to_target_density,
           OBJECT_OT_smart_uv_project_with_settings, VIEW3D_PT_custom_texel_uniformity_panel)
SCENE_PROPERTIES = ("texture_resolution", "target_texel_density_px_cm", "UVangle_limit", "UVisland_margin", "UVscale_to_bounds")


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.texture_resolution = bpy.props.IntProperty(
        name="Texture Size", description="Square texture width and height in pixels",
        default=4096, min=1)
    bpy.types.Scene.target_texel_density_px_cm = bpy.props.FloatProperty(
        name="Target Density", description="Whole-mesh average density in px/cm",
        default=20.48, min=0.01)
    bpy.types.Scene.UVangle_limit = bpy.props.FloatProperty(
        name="Angle Limit", description="Smart UV projection angle in degrees",
        default=66.0, min=0.0, max=89.0)
    bpy.types.Scene.UVisland_margin = bpy.props.FloatProperty(
        name="Island Margin", description="Space between UV islands",
        default=0.0, min=0.0, max=1.0)
    bpy.types.Scene.UVscale_to_bounds = bpy.props.BoolProperty(
        name="Scale to Bounds", description="Scale each mesh's Smart UV result to the 0–1 bounds",
        default=True)
    bpy.types.WindowManager.texel_uniformity_progress = bpy.props.FloatProperty(
        name="Progress", subtype='PERCENTAGE', min=0, max=100, default=0,
        options={'HIDDEN', 'SKIP_SAVE'})
    bpy.types.STATUSBAR_HT_header.append(_draw_batch_progress)


def unregister():
    bpy.types.STATUSBAR_HT_header.remove(_draw_batch_progress)
    del bpy.types.WindowManager.texel_uniformity_progress
    for name in SCENE_PROPERTIES:
        delattr(bpy.types.Scene, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
