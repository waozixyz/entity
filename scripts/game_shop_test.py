#!/usr/bin/env python3
"""Real Dew debits, retry deduplication and cross-device restore on a private node."""
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ENV = {key: value for key, value in os.environ.items()
       if key not in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER')}
ENV.update(MAKEFLAGS='-j1', ZIRAN_PAR_THREADS='1', OMP_NUM_THREADS='1', YUE_DESKTOP_RECOVERY='0')


def package(name):
    return Path(subprocess.check_output(['ziran', 'pkg', 'path', name], cwd=ROOT, env=ENV, text=True).strip())


def main():
    out = ROOT / 'build/game-shop-integration'
    out.mkdir(parents=True, exist_ok=True)
    fixture = Path(tempfile.mkdtemp(prefix='fixture-', dir=out))
    fixture.chmod(0o700)
    compiler, kryon, daochi, crypto, oqs, mono = (package(name) for name in
        ('ziran', 'kryon', 'daochi_client', 'crypto', 'oqs', 'monocypher'))
    generated = out / 'generated'
    paths = ['--module-path', str(ROOT / 'src'), '--module-path', str(compiler / 'std'),
             '--module-path', 'kryon=' + str(kryon / 'src/backend'),
             '--module-path', str(kryon / 'src/backend'),
             '--module-path', 'kryon=' + str(kryon / 'src/ui'), '--module-path', str(kryon / 'src/ui'),
             '--module-path', 'daochi_client=' + str(daochi), '--module-path', str(daochi),
             '--module-path', 'crypto=' + str(crypto / 'src'), '--module-path', 'oqs=' + str(oqs / 'src')]
    subprocess.run(['ziran', 'build', '--root', str(ROOT), *paths, '--target=c', '--entry',
                    'game_shop_integration:Check', '-o', str(generated), 'tests/game_shop_integration.zi'],
                   cwd=ROOT, env=ENV, check=True)
    (generated / 'main.c').write_text('#include "tests/game_shop_integration.h"\n#include <stdio.h>\n#include <unistd.h>\n'
        'int main(void) { int result = Check(); if (result) fprintf(stderr, "shop integration step failed: %d\\n", result); '
        'fflush(NULL); _exit(result != 0); }\n')
    executable = out / 'test'
    libs = subprocess.check_output(['pkg-config', '--libs', 'gtk+-3.0'], text=True).split()
    oqs_library = Path(os.environ.get('LIBOQS_LIBRARY', ROOT / 'build/liboqs/lib/liboqs.a'))
    subprocess.run(['cc', '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
                    '-I' + str(compiler / 'include'), '-I' + str(generated), '-I' + str(mono / 'src'),
                    *map(str, generated.rglob('*.c')), str(mono / 'src/monocypher.c'),
                    str(mono / 'src/optional/monocypher-ed25519.c'), str(oqs_library), *libs,
                    '-lX11', '-l:libcurl.so.4', '-lpthread', '-lm', '-lz', '-o', str(executable)], env=ENV, check=True)
    # A test-only issuer, kept inside this process and its node environment.
    private_der = subprocess.check_output(['openssl', 'genpkey', '-algorithm', 'Ed25519', '-outform', 'DER'])
    public_der = subprocess.check_output(['openssl', 'pkey', '-inform', 'DER', '-pubout', '-outform', 'DER'], input=private_der)
    public = public_der[-32:]
    private = private_der[-32:] + public
    admin = secrets.token_hex(24)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    url = 'http://127.0.0.1:' + str(port)
    node_env = {**ENV, 'DAOCHI_ADDR': '127.0.0.1:' + str(port), 'DAOCHI_DB': str(fixture / 'node.db'),
                'DAOCHI_BASE_URL': url, 'DAOCHI_LAN_DISCOVERY': '0', 'DAOCHI_ALLOW_EPHEMERAL_TOKEN_SECRET': '1',
                'DAOCHI_ADMIN_TOKEN': admin, 'DAOCHI_TOKEN_ISSUER_PUBLIC_KEY_HEX': public.hex(),
                'DAOCHI_TOKEN_ISSUER_PRIVATE_KEY_HEX': private.hex()}
    node_binary = Path(os.environ.get('DAOCHI_BIN', ROOT.parents[1] / 'kryonlabs/daochi/daochi'))
    devices = {name: fixture / name for name in ('first', 'second', 'other')}
    for path in devices.values():
        path.mkdir(mode=0o700)

    def step(device, action):
        subprocess.run([str(executable)], cwd=ROOT, env={**ENV, 'ENTITY_DATA': str(devices[device]),
                       'SHOP_TEST_STEP': action, 'SHOP_TEST_NODE': url}, check=True, timeout=60)

    with (fixture / 'node.log').open('w') as log:
        node = subprocess.Popen([str(node_binary)], cwd=fixture, env=node_env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 25
            while True:
                assert node.poll() is None, 'Private node exited'
                try:
                    urllib.request.urlopen(url + '/api/v1/apps/entity', timeout=2).read()
                    break
                except OSError:
                    assert time.monotonic() < deadline, 'Private node not ready'
                    time.sleep(.1)
            step('first', 'create')
            step('first', 'empty')
            account = next(line.split('=', 1)[1] for line in (devices['first'] / 'account.key').read_text().splitlines()
                           if line.startswith('public_id='))
            payload = json.dumps({'account_id': account, 'app_id': 'entity', 'amount': 6000000,
                                  'source_ref': 'game-shop-test-funding'}).encode()
            request = urllib.request.Request(url + '/api/v1/admin/tokens/manual-credit', data=payload,
                headers={'Content-Type': 'application/json', 'X-Daochi-Admin': admin}, method='POST')
            urllib.request.urlopen(request, timeout=10).read()
            for name in ('account.key', 'entity.json'):
                shutil.copy2(devices['first'] / name, devices['second'] / name)
            step('first', 'buy')
            step('second', 'restored')
            # Retrying from another installation also uses the same three keys.
            step('second', 'buy')
            step('other', 'create')
            step('other', 'empty')
            step('other', 'insufficient')
            with sqlite3.connect(fixture / 'node.db') as db:
                events = db.execute("SELECT amount_delta,source_ref FROM token_ledger WHERE account_id=? AND event_type='debit' ORDER BY ledger_seq", (account,)).fetchall()
                assert [row[0] for row in events] == [-1000000, -2000000, -3000000], events
                assert db.execute('SELECT SUM(amount_delta) FROM token_ledger WHERE account_id=?', (account,)).fetchone()[0] == 0
            (out / 'result.json').write_text(json.dumps({'passed': True, 'purchases': 3,
                'behaviors': ['real authenticated fixed-price debits', 'retries on two devices debit once',
                              'receipt restore on a fresh device', 'unfunded account cannot acquire paid skins',
                              'different accounts have separate ownership']}, indent=2))
            print('Game shop integration local tests: three real private-node debits, cross-device restore, retries and account isolation passed.')
        finally:
            node.terminate()
            node.wait(timeout=10)


if __name__ == '__main__':
    main()
