#!/usr/bin/env python3
"""Build the standalone Entity profile manager for entity.waozi.xyz."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
output = ROOT / 'build/entity-site'
work = ROOT / 'build/profile-site'
work.mkdir(parents=True, exist_ok=True)
ziran = str(ROOT / 'scripts/ziran.sh')
toolchain = Path(subprocess.check_output([ziran, 'pkg', 'path', 'ziran'], cwd=ROOT, text=True).strip())
subprocess.run(['make', '-j2', 'build/entity.zx'], cwd=ROOT, check=True)
subprocess.run([sys.executable, str(ROOT / 'scripts/build-web.py'), '--profile', str(ROOT / 'build/entity.zx'),
                '--output', str(work / 'runtime.html'), '--entry', 'profile_web:main',
                '--source', 'src/profile_web.zi'], cwd=ROOT,
               env={**os.environ, 'ZIRAN': str(toolchain / 'build/bin/ziran')}, check=True)
if output.exists():
    shutil.rmtree(output)
shutil.copytree(ROOT / 'web', output)
revision = hashlib.sha256()
for name in ('runtime.js', 'runtime.wasm'):
    shutil.copyfile(work / name, output / name)
    revision.update(name.encode() + b'\0' + (output / name).read_bytes())
digest = revision.hexdigest()
page = output / 'index.html'
page.write_text(page.read_text().replace('__ENTITY_ASSET_REVISION__', digest))
source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
(output / 'build.json').write_text(json.dumps({'source_revision': source, 'assets_sha256': digest}, indent=2) + '\n')
print('Entity profile manager built in build/entity-site')
