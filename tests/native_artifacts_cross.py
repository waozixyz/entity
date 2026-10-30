"""Compile and link an artifact consumer for an explicitly supplied cross SDK.

CC=/absolute/emcc python3 tests/native_artifacts_cross.py emscripten-wasm32-emscripten
CC=/absolute/aarch64-linux-android24-clang python3 tests/native_artifacts_cross.py android-aarch64-bionic --ndk /absolute/ndk
No generated executable is run. Run native_artifacts.py first for fixture manifests.
"""
import argparse
from pathlib import Path
import shutil
from native_artifacts import ROOT, WORK, ENV, run, descriptor, link_flags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform')
    parser.add_argument('--ndk', default='')
    args = parser.parse_args()
    cc = ENV.get('CC', '')
    assert Path(cc).is_absolute(), 'CC must be an absolute cross compiler executable'
    app = WORK / args.platform
    app.mkdir(exist_ok=True)
    (app / 'src').mkdir(exist_ok=True)
    for name in ('ziran.toml', 'ziran.local.toml', 'ziran.lock'):
        shutil.copyfile(WORK / 'one' / name, app / name)
    if args.ndk:
        with (app / 'ziran.toml').open('a') as stream:
            stream.write(f'[tool.entity]\nndk="{args.ndk}"\n')
    compiler = Path(run([str(ROOT / 'scripts/ziran.sh'), 'pkg', 'path', 'ziran']))
    profile = descriptor(run([compiler / 'build/bin/ziran', 'pkg', 'artifact',
                              'entity:native-profile', '--platform', args.platform], app))
    dependencies = dict(line.split('\t', 1) for line in (profile.parent / 'dependencies.tsv').read_text().splitlines())
    crypto = descriptor(dependencies['self:native-crypto'])
    headers = app / 'headers'
    shutil.rmtree(headers, ignore_errors=True)
    headers.mkdir(exist_ok=True)
    run(['tar', '-xf', profile.parent / 'headers.tar', '-C', headers])
    shutil.copyfile(WORK / 'one/consumer.c', app / 'consumer.c')
    output = app / ('consumer.js' if args.platform.startswith('emscripten') else 'consumer')
    flags = link_flags(profile.parent / 'link.txt', crypto.parent / 'link.txt')
    for line in (profile.parent / 'link.txt').read_text().splitlines():
        kind, value = line.split('\t', 1)
        if kind == 'js-library':
            flags += ['--js-library', str(profile.parent / value)]
    run([cc, '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections',
         '-Wl,--gc-sections', '-I', headers, '-I', headers / 'ziran', app / 'consumer.c',
         profile.parent / 'libentity.a', crypto.parent / 'libmonocypher.a',
         crypto.parent / 'liboqs.a', crypto.parent / 'libziran.a', *flags, '-o', output])
    binary = output.with_suffix('.wasm') if output.suffix == '.js' else output
    with binary.open('rb') as stream:
        magic = stream.read(4)
    assert magic == (b'\0asm' if output.suffix == '.js' else b'\x7fELF')
    (app / 'adoption.txt').write_text(f'{profile}\n{crypto}\n')
    print(f'PASS: {args.platform} descriptors verified; actual cross consumer compiled and linked; executable not run')


if __name__ == '__main__':
    main()
