#!/usr/bin/env python3
"""The entity.records service: on one device, then two devices of one
throwaway account syncing through a private local Daochi node. Nothing here
touches real accounts, nodes or displays."""
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
monocypher = package('monocypher')
liboqs = Path(os.environ['LIBOQS_LIBRARY'])
output = ROOT / 'build/records-test'
shutil.rmtree(output, ignore_errors=True)
output.mkdir(parents=True)
paths = ['--module-path', str(ROOT / 'src'), '--module-path', str(std_root / 'std'),
         '--module-path', f'kryon={kryon / "src/backend"}', '--module-path', str(kryon / 'src/backend'),
         '--module-path', str(kryon / 'src/ui'), '--module-path', f'daochi_client={daochi}', '--module-path', str(daochi),
         '--module-path', f'oqs={oqs / "src"}']
flags = subprocess.check_output(['pkg-config', '--libs', 'gtk+-3.0'], text=True).split()


def build(name):
    generated = output / name
    subprocess.run([ZIRAN, 'build', '--target=c', '--root', str(ROOT), *paths, '--entry', f'{name}:Check',
                    '-o', str(generated), str(ROOT / 'tests' / f'{name}.zi')], check=True, env=ENV)
    # _exit skips curl's TLS library destructors, which crash at exit here.
    (generated / 'main.c').write_text(f'#include "tests/{name}.h"\n#include <stdio.h>\n#include <unistd.h>\n'
        'int main(void) { int result = Check(); if (result) fprintf(stderr, "check %d failed\\n", result); '
        'fflush(NULL); _exit(result != 0); }\n')
    executable = output / (name + '.test')
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections',
                    '-Wl,--gc-sections', f'-I{std_root / "include"}', f'-I{generated}', f'-I{monocypher / "src"}',
                    *map(str, generated.rglob('*.c')), str(monocypher / 'src/monocypher.c'),
                    str(monocypher / 'src/optional/monocypher-ed25519.c'),
                    str(liboqs), *flags, '-lX11', '-l:libcurl.so.4', '-lpthread', '-lm', '-o', str(executable)],
                   check=True, env=ENV)
    return executable


def private(folder):
    for path in [folder, *folder.rglob('*')]:
        assert path.stat().st_mode & 0o077 == 0, f'Non-private record path: {path}'


local = build('entity_records_test')
data = output / 'local'
data.mkdir(mode=0o700)
subprocess.run([str(local)], check=True, env={**ENV, 'ENTITY_DATA': str(data)})
private(data)
print('Entity records on one device: save, list with fields, read, delete and reload passed')

assert DAOCHI.is_file(), f'Build the Daochi node first ({DAOCHI}) or set DAOCHI_BIN'
synced = build('entity_records_sync_test')
node_folder = output / 'node'
node_folder.mkdir(mode=0o700)
node_binary = node_folder / 'daochi'
shutil.copy2(DAOCHI, node_binary)
with socket.socket() as probe:
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
node_env = {**ENV, 'DAOCHI_ADDR': f'127.0.0.1:{port}', 'DAOCHI_DB': str(node_folder / 'node.db'),
            'DAOCHI_BASE_URL': f'http://127.0.0.1:{port}', 'DAOCHI_LAN_DISCOVERY': '0',
            'DAOCHI_ALLOW_EPHEMERAL_TOKEN_SECRET': '1'}
node_url = f'http://127.0.0.1:{port}'
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
        devices = {name: output / name for name in ('first', 'second', 'third')}
        for folder in devices.values():
            folder.mkdir(mode=0o700)

        def step(device, name):
            result = subprocess.run([str(synced)], env={**ENV, 'ENTITY_DATA': str(devices[device]),
                                    'ENTITY_RECORDS_STEP': name, 'ENTITY_RECORDS_NODE': node_url},
                                    capture_output=True, text=True, timeout=120)
            assert result.returncode == 0, f'{device} {name}: {result.stderr}{result.stdout}'

        step('first', 'create')
        for name in ('account.key', 'entity.json'):
            shutil.copy2(devices['first'] / name, devices['second'] / name)
        step('third', 'local')
        step('first', 'first')
        step('second', 'second')
        for name in ('account.key', 'entity.json'):
            shutil.copy2(devices['first'] / name, devices['third'] / name)
        # Returning to an account may already have its cached campaign while
        # the signed-out device also earned progress under that same ID.
        for folder in (devices['first'] / 'records').iterdir():
            if folder.name != 'local' and folder.is_dir():
                shutil.copytree(folder, devices['third'] / 'records' / folder.name)
        step('third', 'adopt')
        step('first', 'third')
        for folder in devices.values():
            private(folder)
        assert not list((devices['third'] / 'records/local').glob('levels/*.json')), 'Device-only copies stayed behind'
        assert not list((devices['third'] / 'records/local').glob('game-progress/*.json')), 'Device-only campaign stayed behind'
    finally:
        node.terminate()
        node.wait(timeout=10)
print('Entity records between two devices of one account: upload, download, change, delete and adopting '
      'records kept before the account passed')
