#!/usr/bin/env python3
"""Link a browser app with the same Entity account provider as native hosts.

Bundles given with --linked, and the bundles embedded in them, run as
compiled code in the page rather than on the portable VM: Ziran writes each
program as C (zi2zx native-c) and the page links it, registered under the
identity of those exact bundle bytes. Any other bundle still runs on the VM.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # A host that draws its own pages, such as dew.waozi.xyz, has no bundle.
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--entry', default='runtime:main')
    parser.add_argument('--source', default='src/web/runtime.zi')
    parser.add_argument('--linked', type=Path, action='append', default=[],
                        help='a bundle the page runs as compiled code')
    args = parser.parse_args()
    project = Path.cwd()
    ziran = os.environ.get('ZIRAN', 'ziran')
    locked = [] if (project / 'ziran.local.toml').exists() else ['--locked']

    def package(name):
        return Path(subprocess.check_output([ziran, 'pkg', 'path', name, *locked], text=True).strip())

    toolchain = package('ziran')
    kryon = package('kryon')
    work = project / 'build/profile-web'
    generated = work / 'generated'
    if generated.exists():
        shutil.rmtree(generated)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    emcc = os.environ.get('EMCC') or str(Path.home() / 'emsdk/upstream/emscripten/emcc')
    if not Path(emcc).exists():
        emcc = 'emcc'
    emar = str(Path(emcc).with_name('emar')) if '/' in emcc else 'emar'
    emcmake = str(Path(emcc).with_name('emcmake')) if '/' in emcc else 'emcmake'
    env = {**os.environ, 'EM_CACHE': str(work / 'emscripten-cache')}
    subprocess.run([ziran, 'build', '--project', *locked, '--target=c', '--define', 'PLATFORM_WEB',
                    '--define', 'BUNDLE_NATIVE_RENDERER', '--entry', args.entry,
                    '-o', str(generated), args.source], check=True, env=env)
    runtime = work / 'runtime/libziran.a'
    subprocess.run(['make', '-C', str(toolchain), 'BOOTSTRAP=1', 'BUILD_DIR=' + str(runtime.parent),
                    'CC=' + emcc, 'AR=' + emar, 'OBJCOPY=true', 'CFLAGS=-O2', str(runtime)], check=True, env=env)
    oqs_source = package('liboqs')
    oqs = work / ('oqs-' + oqs_source.name)
    subprocess.run([emcmake, 'cmake', '-S', str(oqs_source), '-B', str(oqs),
                    '-DCMAKE_BUILD_TYPE=MinSizeRel', '-DBUILD_SHARED_LIBS=OFF', '-DOQS_BUILD_ONLY_LIB=ON',
                    '-DOQS_USE_OPENSSL=OFF', '-DOQS_DIST_BUILD=OFF', '-DOQS_OPT_TARGET=generic',
                    '-DOQS_MINIMAL_BUILD=SIG_ml_dsa_44'], check=True, env=env)
    subprocess.run(['cmake', '--build', str(oqs), '--target', 'oqs', '-j2'], check=True, env=env)
    linked = []
    if args.linked:
        programs, objects = work / 'linked', work / 'linked-objects'
        for folder in (programs, objects):
            if folder.exists():
                shutil.rmtree(folder)
        zi2zx = os.environ.get('ZI2ZX') or str(toolchain / 'build/bin/zi2zx')
        subprocess.run([zi2zx, 'native-c', '--embedded', '-o', str(programs),
                        *[str(bundle.resolve()) for bundle in args.linked]], check=True, env=env)
        emnm = str(Path(emcc).with_name('emnm')) if '/' in emcc else 'emnm'
        compiled = subprocess.run([sys.executable, str(toolchain / 'scripts/linked-zx.py'), str(programs),
                                   '--output', str(objects), '--cc', emcc, '--nm', emnm,
                                   '--cflags=-O2 -ffunction-sections -fdata-sections'],
                                  check=True, env=env, capture_output=True, text=True)
        sys.stderr.write(compiled.stderr)
        linked = compiled.stdout.split()
    # Package the game separately so large bundles do not inflate the Wasm file.
    # Emscripten does not allow --embed-file and --preload-file in one invocation.
    packager = Path(shutil.which(emcc) or emcc).resolve().parent / 'tools/file_packager'
    preload = []
    if args.bundle:
        script = work / 'game-preload.js'
        subprocess.run([str(packager), str(output.with_suffix('.data')), '--preload',
                        str(args.bundle.resolve()) + '@/app.zx', '--js-output=' + str(script),
                        '--no-node'], check=True, env=env)
        preload = ['--pre-js', str(script)]
    subprocess.run([emcc, '-O2', '-ffunction-sections', '-fdata-sections',
                    '-I' + str(toolchain / 'include'), '-iquote', str(generated),
                    *[item for path in generated.rglob('*') if path.is_dir() for item in ('-iquote', str(path))],
                    *map(str, generated.rglob('*.c')), *linked, str(runtime),
                    '-I' + str(package('monocypher') / 'src'), str(package('monocypher') / 'src/monocypher.c'),
                    str(package('monocypher') / 'src/optional/monocypher-ed25519.c'), str(oqs / 'lib/liboqs.a'),
                    '--js-library', str(toolchain / 'web/ziran_web.js'), '-lidbfs.js',
                    '--embed-file', str(kryon / 'assets/fonts/LiberationSans-Regular.ttf') + '@/kryon-font.ttf',
                    *preload,
                    '--embed-file', str(args.profile.resolve()) + '@/entity.zx',
                    '-sASYNCIFY', '-sALLOW_MEMORY_GROWTH=1', '-sFORCE_FILESYSTEM=1',
                    '-sSTACK_SIZE=16777216', '-sASYNCIFY_STACK_SIZE=1048576', '-sENVIRONMENT=web',
                    '-sEXPORTED_RUNTIME_METHODS=FS',
                    '-sEXPORTED_FUNCTIONS=_main',
                    '--shell-file', str(kryon / 'mk/zx-shell.html'), '-o', str(output)], check=True, env=env)


if __name__ == '__main__':
    main()
