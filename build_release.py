"""Build deterministic, public-safe archives. No network or publication actions."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parent
DIST = ROOT / 'dist'
PUBLIC_FILES = [
    'TexelUniformityTool.py', 'LICENSE.txt', 'README.md', 'CHANGELOG.md',
    'REVIEW_NOTES.md', 'build_release.py', '.gitignore',
    'tests/test_regression.py', 'tests/benchmark.py', 'tests/astra_benchmark.py',
    'tests/astra_large_mesh.py', 'tests/upstream_v1_1.py', 'tests/install_smoke.py',
    'tests/extension_install_smoke.py', 'tests/test_progress_ui.py', 'ISSUE_REVIEW_1_2_2.md',
    'artifacts/regression-4.2.json', 'artifacts/issues-probe.json',
    'artifacts/issues-ui-4.0.json', 'artifacts/issues-ui-4.2.json', 'artifacts/issues-ui-5.2.json',
    'artifacts/regression-4.0.json', 'artifacts/regression-5.2.json',
    'artifacts/astra-benchmark-4.0.json', 'artifacts/astra-benchmark-5.2.json',
    'artifacts/astra-large-original-5.2.json', 'artifacts/astra-large-reviewed-5.2.json',
    'artifacts/benchmark-paired-4.0.json', 'artifacts/benchmark-paired-5.2.json',
    'artifacts/install-4.0.json', 'artifacts/install-4.2.json', 'artifacts/install-5.2.json',
    'artifacts/extension-install-4.2.json', 'artifacts/extension-install-5.2.json',
    'CURRENT_COMPARISON.md',
    'tests/prepare_current_comparator.py', 'tests/comparator_setup.py',
    'tests/comparison_common.py', 'tests/generate_comparison_scenes.py',
    'tests/benchmark_current_comparator.py', 'tests/comparator_semantics.py',
    'tests/benchmark_independent_unwrap.py', 'tests/measure_unwrap_memory.py',
    'tests/probe_unwrap_batch_context.py', 'tests/run_isolated.ps1',
    'tests/fixtures/texel_uniformity_v1_2_0.py',
    'tests/fixtures/texel_uniformity_v1_2_1_candidate.py',
    'tests/fixtures/candidate_batch64_verified.py',
    'artifacts/current-comparator-provenance.json',
    'artifacts/current-input-manifest.json',
    'artifacts/source-equivalence-1.2.1.json',
    'artifacts/current-comparison-python-5.2-pilot2.json',
    'artifacts/current-comparison-native-5.2-final.json',
    'artifacts/current-comparison-python-5.2-calculate-verified.json',
    'artifacts/current-comparison-native-5.2-calculate-verified.json',
    'artifacts/current-comparison-native-4.0-calculate-verified.json',
    'artifacts/current-comparison-python-5.2-memory-ours.json',
    'artifacts/current-comparison-python-5.2-memory-python.json',
    'artifacts/current-comparison-native-5.2-memory-native.json',
    'artifacts/current-semantics-python-5.2.json',
    'artifacts/current-semantics-native-5.2.json',
    'artifacts/independent-unwrap-5.2-candidate.json',
    'artifacts/independent-unwrap-5.2-candidate-props.json',
    'artifacts/independent-unwrap-4.0-candidate.json',
    'artifacts/independent-unwrap-5.2-tuning.json',
    'artifacts/independent-unwrap-4.0-tuning.json',
    'artifacts/independent-unwrap-5.2-dense-final.json',
    'artifacts/independent-unwrap-5.2-shared-final-shared.json',
    'artifacts/independent-unwrap-5.2-production-final.json',
    'artifacts/independent-unwrap-4.0-production-final.json',
    'artifacts/unwrap-memory-5.2-baseline-cubes1024.json',
    'artifacts/unwrap-memory-5.2-candidate-cubes1024.json',
    'artifacts/unwrap-context-proof-5.2-faces.json',
    'artifacts/unwrap-context-proof-4.0-faces.json',
    'artifacts/extension-validation-4.2.json', 'artifacts/extension-validation-5.2.json',
    'ASTRA_REVIEW_1_2_1.md', 'tests/astra_current_accuracy.py',
    'artifacts/astra-current-accuracy-python-5.2.json',
    'artifacts/astra-current-accuracy-native-5.2.json',
    'artifacts/current-comparison-python-5.2-astra-confirmed.json',
    'artifacts/current-comparison-native-5.2-astra-confirmed.json',
]


def public_bytes(name):
    data = (ROOT / name).read_bytes()
    if name.startswith('artifacts/install-'):
        report = json.loads(data)
        report['installed_module'] = '<isolated test scripts directory>/addons/TexelUniformityTool/__init__.py'
        data = (json.dumps(report, indent=2) + '\n').encode()
    if re.search(rb'(?<![A-Za-z])[A-Za-z]:[\\/]', data):
        raise ValueError(f'Private machine path in public file: {name}')
    return data


def archive(path, entries):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 15, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            output.writestr(info, data)
    return {'file': path.name, 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    DIST.mkdir(exist_ok=True)
    common = [(name, public_bytes(name)) for name in ('LICENSE.txt', 'README.md', 'CHANGELOG.md', 'REVIEW_NOTES.md', 'ISSUE_REVIEW_1_2_2.md')]
    code = public_bytes('TexelUniformityTool.py')
    info = next(node for node in ast.parse(code).body if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'bl_info' for t in node.targets))
    version = '.'.join(map(str, ast.literal_eval(info.value)['version']))
    addon = archive(DIST / f'TexelUniformityTool-{version}.zip',
                    [('TexelUniformityTool/__init__.py', code)] +
                    [(f'TexelUniformityTool/{name}', data) for name, data in common])
    source = archive(DIST / f'TexelUniformityTool-{version}-source-evidence.zip',
                     [(f'TexelUniformityTool/{name}', public_bytes(name)) for name in PUBLIC_FILES])
    # Extensions candidate uses the same explicit license grant as release 1.2.0.
    # Validation/building does not submit it to the online Extensions platform.
    lines = code.decode().splitlines(keepends=True)
    extension_code = ''.join(lines[:info.lineno-1] + lines[info.end_lineno:]).encode()
    manifest = '''schema_version = "1.0.0"
id = "texel_uniformity_tool"
version = "VERSION_PLACEHOLDER"
name = "TexelUniformityTool"
tagline = "Bulk Smart UV Project and consistent object texel density"
maintainer = "Artem Makeev"
type = "add-on"
website = "https://github.com/artemmakeev/TexelUniformityTool"
blender_version_min = "4.2.0"
license = ["SPDX:GPL-3.0-or-later"]
platforms = ["windows-x64"]
'''.replace('VERSION_PLACEHOLDER', version)
    extension = archive(DIST / f'texel_uniformity_tool-{version}-extension-candidate.zip',
                        [('blender_manifest.toml', manifest.encode()), ('__init__.py', extension_code)] + common)
    result = {'version': version, 'addon': addon, 'source_evidence': source, 'extension_candidate': extension,
              'source_sha256': hashlib.sha256(code).hexdigest(),
              'upstream_commit': '324d220bc06669e1fc35bb32f826e44b00c1a89b',
              'license': 'GPL-3.0-or-later',
              'extension_status': 'local candidate; online submission pending accessible account tools'}
    (DIST / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
