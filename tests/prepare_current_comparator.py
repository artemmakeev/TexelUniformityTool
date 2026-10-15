"""Verify and stage inspected current comparator sources; no add-on execution."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT.parent / 'comparators'
REPO = COMP / 'Blender-Texel-Density-Checker'
ARCHIVE = COMP / 'texel-density-checker-2026.1.1-official-extension.zip'
EXPECTED = 'ca5554ec5c08a830c344ddc08a4c4f8f2e619178ac05ef582ea0293ab540308d'
assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == EXPECTED
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO).decode().strip() == '3737a8c9d87b29bffa670a79828f49c4cd656599'
with zipfile.ZipFile(ARCHIVE) as z:
    for info in z.infolist():
        path = Path(info.filename)
        assert not path.is_absolute() and '..' not in path.parts
    assert all(not i.filename.lower().endswith(('.dll', '.so', '.dylib', '.exe')) for i in z.infolist())
    z.extractall(COMP / 'official-extension-inspected')
    comparisons = {}
    for info in z.infolist():
        if info.filename.endswith('.py'):
            a = z.read(info)
            b = (REPO / 'Blender Extensions' / info.filename).read_bytes()
            comparisons[info.filename] = a.replace(b'\r\n', b'\n') == b.replace(b'\r\n', b'\n')
    assert all(comparisons.values()), comparisons

native = COMP / 'native-source-build/texel_density'
native.mkdir(parents=True, exist_ok=True)
for path in (REPO / 'texel_density').glob('*'):
    if path.is_file() and path.suffix in ('.py', '.json', '.toml'):
        shutil.copyfile(path, native / path.name)
shutil.copyfile(REPO / 'LICENSE', native / 'LICENSE')
(native / 'libs').mkdir(exist_ok=True)

audits = {}
for label, directory in [('marketplace_python', COMP / 'official-extension-inspected'),
                         ('native_source', native)]:
    risky = []
    imports = set()
    for path in directory.rglob('*.py'):
        tree = ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(x.name for x in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
            elif isinstance(node, ast.Call):
                call = ast.unparse(node.func)
                if any(k in call for k in ('open', 'remove', 'unlink', 'rmdir', 'system', 'Popen',
                                           'urlopen', 'request', 'exec', 'eval', 'WinDLL', 'CDLL')):
                    risky.append({'file':path.name, 'line':node.lineno, 'call':call})
    audits[label] = {'imports':sorted(imports), 'review_call_sites':risky}
report = {
    'author':'Ivan Vostrikov and credited contributors', 'version':'2026.1.1',
    'source_repository':'https://github.com/mrven/Blender-Texel-Density-Checker',
    'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO).decode().strip(),
    'marketplace_url':'https://extensions.blender.org/add-ons/texel-density-checker/',
    'marketplace_sha256':EXPECTED, 'marketplace_license':'GPL-3.0-or-later',
    'marketplace_blender_min':'4.2.0', 'native_blender_min':'3.0.0',
    'marketplace_sources_match_repository_ignoring_checkout_newlines':comparisons,
    'native_execution':'local MSVC Release build of inspected current tdcore.cpp/h; shipped binary not executed',
    'source_audit':audits,
}
native_dll = native / 'libs/tdcore.dll'
if native_dll.exists():
    report['native_dll_sha256'] = hashlib.sha256(native_dll.read_bytes()).hexdigest()
(COMP / 'provenance.json').write_text(json.dumps(report,indent=2))
if native_dll.exists():
    with zipfile.ZipFile(COMP / 'texel-density-checker-2026.1.1-source-built.zip', 'w', zipfile.ZIP_DEFLATED) as output:
        for path in sorted(native.rglob('*')):
            if path.is_file() and (path.suffix == '.py' or path.name in ('LICENSE', 'tdcore.dll')):
                output.write(path, 'texel_density/' + path.relative_to(native).as_posix())
print(json.dumps(report,indent=2))
