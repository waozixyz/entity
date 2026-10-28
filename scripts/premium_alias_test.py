#!/usr/bin/env python3
"""Purchase with throwaway accounts on a private node, including a lost local save."""
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ENV = {key: value for key, value in os.environ.items() if key not in
       ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER')}
ZIRAN = os.environ.get('ZIRAN_BIN', 'ziran')


def package(name):
    return Path(os.environ.get(name.upper() + '_DIR') or subprocess.check_output(
        [ZIRAN, 'pkg', 'path', name], cwd=ROOT, text=True).strip())


std = Path(os.environ.get('ZIRAN_ROOT') or package('ziran'))
kryon, client, oqs, crypto, monocypher = map(package, ('kryon', 'daochi_client', 'oqs', 'crypto', 'monocypher'))
output = ROOT / 'build/premium-alias-node-test'
output.mkdir(parents=True, exist_ok=True)
generated = output / 'generated'
paths = ['--module-path', str(ROOT / 'src'), '--module-path', str(std / 'std'),
         '--module-path', f'kryon={kryon / "src/backend"}', '--module-path', str(kryon / 'src/backend'),
         '--module-path', str(kryon / 'src/ui'), '--module-path', f'daochi_client={client}',
         '--module-path', str(client), '--module-path', f'oqs={oqs / "src"}',
         '--module-path', f'crypto={crypto / "src"}']
subprocess.run([ZIRAN, 'build', '--target=c', '--root', str(ROOT), *paths,
                '--entry', 'premium_alias_node_test:PremiumAliasCheck', '-o', str(generated),
                str(ROOT / 'tests/premium_alias_node_test.zi')], check=True, env=ENV)
(generated / 'main.c').write_text(
    '#include "tests/premium_alias_node_test.h"\n#include <stdio.h>\n#include <unistd.h>\n'
    'int main(void) { int result = PremiumAliasCheck(); '
    'if (result) fprintf(stderr, "check %d failed\\n", result); fflush(NULL); _exit(result != 0); }\n')
executable = output / 'test'
flags = subprocess.check_output(['pkg-config', '--libs', 'gtk+-3.0'], text=True).split()
subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections',
                '-Wl,--gc-sections', f'-I{std / "include"}', f'-I{generated}', f'-I{monocypher / "src"}',
                *map(str, generated.rglob('*.c')), str(monocypher / 'src/monocypher.c'),
                str(monocypher / 'src/optional/monocypher-ed25519.c'), os.environ['LIBOQS_LIBRARY'],
                *flags, '-lX11', '-l:libcurl.so.4', '-lpthread', '-lm', '-lz', '-o', str(executable)],
               check=True, env=ENV)
node_binary = Path(os.environ.get('DAOCHI_BIN', ROOT.parents[2] / 'kryonlabs/daochi/daochi'))
assert node_binary.is_file(), 'Build the canonical Daochi executable first'
work = ROOT / 'work'
work.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='premium-alias-', dir=work) as temporary:
    private = Path(temporary)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    address = f'http://127.0.0.1:{port}'
    admin = secrets.token_hex(32)
    node_env = dict(ENV, DAOCHI_ADDR=f'127.0.0.1:{port}', DAOCHI_DB=str(private / 'node.db'),
                    DAOCHI_BASE_URL=address, DAOCHI_LAN_DISCOVERY='0',
                    DAOCHI_ALLOW_EPHEMERAL_TOKEN_SECRET='1', DAOCHI_PREMIUM_ALIASES_ENABLED='true',
                    DAOCHI_TOKEN_ISSUER_PRIVATE_KEY_HEX=secrets.token_hex(32), DAOCHI_ADMIN_TOKEN=admin)
    with (private / 'node.log').open('w') as log:
        node = subprocess.Popen([str(node_binary)], cwd=private, env=node_env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            while True:
                assert node.poll() is None, 'Private node exited'
                try:
                    urllib.request.urlopen(address + '/api/v1/apps/entity', timeout=1).close()
                    break
                except OSError:
                    assert time.monotonic() < deadline, 'Private node did not become ready'
                    time.sleep(.1)

            def step(device, name):
                result = subprocess.run([str(executable)], env=dict(ENV, ENTITY_DATA=str(private / device),
                                        ALIAS_STEP=name, ALIAS_NODE=address), capture_output=True, text=True, timeout=90)
                assert result.returncode == 0, f'{device}/{name}: {result.stderr[-2000:]}'

            for device in ('first', 'second'):
                step(device, 'create')
            step('first', 'quote')
            step('first', 'insufficient')
            account = json.loads((private / 'first/entity.json').read_text())['owner_id']
            request = urllib.request.Request(address + '/api/v1/admin/tokens/manual-credit',
                data=json.dumps(dict(account_id=account, app_id='entity', amount=200000000,
                                     source_ref='premium-alias-fixture')).encode(),
                headers={'Content-Type': 'application/json', 'X-Daochi-Admin': admin})
            with urllib.request.urlopen(request, timeout=10) as response:
                assert response.status == 200
            step('first', 'buy')
            step('first', 'owned')
            step('second', 'taken')
            # The node debits successfully but the device cannot finish its
            # local save. Restart and retry the durable request at zero balance.
            step('first', 'uncertain')
            with sqlite3.connect(private / 'node.db') as db:
                before = db.execute('SELECT count(*),sum(amount_delta) FROM token_ledger WHERE account_id=?',
                                    (account,)).fetchone()
                assert before == (3, 0), before
            step('first', 'retry')
            with sqlite3.connect(private / 'node.db') as db:
                assert db.execute('SELECT count(*),sum(amount_delta) FROM token_ledger WHERE account_id=?',
                                  (account,)).fetchone() == before, 'Retry charged twice'
            print('Private-node local tests passed: quote, no implicit debit, insufficient funds, purchase, taken/owned names, restart retry without a second debit.')
        finally:
            node.terminate()
            node.wait(timeout=10)
