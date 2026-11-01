#!/usr/bin/env python3
"""No Google account, SDK, network, or desktop required."""
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[2]
output = root / 'build/drive-test'
output.mkdir(parents=True, exist_ok=True)
source = root / 'android/gplay/java/xyz/waozi/entity'
subprocess.run(['javac', '-d', str(output), str(source / 'DriveBackupFlow.java'),
                str(root / 'android/tests/DriveBackupFlowTest.java')], check=True)
subprocess.run(['java', '-ea', '-cp', str(output), 'xyz.waozi.entity.DriveBackupFlowTest'], check=True)
# Enforce the edition boundary and the only permitted scope.
for path in (root / 'android').rglob('*.java'):
    if '/tests/' in str(path) or '/gplayTest/' in str(path):
        continue
    assert '/gplay/' in str(path), path
activity = (source / 'DriveActivity.java').read_text()
assert activity.count('https://www.googleapis.com/auth/') == 1
assert 'https://www.googleapis.com/auth/drive.file' in activity
assert 'addJavascriptInterface' not in activity
assert 'setAllowFileAccess(false)' in activity
rest = (source / 'DriveRest.java').read_text()
assert 'setInstanceFollowRedirects(false)' in rest
assert '"Authorization", "Bearer " + token' in rest
assert '"pending_create"' in rest
assert 'appDataFolder' not in rest
assert 'private_key' not in rest
print('Drive edition, Picker bridge, bounded REST and scope contracts passed.')

translations = list((root / 'android/gplay/res').glob('values*/waozi_drive.xml'))
assert len(translations) == 12
base = {node.attrib['name'] for node in ET.parse(root / 'android/gplay/res/values/waozi_drive.xml').getroot()}
for translation in translations:
    assert {node.attrib['name'] for node in ET.parse(translation).getroot()} == base, translation
assert activity.index('config("picker_key").isEmpty()') < activity.index('startActivityForResult(android.accounts.AccountManager')
print('All 12 Drive locales complete; unconfigured builds stop before authorization.')
