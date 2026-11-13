#!/usr/bin/env python3
"""Build the real compiled app/provider graph, then drive its browser frame loop."""
import os
import json
import re
from pathlib import Path
import subprocess
import shutil

root = Path(__file__).resolve().parents[1]
work = root / 'work/canvas-profile-host-test'
subprocess.run(['git', 'check-ignore', '-q', str(work)], cwd=root, check=True)
work.mkdir(parents=True, exist_ok=True)
# Chromium's SingletonSocket lives under TMPDIR and must fit sockaddr_un.
# The compiler scratch path passed to make is longer than that socket permits.
browser_tmp = root / 'work/canvas-tmp'
subprocess.run(['git', 'check-ignore', '-q', str(browser_tmp)], cwd=root, check=True)
browser_tmp.mkdir(exist_ok=True)
env = dict(os.environ)
for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER',
            'GDK_DISPLAY', 'DESKTOP_SESSION', 'XDG_SESSION_ID', 'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP'):
    env.pop(key, None)
bun = env.get('BUN') or shutil.which('bun') or str(Path.home() / '.bun/bin/bun')
env.update(EM_NODE_JS=bun, JS_RUNTIME=bun, YUE_DESKTOP_RECOVERY='0',
           ZIRAN_JOBS='1', EMCC_CORES='1', CMAKE_BUILD_PARALLEL_LEVEL='1')
# Consumer commands resolve the consumer manifest; scripts/ziran.sh always
# enters Entity's root, so the cwd-aware front end runs them, including build-web.
ziran = 'ziran'
env['ZIRAN'] = ziran
consumer = work / 'consumer'
consumer.mkdir(exist_ok=True)
(consumer / 'src').mkdir(exist_ok=True)
# Only the explicit test fixture is staged; all product code is imported
# from the canonical package overrides.
shutil.copyfile(root / 'tests/canvas_profile_app.zi', consumer / 'src/canvas_profile_app.zi')
# Deliberately shares a name with daochi_client's private rewards module.
# The app calls this implementation while the real provider uses its own.
(consumer / 'src/rewards.zi').write_text('''CanvasRewardsFixture :: () -> string {
    return "consumer rewards"
}
''')
(consumer / 'src/canvas_bare_entry.zi').write_text('''using Runner :: #import "kryon/canvas_app_run";
#import "canvas_profile_app"
#program_export
main :: () -> s32 { return Runner.CanvasAppMainLoop(false) }
''')
locked = json.loads((root / 'ziran.lock').read_text())
tool_ref = locked['toolchain']['commit']
packages = {package['id']: package for package in locked['packages']}
kryon_ref = packages[locked['root']['dependencies']['kryon']]['commit']
(consumer / 'ziran.toml').write_text(f'''[package]
name = "canvas_profile_consumer"
module_roots = ["src"]
[toolchain]
git = "https://github.com/ziranlang/ziran.git"
ref = "{tool_ref}"
[dependencies.entity]
git = "https://github.com/waozixyz/entity.git"
ref = "master"
[dependencies.kryon]
git = "https://github.com/kryonlabs/kryon.git"
ref = "{kryon_ref}"
''')
overrides = (root / 'ziran.local.toml').read_text() if (root / 'ziran.local.toml').exists() else '[overrides]\n'
(consumer / 'ziran.local.toml').write_text(overrides + f'entity = "{root}"\n')
subprocess.run([ziran, 'lock'], cwd=consumer, env=env, check=True)
def build_and_run(entry=None, mode=None):
    command = ['python3', str(root / 'scripts/build-web.py'), '--profile', str(root / 'build/entity.zx'),
               '--output', str(work / 'index.html'), '--canvas-app', 'canvas_profile_app:Main',
               '--source', 'src/canvas_bare_entry.zi' if mode == 'bare' else 'src/canvas_profile_app.zi']
    if entry:
        command += ['--entry', entry]
    subprocess.run(command, cwd=consumer, env=env, check=True)
    module_map = (consumer / 'build/.ziran/module-map.tsv').read_text().splitlines()
    rewards = [line.split('\t') for line in module_map if line.startswith('M\t')
               and line.split('\t')[2] == 'rewards']
    assert any(row[1] == 'root' and Path(row[3]) == consumer / 'src/rewards.zi'
               for row in rewards), 'Consumer rewards is missing from the package graph'
    assert any(row[1] != 'root' for row in rewards), 'Provider rewards is missing from the package graph'
    generated = consumer / 'build/profile-web/generated'
    assert (generated / 'rewards.c').is_file(), 'Consumer rewards implementation was not compiled'
    if mode != 'bare':
        assert list(generated.glob('p*_rewards.c')), 'Provider rewards implementation was not compiled'
    html = work / 'index.html'
    shell, count = re.subn(r'var Module\s*=\s*\{', '''var Module = {
          preRun: [function() { ENV.KRYON_TEST_DRIVER = '/driver'; Module.FS.mkdir('/driver'); }],''', html.read_text(), count=1)
    assert count == 1, 'Missing Emscripten Module initializer'
    html.write_text(shell)
    subprocess.run(['timeout', '--kill-after=10s', '120s', 'xvfb-run', '-a', bun,
                    str(root / 'scripts/canvas-profile-host-browser.mjs'), str(html), *([mode] if mode else [])],
                   cwd=root, env={**env, 'TMPDIR': str(browser_tmp)}, check=True)

build_and_run('canvas_bare_entry:main', 'bare')
build_and_run()
print('Consumer package namespace local test passed: app and provider rewards retain distinct identities')
