# Changelog

## 1.2.1

- Accelerate independent Smart UV Project across separate meshes by entering
  Edit Mode in bounded batches, while selecting and packing one mesh at a time.
- Keep a native single-mesh path for dense geometry and linked mesh users.
  Shared meshes remain independent when edited and unselected users stay intact.
- Add per-mesh UV oracle checks through 1,024 objects, batch-boundary undo and
  failure recovery tests, mixed material/UV-layer tests, and memory measurements.
- Compare equivalent density operations with Texel Density Checker 2026.1.1's
  official Python extension and a source-built native backend. Report different
  density definitions and linked-data behavior separately from timings.

36 regression tests pass on Blender 4.0.2 and 5.2.2 LTS, Windows. See
CURRENT_COMPARISON.md for repeated trials, accuracy, memory and known limits.

## 1.2.0

- Release under GNU GPL version 3 or (at your option) any later version
  (`GPL-3.0-or-later`), retaining Artem Makeev's attribution and the GPLv3 text.
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
release 1.2.0 is GPL-3.0-or-later.
