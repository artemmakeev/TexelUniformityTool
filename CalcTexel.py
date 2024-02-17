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

# Example usage
# Replace 'your_texture_resolution_here' with the actual texture resolution
texture_resolution = 4096  # Example texture resolution in pixels
selected_obj = bpy.context.active_object
texel_density = calculate_texel_density(selected_obj, texture_resolution)
print(f"Texel Density: {texel_density} px/cm")