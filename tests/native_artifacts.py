"""Real provider and external C consumers; no account, network or display use."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

# Bound this fixture and its compiler children to one managed CPU.
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work/recipe-provider'
ZIRAN = str(ROOT / 'scripts/ziran.sh')
ENV = {k: v for k, v in os.environ.items() if k not in
       ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER')}
ENV.update(MAKEFLAGS='-j1', CMAKE_BUILD_PARALLEL_LEVEL='1', ZIRAN_BUILD_JOBS='1',
           ZIRAN_PAR_THREADS='1', OMP_NUM_THREADS='1', TMPDIR=str(WORK))


def run(args, cwd=ROOT, ok=True):
    result = subprocess.run(list(map(str, args)), cwd=cwd, env=ENV, text=True,
                            stdout=subprocess.PIPE, stderr=None)
    if ok and result.returncode:
        raise RuntimeError(f'{args}: exit {result.returncode}')
    if not ok:
        assert result.returncode, args
    return result.stdout.strip()


def hash_file(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def link_flags(*paths, ordinary_imports=False):
    flags = []
    for path in paths:
        for line in path.read_text().splitlines():
            kind, value = line.split('\t', 1)
            if ordinary_imports and kind == 'archive' and value == 'libentity.a':
                continue
            if kind == 'pkg-config':
                flags += run(['pkg-config', '--libs', *value.split()]).split()
            elif kind == 'archive':
                flags.append(str(path.parent / value))
            elif kind in ('library', 'flag'):
                flags.append(value)
    return flags


def descriptor(path):
    path = Path(path)
    assert path.is_absolute() and path.is_file(), path
    rows = dict(line.split('\t', 1) for line in path.read_text().splitlines())
    for name, digest in rows.items():
        if len(digest) == 64 and name not in ('key', 'package'):
            assert hash_file(path.parent / name) == digest
    return path


def consume(app, profile, crypto):
    headers = app / 'headers'
    shutil.rmtree(headers, ignore_errors=True)
    headers.mkdir(exist_ok=True)
    run(['tar', '-xf', profile / 'headers.tar', '-C', headers])
    # Call real native host policy and real Monocypher without keys/accounts.
    (app / 'consumer.c').write_text('#include "src/native_host.h"\n'
        'extern void crypto_wipe(void *, unsigned long);\n'
        'extern void *OQS_SIG_new(const char *); extern void OQS_SIG_free(void *);\n'
        'int main(int argc, char **argv) { unsigned char b[8]={1,2,3}; '
        'native_host_EntityHostProfileSections(7); native_host_EntityHostEdition(0); '
        'crypto_wipe(b, sizeof b); void *sig=OQS_SIG_new("ML-DSA-44"); '
        'if (!sig) return 1; OQS_SIG_free(sig); '
        'if (argc > 1) { void *bundle=OpenBundle((uint8_t *)argv[1]); if (!bundle) return 2; '
        'uint64_t count=BundleAssets(bundle); CloseBundle(bundle); if (!count) return 3; } '
        'return b[0] != 0; }\n')
    flags = link_flags(profile / 'link.txt', crypto / 'link.txt')
    run(['cc', '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections', '-I', headers, '-I', headers / 'ziran',
         app / 'consumer.c', *flags,
         '-o', app / 'consumer'])
    run([app / 'consumer', profile / 'entity.zx'])


def main():
    run(['git', 'check-ignore', 'work/recipe-provider/probe'])
    WORK.mkdir(parents=True, exist_ok=True)
    compiler = None
    # These are synthetic consumer manifests, never source copies/checkouts.
    dirty = argparse.ArgumentParser()
    dirty.add_argument('--dirty', action='store_true', help='assert dirty graph isolation before commit; default requires clean reuse')
    allow_dirty = dirty.parse_args().dirty
    tool_ref = json.loads((ROOT / 'ziran.lock').read_text())['toolchain']['commit']
    apps = []
    for name in ('one', 'two'):
        app = WORK / name
        app.mkdir(exist_ok=True)
        (app / 'src').mkdir(exist_ok=True)
        (app / 'ziran.toml').write_text('[package]\nname="' + name + '"\n'
            '[toolchain]\ngit="https://github.com/ziranlang/ziran.git"\nref="' + tool_ref + '"\n'
            '[dependencies.entity]\ngit="https://github.com/waozixyz/entity.git"\nref="master"\n')
        (app / 'ziran.local.toml').write_text(f'[overrides]\nentity="{ROOT}"\n')
        run(['ziran', 'lock'], app)
        selected = Path(run(['ziran', 'pkg', 'path', 'ziran'], app))
        assert compiler is None or compiler == selected
        compiler = selected
        apps.append(app)
    def build(app, recipe='native-profile', target='linux-x86_64-gnu', ok=True):
        return run([compiler / 'build/bin/ziran', 'pkg', 'artifact', 'entity:' + recipe,
                    '--platform', target], app, ok)
    first = descriptor(build(apps[0]))
    second = descriptor(build(apps[1]))
    (WORK / "attempt.json").write_text(json.dumps({"one": str(first), "two": str(second)}))
    dependencies = dict(line.split('\t', 1) for line in (first.parent / 'dependencies.tsv').read_text().splitlines())
    crypto = descriptor(dependencies['self:native-crypto'])
    assert (first.parent / 'entity.zx').stat().st_size > 1000
    for app in apps:
        consume(app, first.parent, crypto.parent)
    print('Linked both external native consumers successfully', flush=True)
    if allow_dirty:
        assert first != second, 'dirty graph artifacts must remain isolated'
    else:
        assert first == second, 'clean consumers must reuse one artifact (commit provider changes before this test)'
    (apps[1] / 'ziran.toml').write_text((apps[1] / 'ziran.toml').read_text() + '[tool.entity]\nedition="fdroid"\n')
    different = descriptor(build(apps[1]))
    assert different != first
    build(apps[0], target='freebsd-x86_64-gnu', ok=False)
    assert descriptor(first) == first
    (apps[1] / 'ziran.toml').write_text((apps[1] / 'ziran.toml').read_text().replace('fdroid', 'invalid'))
    build(apps[1], ok=False)
    print(('DIRTY isolation mode: ' if allow_dirty else 'CLEAN reuse mode: ') + 'PASS: linked two external native profile/crypto consumers; shared artifact; edition separation; unsupported target/options rejected')
    (WORK / 'adoption.txt').write_text(f'native-profile\t{first}\nnative-crypto\t{crypto}\nfdroid\t{different}\n')


if __name__ == '__main__':
    main()
