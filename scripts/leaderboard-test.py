#!/usr/bin/env python3
"""Native leaderboard boundaries; --ui also renders the real Profile privately."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
output = root / 'build/leaderboard-test'
output.mkdir(parents=True, exist_ok=True)
shutil.rmtree(output / 'profile', ignore_errors=True)
env = dict(os.environ)
for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
            'SESSION_MANAGER', 'GDK_DISPLAY'):
    env.pop(key, None)
env.update(YUE_DESKTOP_RECOVERY='0', ENTITY_LEADERBOARD_TEST_DATA=str(output / 'profile'))
ziran = str(root / 'scripts/ziran.sh')
subprocess.run(['make', 'build/liboqs/lib/liboqs.a'], cwd=root, env=env, check=True)


def package(name):
    return Path(subprocess.check_output([ziran, 'pkg', 'path', name], cwd=root, text=True).strip())


toolchain, monocypher = package('ziran'), package('monocypher')


def build(entry, directory, ui=False):
    flags = ['--define', 'PLATFORM_DESKTOP'] if ui else []
    subprocess.run([ziran, 'build', '--project', *flags, '--target=c', '--entry', entry + ':main',
                    '-o', str(directory / 'c'), 'tests/' + entry + '.zi'], cwd=root, env=env, check=True)
    command = ['cc', '-std=c11', '-O1', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
               '-I' + str(toolchain / 'include'), '-I' + str(monocypher / 'src'), '-iquote' + str(directory / 'c')]
    command += ['-iquote' + str(path) for path in (directory / 'c').rglob('*') if path.is_dir()]
    command += [str(path) for path in (directory / 'c').rglob('*.c')]
    command += [str(monocypher / 'src/monocypher.c'), str(monocypher / 'src/optional/monocypher-ed25519.c'),
                str(root / 'build/liboqs/lib/liboqs.a')]
    if ui:
        command += [str(root / 'build/ziran/libziran.a')]
        command += subprocess.check_output(['pkg-config', '--libs', 'sdl2', 'cairo', 'freetype2', 'fontconfig',
                                            'pangocairo', 'gtk+-3.0'], text=True).split()
        command += ['-lX11', '-lz']
    binary = directory / 'test'
    command += ['-l:libcurl.so.4', '-lm', '-lpthread', '-o', str(binary)]
    subprocess.run(command, cwd=root, env=env, check=True)
    return binary


subprocess.run([str(build('leaderboard_test', output))], cwd=root, env=env, check=True)
print('PASS: installed-only boards, retained scores, account changes, async friend rankings and validation')
if '--ui' in sys.argv:
    subprocess.run(['make', 'all'], cwd=root, env=env, check=True)
    fixture = build('leaderboard_ui_fixture', root / 'build/leaderboard-ui-fixture', ui=True)
    for binary, extra in [(root / 'build/entity', []), (fixture, ['--leaderboard-populated'])]:
        private = env | dict(ENTITY_PRIVATE_DISPLAY='1', ENTITY_TEST_BINARY=str(binary))
        subprocess.run(['xvfb-run', '-a', sys.executable, 'scripts/native_ui_test.py', '--leaderboard-only', *extra],
                       cwd=root, env=private, check=True)
    private = env | dict(ENTITY_PRIVATE_DISPLAY='1', ENTITY_TEST_BINARY=str(fixture), ENTITY_LEADERBOARD_WURM='1')
    subprocess.run(['xvfb-run', '-a', sys.executable, 'scripts/native_ui_test.py', '--leaderboard-only',
                    '--leaderboard-populated', '--leaderboard-wurm'], cwd=root, env=private, check=True)
