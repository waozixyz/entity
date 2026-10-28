#!/usr/bin/env python3
"""Account aliases through the standalone account's provider, the way the
Alias page saves one, against a private local Daochi node: normalizing what
people type, saving, changing, a taken alias and an unreachable node.
Nothing here touches real accounts, nodes or displays."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ENV = {key: value for key, value in os.environ.items()
       if key not in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS')}
ZIRAN = os.environ.get('ZIRAN_BIN', 'ziran')
DAOCHI = Path(os.environ.get('DAOCHI_BIN', ROOT.parents[1] / 'kryonlabs/daochi/daochi'))


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
output = ROOT / 'build/alias-test'
shutil.rmtree(output, ignore_errors=True)
output.mkdir(parents=True)
paths = ['--module-path', str(ROOT / 'src'), '--module-path', str(std_root / 'std'),
         '--module-path', f'kryon={kryon / "src/backend"}', '--module-path', str(kryon / 'src/backend'),
         '--module-path', str(kryon / 'src/ui'), '--module-path', f'daochi_client={daochi}', '--module-path', str(daochi),
         '--module-path', f'oqs={oqs / "src"}', '--module-path', f'crypto={crypto / "src"}']
flags = subprocess.check_output(['pkg-config', '--libs', 'gtk+-3.0'], text=True).split()

generated = output / 'alias_test'
subprocess.run([ZIRAN, 'build', '--target=c', '--root', str(ROOT), *paths, '--entry', 'alias_test:Check',
                '-o', str(generated), str(ROOT / 'tests/alias_test.zi')], check=True, env=ENV)
# _exit skips curl's TLS library destructors, which crash at exit here.
(generated / 'main.c').write_text('#include "tests/alias_test.h"\n#include <stdio.h>\n#include <unistd.h>\n'
    'int main(void) { int result = Check(); if (result) fprintf(stderr, "check %d failed\\n", result); '
    'fflush(NULL); _exit(result != 0); }\n')
executable = output / 'alias.test'
subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections',
                '-Wl,--gc-sections', f'-I{std_root / "include"}', f'-I{generated}', f'-I{monocypher / "src"}',
                *map(str, generated.rglob('*.c')), str(monocypher / 'src/monocypher.c'),
                str(monocypher / 'src/optional/monocypher-ed25519.c'),
                str(liboqs), *flags, '-lX11', '-l:libcurl.so.4', '-lpthread', '-lm', '-lz', '-o', str(executable)],
               check=True, env=ENV)

assert DAOCHI.is_file(), f'Build the Daochi node first ({DAOCHI}) or set DAOCHI_BIN'
node_folder = output / 'node'
node_folder.mkdir(mode=0o700)
node_binary = node_folder / 'daochi'
shutil.copy2(DAOCHI, node_binary)


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


port = free_port()
node_url = f'http://127.0.0.1:{port}'
node_env = {**ENV, 'DAOCHI_ADDR': f'127.0.0.1:{port}', 'DAOCHI_DB': str(node_folder / 'node.db'),
            'DAOCHI_BASE_URL': node_url, 'DAOCHI_LAN_DISCOVERY': '0',
            'DAOCHI_ALLOW_EPHEMERAL_TOKEN_SECRET': '1'}
devices = {name: output / name for name in ('first', 'second', 'offline')}
for folder in devices.values():
    folder.mkdir(mode=0o700)


def step(device, name, node):
    result = subprocess.run([str(executable)], env={**ENV, 'ENTITY_DATA': str(devices[device]),
                            'ALIAS_STEP': name, 'ALIAS_NODE': node},
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f'{device} {name}: {result.stderr}{result.stdout}'


with (node_folder / 'node.log').open('w') as log:
    node = subprocess.Popen([str(node_binary)], cwd=node_folder, env=node_env, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 30
        while True:
            assert node.poll() is None, 'The node exited: ' + (node_folder / 'node.log').read_text()[-2000:]
            try:
                urllib.request.urlopen(node_url + '/api/v1/apps/entity', timeout=2).read()
                break
            except OSError:
                assert time.monotonic() < deadline, 'The node did not start'
                time.sleep(.2)
        for device in ('first', 'second'):
            step(device, 'create', node_url)
        step('first', 'first', node_url)
        for alias_file in devices['first'].glob('alias.*.txt'):
            alias_file.unlink()
        step('first', 'restore', node_url)
        step('first', 'picture', node_url)
        profile_path = devices['first'] / 'entity.json'
        import json
        profile = json.loads(profile_path.read_text())
        profile['picture'] = 0
        profile_path.write_text(json.dumps(profile))
        step('first', 'picture_restore', node_url)
        step('second', 'second', node_url)
        # Nothing listens on this port: the node cannot be reached.
        step('offline', 'create', f'http://127.0.0.1:{free_port()}')
        step('offline', 'offline', '')
    finally:
        node.terminate()
        node.wait(timeout=10)
print('Account aliases: capitals, @ and spaces save as the node stores them; changing, a taken alias, '
      'a too short one and an unreachable node each answer as they should')
