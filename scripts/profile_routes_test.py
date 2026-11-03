#!/usr/bin/env python3
"""Execute the production route functions against a command-only fake host."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work/profile-routes-test'
subprocess.run(['git', 'check-ignore', '-q', str(WORK)], cwd=ROOT, check=True)
WORK.mkdir(parents=True, exist_ok=True)

def function(path, name):
    text = path.read_text()
    start = re.search(r'^' + name + r' ::', text, re.M).start()
    end = re.search(r'^\w+ ::', text[start + len(name) + 3:], re.M)
    return text[start:start + len(name) + 3 + end.start()] if end else text[start:]

native = ROOT / 'src/native_host.zi'
source = '''entity_host_page: string;
entity_host_may_restart: bool;
command: string;
calls: s32;
accept: bool = true;
EntityHostCommand :: (page: string) -> bool { command = page; calls += 1; return accept }
'''
for name in ('EntityHostProfileRequest', 'EntityHostLeaderboard', 'EntityHostPage'):
    source += function(native, name) + '\n'
source += '\n' + function(ROOT / 'src/browser_host.zi', 'BrowserServices') + '\n'
source += function(ROOT / 'src/entity.zi', 'CurrentPageTitle').replace('#program_export\n', '') + '\n'
source += '''
telegram_open: bool;
profile_leaderboard_open: bool;
achievement_open: bool;
dew_page: bool;
referrals_open: bool;
management_page: s32;
Label :: (key: string, fallback: string) -> string { return key }
PageTitle :: () -> string { return "friends-title" }
HostValue :: struct { text: string }
browser_mini: bool;
browser_profile: bool;
PUBLICATIONS_READ_SERVICE :: "publications.read";
ENTITY_RECORDS_SERVICE :: "entity.records";
ENTITY_DEW_SERVICE :: "entity.dew";
TextFromCString :: (value: *u8) -> string { return "AppServiceHost" }
AppArgumentText :: (value: HostValue) -> string { return value.text }
EntityHostText :: (value: string) -> HostValue { return HostValue.{value} }
EntityGameShopAnswer :: (request: string) -> string { return "shop" }
PublicationsReadAnswer :: (request: string) -> string { return "publications" }
EntityRecordsAnswer :: (request: string) -> string { return "records" }
EntityDewAnswer :: (request: string) -> string { return "dew" }
BundleAppServices :: (context: *void, module: *u8, function: *u8, arguments: *HostValue, count: s32, result: *HostValue) -> s32 { return 0 }
#program_export
Check :: () -> s32 {
    if !EntityHostProfileRequest("open") || command != "root:profile" { return 1 }
    if !EntityHostProfileRequest("leaderboard") || command != "root:leaderboard" { return 2 }
    if !EntityHostProfileRequest("dew") || command != "root:dew" { return 3 }
    if !entity_host_may_restart || calls != 3 { return 4 }
    if EntityHostProfileRequest("buy") || EntityHostProfileRequest("appearance") ||
        EntityHostProfileRequest("") || EntityHostProfileRequest("shovey.gold") || calls != 3 { return 5 }
    accept = false
    if EntityHostProfileRequest("dew") || calls != 4 { return 6 }
    accept = true
    args: [2]HostValue = .[HostValue.{"entity.profile"}, HostValue.{"leaderboard"}]
    answer: HostValue
    if BrowserServices(null, null, null, *args[0], 2, *answer) != 1 ||
        answer.text != "queued" || command != "root:leaderboard" || !browser_profile { return 7 }
    browser_profile = false
    args[1].text = "buy"
    if BrowserServices(null, null, null, *args[0], 2, *answer) != 1 ||
        answer.text != "unavailable" || browser_profile { return 8 }
    before := calls
    browser_mini = true
    args[1].text = "open"
    if BrowserServices(null, null, null, *args[0], 2, *answer) != 0 || calls != before || browser_profile { return 9 }
    args[0].text = "entity.game-shop"
    if BrowserServices(null, null, null, *args[0], 2, *answer) != 0 { return 10 }
    browser_mini = false
    if BrowserServices(null, null, null, *args[0], 2, *answer) != 1 || answer.text != "shop" { return 11 }
    if CurrentPageTitle() != "entity.title" { return 12 }
    management_page = 1
    if CurrentPageTitle() != "friends-title" { return 13 }
    dew_page = true
    if CurrentPageTitle() != "profile_dew_title" { return 14 }
    achievement_open = true
    if CurrentPageTitle() != "achievements_title" { return 15 }
    profile_leaderboard_open = true
    if CurrentPageTitle() != "leaderboard_title" { return 16 }
    telegram_open = true
    if CurrentPageTitle() != "Telegram" { return 17 }
    telegram_open = false
    if CurrentPageTitle() != "leaderboard_title" { return 18 }
    profile_leaderboard_open = false
    if CurrentPageTitle() != "achievements_title" { return 19 }
    achievement_open = false
    if CurrentPageTitle() != "profile_dew_title" { return 20 }
    dew_page = false
    if CurrentPageTitle() != "friends-title" { return 21 }
    management_page = 0
    if CurrentPageTitle() != "entity.title" { return 22 }
    return 42
}
'''
fixture = WORK / 'routes.zi'
fixture.write_text(source)
subprocess.run([str(ROOT / 'scripts/ziran.sh'), 'build', '--target=c', '--exe', '--root', str(WORK),
                '--entry', 'routes:Check', '-o', str(WORK / 'native'), str(fixture)], cwd=ROOT, check=True)
result = subprocess.run([str(WORK / 'native/routes')], cwd=ROOT)
assert result.returncode == 42, result.returncode
browser = function(ROOT / 'src/browser_host.zi', 'BrowserServices')
assert 'AppArgumentText(arguments[0]) == "entity.profile" && !browser_mini' in browser
assert 'opened := EntityHostProfileRequest(AppArgumentText(arguments[1]))' in browser
assert 'if opened { browser_profile = true }' in browser
assert 'ifx opened then "queued" else "unavailable"' in browser
print('Entity profile route local tests: profile, leaderboard, Dew, rejected actions, command failure and mini guard passed')
