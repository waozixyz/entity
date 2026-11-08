"""Select and reopen a profile picture on an isolated private display."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from PIL import Image, ImageChops

assert os.environ.get("ENTITY_PRIVATE_DISPLAY") == "1"
project = Path(__file__).resolve().parents[1]
output = project / "build/gui-test"
output.mkdir(parents=True, exist_ok=True)


def launch(environment):
    process = subprocess.Popen([str(project / "build/entity"), str(project / "build/entity.zx")], env=environment)
    for _ in range(100):
        result = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(process.pid)],
                                capture_output=True, text=True, env=environment)
        if result.returncode == 0:
            window = result.stdout.splitlines()[0]
            subprocess.run(["xdotool", "windowfocus", "--sync", window], check=True, env=environment)
            return process, window
        if process.poll() is not None:
            raise RuntimeError("player exited")
        time.sleep(.1)
    process.terminate()
    process.wait(timeout=10)
    raise RuntimeError("no window")


def click(window, x, y, environment):
    subprocess.run(["xdotool", "mousemove", "--window", window, str(x), str(y)], check=True, env=environment)
    subprocess.run(["xdotool", "click", "--window", window, "1"], check=True, env=environment)
    time.sleep(.4)


def stop(process):
    process.terminate()
    process.wait(timeout=10)


with tempfile.TemporaryDirectory(prefix="profile-picture-", dir=output) as directory:
    environment = os.environ.copy()
    environment.pop("ENTITY_DATA", None)
    environment["XDG_DATA_HOME"] = directory
    profile = Path(directory) / "entity/entity.json"
    process, window = launch(environment)
    try:
        time.sleep(.5)
        # A fresh host has no saved profile; save its default Classic choice.
        assert not profile.exists(), "profile was not isolated"
        before = Path(directory) / "before.png"
        after = Path(directory) / "default.png"
        subprocess.run(["import", "-window", window, str(before)], check=True, env=environment)
        click(window, 100, 188, environment)
        click(window, 62, 220, environment)
        time.sleep(.5)
        assert json.loads(profile.read_text())["picture"] == 0, "unexpected initial picture"
        subprocess.run(["import", "-window", window, str(after)], check=True, env=environment)
        with Image.open(before) as first, Image.open(after) as second:
            area = (195, 65, 285, 155)
            assert ImageChops.difference(first.convert("RGB").crop(area), second.convert("RGB").crop(area)).getbbox() is None, "initial picture differs from default"
        click(window, 100, 188, environment)
        click(window, 150, 220, environment)
        time.sleep(1)
        assert json.loads(profile.read_text())["picture"] == 1, "picture selection was not saved"
    finally:
        stop(process)
    process, window = launch(environment)
    try:
        time.sleep(.5)
        assert json.loads(profile.read_text())["picture"] == 1, "picture changed after reopen"
        subprocess.run(["import", "-window", window, str(project / "build/profile-picture-reopen-private.png")],
                       check=True, env=environment)
    finally:
        stop(process)
print("Private profile UI: default, select bird, save and reopen passed")
