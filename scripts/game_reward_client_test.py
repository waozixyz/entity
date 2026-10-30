#!/usr/bin/env python3
"""Serial fake-host reward lifecycle: native C, source VM, saved portable VM."""
import os
from pathlib import Path
import subprocess
import shutil

root = Path(__file__).resolve().parents[1]
os.chdir(root)
env = os.environ.copy()
for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS'):
    env.pop(key, None)
compiler = env.get('ZIRAN_BIN', './scripts/ziran.sh')
work = Path('work/reward-client')
subprocess.run(['git', 'check-ignore', '-q', str(work / 'test')], check=True)
work.mkdir(parents=True, exist_ok=True)
for directory in ('native', 'ir', 'wire'):
    shutil.rmtree(work / directory, ignore_errors=True)

def run(*args):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), env=env, check=True)

fixture = 'tests/game_reward_client_test.zi'
entry = 'game_reward_client_test:main'
tool_root = Path(subprocess.check_output([compiler, 'pkg', 'path', 'ziran'], env=env, text=True).strip())
run(compiler, 'build', '--project', '--target=c', '--entry', entry, '-o', work / 'native', fixture)
run(env.get('CC', 'cc'), '-std=c99', '-O2', '-I' + str(tool_root / 'include'),
    '-I' + str(work / 'native'), *sorted((work / 'native').rglob('*.c')), '-o', work / 'game_reward_client_test')
run(work / 'game_reward_client_test')
run(compiler, 'bundle', '--project', '--entry', entry, '-o', work / 'test.zx', fixture)
run(compiler, 'run', work / 'test.zx')
run(compiler, 'ir', '--project', '-o', work / 'ir', fixture)
run(compiler, 'bundle', '--project', '--entry', entry, '--root', work / 'ir', '-o', work / 'test.zx', work / 'ir/game_reward_client_test.zir')
run(compiler, 'run', work / 'test.zx')

# Exercise the dependency's existing reward wire/model fixture with a fake node.
daochi = Path(subprocess.check_output([compiler, 'pkg', 'path', 'daochi_client'], env=env, text=True).strip())
run(compiler, 'build', '--root', daochi, '--module-path', tool_root / 'std',
    '--target=c', '--no-main', '-o', work / 'wire', daochi / 'rewards.zi')
run(env.get('CC', 'cc'), '-std=c11', '-O0', '-ffunction-sections', '-fdata-sections',
    '-Wl,--gc-sections', '-I' + str(tool_root / 'include'), '-I' + str(work / 'wire'),
    daochi / 'tests/rewards_test.c', *sorted((work / 'wire').rglob('*.c')),
    '-o', work / 'reward-wire-test')
run(work / 'reward-wire-test')
