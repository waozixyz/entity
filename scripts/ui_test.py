#!/usr/bin/env python3
"""Exercise Self's saved profile and nodes on a private display only."""
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

assert os.environ.get("SELF_PRIVATE_DISPLAY") == "1"
root = Path(__file__).resolve().parents[1]
narrow = "--narrow" in sys.argv[3:]
output = root / "build/gui-test" / ("narrow" if narrow else "desktop")
shutil.rmtree(output, ignore_errors=True)
output.mkdir(parents=True)
environment = dict(os.environ, KRYON_APP_DATA=str(output / "data"), XDG_CACHE_HOME=str(output / "cache"))
player, bundle = map(lambda value: str(Path(value).resolve()), sys.argv[1:3])
app = None
window = None


def command(*args):
    return subprocess.check_output(args, env=environment, text=True, timeout=20)


def start():
    global app, window
    app = subprocess.Popen([player, bundle], env=environment)
    for _ in range(100):
        assert app.poll() is None, f"Self exited before opening: {app.returncode}"
        found = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(app.pid)],
                               env=environment, capture_output=True, text=True)
        if found.returncode == 0:
            window = found.stdout.splitlines()[0]
            command("xdotool", "windowfocus", "--sync", window)
            if narrow:
                command("xdotool", "windowsize", window, "420", "760")
            time.sleep(.5)
            return
        time.sleep(.1)
    raise AssertionError("Self did not open")


def stop():
    if app and app.poll() is None:
        app.terminate()
        app.wait(timeout=10)


def click(x, y):
    command("xdotool", "mousemove", "--window", window, str(x), str(y))
    command("xdotool", "click", "--window", window, "1")
    time.sleep(.2)


def text(value):
    command("xdotool", "type", "--window", window, "--delay", "10", value)
    time.sleep(.2)


def saved():
    return json.loads((output / "data/self.json").read_text())



def capture(name):
    time.sleep(.2)
    path = output / (name + ".png")
    command("import", "-window", window, str(path))
    return path


def word(value):
    path = capture("controls")
    for factor in (1, 3):
        target = path
        if factor > 1:
            target = output / "controls-enlarged.png"
            with Image.open(path) as source:
                source.resize((source.width * factor, source.height * factor)).save(target)
        tsv = command("tesseract", str(target), "stdout", "--psm", "11", "-c", "tessedit_create_tsv=1")
        for item in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
            if item["text"].strip() == value:
                return tuple(int(item[key]) // factor for key in ("left", "top", "width", "height"))
    raise AssertionError("Missing visible control: " + value)


def click_word(value):
    x, y, width, height = word(value)
    click(x + width // 2, y + height // 2)



def primary_bounds():
    # White text on a small colored button is unreliable in whole-page OCR.
    # Locate the rendered filled control, then exercise its real hit target.
    with Image.open(capture("controls")) as source:
        pixels = source.convert("RGB")
        runs = []
        for y in range(pixels.height):
            start = None
            for x in range(pixels.width + 1):
                match = False
                if x < pixels.width:
                    red, green, blue = pixels.getpixel((x, y))
                    match = red < 100 and green > red + 30 and blue > red + 30 and max(green, blue) < 200
                if match and start is None:
                    start = x
                if not match and start is not None:
                    if x - start >= 30:
                        runs.append((start, y, x))
                    start = None
        assert runs, "No filled Add control is visible"
        return min(row[0] for row in runs), min(row[1] for row in runs), max(row[2] for row in runs), max(row[1] for row in runs)


def click_add():
    left, top, right, bottom = primary_bounds()
    click((left + right) // 2, (top + bottom) // 2)

try:
    start()
    x, y, _, _ = word("Name")
    click(x + 80, y + 40)
    text("Fixture Person")
    command("xdotool", "key", "--window", window, "Return")
    time.sleep(.3)
    assert saved()["name"] == "Fixture Person"
    x, y, width, height = word("address")
    node_field = (x + width // 2, y + height // 2)
    click(*node_field)
    text("https://sync.example.invalid/path")
    click_add()
    assert saved()["nodes"] == ["https://api.waozi.xyz"]
    click(*node_field)
    command("xdotool", "key", "--window", window, "ctrl+a")
    text("https://sync.example.invalid:8443/")
    click_add()
    assert saved()["nodes"] == ["https://api.waozi.xyz", "https://sync.example.invalid:8443"]
    assert saved()["preferred"] == 1
    capture("nodes")
    stop()
    start()
    x, y, _, _ = word("Nodes")
    click(x + 80, y + 48)
    assert saved()["preferred"] == 0 and saved()["name"] == "Fixture Person"
    _, _, right, _ = primary_bounds()
    click(right - 18, y + 112)
    assert saved()["nodes"] == ["https://api.waozi.xyz"]
    capture("restarted")
    click_word("Change")
    capture("picture-picker")
    click_word("Done")
    print("Self: responsive profile, picture picker, node validation, add/prefer/remove and restart passed")
finally:
    stop()
