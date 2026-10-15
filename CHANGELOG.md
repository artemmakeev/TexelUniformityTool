# Changelog

## 1.2.0

- Accelerate density calculation and scaling with bulk mesh/UV reads, NumPy
  operations and one UV write per object. Remove density-operation mode changes.
- Measure world-space surface area, including nonuniform/negative scale, parent
  shear and scene units. Mirrored UV triangles no longer cancel each other.
- Ignore collapsed 3D triangles in both area sums; report missing UVs, empty
  geometry and invalid numeric inputs without changing them.
- Preserve selected objects, active object, materials and transforms. Make shared
  mesh data independent when editing requires it, preserving unselected users.
- Restore mesh selection/visibility after whole-object Smart UV Project, and
  recover the previous UV layout when a per-object unwrap fails.
- Support Blender 4.x mesh implicit sharing safely during bulk UV writes.
- Reject target densities that cannot be represented accurately by float32 UVs.
- Update every processed object's Last Density and clear it after unwrapping.

Tested on Blender 4.0.2 and 5.2.2 LTS, Windows. See REVIEW_NOTES.md for measured
performance, correctness evidence and limitations. Original author Artem Makeev;
original GPL-3.0 license retained.
