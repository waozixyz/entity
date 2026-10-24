#!/usr/bin/env python3
"""Exercise standalone Entity's native account provider on a private display."""
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from PIL import Image

assert os.environ.get('ENTITY_PRIVATE_DISPLAY') == '1'
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/native-gui-test'
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
DATA = OUT / 'data'
DATA.mkdir(mode=0o700)
# Pairing never reaches a public node in this fixture.
state = dict(version=1, owner_id='', name='', intention='', picture=0, pictures=268435455,
             theme=0, accent=0, material=1, controls=33, preferred=0,
             nodes=['http://127.0.0.1:9'], extensions=[])
(DATA / 'entity.json').write_text(json.dumps(state))
(DATA / 'entity.json').chmod(0o600)
ENV = dict(os.environ, ENTITY_DATA=str(DATA), XDG_CACHE_HOME=str(OUT / 'cache'))
APP = None
WINDOW = None

def command(*args):
    return subprocess.check_output(args, env=ENV, text=True, timeout=20)

def start():
    global APP, WINDOW
    APP = subprocess.Popen([str(ROOT / 'build/entity'), str(ROOT / 'build/entity.zx')], env=ENV)
    for _ in range(100):
        assert APP.poll() is None, 'Entity exited before opening'
        found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(APP.pid)], env=ENV, capture_output=True, text=True)
        if found.returncode == 0:
            WINDOW = found.stdout.splitlines()[0]
            command('xdotool', 'windowfocus', '--sync', WINDOW)
            time.sleep(.5)
            return
        time.sleep(.1)
    raise AssertionError('Entity did not open')

def stop():
    if APP and APP.poll() is None:
        APP.terminate()
        APP.wait(timeout=10)

def capture(name):
    path = OUT / (name + '.png')
    command('import', '-window', WINDOW, str(path))
    return path

def words():
    original = capture('controls')
    for variant in range(3):
        path = original
        if variant:
            path = OUT / 'controls-ocr.png'
            with Image.open(original) as source:
                image = source.convert('L').resize((source.width * 3, source.height * 3))
                if variant == 2:
                    image = image.point(lambda value: 0 if value < 140 else 255)
                image.save(path)
        tsv = command('tesseract', str(path), 'stdout', '--psm', '11', '-c', 'tessedit_create_tsv=1')
        factor = 1 if variant == 0 else 3
        for row in csv.DictReader(io.StringIO(tsv), delimiter='\t'):
            yield row['text'].strip(), tuple(int(row[key]) // factor for key in ('left', 'top', 'width', 'height'))

def click(x, y):
    command('xdotool', 'mousemove', '--window', WINDOW, str(x), str(y))
    command('xdotool', 'click', '--window', WINDOW, '1')
    time.sleep(.35)

def find(word, scroll=False):
    for _ in range(16 if scroll else 1):
        for text, bounds in words():
            if text == word:
                return bounds
        if scroll:
            command('xdotool', 'mousemove', '--window', WINDOW, '440', '650')
            command('xdotool', 'click', '--window', WINDOW, '--repeat', '3', '--delay', '80', '5')
            time.sleep(.2)
    raise AssertionError('Missing visible control: ' + word)

def click_word(word, scroll=False, last=False):
    bounds = find(word, scroll)
    if last:
        matches = [item for text, item in words() if text == word]
        bounds = max(matches, key=lambda item: item[1])
    x, y, width, height = bounds
    click(x + width // 2, y + height // 2)

def click_filled():
    with Image.open(capture('filled-button')) as source:
        pixels = source.convert('RGB')
        rows = []
        for y in range(pixels.height):
            span = []
            for x in range(pixels.width):
                rgb = pixels.getpixel((x, y))
                if min(rgb) < 120 and max(rgb) < 220 and max(rgb) - min(rgb) > 40:
                    span.append(x)
            if len(span) > 200:
                rows.append((min(span), y, max(span)))
        assert rows, 'Filled action button is not visible'
    click((rows[0][0] + rows[0][2]) // 2, (rows[0][1] + rows[-1][1]) // 2)

def profile():
    return json.loads((DATA / 'entity.json').read_text())

try:
    start()
    x, y, _, _ = find('Name')
    click(x + 100, y + 40)
    command('xdotool', 'type', '--window', WINDOW, '--delay', '10', 'Fixture Native')
    command('xdotool', 'key', '--window', WINDOW, 'Return')
    time.sleep(.3)
    assert profile()['name'] == 'Fixture Native'
    click_word('Connect', last=True)
    capture('account-empty')
    click_filled()
    time.sleep(.8)
    click_word('merge', last=True)
    time.sleep(.8)
    owner = profile()['owner_id']
    assert len(owner) == 64 and (DATA / 'account.key').exists()
    capture('account-connected')
    click_word('Back')
    capture('profile-connected')
    stop()
    start()
    assert profile()['owner_id'] == owner and profile()['name'] == 'Fixture Native'
    click_word('Fixture')
    click_word('out', True)
    capture('logout-confirm')
    click_filled()
    time.sleep(.8)
    assert not (DATA / 'account.key').exists()
    assert profile()['name'] == 'Fixture Native' and profile()['owner_id'] == ''
    capture('logged-out')
    print('Native Entity identity, account creation with merge, restart and logout preserving local profile passed.')
finally:
    stop()
