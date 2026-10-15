import bpy
import math
import bmesh

bl_info = {
    "name": "TexelUniformityTool",
    "author": "Artem Makeev",
    "version": (1, 1),
    "blender": (4, 0),
    "description": "Applies Smart UV project to multiple meshes. Sets desired texel density to multiple meshes.",
    "category": "Object",
}

def smart_uv_project_unwrap_with_settings(radians_angle_limit, UIisland_margin):
    # Store the current mode to restore it later
    original_mode = bpy.context.object.mode
    # Ensure we're in Object mode
    bpy.ops.object.mode_set(mode='OBJECT')
    
    
        
    for obj in bpy.context.selected_objects:
        # Only operate on mesh objects
        if obj.type == 'MESH':
            # Deselect all objects
            bpy.ops.object.select_all(action='DESELECT')
            # Select the current object
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            # Switch to Edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            # Select all faces
            bpy.ops.mesh.select_all(action='SELECT')
            # Apply the Smart UV Project unwrapping with the angle limit in radians
            bpy.ops.uv.smart_project(angle_limit=radians_angle_limit, island_margin=UIisland_margin)
            # Switch back to Object mode
            bpy.ops.object.mode_set(mode='OBJECT')

    # Reselect all originally selected objects
    for obj in bpy.context.selected_objects:
        obj.select_set(True)
    # Restore the original mode
    bpy.ops.object.mode_set(mode=original_mode)


def calculate_texel_density(obj, texture_resolution):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='OBJECT')

    # Calculate the 3D surface area
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    surface_area = sum(face.calc_area() for face in bm.faces)
    bm.free()

    # Calculate the UV area
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.verify()
    uv_area = 0
    for face in bm.faces:
        loops = face.loops
        for i in range(len(loops)):
            loop_a = loops[i - 1]
            loop_b = loops[i]
            uv_a = loop_a[uv_layer].uv
            uv_b = loop_b[uv_layer].uv
            uv_area += (uv_a.x * uv_b.y - uv_a.y * uv_b.x)
    uv_area = abs(uv_area) / 2
    bm.free()

    # Assuming the texture is applied uniformly across the entire UV map
    # Convert texture resolution from pixels to centimeters (assuming 1px = 1cm for simplicity)
    texture_resolution_cm = texture_resolution / 100  # Convert px to cm

    # Calculate texel density (px/cm)
    if uv_area > 0:  # Avoid division by zero
        texel_density = texture_resolution_cm / math.sqrt(surface_area / uv_area)
    else:
        texel_density = 0

    return texel_density

def scale_uv_to_target_density(obj, target_density_px_cm, texture_resolution):
    # Calculate current texel density
    current_texel_density = calculate_texel_density(obj, texture_resolution)
    
    # Calculate scale factor
    scale_factor = target_density_px_cm / current_texel_density if current_texel_density else 0
    
    # Proceed if we have a valid scale factor
    if scale_factor > 0:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        mesh = bmesh.from_edit_mesh(obj.data)
        uv_layer = mesh.loops.layers.uv.active
        
        for face in mesh.faces:
            for loop in face.loops:
                loop_uv = loop[uv_layer]
                # Apply scale factor, centering the UV map scaling at (0.5, 0.5)
                new_u = (loop_uv.uv[0] - 0.5) * scale_factor + 0.5
                new_v = (loop_uv.uv[1] - 0.5) * scale_factor + 0.5
                loop_uv.uv = (new_u, new_v)
        
        bmesh.update_edit_mesh(obj.data)
        bpy.ops.object.mode_set(mode='OBJECT')



class OBJECT_OT_smart_uv_project_with_settings(bpy.types.Operator):
    """Apply Smart UV Project with predefined settings"""
    bl_idname = "object.smart_uv_project_with_settings"
    bl_label = "Smart UV Project"
    bl_options = {'REGISTER', 'UNDO'}

    UVangle_limit = bpy.props.FloatProperty(
        name="Angle Limit",
        description="Angle limit for UV seams",
        default=66.0,
        min=0.0,
        max=89.0
    )
    UVisland_margin = bpy.props.FloatProperty(
        name="Island Margin",
        description="Space between islands",
        default=0.0,
        min=0.0,
        max=1.0
    )

    def execute(self, context):
        UIangle_limit = context.scene.UVangle_limit
        UIisland_margin = context.scene.UVisland_margin
        
        print("UIangle_limit: ", UIangle_limit)
        print("UIisland_margin: ", UIisland_margin)
        # Now, convert angle_limit to radians
        radians_angle_limit = math.radians(UIangle_limit)

        # Call your function with the correct parameters
        smart_uv_project_unwrap_with_settings(radians_angle_limit, UIisland_margin)
        self.report({'INFO'}, "Smart UV Project applied.")
        return {'FINISHED'}


class VIEW3D_PT_custom_texel_uniformity_panel(bpy.types.Panel):
    """Creates a Panel in the N panel for Texel Uniformity"""
    bl_label = "Texel Uniformity"
    bl_idname = "VIEW3D_PT_custom_texel_uniformity"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TexelUniformity'
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout

        # UV Section
        layout.label(text="UV Section:")
        row = layout.row()
        row.prop(context.scene, "UVangle_limit", text="Angle Limit")
        row = layout.row()
        row.prop(context.scene, "UVisland_margin", text="Island Margin")
        row = layout.row()
        row.operator("object.smart_uv_project_with_settings", text="Bulk Apply Smart UV Project")
        
        # Texel Section
        layout.label(text="Texture Resolution:")
        row = layout.row()
        row.prop(context.scene, "texture_resolution", text="")
        row.label(text="px")
        
        # Current Density Display (Placeholder, implement actual display logic)
        obj = context.active_object
        if obj and "texel_density" in obj:
            row = layout.row()
            row.label(text=f"Current Density: {obj['texel_density']:.2f} px/cm")
        else:
            row = layout.row()
            row.label(text="Current Density: ")
        
        # Calculate Density Button
        row = layout.row()
        row.operator("object.calculate_density", text="Calculate Density")
        
        # Target Density Input
        row = layout.row()
        row.prop(context.scene, "target_texel_density_px_cm", text="Target Density")
        
        # Set Density Button
        row = layout.row()
        row.operator("object.set_target_texel_density", text="Set Density")


class OBJECT_OT_calculate_density(bpy.types.Operator):
    """Calculate the current texel density"""
    bl_idname = "object.calculate_density"
    bl_label = "Calculate Density"

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "No active mesh object selected.")
            return {'CANCELLED'}

        texture_resolution = context.scene.texture_resolution
        texel_density = calculate_texel_density(obj, texture_resolution)
        
        # Store the calculated density in a custom property for display
        obj["texel_density"] = texel_density
        
        self.report({'INFO'}, f"Density calculated: {texel_density:.2f} px/cm")
        return {'FINISHED'}

class OBJECT_OT_scale_uv_to_target_density(bpy.types.Operator):
    """Set the target texel density"""
    bl_idname = "object.set_target_texel_density"
    bl_label = "Set Target Texel Density"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        target_density_px_cm = context.scene.target_texel_density_px_cm
        texture_resolution = context.scene.texture_resolution

        for obj in context.selected_objects:
            if obj.type == 'MESH':
                scale_uv_to_target_density(obj, target_density_px_cm, texture_resolution)
        
        texel_density = calculate_texel_density(obj, texture_resolution)
        obj["texel_density"] = texel_density
        self.report({'INFO'}, "Target texel density set for selected objects.")
        
        return {'FINISHED'}




def register():
    bpy.utils.register_class(OBJECT_OT_calculate_density)
    bpy.utils.register_class(OBJECT_OT_scale_uv_to_target_density)
    bpy.types.Scene.texture_resolution = bpy.props.IntProperty(
        name="Texture Size",
        description="Texture resolution in pixels",
        default=4096,
        min=1
    )

    bpy.types.Scene.target_texel_density_px_cm = bpy.props.FloatProperty(
        name="Target Density",
        description="Target texel density in px/cm",
        default=20.48,
        min=0.01
    )

    bpy.utils.register_class(OBJECT_OT_smart_uv_project_with_settings)
    bpy.utils.register_class(VIEW3D_PT_custom_texel_uniformity_panel)
    bpy.types.Scene.UVangle_limit = bpy.props.FloatProperty(
        name="Angle Limit",
        description="Limit for the angle",
        default=66.0,
        min=0.0,
        max=180.0
    )
    bpy.types.Scene.UVisland_margin = bpy.props.FloatProperty(
        name="Island Margin",
        description="Margin for the island",
        default=0.0,
        min=0.0,
        max=1.0
    )

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_calculate_density)
    bpy.utils.unregister_class(OBJECT_OT_scale_uv_to_target_density)
    del bpy.types.Scene.texture_resolution
    del bpy.types.Scene.target_texel_density_px_cm
    
    bpy.utils.unregister_class(OBJECT_OT_smart_uv_project_with_settings)
    bpy.utils.unregister_class(VIEW3D_PT_custom_texel_uniformity_panel)
    del bpy.types.Scene.UVangle_limit
    del bpy.types.Scene.UVisland_margin

if __name__ == "__main__":
    register()