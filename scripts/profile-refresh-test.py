#!/usr/bin/env python3
"""Exercise delayed account-picture reads using only private local files."""
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

root = Path(__file__).resolve().parents[1]
manifest = tomllib.loads((root / "ziran.toml").read_text())
assert "module_aliases" not in manifest["dependencies"]["kryon"], (
    "Obsolete Kryon module_aliases in ziran.toml duplicates file_dialog_linux")
assert 'Dialog :: #import "file_dialog_linux";' in (root / "src/account_store.zi").read_text()
output = root / "build/profile-refresh-test"
output.mkdir(parents=True, exist_ok=True)
for name in ("profile", "shared"):
    shutil.rmtree(output / name, ignore_errors=True)
env = dict(os.environ)
for key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS",
            "SESSION_MANAGER", "GDK_DISPLAY"):
    env.pop(key, None)
env.update(ENTITY_PROFILE_REFRESH_DATA=str(output / "profile"),
           XDG_DATA_HOME=str(output / "shared"), YUE_DESKTOP_RECOVERY="0")
ziran = str(root / "scripts/ziran.sh")
lock = [] if (root / "ziran.local.toml").exists() else ["--locked"]
subprocess.run(["make", "build/liboqs/lib/liboqs.a"], cwd=root, env=env, check=True)
def package(name):
    return Path(subprocess.check_output(
        [ziran, "pkg", "path", name, *lock], cwd=root, env=env, text=True).strip())


toolchain, monocypher, kryon = package("ziran"), package("monocypher"), package("kryon").resolve()
generated = output / "c"
subprocess.run([ziran, "build", "--project", *lock, "--target=c", "--entry", "profile_refresh_test:main",
                "-o", str(generated), "tests/profile_refresh_test.zi"], cwd=root, env=env, check=True)
rows = [line.split("\t") for line in (root / "build/.ziran/module-map.tsv").read_text().splitlines() if line]
packages = {row[1]: Path(row[2]).resolve() for row in rows if row[0] == "P"}
resolutions = [row for row in rows if row[:3] == ["D", "root", "file_dialog_linux"]]
assert len(resolutions) == 1 and packages.get(resolutions[0][3]) == kryon and resolutions[0][4] == "file_dialog_linux", (
    f"Expected unique Kryon file_dialog_linux resolution, got {resolutions}")
command = ["cc", "-std=c11", "-O1", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
           "-I" + str(toolchain / "include"), "-I" + str(monocypher / "src"), "-iquote" + str(generated)]
command += ["-iquote" + str(path) for path in generated.rglob("*") if path.is_dir()]
command += [str(path) for path in generated.rglob("*.c")]
command += [str(monocypher / "src/monocypher.c"), str(monocypher / "src/optional/monocypher-ed25519.c"),
            str(root / "build/liboqs/lib/liboqs.a"), "-l:libcurl.so.4", "-lm", "-lpthread",
            "-o", str(output / "test")]
subprocess.run(command, cwd=root, env=env, check=True)
subprocess.run([str(output / "test")], cwd=root, env=env, check=True)
