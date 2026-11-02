#!/usr/bin/env python3
"""Real Dew debits, retry deduplication and cross-device restore on a private node."""
import json
import os
from pathlib import Path
import secrets
import re
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
    out = ROOT / 'work/game-shop-integration'
    out.mkdir(parents=True, exist_ok=True)
    fixture = Path(tempfile.mkdtemp(prefix='fixture-', dir=out))
    fixture.chmod(0o700)
    compiler, kryon, daochi, crypto, oqs, mono = (package(name) for name in
        ('ziran', 'kryon', 'daochi_client', 'crypto', 'oqs', 'monocypher'))
    generated = out / 'generated'
    # This disposable output also held the previous fixture's module path.
    shutil.rmtree(generated, ignore_errors=True)
    paths = ['--module-path', str(ROOT / 'src'), '--module-path', str(compiler / 'std'),
             '--module-path', 'kryon=' + str(kryon / 'src/backend'),
             '--module-path', str(kryon / 'src/backend'),
             '--module-path', 'kryon=' + str(kryon / 'src/ui'), '--module-path', str(kryon / 'src/ui'),
             '--module-path', 'daochi_client=' + str(daochi), '--module-path', str(daochi),
             '--module-path', 'crypto=' + str(crypto / 'src'), '--module-path', 'oqs=' + str(oqs / 'src')]
    model = out / 'model'
    subprocess.run(['ziran', 'build', '--root', str(ROOT), *paths, '--target=c', '--entry',
                    'game_shop_test:main', '-o', str(model), 'tests/game_shop_test.zi'],
                   cwd=ROOT, env=ENV, check=True)
    subprocess.run(['cc', '-std=c11', '-O2', '-I' + str(compiler / 'include'), '-I' + str(model),
                    *map(str, model.rglob('*.c')), '-lm', '-o', str(model / 'test')], env=ENV, check=True)
    subprocess.run([str(model / 'test')], env=ENV, check=True)
    browser = (ROOT / 'src/browser_host.zi').read_text()
    begin = browser.index('BrowserServices ::')
    end = re.search(r'^\w+ ::', browser[begin + 18:], re.M)
    router = browser[begin:begin + 18 + end.start()]
    fixture_source = out / 'game_shop_integration.zi'
    fixture_source.write_text((ROOT / 'tests/game_shop_integration.zi').read_text() + '\n' + router + r"""
HostValue :: struct { text: string }
browser_mini: bool;
browser_profile: bool;
PUBLICATIONS_READ_SERVICE :: "publications.read";
ENTITY_RECORDS_SERVICE :: "entity.records";
ENTITY_DEW_SERVICE :: "entity.dew";
TextFromCString :: (value: *u8) -> string { return "AppServiceHost" }
AppArgumentText :: (value: HostValue) -> string { return value.text }
EntityHostText :: (value: string) -> HostValue { return HostValue.{value} }
PublicationsReadAnswer :: (request: string) -> string { return "" }
EntityRecordsAnswer :: (request: string) -> string { return "" }
EntityHostProfileRequest :: (request: string) -> bool { return false }
BundleAppServices :: (context: *void, module: *u8, function: *u8, arguments: *HostValue, count: s32, result: *HostValue) -> s32 { return 0 }
""")
    subprocess.run(['ziran', 'build', '--root', str(ROOT), *paths, '--target=c', '--entry',
                    'game_shop_integration:Check', '-o', str(generated), str(fixture_source)],
                   cwd=ROOT, env=ENV, check=True)
    (generated / 'main.c').write_text('#include "work/game-shop-integration/game_shop_integration.h"\n#include <stdio.h>\n#include <unistd.h>\n'
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
                'DAOCHI_SHOVEY_ISLAND_LAUNCH_AT': str(int(time.time()) - 86400),
                'DAOCHI_ADMIN_TOKEN': admin, 'DAOCHI_TOKEN_ISSUER_PUBLIC_KEY_HEX': public.hex(),
                'DAOCHI_TOKEN_ISSUER_PRIVATE_KEY_HEX': private.hex()}
    node_binary = Path(os.environ.get('DAOCHI_BIN', ROOT.parents[2] / 'kryonlabs/daochi/daochi'))
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
            step('other', 'local')
            step('first', 'grant_unowned')
            account = next(line.split('=', 1)[1] for line in (devices['first'] / 'account.key').read_text().splitlines()
                           if line.startswith('public_id='))
            payload = json.dumps({'account_id': account, 'app_id': 'entity', 'amount': 296000000,
                                  'source_ref': 'game-shop-test-funding'}).encode()
            request = urllib.request.Request(url + '/api/v1/admin/tokens/manual-credit', data=payload,
                headers={'Content-Type': 'application/json', 'X-Daochi-Admin': admin}, method='POST')
            urllib.request.urlopen(request, timeout=10).read()
            for name in ('account.key', 'entity.json'):
                shutil.copy2(devices['first'] / name, devices['second'] / name)
            step('first', 'buy')
            step('first', 'grant_owned')
            step('second', 'restored')
            # Retrying from another installation also uses the same keys.
            step('second', 'buy')
            step('first', 'holiday_early')
            step('first', 'holiday_claim')
            step('first', 'holiday_after')
            step('other', 'create')
            step('other', 'empty')
            step('other', 'insufficient')
            step('other', 'grant_unowned')
            with sqlite3.connect(fixture / 'node.db') as db:
                events = db.execute("SELECT amount_delta,source_ref FROM token_ledger WHERE account_id=? AND event_type='debit' ORDER BY ledger_seq", (account,)).fetchall()
                assert [row[0] for row in events] == [-10000000, -20000000, -30000000, -50000000, -20000000, -10000000, -20000000, -30000000, -10000000, -30000000, -5000000, -10000000, -51000000], events
                assert [row[1] for row in events[5:]] == [
                    'choano.pearl:decoration-choano-pearl-v1', 'choano.flower:decoration-choano-flower-v1',
                    'choano.wizard:decoration-choano-wizard-v1', 'shovey.night:skin-shovey-night-v1',
                    'shovey.crystal:skin-shovey-crystal-v1', 'wurm.coins:coins-wurm-2-1-v1',
                    'shovey.coins:coins-shovey-3-1-v1', 'shovey.island'], events
                assert db.execute('SELECT SUM(amount_delta) FROM token_ledger WHERE account_id=?', (account,)).fetchone()[0] == 0
            (out / 'result.json').write_text(json.dumps({'passed': True, 'purchases': 13,
                'behaviors': ['real authenticated fixed-price debits', 'retries on two devices debit once',
                              'receipt restore on a fresh device', 'separate Wurm and Shovey coin packs',
                              'unfunded account cannot acquire paid skins', 'different accounts have separate ownership',
                              'owned grants through production browser router and native service',
                              'unowned spoofed flag refused without debit',
                              'grant expiry, malformed product/expiry, offline and HTTP errors',
                              'late cancelled grant response cannot cross account switch']}, indent=2))
            print('Game shop integration local tests: thirteen private-node debits including Shovey Island launch-sale unlock, separate coin packs, cross-device restore, retries, account isolation December claim persistence, browser/native grants, expiry, errors and late account-switch isolation passed.')
        finally:
            node.terminate()
            node.wait(timeout=10)


if __name__ == '__main__':
    main()
