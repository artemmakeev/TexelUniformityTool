import bpy
import bmesh
from math import sqrt

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
        texel_density = texture_resolution_cm / sqrt(surface_area / uv_area)
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

# Parameters
target_texel_density_px_cm = 20.48
texture_resolution = 4096  # Your texture resolution here

# Apply to all selected mesh objects
for obj in bpy.context.selected_objects:
    if obj.type == 'MESH':
        scale_uv_to_target_density(obj, target_texel_density_px_cm, texture_resolution)