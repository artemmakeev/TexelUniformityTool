# TexelUniformityTool 1.2.0 review evidence

Original author: Artem Makeev. Release 1.2.0: GPL-3.0-or-later; the original full
GPLv3 license document and historical v1.1 fixture are retained. Comparison base:
`324d220bc06669e1fc35bb32f826e44b00c1a89b` (v1.1). Implementation followed by
independent Astra review; all experiments used disposable synthetic scenes.

## Final independent benchmark

Set Density on Windows, two Blender worker threads, 4096-square texture,
target 17.3 px/cm. Five paired trials alternate original/reviewed order after a
warmup. Every object starts with different UV scale/aspect/tile coordinates;
world transforms are identity so the original and corrected formulas agree.
Timing includes the registered operator, explicitly requested automatic undo,
and dependency-graph flush. Scene generation/reset and registration are excluded.
Every output UV is checked analytically; largest absolute error in either version
is 1.20e-7 UV units. Selection and active object are checked for the revised tool.

| Blender | Objects | Total quads | v1.1 median ms | 1.2.0 median ms | Speedup |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5.2.2 LTS | 128 | 8,192 | 2,207.07 | 22.64 | 97.5x |
| 5.2.2 LTS | 1 | 65,536 | 928.03 | 73.13 | 12.7x |
| 5.2.2 LTS | 32 | 32,768 | 895.87 | 23.13 | 38.7x |
| 4.0.2 | 128 | 8,192 | 2,316.88 | 23.03 | 100.6x |
| 4.0.2 | 1 | 65,536 | 760.07 | 52.24 | 14.5x |
| 4.0.2 | 32 | 32,768 | 888.05 | 24.95 | 35.6x |

Raw samples: `artifacts/astra-benchmark-5.2.json` and `astra-benchmark-4.0.json`.
They record the exact source SHA-256, Blender version/build and validation error.
The later license notice update changes only source comments; its executable
Python syntax tree is identical to the version fingerprinted in those timings.
These are synthetic comparisons with this add-on's v1.1, not competing products.
The computer was shared; timing variation is visible in the raw samples.
Interactive redraw is excluded. No cross-platform or real production-asset
performance claim is made.

The large multi-object gain comes from removing repeated transitions into
multi-object Edit Mode, BMesh construction, Python UV loops and duplicate density
calculation. The new path bulk-reads triangles and UVs, transforms area normals
with the world-matrix cofactor, and writes UVs once. It uses Blender's bundled
NumPy and no persistent geometry cache.

## Million-quad memory check

Blender 5.2.2 LTS, one 1,048,576-quad mesh (2,097,152 triangles; 4,194,304 loops),
fresh process for each version. Cold Set operator includes automatic undo and
dependency-graph flush. Every output UV matches the analytic answer exactly.

| Measurement | v1.1 | 1.2.0 |
| --- | ---: | ---: |
| Set elapsed | 8.880 s | 0.699 s |
| Working set before Set | 425 MiB | 425 MiB |
| Peak working set | 1,765 MiB | 731 MiB |
| Peak private commit | 1,922 MiB | 863 MiB |

One observation per version, not a statistical throughput estimate. Windows
process lifetime peaks include Blender startup and mesh generation. The JSON
records the pre-operation peaks separately. Source and results:
`tests/astra_large_mesh.py`, `artifacts/astra-large-*-5.2.json`.

## Unwrap tradeoff

Smart UV Project still invokes Blender's built-in algorithm separately per object.
Restoring selection and visibility adds cost. Earlier five-trial checks measured
19.20 to 20.19 ms for 32 small meshes and 12.34 to 12.99 ms for eight 1,024-quad
meshes on 5.2.2 (about 5%); 4.0.2 measured 22.58 to 27.11 and 20.18 to 22.36 ms
(11-20%). These timings precede the final density-only precision guard, which
does not change unwrap. Raw data: `artifacts/benchmark-paired-*.json`.
Unwrap is not claimed as a speed improvement.

## Correctness and compatibility

**30 regression tests pass on Blender 4.0.2 and 5.2.2 LTS, Windows.** Tests use
analytic planes and an independent scalar oracle that transforms triangle edges.
They cover 100 triangles under 12 randomized affine parent/child transforms,
nonuniform/negative/singular scale, shear, scene units, concave/nonplanar faces,
mirrored/overlapping/distant UVs, degenerate/empty/missing geometry, invalid
numeric values, modifiers being excluded, inactive UV maps, shared materials,
selected/unselected linked users and library-linked meshes. State tests include
selection, visibility, active object, Object Mode polling, UV pins/selection,
injected unwrap failures, registration, undo and redo.

Automatic undo tests explicitly call registered operators with
`('EXEC_DEFAULT', True)`, then undo/redo without an extra post-operation checkpoint.
They verify both UV restoration and original mesh sharing. This exercises the
operator UNDO flag headlessly; interactive Ctrl-Z and redo-panel UX were not
manually inspected to avoid taking over the user's desktop.

The independent review reproduced a further float32 failure: scaling a 1e-6-unit
plane to 0.01 px/cm at resolution 4096 collapsed all UVs onto (0.5, 0.5), while
reporting success. A conservative coordinate-rounding area bound now detects
suspect layouts and verifies their actual stored area before writing. The usual
path avoids a second triangle UV pass. Unrepresentable targets are rejected;
separate islands collapsing to different points are also covered.

The final legacy ZIP passes install, enable, calculate, set, unwrap and disable
smoke tests in dedicated temporary configuration/scripts directories on both
versions. Preferences are not saved. See `artifacts/install-*.json`.
The GPL-3.0-or-later Extensions ZIP also passes Blender 5.2.2's manifest validator
and install/enable/calculate/set/unwrap/disable checks using an isolated local
extension repository, without network access or saved preferences. See
`tests/extension_install_smoke.py` and `artifacts/extension-install-5.2.json`.

Concrete original bugs: a 1-unit plane scaled (2,3,1) at resolution 1024 should
measure 4.180462 px/cm; v1.1 gives 10.24. Equal opposite-winding UV islands should
measure 10.24; v1.1 returns zero. Bulk unwrap loses selection/active object, and the
original setter updates only the final object's density display.

Blender 4.0 lacks `ID.is_editable` and its UV-layer write access bypasses implicit
sharing after `Mesh.copy()`. The compatibility path uses a fallback editability
check and the generic attribute accessor that requests writable detached storage.
Official source and linked-user regressions support that choice.

## Reproduction

Run from the repository root using the desired Blender executable, with no
personal scene loaded:

```text
blender --background --factory-startup --disable-autoexec -t 2 --python-exit-code 1 --python tests/test_regression.py
blender --background --factory-startup --disable-autoexec -t 2 --python-exit-code 1 --python tests/astra_benchmark.py
blender --background --factory-startup --disable-autoexec -t 2 --python-exit-code 1 --python tests/astra_large_mesh.py -- --kind original
blender --background --factory-startup --disable-autoexec -t 2 --python-exit-code 1 --python tests/astra_large_mesh.py -- --kind reviewed
python build_release.py
```

The large-mesh memory counters are Windows-specific. Installation smoke tests
require BLENDER_USER_CONFIG and BLENDER_USER_SCRIPTS set to separate directories
inside `artifacts/install-sandbox/`; the script refuses other destinations.

## Scope and limits

The original three-button workflow, operator/property names and UV pivot remain.
See README for the base-mesh, active-UV, square-resolution, whole-object-average
contract. It does not normalize islands independently, repair arbitrary broken
UVs, or include modifiers/material shader transformations. The asset behind
[issue #3](https://github.com/artemmakeev/TexelUniformityTool/issues/3) was not
available, so that report is not claimed fully resolved. Progress UI and Scale
to Bounds feature requests remain deferred.

Only Blender 4.0.2 and 5.2.2 LTS on Windows were executed. The legacy minimum is
4.0; intermediate versions and other operating systems remain untested. The
Extensions candidate conservatively declares minimum 5.2 and Windows x64, uses
GPL-3.0-or-later, and still requires accessible account tools for submission.
No user scenes, preferences or unrelated projects were modified.

## Official references checked

- [Mesh triangles](https://docs.blender.org/api/current/bpy.types.Mesh.html#bpy.types.Mesh.calc_loop_triangles)
- [UV layers](https://docs.blender.org/api/current/bpy.types.MeshUVLoopLayer.html)
- [Scene units](https://docs.blender.org/api/current/bpy.types.UnitSettings.html#bpy.types.UnitSettings.scale_length)
- [Smart UV Project](https://docs.blender.org/api/current/bpy.ops.uv.html#bpy.ops.uv.smart_project)
- [Blender 4.0.2 writable attribute access](https://github.com/blender/blender/blob/v4.0.2/source/blender/makesrna/intern/rna_attribute.cc#L289)
- [Extensions packaging](https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html)
- [Extensions license requirements](https://docs.blender.org/manual/en/latest/advanced/extensions/licenses.html)

Tested executable builds: 5.2.2 LTS `d13f752e3b9c`; 4.0.2 `9be62e85b727`.
The official portable 4.0.2 archive was SHA-256 verified before execution:
`bddb7ab6880bbb80297b93731506a48bbebdce214ee5edd17dbef8380daecded`.
