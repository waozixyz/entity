#!/usr/bin/env python3
"""Render synthetic Shovey leaderboard thumbnails through the actual native host.

An optional consumer project tests its immutable Entity dependency before adoption.
No account, provider pump or network operation is used.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project', type=Path, default=ROOT)
parser.add_argument('--compiler', type=Path, required=True)
parser.add_argument('--bundle', type=Path, required=True)
args = parser.parse_args()
project = args.project.resolve()
work = ROOT / 'work/profile-thumbnail-test'
subprocess.run(['git', 'check-ignore', '-q', str(work)], cwd=ROOT, check=True)
work.mkdir(parents=True, exist_ok=True)
env = {k: v for k, v in os.environ.items() if k not in
       ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER', 'GDK_DISPLAY',
        'LISTEN_PID', 'LISTEN_FDS', 'LISTEN_FDNAMES', 'NOTIFY_SOCKET')}
env.update(YUE_DESKTOP_RECOVERY='0', SDL_AUDIODRIVER='dummy', APP_NO_TRAY='1',
           ENTITY_DATA=str(work / 'profile'), XDG_DATA_HOME=str(work / 'xdg'),
           MAKEFLAGS='-j1', CMAKE_BUILD_PARALLEL_LEVEL='1', ZIRAN_PAR_THREADS='1', ZIRAN_BUILD_JOBS='1')
shutil.rmtree(work / 'profile', ignore_errors=True)
shutil.rmtree(work / 'xdg', ignore_errors=True)
flags = [] if (project / 'ziran.local.toml').exists() else ['--locked']

def package(name):
    return Path(subprocess.check_output([str(args.compiler), 'pkg', 'path', name, *flags],
                                       cwd=project, text=True, env=env).strip())

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

toolchain = package('ziran')
kryon = package('kryon')
if project == ROOT:
    # The artifact API takes a dependency alias. Use the same synthetic
    # consumer-manifest pattern as native_artifacts.py, never source copies.
    consumer = work / 'consumer'
    consumer.mkdir(exist_ok=True)
    def head(path):
        return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    (consumer / 'ziran.toml').write_text('[package]\nname="ProfileThumbnailFixture"\nmodule_roots=["src"]\n'
        '[toolchain]\ngit="https://github.com/ziranlang/ziran.git"\nref=' + json.dumps(head(toolchain)) + '\n'
        '[dependencies.entity]\ngit="https://github.com/waozixyz/entity.git"\nref=' + json.dumps(head(ROOT)) + '\n'
        '[dependencies.kryon]\ngit="https://github.com/kryonlabs/kryon.git"\nref=' + json.dumps(head(kryon)) + '\n')
    overrides = {}
    local = ROOT / 'ziran.local.toml'
    if local.exists():
        overrides = {name: str((ROOT / path).resolve()) for name, path in
                     tomllib.loads(local.read_text()).get('overrides', {}).items()}
    overrides.update(entity=str(ROOT), kryon=str(kryon), ziran=str(toolchain))
    (consumer / 'ziran.local.toml').write_text('[overrides]\n' + ''.join(
        name + '=' + json.dumps(path) + '\n' for name, path in overrides.items()))
    subprocess.run([str(args.compiler), 'lock'], cwd=consumer, env=env, check=True)
    project = consumer
    flags = []
artifacts = load('ziran_artifacts', toolchain / 'scripts/ziran_artifacts.py')
renderer_api = load('renderer_artifact', kryon / 'scripts/renderer_artifact.py')
source = (ROOT / 'tests/profile_thumbnail_test.zi').read_text()
if project != ROOT:
    for name in ('native_host', 'native_files', 'leaderboard_model', 'model'):
        source = source.replace('#import "' + name + '"', '#import "entity/' + name + '"')
source = source.replace('BUNDLE', json.dumps(str(args.bundle.resolve()))).replace(
    'PROFILE', json.dumps(str(work / 'profile')))
fixture_folder = project / 'src' if project == work / 'consumer' else work
fixture_folder.mkdir(parents=True, exist_ok=True)
fixture = fixture_folder / 'profile_thumbnail.zi'
fixture.write_text(source)
generated = work / 'c'
shutil.rmtree(generated, ignore_errors=True)
module_path = [] if fixture_folder == project / 'src' else ['--module-path', str(fixture_folder)]
subprocess.run([str(args.compiler), 'build', '--project', *flags, '--target=c', '--define', 'PLATFORM_DESKTOP',
                *module_path, '--entry', 'profile_thumbnail:main', '-o', str(generated), str(fixture)],
               cwd=project, env=env, check=True)
profile = artifacts.request('entity:native-profile',
    'linux-x86_64-gnu', project=project, ziran=args.compiler, env=env)
renderer = renderer_api.renderer_metadata(artifacts.request('kryon:renderer-desktop',
    'linux-x86_64-gnu', project=project, ziran=args.compiler, env=env))
sources = sorted(generated.rglob('*.c'))
subprocess.run(['cc', '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections',
    '-I' + str(toolchain / 'include'),
    *['-iquote' + str(p) for p in sorted({generated, *(p.parent for p in sources)})],
    *renderer['compile_flags'], *['-I' + p for p in renderer['include_directories']],
    *map(str, sources), '-Wl,--gc-sections', *renderer_api.renderer_link(renderer),
    *profile.link_flags(include_archives=False), '-o', str(work / 'test')], cwd=project, env=env, check=True)
subprocess.run(['xvfb-run', '-a', '-n', '450', '-e', str(work / 'xvfb.log'),
                '-s', '-screen 0 480x820x24', str(work / 'test')],
               cwd=project, env=env, check=True)
print('Profile thumbnail local test: eight extracted/allowed Shovey portraits, rejected unsafe paths and three real hosted frames passed')
