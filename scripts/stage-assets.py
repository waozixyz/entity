#!/usr/bin/env python3
"""Stage declared Entity asset groups for an embedding host."""
import argparse
import json
from pathlib import Path, PurePosixPath
import shutil

ROOT = Path(__file__).resolve().parents[1]


def declared_assets(groups, selected):
    result = set()
    for group in selected:
        for name in groups[group]:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or str(path) != name or not name.startswith('assets/entity/'):
                raise ValueError('Unsafe Entity asset declaration')
            if name in result:
                raise ValueError('Duplicate Entity asset declaration')
            result.add(name)
    return result


def stage(output, selected):
    groups = json.loads((ROOT / 'asset-groups.json').read_text())
    names = declared_assets(groups, selected)
    # Validate before replacing disposable staging, never a source asset tree.
    output = output.resolve()
    if output == ROOT or output == ROOT / 'assets' or ROOT / 'assets' in output.parents:
        raise ValueError('Output must be disposable host staging')
    for name in names:
        if not (ROOT / name).is_file():
            raise ValueError('Missing declared Entity asset: ' + name)
    if output.exists():
        shutil.rmtree(output)
    for name in sorted(names):
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    return names


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    stage(args.output, args.group)
