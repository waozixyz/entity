"""Send keys only to the fixture launched on this private Xvfb display."""
import os
import subprocess
import sys
import time

assert os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY')
app = subprocess.Popen([sys.argv[1], '--keys'])
try:
    for _ in range(150):
        found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(app.pid)], capture_output=True, text=True)
        if found.returncode == 0 and found.stdout.strip():
            window = found.stdout.splitlines()[0]
            break
        if app.poll() is not None:
            raise AssertionError(f'Password fixture exited before window: {app.returncode}')
        time.sleep(0.1)
    else:
        raise AssertionError('Password fixture window missing')
    subprocess.run(['xdotool', 'windowfocus', window], check=True)
    time.sleep(0.2)
    for key in ('ctrl+a', 'z', 'ctrl+a', 'BackSpace'):
        subprocess.run(['xdotool', 'key', '--clearmodifiers', key], check=True)
        time.sleep(0.25)
    assert app.wait(timeout=10) == 0, 'Physical password key regression failed'
finally:
    if app.poll() is None:
        app.terminate()
        app.wait(timeout=5)
