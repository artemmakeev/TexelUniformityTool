# GitHub issue review for 1.2.2

Base: published 1.2.1 commit b3225898c816f8d604a0089fd638f42e3088b321.
Original author Artem Makeev; GPL-3.0-or-later unchanged.

## #2: progress during batch work

1.2.1 had no progress reporting. 1.2.2 adds a status-bar/panel progress bar,
completed/total mesh count, current object in the status text, and Blender's
native progress cursor. Skips count as attempts and retain the final failure
report. Progress is cleared in a context-manager finally path, including
unexpected errors. Foreground redraws are limited to approximately 7 Hz after
the initial frame. Headless execution avoids UI work.

`tests/test_progress_ui.py` opens only an isolated test window, captures actual
intermediate progress during both unwrap and Set Density, checks cleanup, then
quits. The capture deliberately forces each redraw so a fast operation cannot
finish between frames; it is not a performance benchmark. Native screenshots
and `artifacts/issues-ui-*.json` record the results on Blender 4.0.2, 4.2.0 and
5.2.2 LTS. Test profiles are disposable; real user preferences are not touched.

Progress measures meshes, not work inside a single native Smart UV call. A
large mesh can still block between updates. No ETA or cancellation is promised.
The previously published headless 1.2.1 benchmark numbers exclude these new UI
redraws and must not be represented as 1.2.2 foreground measurements.

## #3: applied Boolean and incorrect density

The original issue has no attached .blend. A concrete reproduction creates a
cube, subtracts a 16-sided cylinder with the Exact Boolean solver, applies the
modifier and measures the resulting UVs. On Blender 4.2.0 the old v1.1 algorithm
returns 0.16083661 px/cm, whereas an independent scalar triangle/world-area
oracle gives 1.55330244 px/cm. The already-released 1.2.1 implementation gives
1.55330244 px/cm. `artifacts/issues-probe.json` records this pre-fix review.

The old algorithm summed signed UV edges across the whole mesh before taking
one absolute value, allowing opposite orientation to cancel. The current
algorithm sums absolute UV triangle areas and handles transformed world area.
The new `test_issue3_applied_boolean_uv_area_does_not_cancel` applies a real
Boolean, compares against the independent oracle, confirms the old failure and
checks subsequent density adjustment. It passes on all three Blender versions.

This establishes a fix for that reproduced calculation error, not automatic UV
repair or proof about every possible malformed original asset. Invalid UV data
is rejected, and a genuinely collapsed UV map cannot be scaled. A different
remaining case needs a reproducible .blend and expected result.

## #4: Scale to Bounds

1.2.1 omitted the native parameter, which defaults to false. 1.2.2 adds an
enabled-by-default checkbox and passes its value to each separate native Smart
UV Project call. Turning it off retains the previous scale/aspect behavior.
Blender's option can stretch UV proportions when filling both axes.
The regression verifies both settings, native results, and separate 0–1 bounds
for two differently shaped selected meshes.

## Verification and compatibility

41 established and new regressions pass on Windows x64 with Blender 4.0.2,
4.2.0 and 5.2.2 LTS. Coverage includes selection/visibility, linked mesh users,
undo/redo, error recovery, UV precision and the three issue-specific cases.
The standard add-on minimum remains 4.0; the Extensions manifest minimum is
4.2.0. Other releases and operating systems have not been executed.
