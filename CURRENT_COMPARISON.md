# Independent unwrap and current comparator review — 1.2.1

Final Astra review passed with 36 regressions on both installed Blender versions.
See [final review](ASTRA_REVIEW_1_2_1.md) for additional selection-mode, failure
recovery, real-layout accuracy checks and independently repeated timings.

## Main behavior and improvement

Artem Makeev's original workflow unwraps each selected mesh independently. Each
mesh gets a complete Smart UV Project layout; selecting more objects does not
combine them into an atlas. Texel Density Checker has no equivalent bulk
per-mesh Smart UV operation, so there is no competing-product unwrap speed rank.

The measured bottleneck was repeated Object/Edit Mode transitions, rather than
UV packing itself. At 1,024 cubes the old path made 2,048 mode changes, spending
about 10 s of a 12 s profiling pass there. The new path enters Edit Mode in
batches of at most 64 distinct mesh datablocks and 200,000 loops, selects the
faces of one mesh, runs Blender's Smart UV Project, then moves to the next mesh.
A single larger mesh stays on the original native selection path. No production
geometry/UV cache or result reuse is used.

Object context overrides alone were experimentally insufficient: Blender packed
multiple meshes together. That prototype was rejected. Real per-mesh face
selection is required, and every timed output is compared with a solo Blender
Smart UV result. Material image aspect, active UV layers, pins, hidden geometry,
selection, failed linked users and batch-boundary undo have regression coverage.
Shared source meshes are processed in separate batches so a failure can restore
the original before another user is edited. They get correctness, not a batching
gain.

Paired medians, three alternating trials after warmup, including automatic undo
and graph flush:

| Blender | Input | 1.2.0 ms | Batched ms | Ratio |
| --- | --- | ---: | ---: | ---: |
| 5.2.2 | 16 cubes | 14.03 | 9.14 | 1.54x |
| 5.2.2 | 128 cubes | 216.97 | 85.03 | 2.55x |
| 5.2.2 | 512 cubes | 3440.73 | 744.49 | 4.62x |
| 5.2.2 | 1,024 cubes | 15930.39 | 2778.45 | 5.73x |
| 5.2.2 | 1,024 mixed props | 11896.51 | 2166.77 | 5.49x |
| 4.0.2 | 1,024 cubes | 6944.09 | 1398.26 | 4.97x |

**Every UV coordinate matched the solo Blender reference exactly** in these
captures. The mixed scene has 48,128 triangles / 144,384 loops, including bevelled
crates, capped pipes, concave brackets and cubes, with rotations/nonuniform scale.
The cube scene has 12,288 triangles / 36,864 loops. Original selection, active
non-mesh sentinel, Object Mode, hide flags and transforms were preserved.

These paired captures use `candidate_batch64_verified.py`. The final candidate
adds only the native selection fast path for single-object batches. A subsequent
paired 65,536-quad test measured 121.73 vs 119.07 ms (ranges 102.04–123.65 and
104.08–120.60 ms), with exact UV equality. Linked-user medians were 406.18 vs
439.12 ms at 128 users, and 32079.22 vs 28726.60 ms at 1,024 users; ranges overlap
widely, so no gain is claimed. Unselected shared UVs stayed untouched and every
selected user became independent. Batch sizes 16, 32 and 64 were also measured:
16 was slower; 32 offered no clear benefit over 64. No new tuning UI is added.

Raw trials, source hashes and profiles are in `artifacts/independent-unwrap-*.json`.
The final source has the same executable syntax tree as the tested final
candidate. `artifacts/source-equivalence-1.2.1.json` proves all density functions
and operator classes are unchanged from the exact published 1.2.0 source.
Final production-source captures are named `*-production-final.json`.

## Exact current competing product

- **Texel Density Checker 2026.1.1**, Ivan Vostrikov and credited contributors.
- [Official Blender Extensions listing](https://extensions.blender.org/add-ons/texel-density-checker/):
  Python edition, updated July 6, 2026, Blender minimum 4.2.0, GPL-3.0-or-later.
- Official ZIP SHA-256:
  `ca5554ec5c08a830c344ddc08a4c4f8f2e619178ac05ef582ea0293ab540308d`.
- [Official source](https://github.com/mrven/Blender-Texel-Density-Checker), commit
  `3737a8c9d87b29bffa670a79828f49c4cd656599`, includes the free native edition
  advertised for Blender 3.0+. Python extension sources match that checkout
  ignoring checkout line endings.
- The native backend tested here is **locally compiled inspected source**, using
  installed MSVC 2022 with `/LD /O2 /GL /MD /EHsc /std:c++17 /DNDEBUG /LTCG`.
  Shipped opaque binaries were not executed. DLL SHA-256:
  `831fa3cff04495cf062ae82b2b4111fc3c7318a731901582a5b74bf558dfc938`.
  These numbers are not a measurement of the distributed native binary.

No comparator files are changed to improve or impair performance. Normal deferred
initialization runs before timing, automatic recalculation is disabled during
input setup, and the native backend is asserted loaded without Python fallback.
No help links, downloads or installers run from the add-ons. Provenance and
inspected call-site inventory: `artifacts/current-comparator-provenance.json`.

## Fairness and accuracy

The tools use different definitions on stretched layouts. This tool calculates
`R * sqrt(total_abs_UV_area / total_world_area) / (100 * scale_length)`.
TDC's `AVERAGE` uses a UV-area-weighted arithmetic mean of face densities. On two
equal-world-area triangles with a 1:4 UV-area ratio, the input reports are
64.76345 and 73.728 px/cm. After target 17.3, our area average is 17.30000 and TDC's
area average is 15.19650. That difference is a semantic choice, not a speed or
correctness defect attributed to the comparator.

All speed inputs therefore have constant UV/world-area ratio within each object,
so both averages agree mathematically. Each trial reloads the **same .blend
file**. Resolution is 4096 square, target 17.3 px/cm, scene scale 1, Object Mode,
whole selected meshes, `AVERAGE`, `UV_CENTER`, automatic undo enabled (two steps).
The independent oracle transforms triangle vertex edges, not the production
cofactor calculation. Expected UV scaling about (0.5,0.5), every resulting object
density, unchanged transforms and object state are checked after every trial.
Common density tolerance is explicitly 0.1%; expected UV tolerance is 0.0002.
TDC formats intermediate densities to three decimals and sums float32 weighted
terms; actual errors are retained rather than rounded to zero.

Linked data has different contracts too: with two selected users at scales 1 and
2 plus an unselected third, this tool produces densities 17.3 / 17.3 and leaves
the third untouched. Current TDC retains sharing: measured selected densities
34.6 / 17.3, and the unselected UVs change. This case is reported separately and
is not used for speed ranking. See `artifacts/current-semantics-*-5.2.json`.

## Set Density scaling, Blender 5.2.2 LTS

All times below are **our tool / TDC in milliseconds**, paired within the same
run. Three alternating trials after one warmup. Setup/reset/validation are
excluded; registered operator, automatic undo and dependency-graph flush are
included. The density implementation fingerprint is 1.2.0; it is unchanged in
1.2.1. `not run` is deliberately not inferred from another edition.

| Input | Objects | Faces | Official Python run ms | Source-built native run ms |
| --- | ---: | ---: | ---: | ---: |
| grid64 | 1 | 64 | not run | 1.07 / 5.19 |
| grid65536 | 1 | 65,536 | 44.57 / 1556.29 | 44.58 / 938.04 |
| props64 | 64 | 3,008 | 17.75 / 210.94 | 17.78 / 245.14 |
| cubes16 | 16 | 192 | not run | 3.39 / 42.47 |
| cubes128 | 128 | 1,536 | 19.85 / 536.81 | 19.48 / 619.81 |
| cubes512 | 512 | 6,144 | not run | 75.41 / 7215.09 |
| cubes1024 | 1,024 | 12,288 | 152.40 / 38873.13 | 255.40 / 47357.94 |
| props1024 | 1,024 | 48,128 | 282.57 / 43217.82 | 301.29 / 41388.58 |

Largest relative Set density error: ours **0.00005394%**, TDC
**0.01190434%**. All tested outputs satisfy the common tolerance and
retain object selection/active object/mode. Complete captures:
`artifacts/current-comparison-python-5.2-pilot2.json` and
`artifacts/current-comparison-native-5.2-final.json`. The earlier `pilot.json`
is incomplete exploratory data and is excluded from the package and these tables.

## Calculate Density

Only one selected object is used: this tool measures the active object while
TDC can aggregate selection. These later runs additionally assert unchanged UVs
and validate the reported number against the oracle. Earlier calculation timing
fields were exploratory and are superseded by `*-calculate-verified.json`.

| Blender | TDC edition | Input | Our median ms | TDC median ms |
| --- | --- | --- | ---: | ---: |
| 5.2.2 LTS | Official Python | grid64 | 0.896 | 1.690 |
| 5.2.2 LTS | Official Python | grid65536 | 34.604 | 675.968 |
| 5.2.2 LTS | Source-built native | grid64 | 0.913 | 2.172 |
| 5.2.2 LTS | Source-built native | grid65536 | 32.396 | 345.952 |
| 4.0.2 | Source-built native | grid64 | 0.453 | 1.976 |
| 4.0.2 | Source-built native | grid65536 | 31.345 | 269.395 |

## Memory and practical limits

Fresh process per operation, Windows counters. Peaks include startup, add-on
setup and scene loading; the pre-operation peak is recorded separately. One cold
sample each, not a throughput estimate:

| Operation, 5.2.2 | Peak working set MiB | Peak private commit MiB |
| --- | ---: | ---: |
| Independent unwrap, 1,024 cubes, 1.2.0 | 263.56 | 324.48 |
| Independent unwrap, 1,024 cubes, 1.2.1 | 289.97 | 364.73 |
| Set, 1,024 props, ours | 280.24 | 341.87 |
| Set, 1,024 props, TDC official Python | 280.23 | 341.47 |
| Set, 1,024 props, TDC source-built native | 279.70 | 345.51 |

Unwrap batching trades about 26 MiB peak working set for fewer mode changes in
this sample. The density scene's peaks are mostly established during setup; it
shows no meaningful memory advantage for either tool. Measurements are in
`unwrap-memory-*.json` and `current-comparison-*-memory-*.json`.

The shared Windows computer has a Ryzen 9 5900X (12 cores/24 threads) and 64 GiB
RAM. Only our own headless processes ran sequentially with two Blender threads,
OpenBLAS/OMP limits of two and BelowNormal priority. Other tasks were left alone;
wall-time variability is visible in the samples. Interactive redraw, additional
operating systems, production assets and every competitor feature are untested.
Tiny-mesh cases are dominated by operator/scene overhead; native is not always
faster than Python. No general fastest-tool claim is supported.

A 4.0 headless TDC Set run crashed inside Blender's UV transform/editor context
(`ED_region_draw_cb_activate` / `initTransform`). An area-only attempt also
crashed. No 4.0 Set timings are reported, and this is not evidence of failure in
interactive Blender. Calculate works on 4.0 without a synthetic area override.
The 5.2 harness also exposed a redo-HUD crash with unnecessary editor overrides
on data-only operators (`BKE_regiontype_from_id` / `ED_area_type_hud_ensure`);
removing those overrides resolved it. No comparator code was patched to do so.

## Reproduction

Use disposable profiles, never normal user preferences. Windows launcher:

```powershell
.\tests\run_isolated.ps1 -BlenderExe <path-to-Blender-4.0.2.exe> -Version 4.0 -Script tests/generate_comparison_scenes.py -Label inputs
.\tests\run_isolated.ps1 -BlenderExe <path-to-Blender.exe> -Script tests/test_regression.py -Label regression
.\tests\run_isolated.ps1 -BlenderExe <path-to-Blender.exe> -Script tests/benchmark_independent_unwrap.py -Arguments '--paired --trials 3' -Label unwrap
```

The launcher takes an explicit Blender path (or `blender.exe` on PATH), sets
isolated config/scripts/extensions directories and resource limits, and checks
exit codes. It can optionally read a private `benchmark-local-paths.json` next
to the repository. No local path configuration is distributed.

For comparator tests, create sibling `comparators/`, clone the official source
there as `Blender-Texel-Density-Checker` and check out the pinned commit above.
Download the official archive from
[its checksum-addressed URL](https://extensions.blender.org/download/sha256:ca5554ec5c08a830c344ddc08a4c4f8f2e619178ac05ef582ea0293ab540308d/add-on-texel-density-checker-v2026.1.1.zip)
as `texel-density-checker-2026.1.1-official-extension.zip`. Read the source before
execution. `python tests/prepare_current_comparator.py` verifies the checksum,
commit and matching sources, inventories review call sites and stages native
source files. For native measurements, use an installed x64 MSVC developer prompt
inside `comparators/`, create `native-source-build/texel_density/libs`, and build:

```text
cl /nologo /LD /O2 /GL /MD /EHsc /std:c++17 /DNDEBUG /Fo:native-source-build/tdcore.obj /Fe:native-source-build/texel_density/libs/tdcore.dll Blender-Texel-Density-Checker/tdcore/tdcore.cpp /link /LTCG /IMPLIB:native-source-build/tdcore.lib
```

Run the preparation script again to package that local build. Never substitute
the shipped opaque library in a source-built reproduction.

```powershell
.\tests\run_isolated.ps1 -BlenderExe <path-to-Blender.exe> -Script tests/benchmark_current_comparator.py -Arguments '--kind python --cases grid65536,props64,cubes128,cubes1024,props1024 --operations set --trials 3 --label reproduced' -Label compare-python
.\tests\run_isolated.ps1 -BlenderExe <path-to-Blender.exe> -Script tests/benchmark_current_comparator.py -Arguments '--kind native --operations set --trials 3 --label reproduced' -Label compare-native
.\tests\run_isolated.ps1 -BlenderExe <path-to-Blender.exe> -Script tests/benchmark_current_comparator.py -Arguments '--kind native --cases grid64,grid65536 --operations calculate --trials 3 --label reproduced' -Label compare-calculate
.\tests\run_isolated.ps1 -BlenderExe <path-to-Blender.exe> -Script tests/comparator_semantics.py -Arguments '--kind python' -Label semantics
.\tests\run_isolated.ps1 -BlenderExe <path-to-Blender.exe> -Script tests/measure_unwrap_memory.py -Arguments '--source TexelUniformityTool.py --scene cubes1024 --label reproduced' -Label memory
```

`artifacts/current-input-manifest.json` records exact original binary input hashes
and counts. Regeneration produces equivalent geometry; .blend file hashes can
vary with Blender serialization/session metadata. Both compared tools must reload
the same newly generated file, whose hash is recorded in their capture.

Official API references: [Smart UV Project](https://docs.blender.org/api/current/bpy.ops.uv.html#bpy.ops.uv.smart_project),
[BMesh update](https://docs.blender.org/api/current/bmesh.html#bmesh.update_edit_mesh),
[context override](https://docs.blender.org/api/current/bpy.types.Context.html#bpy.types.Context.temp_override).
See REVIEW_NOTES.md for earlier transform/UV fixes, the full density definition,
license and compatibility evidence. Only 4.0.2 and 5.2.2 on Windows were executed;
other versions and platforms remain untested.
