"""Real cross compile/link fixtures; generated executables are never run.

Run native_artifacts.py first. Supply absolute CC and matching AR.
Android: --ndk /absolute/ndk [--android-api 21|23|24] (default24).
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import shlex
from native_artifacts import ROOT, WORK, ENV, run, descriptor, link_flags, hash_file


def rejected_before_compile(command, app, reason):
    result = subprocess.run(list(map(str, command)), cwd=app, env=ENV,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode and reason in result.stderr, result.stderr[-2000:]
    assert 'Building C object' not in result.stderr and 'Configuring done' not in result.stderr, result.stderr[-2000:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform')
    parser.add_argument('--ndk', default='')
    parser.add_argument('--android-api', default='24')
    parser.add_argument('--edition', default='direct')
    parser.add_argument('--dirty', action='store_true')
    parser.add_argument('--crypto-only', action='store_true', help='independent support archive compile/link diagnostic')
    args = parser.parse_args()
    cc = ENV.get('CC', '')
    assert Path(cc).is_absolute(), 'CC must be an absolute cross compiler executable'
    run(['git', 'check-ignore', 'work/artifact-targets/probe'])
    app = ROOT / 'work/artifact-targets' / (args.platform + '-' + args.android_api + '-' + args.edition)
    app.mkdir(parents=True, exist_ok=True)
    (app / 'src').mkdir(exist_ok=True)
    for name in ('ziran.toml', 'ziran.local.toml', 'ziran.lock'):
        source = WORK / 'one' / name
        if source.exists():
            shutil.copyfile(source, app / name)
        else:
            (app / name).unlink(missing_ok=True)
    options = f'[tool.entity]\nedition="{args.edition}"\n'
    if args.ndk:
        options += f'ndk="{args.ndk}"\nandroid_api="{args.android_api}"\n'
    manifest = app / 'ziran.toml'
    original = manifest.read_text()
    manifest.write_text(original + options)
    compiler = Path(run(['ziran', 'pkg', 'path', 'ziran'], app))
    command = [compiler / 'build/bin/ziran', 'pkg', 'artifact',
               'entity:' + ('native-crypto' if args.crypto_only else 'native-profile'), '--platform', args.platform]
    profile = descriptor(run(command, app))
    if args.crypto_only:
        crypto = profile
    else:
        dependencies = dict(line.split('\t', 1) for line in (profile.parent / 'dependencies.tsv').read_text().splitlines())
        crypto = descriptor(dependencies['self:native-crypto'])
    assert dict(line.split('\t', 1) for line in profile.read_text().splitlines())['platform'] == args.platform
    headers = app / 'headers'
    if not args.crypto_only:
        shutil.rmtree(headers, ignore_errors=True)
        headers.mkdir(exist_ok=True)
        run(['tar', '-xf', profile.parent / 'headers.tar', '-C', headers])
        shutil.copyfile(WORK / 'one/consumer.c', app / 'consumer.c')
    else:
        (app / 'consumer.c').write_text('#include <stddef.h>\nextern void crypto_wipe(void*, size_t);\n'
            'extern void *OQS_SIG_new(const char*); extern void OQS_SIG_free(void*);\n'
            'extern void *BundleOpen(unsigned char*); extern void BundleClose(void*);\n'
            + ('extern void *curl_easy_init(void); extern void curl_easy_cleanup(void*);\n' if args.platform.startswith('windows') else '')
            + 'int main(int argc,char **argv) { unsigned char data[8]={1}; crypto_wipe(data,8); '
            'void *sig=OQS_SIG_new("ML-DSA-44"); OQS_SIG_free(sig); '
            + ('void *curl=curl_easy_init(); curl_easy_cleanup(curl); ' if args.platform.startswith('windows') else '')
            + 'if(argc>1) BundleClose(BundleOpen((unsigned char*)argv[1])); return data[0]; }\n')
    windows = args.platform.startswith('windows')
    web = args.platform.startswith('emscripten')
    output = app / ('consumer.js' if web else 'consumer.exe' if windows else 'consumer')
    metadata = [crypto.parent / 'link.txt'] if args.crypto_only else [profile.parent / 'link.txt', crypto.parent / 'link.txt']
    flags = link_flags(*metadata)
    for line in (profile.parent / 'link.txt').read_text().splitlines():
        kind, value = line.split('\t', 1)
        if kind == 'js-library':
            flags += ['--js-library', str(profile.parent / value)]
    run([cc, '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections',
         '-Wl,--gc-sections', '-I', headers, '-I', headers / 'ziran', app / 'consumer.c',
         *flags, *shlex.split(ENV.get('LDFLAGS', '')), '-o', output])
    binary = output.with_suffix('.wasm') if web else output
    with binary.open('rb') as stream:
        magic = stream.read(4)
    assert magic.startswith(b'MZ') if windows else magic == (b'\0asm' if web else b'\x7fELF')
    if windows and not args.crypto_only:
        # Retain real transport and compression without contacting any service.
        # The C-host test above includes Entity's complete graph once. This
        # ordinary Ziran consumer owns its generated graph and links crypto only.
        (app / 'src/ordinary.zi').write_text('#import "entity/native_host"\n'
            'libc :: #system_library "libc";\n'
            'CurlInit :: () -> *void #foreign libc "curl_easy_init";\n'
            'CurlFree :: (value: *void) #foreign libc "curl_easy_cleanup";\n'
            'main :: () -> s32 { EntityHostProfileSections(7); EntityHostEdition(0); '
            'handle := CurlInit(); CurlFree(handle); return 0 }\n')
        generated = app / 'ordinary'
        run([compiler / 'build/bin/ziran', 'build', '--project', '--target=c',
             '--define', '_WIN32', '--define', '__x86_64__', '--define', 'PLATFORM_DESKTOP',
             '--entry', 'ordinary:main', '-o', generated, 'src/ordinary.zi'], app)
        support = link_flags(profile.parent / 'link.txt', crypto.parent / 'link.txt', ordinary_imports=True)
        assert str(profile.parent / 'libentity.a') not in support
        run([cc, '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections',
             '-Wl,--gc-sections', '-static', '-static-libgcc', '-I', compiler / 'include', '-I', generated,
             *sorted(generated.rglob('*.c')), *support, *shlex.split(ENV.get('LDFLAGS', '')), '-o', app / 'ordinary.exe'])
    if windows:
        members = run([ENV['AR'], 't', crypto.parent / 'libplatform.a']).splitlines()
        assert members and len(members) == len(set(members)), 'platform archive member collisions'
        assert 'archive\tlibplatform.a' in (crypto.parent / 'link.txt').read_text()
    # Repeat builds certify clean reuse or explicit dirty isolation; bad API /
    # driver combinations must fail before any C compilation, retaining old data.
    again = descriptor(run(command, app))
    assert (again != profile) if args.dirty else (again == profile)
    before = hash_file(profile)
    if args.ndk:
        manifest.write_text(original + options.replace(f'android_api="{args.android_api}"', 'android_api="22"'))
        rejected_before_compile(command, app, "android_api must be")
        mismatch = '24' if args.android_api != '24' else '21'
        manifest.write_text(original + options.replace(f'android_api="{args.android_api}"', f'android_api="{mismatch}"'))
        rejected_before_compile(command, app, "CC target does not match")
        manifest.write_text(original + options)
    assert hash_file(profile) == before
    descriptor(profile)
    (app / 'adoption.txt').write_text(f'{profile}\n{crypto}\n')
    (app / 'result.json').write_text(json.dumps(vars(args) | {'profile': str(profile), 'crypto': str(crypto), 'runtime': 'not executed'}, indent=2))
    print(f'PASS: {args.platform} API{args.android_api} {args.edition}; descriptor hashes, {"crypto" if args.crypto_only else "C-host"} compile/link, '
          f'{"ordinary Ziran transport link, " if windows and not args.crypto_only else ""}reuse/isolation and failure preservation; executables not run')


if __name__ == '__main__':
    main()
