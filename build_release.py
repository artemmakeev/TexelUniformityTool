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
    'artifacts/regression-4.0.json', 'artifacts/regression-5.2.json',
    'artifacts/astra-benchmark-4.0.json', 'artifacts/astra-benchmark-5.2.json',
    'artifacts/astra-large-original-5.2.json', 'artifacts/astra-large-reviewed-5.2.json',
    'artifacts/benchmark-paired-4.0.json', 'artifacts/benchmark-paired-5.2.json',
    'artifacts/install-4.0.json', 'artifacts/install-5.2.json',
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
    common = [(name, public_bytes(name)) for name in ('LICENSE.txt', 'README.md', 'CHANGELOG.md', 'REVIEW_NOTES.md')]
    code = public_bytes('TexelUniformityTool.py')
    addon = archive(DIST / 'TexelUniformityTool-1.2.0.zip',
                    [('TexelUniformityTool/__init__.py', code)] +
                    [(f'TexelUniformityTool/{name}', data) for name, data in common])
    source = archive(DIST / 'TexelUniformityTool-1.2.0-source-evidence.zip',
                     [(f'TexelUniformityTool/{name}', public_bytes(name)) for name in PUBLIC_FILES])
    # Local-only Extensions candidate. Preserve the existing license; online
    # submission needs an explicit GPL-3.0-or-later grant from the copyright owner.
    lines = code.decode().splitlines(keepends=True)
    info = next(node for node in ast.parse(code).body if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'bl_info' for t in node.targets))
    extension_code = ''.join(lines[:info.lineno-1] + lines[info.end_lineno:]).encode()
    manifest = '''schema_version = "1.0.0"
id = "texel_uniformity_tool"
version = "1.2.0"
name = "TexelUniformityTool"
tagline = "Bulk Smart UV Project and consistent object texel density"
maintainer = "Artem Makeev"
type = "add-on"
website = "https://github.com/artemmakeev/TexelUniformityTool"
blender_version_min = "5.2.0"
license = ["SPDX:GPL-3.0-only"]
platforms = ["windows-x64"]
'''
    extension = archive(DIST / 'texel_uniformity_tool-1.2.0-extension-candidate.zip',
                        [('blender_manifest.toml', manifest.encode()), ('__init__.py', extension_code)] + common)
    result = {'addon': addon, 'source_evidence': source, 'extension_candidate': extension,
              'source_sha256': hashlib.sha256(code).hexdigest(),
              'upstream_commit': '324d220bc06669e1fc35bb32f826e44b00c1a89b',
              'extension_status': 'local candidate; online submission pending license grant and account access'}
    (DIST / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
