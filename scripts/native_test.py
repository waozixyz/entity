#!/usr/bin/env python3
"""Run native account fixtures without any inherited display or real data."""
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ENV = {key: value for key, value in os.environ.items()
       if key not in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS')}
ZIRAN = os.environ.get('ZIRAN_BIN', 'ziran')

def package(name):
    return Path(os.environ.get(name.upper() + '_DIR') or subprocess.check_output(
        [ZIRAN, 'pkg', 'path', name], cwd=ROOT, text=True).strip())

std_root = Path(os.environ.get('ZIRAN_ROOT') or package('ziran'))
kryon = package('kryon')
daochi = package('daochi_client')
oqs = package('oqs')
crypto = package('crypto')
monocypher = package('monocypher')
liboqs = Path(os.environ['LIBOQS_LIBRARY'])
output = ROOT / 'build/native-test'
output.mkdir(parents=True, exist_ok=True)
generated = output / 'generated'
shutil.rmtree(generated, ignore_errors=True)
paths = ['--module-path', str(ROOT / 'src'), '--module-path', str(std_root / 'std'),
         '--module-path', f'kryon={kryon / "src/backend"}', '--module-path', str(kryon / 'src/backend'), '--module-path', str(kryon / 'src/ui'),
         '--module-path', f'daochi_client={daochi}', '--module-path', str(daochi),
         '--module-path', f'oqs={oqs / "src"}', '--module-path', f'crypto={crypto / "src"}']
subprocess.run([ZIRAN, 'build', '--target=c', '--root', str(ROOT), *paths,
                '--entry', 'management_test:Check', '-o', str(generated),
                str(ROOT / 'tests/management_test.zi')], check=True, env=ENV)
(generated / 'main.c').write_text('#include "tests/management_test.h"\n#include <stdio.h>\n'
    'int main(void) { int result = Check(); if (result) fprintf(stderr, "Account fixture %d failed\\n", result); return result != 0; }\n')
flags = subprocess.check_output(['pkg-config', '--libs', 'gtk+-3.0'], text=True).split()
executable = output / 'test'
subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections',
                '-Wl,--gc-sections', f'-I{std_root / "include"}', f'-I{generated}', f'-I{monocypher / "src"}',
                *map(str, generated.rglob('*.c')), str(monocypher / 'src/monocypher.c'),
                str(monocypher / 'src/optional/monocypher-ed25519.c'),
                str(liboqs), *flags, '-lX11', '-l:libcurl.so.4', '-lpthread', '-lm', '-lz', '-o', str(executable)], check=True, env=ENV)
data = output / 'data'
shutil.rmtree(data, ignore_errors=True)
ENV['ENTITY_DATA'] = str(data)
subprocess.run([str(executable)], check=True, env=ENV)
for path in data.rglob('*'):
    assert path.stat().st_mode & 0o077 == 0, f'Non-private fixture path: {path.name}'
# Entity was called Self: an existing self folder moves over once.
legacy = output / 'legacy'
shutil.rmtree(legacy, ignore_errors=True)
(legacy / 'self').mkdir(parents=True, mode=0o700)
(legacy / 'self/marker.txt').write_text('kept')
shutil.copyfile(data / 'entity.json', legacy / 'self/self.json')
moved = {**ENV, 'XDG_DATA_HOME': str(legacy)}
moved.pop('ENTITY_DATA')
subprocess.run([str(executable)], check=True, env=moved)
assert not (legacy / 'self').exists(), 'The self folder was not moved'
assert (legacy / 'entity/marker.txt').read_text() == 'kept', 'The self folder lost its files'
assert (legacy / 'entity/entity.json').exists() and not (legacy / 'entity/self.json').exists()
print('Recovery compatibility, tampering, QR transfer, one-time actions, cancelled switches and identity-scoped storage and the move from Self passed.')
