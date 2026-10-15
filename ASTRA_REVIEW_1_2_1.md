# Astra final review — 1.2.1

**Passed.** No production-code change was required after Sol's implementation.
The add-on source SHA-256 remains
`d13326da45b14a7a4529972ed4d6127669349c5c9b72ff6fa94d3a049e51e8f7`.
Original author Artem Makeev and GPL-3.0-or-later are retained; LICENSE.txt is
byte-identical to the prior public version.

## Independent per-mesh unwrap

Reviewed the bounded batch loop, real BMesh face selection, context override,
per-object UV backups, failed-operation rollback, linked mesh separation and
Object Mode cleanup. The optimization still invokes Smart UV once per mesh.
It does not combine meshes into an atlas or reuse another object's output.
The already recorded 1,024-object output comparisons and batch-boundary undo
results were inspected instead of repeating every expensive trial.

Two additional regressions exercise six UV-sync/mesh-selection combinations
(sync off/on times vertex/edge/face mode) on a crate, capped pipe and concave
bracket, and failure after a partially written UV in the middle of a three-mesh
batch. Results match the independent v1.2.0 solo path exactly, inactive UVs and
settings remain intact, the failed object's UVs are restored, and successful
neighbors still complete. Existing tests cover pins, aspect materials, shared
users including failed users, active-object state and automatic undo/redo.

**36 regressions pass on Blender 4.0.2 and 5.2.2 LTS**, Windows, with the same
production source fingerprint. Reports: `artifacts/regression-4.0.json` and
`artifacts/regression-5.2.json`. Only disposable headless profiles were used.
Interactive Ctrl-Z/redraw and other Blender versions/platforms remain untested.

## Density accuracy on ordinary Smart UV layouts

The comparison suite's uniform-area-ratio fixtures are intentionally constructed
so the two different density formulas agree. Additional validation now covers
24 mixed props with native solo Smart UV layouts and nonuniform world scale.
Each tool is checked against an independent implementation of **its own** average.
These are accuracy checks, not equivalent-output speed comparisons.

At target 17.3 px/cm:

| Tool / definition | Maximum relative Calculate error | Maximum relative Set error |
| --- | ---: | ---: |
| Ours, square root of total UV / total world area | 0.00000060% | 0.00000821% |
| TDC Python, UV-area-weighted face density | 0.00234540% | 0.00234905% |
| TDC source-built native, same weighted definition | 0.00234540% | 0.00234905% |

Both pass. Our resulting area averages span 17.29999858–17.29999998; their
weighted face averages span 17.4240–17.5697. TDC's weighted averages span
17.29959362–17.30040015, while its area averages span 17.0342–17.1765. The layouts
therefore differ for a valid semantic reason. Neither average is treated as an
accuracy defect in the other tool. Selection, active object, mode and transforms
were preserved. Raw data: `artifacts/astra-current-accuracy-*-5.2.json`.

## Exact competitor timing ratios

Texel Density Checker **2026.1.1**, Ivan Vostrikov and contributors. Official
Python Extensions ZIP and source-built native backend at the exact pinned
commit/hash in CURRENT_COMPARISON.md. The distributed native binary was not run.

Set Density, Blender **5.2.2 LTS**, medians in milliseconds. Ratio is TDC median
divided by ours from the same run. These original captures were checked against
the scripts, per-object accuracy/state outcomes and source fingerprints:

| TDC edition | Input | Our ms | TDC ms | Ratio |
| --- | --- | ---: | ---: | ---: |
| Official Python | grid65536 | 44.57 | 1556.29 | 34.92x |
| Official Python | props64 | 17.75 | 210.94 | 11.88x |
| Official Python | cubes128 | 19.85 | 536.81 | 27.05x |
| Official Python | cubes1024 | 152.40 | 38873.13 | 255.08x |
| Official Python | props1024 | 282.57 | 43217.82 | 152.95x |
| Source-built native | grid64 | 1.07 | 5.19 | 4.87x |
| Source-built native | grid65536 | 44.58 | 938.04 | 21.04x |
| Source-built native | props64 | 17.78 | 245.14 | 13.78x |
| Source-built native | cubes16 | 3.39 | 42.47 | 12.51x |
| Source-built native | cubes128 | 19.48 | 619.81 | 31.82x |
| Source-built native | cubes512 | 75.41 | 7215.09 | 95.68x |
| Source-built native | cubes1024 | 255.40 | 47357.94 | 185.43x |
| Source-built native | props1024 | 301.29 | 41388.58 | 137.37x |

Independent repeat, three alternating paired trials after warmup, same files,
settings, undo and graph flush:

| TDC edition | Input | Our ms | TDC ms | Ratio |
| --- | --- | ---: | ---: | ---: |
| Official Python | 64 mixed props / 3,008 triangles | 17.81 | 210.76 | 11.83x |
| Official Python | 128 cubes / 1,536 triangles | 19.50 | 527.72 | 27.06x |
| Source-built native | 64 mixed props / 3,008 triangles | 18.06 | 255.25 | 14.13x |
| Source-built native | 128 cubes / 1,536 triangles | 19.41 | 640.97 | 33.03x |

Raw repeat captures: `artifacts/current-comparison-*-5.2-astra-confirmed.json`.
They validate the same source shipped in 1.2.1. Calculate-only ratios for the
64-quad / 65,536-quad meshes are 1.89x / 19.53x (5.2 Python), 2.38x / 10.68x
(5.2 source-built native), and 4.36x / 8.59x (4.0 source-built native), with
validated numeric outputs and unchanged UVs. Full times and samples are in
CURRENT_COMPARISON.md and `*-calculate-verified.json`.

## Interpretation and limits

The 5.5–5.7x bulk unwrap improvement is **versus this add-on's own 1.2.0**, not
Texel Density Checker; the latter has no equivalent bulk per-mesh Smart UV
operation. Linked users intentionally take separate batches and have no claimed
speedup. One cold 1,024-cube unwrap used about 26 MiB more peak working set.
Density memory peaks were similar across tools, dominated by scene setup.

TDC offers different features and Edit Mode/face-selection workflows. The speed
results apply to the specified whole-mesh Object Mode operation and synthetic
inputs only. TDC keeps linked mesh data shared; ours separates edited users to
protect unselected users and independently satisfy different world densities.
Such cases are documented separately and excluded from timing rankings.

Shared-machine timing varies; native is not always faster than Python. No
all-scenes, all-platforms or fastest-product claim follows from these results.
The 4.0 TDC Set headless editor/transform crash remains a harness compatibility
limit, not an asserted interactive add-on failure. Earlier exploratory calculation
fields are superseded by validated calculation captures. No paid components or
user scenes/settings were used.

## Reproduce added checks

```powershell
.\tests\run_isolated.ps1 -BlenderExe <blender.exe> -Script tests/test_regression.py -Label final-review
.\tests\run_isolated.ps1 -BlenderExe <blender.exe> -Script tests/astra_current_accuracy.py -Arguments '--kind python' -Label accuracy-python
.\tests\run_isolated.ps1 -BlenderExe <blender.exe> -Script tests/astra_current_accuracy.py -Arguments '--kind native' -Label accuracy-native
.\tests\run_isolated.ps1 -BlenderExe <blender.exe> -Script tests/benchmark_current_comparator.py -Arguments '--kind python --cases props64,cubes128 --operations set --trials 3 --label reviewed' -Label repeat-python
```

Use CURRENT_COMPARISON.md's pinned comparator preparation and synthetic scene
generation first. All operations use isolated temporary profiles. Release-file
hosting and marketplace submission are separate from this source review.
