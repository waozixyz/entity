#!/usr/bin/env python3
"""Bounded native tests of installed boards and account-isolated scores."""
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
output = root / 'build/leaderboard-test'
output.mkdir(parents=True, exist_ok=True)
shutil.rmtree(output / 'profile', ignore_errors=True)
env = dict(os.environ)
for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS'):
    env.pop(key, None)
env['YUE_DESKTOP_RECOVERY'] = '0'
env['ENTITY_LEADERBOARD_TEST_DATA'] = str(output / 'profile')
ziran = str(root / 'scripts/ziran.sh')
subprocess.run([ziran, 'build', '--project', '--target=c', '--entry', 'leaderboard_test:main',
                '-o', str(output / 'c'), 'tests/leaderboard_test.zi'], cwd=root, env=env, check=True)
toolchain = Path(subprocess.check_output([ziran, 'pkg', 'path', 'ziran'], cwd=root, text=True).strip())
command = ['cc', '-std=c11', '-O1', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
           '-I' + str(toolchain / 'include')]
command += ['-iquote' + str(path) for path in (output / 'c').rglob('*') if path.is_dir()]
command += [str(path) for path in (output / 'c').rglob('*.c')]
command += ['-l:libcurl.so.4', '-lm', '-lpthread', '-o', str(output / 'test')]
subprocess.run(command, cwd=root, env=env, check=True)
subprocess.run([str(output / 'test')], cwd=root, env=env, check=True)
print('PASS: installed-only boards, retained scores, account changes, validation and display encoding')
