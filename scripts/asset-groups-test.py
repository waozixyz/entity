#!/usr/bin/env python3
"""Verify complete/profile groups and actual-bundle availability policy."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('assets', ROOT / 'scripts/stage-assets.py')
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--compiler', type=Path, required=True)
parser.add_argument('--toolchain', type=Path, required=True)
parser.add_argument('--runtime', type=Path, required=True)
args = parser.parse_args()
output = ROOT / 'work/asset-groups-test'
output.mkdir(parents=True, exist_ok=True)
env = {k: v for k, v in os.environ.items() if k not in
       ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER')}
groups = json.loads((ROOT / 'asset-groups.json').read_text())
for unsafe in ('/etc/passwd', 'assets/entity/../secret', 'assets/entity/sub/../../secret'):
    try:
        assets.declared_assets({'bad': [unsafe]}, ['bad'])
    except ValueError:
        pass
    else:
        raise AssertionError('Unsafe declaration accepted')
source = output / 'fixture.zi'
source.write_text('Main :: () -> s32 { return 0 }\n')
for name, selected in [('profile', ['profile']), ('complete', list(groups))]:
    stage = output / name
    names = assets.stage(stage, selected)
    actual = {str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file()}
    assert actual == names
    for path in actual:
        assert (stage / path).read_bytes() == (ROOT / path).read_bytes()
    subprocess.run([str(args.compiler), 'bundle', '--root', str(output), '--entry', 'fixture:Main',
                    '--asset-dir', 'assets=' + str(stage / 'assets'), '-o', str(output / (name + '.zx')),
                    str(source)], cwd=ROOT, env=env, check=True)
generated = output / 'c'
subprocess.run([str(args.compiler), 'build', '--target=c', '--root', str(ROOT),
                '--module-path', str(ROOT / 'src'), '--module-path', str(args.toolchain / 'std'),
                '--entry', 'asset_presence_test:Check', '-o', str(generated),
                str(ROOT / 'tests/asset_presence_test.zi')], cwd=ROOT, env=env, check=True)
(generated / 'main.c').write_text('''#include "ziran_host.h"
#include "tests/asset_presence_test.h"
#include <assert.h>
int main(int argc, char **argv) {
 assert(argc == 3);
 for (int i = 1; i < 3; ++i) {
  Bundle *bundle = BundleOpen(argv[i]); assert(bundle);
  assert(Check(bundle, i == 2) == 0); BundleClose(bundle);
 }
 return 0;
}
''')
command = ['cc', '-std=c11', '-O1', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
           '-I' + str(args.toolchain / 'include'), '-I' + str(generated)]
command += ['-I' + str(p) for p in generated.rglob('*') if p.is_dir()]
command += [str(p) for p in generated.rglob('*.c')]
command += [str(args.runtime), '-lm', '-lpthread', '-o', str(output / 'test')]
subprocess.run(command, cwd=ROOT, env=env, check=True)
subprocess.run([str(output / 'test'), str(output / 'profile.zx'), str(output / 'complete.zx')], env=env, check=True)
print('Entity profile/full asset groups and current-bundle availability, missing/unsafe paths passed')
