import bpy
import math

def smart_uv_project_unwrap_with_settings():
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
            bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0)
            # Switch back to Object mode
            bpy.ops.object.mode_set(mode='OBJECT')

    # Reselect all originally selected objects
    for obj in bpy.context.selected_objects:
        obj.select_set(True)
    # Restore the original mode
    bpy.ops.object.mode_set(mode=original_mode)

# Run the Smart UV Project unwrapping function
smart_uv_project_unwrap_with_settings()
