# TexelUniformityTool

Blender add-on by **Artem Makeev**. Independently unwrap selected meshes with
Smart UV Project, measure texel density in px/cm, and set a common density across
selected meshes. Select hundreds of separate props and unwrap each mesh into its
own UV layout in one operation. Version 1.2.1 reduces the repeated Edit Mode cost
of this workflow while retaining the original three-button panel.

## Installation

Install `TexelUniformityTool-1.2.1.zip` through **Edit > Preferences >
Add-ons > Install** (Blender 4.0), or the Add-ons menu's **Install from Disk** in
newer Blender. Enable TexelUniformityTool. The single `TexelUniformityTool.py`
source can also be installed directly. Disable the older copy first if it was
installed under another module name.

This is a legacy add-on ZIP. No downloads, paid dependencies or additional Python packages are
needed when using the add-on; it uses the NumPy included with Blender.

Validated on **Blender 4.0.2 and 5.2.2 LTS, Windows**, using factory-startup
headless tests. The declared minimum is Blender 4.0. Intervening releases and
other operating systems have not been run. See [review evidence](REVIEW_NOTES.md)
for the original density fixes. In the paired 5.2.2 unwrap benchmark, 1,024
separate cubes took 2.78 s versus 15.93 s in v1.2.0; 1,024 mixed props took
2.17 s versus 11.90 s. Every output UV matched a solo Blender Smart UV Project
run. Linked mesh users take a safer sequential path and do not get this gain.
See [current comparison](CURRENT_COMPARISON.md) for raw trials, memory costs,
scaling, and the separate comparison with Texel Density Checker 2026.1.1.

## Usage

Use **Object Mode**. Open **3D View > Sidebar (N) > TexelUniformity**.

1. Select meshes, choose Angle Limit and Island Margin, and click **Bulk Apply
   Smart UV Project**. Each object's whole mesh is unwrapped independently;
   selected objects are never packed together into a shared atlas.
2. Enter the square texture resolution in pixels, such as 4096. Click
   **Calculate Density** to measure the active mesh's active UV map.
3. Select the meshes to normalize, enter **Target Density** in px/cm, and click
   **Set Density**. All selected meshes get the same whole-mesh average density.

**Last Density** is the last requested measurement or set result. Recalculate
after changing geometry, transforms, texture resolution, scene units or UVs.
Unwrap clears the affected objects' previous measurement.

Selection, active object, materials and object transforms are preserved. Shared
mesh data is made independent when necessary so selected instances can reach
different world-space densities and unselected users stay unchanged. Undo
restores the UVs and original mesh sharing.

## Density definition and limits

For square resolution `R`, the density is:

`R * sqrt(sum(abs(UV triangle area)) / sum(world triangle area)) / (100 * scene scale_length)`

`scale_length` is meters per Blender unit; its default is 1. Object and parent
transforms, including nonuniform/negative scale and shear, affect world area.
Mirrored islands and overlapping faces each contribute their absolute area.
Triangles collapsed in 3D contribute neither UV nor surface area.

The tool works on the **base mesh and active UV layer**. Modifiers, material image
sizes, shader UV transforms, non-square textures and per-face texture resolutions
are outside this calculation. It neither applies modifiers nor changes materials.
Missing/fully collapsed UVs and zero-area meshes cannot be scaled and are skipped
with a reason. It does not repair malformed UVs or geometry.
Targets too small to retain accurate float32 UV coordinates are rejected before
any UV change, rather than silently collapsing the layout.

Set Density scales every island together around UV (0.5, 0.5), retaining the
original tool's relative island sizes and layout. It equalizes object averages;
it does not remove internal UV stretch or normalize islands separately. UVs may
extend beyond 0–1, and are not repacked after scaling. Hidden mesh geometry is
included in whole-object operations; visibility and selection flags are restored.

## Development and license

Run the scripts under `tests/` in background Blender with factory startup. Build
the ZIP and source/evidence archive with `python build_release.py`; output stays
in `dist/`. See [review evidence](REVIEW_NOTES.md) for reproduction commands.

Original source: [artemmakeev/TexelUniformityTool](https://github.com/artemmakeev/TexelUniformityTool).
Release **1.2.1** is licensed under the **GNU General Public License, version 3
or (at your option) any later version** (`GPL-3.0-or-later`). Original author
Artem Makeev's attribution and the full [GPLv3 license text](LICENSE.txt) are
retained. The historical v1.1 source fixture is preserved unchanged.
