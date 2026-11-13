#!/usr/bin/env python3
"""Failure injection around the production adapter and unconditional teardown bodies."""
from pathlib import Path
import os
import re
import subprocess
root = Path(__file__).resolve().parents[1]
work = root / 'work/canvas-profile-lifecycle-test'
subprocess.run(['git', 'check-ignore', '-q', str(work)], cwd=root, check=True)
work.mkdir(parents=True, exist_ok=True)
def function(path, name):
    source = path.read_text()
    start = re.search(r'^' + name + r' ::', source, re.M).start()
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    # These lifecycle bodies contain no braces in strings.
    while depth:
        if source[end] == '{': depth += 1
        if source[end] == '}': depth -= 1
        end += 1
    return source[start:end] + '\n'
# Stand-ins for the namespaced Kryon widget modules the adapter imports.
(work / 'fixture_types.zi').write_text('''
Session :: struct { id: s32 }
Rectangle :: struct { x: float32; y: float32; width: float32; height: float32 }
''')
(work / 'text_field.zi').write_text('Input :: struct { text: string }\n')
(work / 'button.zi').write_text('''#import "fixture_types"
Props :: struct { key: u64; id: s32; label: string; bounds: Rectangle }
Draw :: (session: Session, props: Props) -> s32 { return 1 }
''')
source = '''
#import "fixture_types"
TextField :: #import "text_field";
Button :: #import "button";
Hosted :: struct { alive: bool }
Portable :: struct { app: Hosted }
portable: Portable;
entity_canvas_ready: bool;
entity_canvas_visible: bool;
entity_canvas_client: string = "arcade";
entity_canvas_saved: float64;
profile_document: string;
entity_referral_command: string;
found: bool = true;
open_ok: bool;
save_ok: bool;
allocated: bool;
cancelled: s32;
closed: s32;
saved: s32;
WebScope :: () -> s32 { return 0 }
WebEnd :: (scope: s32) {}
EntityCanvasStatus :: (ready: bool) {}
PageNow :: () -> float64 { return 1.0 }
ReadEntireFile :: (path: string) -> (text: string, ok: bool) { return "fixture", found }
AppFileFree :: (value: string) {}
EntityFree :: (value: string) {}
EntityHostOpen :: (bytes: string, path: string, client: string, navigation: bool) -> bool { allocated = true; portable.app.alive = true; return open_ok }
EntityHostSave :: () -> bool { saved += 1; return save_ok }
EntityReferralsReset :: () { cancelled |= 1 }
DewReset :: () { cancelled |= 2 }
EntityDewStop :: () { cancelled |= 4 }
EntityGameShopStop :: () { cancelled |= 8 }
EntityRecordsStop :: () { cancelled |= 16 }
PublicationsStop :: () { cancelled |= 32 }
EntityLeaderboardStop :: () { cancelled |= 64 }
EntityFriendsStop :: () { cancelled |= 128 }
PublicationsReadStop :: () {}
AccountStoreStop :: () { allocated = false; cancelled |= 256 }
HostedAppClose :: (app: *Hosted) { app.alive = false; closed += 1 }
EntityHostFrame :: (session: Session, area: Rectangle, key: s32, modifiers: s32, input: TextField.Input) -> bool { return true }
EntityHostBack :: () -> bool { return false }
'''
for name in ('EntityHostClose', 'EntityHostDispose'):
    source += function(root / 'src/native_host.zi', name)
for name in ('EntityCanvasStart', 'EntityCanvasStop', 'EntityCanvasFrame'):
    source += function(root / 'src/canvas_profile_host.zi', name)
source += '''
main :: () -> s32 {
    // Partial allocation on open failure is disposed even though start fails.
    if EntityCanvasStart(false) || allocated || portable.app.alive || cancelled != 511 || closed != 1 { return 1 }
    cancelled = 0
    open_ok = true
    if !EntityCanvasStart(false) || !allocated || !entity_canvas_ready { return 2 }
    entity_canvas_visible = true
    // Interactive save refusal preserves the visible account and does not dispose.
    if EntityCanvasFrame(.{}, Rectangle.{0.0, 0.0, 480.0, 800.0}, 0, 0, .{}) != 1 ||
        !entity_canvas_visible || !allocated || cancelled != 0 { return 3 }
    // Terminal shutdown cancels and frees even if that same APP_SAVE fails.
    if EntityCanvasStop() { return 10 }
    if allocated || portable.app.alive || entity_canvas_ready || entity_canvas_visible || cancelled != 511 || closed != 2 { return 4 }
    if !EntityCanvasStop() { return 11 }
    if closed != 2 { return 5 }
    cancelled = 0
    save_ok = true
    if !EntityCanvasStart(false) { return 6 }
    if !EntityCanvasStop() { return 12 }
    if allocated || cancelled != 511 || closed != 3 { return 7 }
    // Mini mode neither allocates the provider nor tears down someone else's host.
    cancelled = 0
    if !EntityCanvasStart(true) || entity_canvas_ready { return 8 }
    if !EntityCanvasStop() { return 13 }
    if cancelled != 0 || closed != 3 { return 9 }
    return 0
}
'''
fixture = work / 'lifecycle.zi'
fixture.write_text(source)
ziran = os.environ.get('ZIRAN', str(root / 'scripts/ziran.sh'))
subprocess.run([ziran, 'build', '--target=c', '--exe', '--root', str(work), '--entry', 'lifecycle:main',
                '-o', str(work / 'native'), str(fixture)], cwd=root, check=True)
subprocess.run([str(work / 'native/lifecycle')], cwd=root, check=True)
print('Canvas lifecycle failure local tests passed: partial open, save refusal, terminal cleanup, repeated stop and mini')

# Compile the real provider teardown separately: its sign-in-method discovery
# owns a second transfer, independent of the normal signed account request.
provider_source = '''
Request :: struct { active: bool }
Transfer :: struct { slot: s32 }
Recovery :: struct { present: bool }
ManagementProvider :: struct {
    drive_pending: bool; handoff_pending: bool; bridge_operation: s32;
    pending_request: Request; transfer: Transfer; methods_transfer: Transfer;
    backup_status_request: Request; backup_status_transfer: Transfer;
    incoming: Recovery; document: string;
}
busy: [8]bool;
cancelled: s32;
DriveBackupCancel :: () { cancelled |= 1 }
AccountHandoffCancel :: () { cancelled |= 2 }
SignInBridgeCancel :: () { cancelled |= 4 }
CancelRequest :: (request: *Request) { if request.active { cancelled |= 8 }; request.active = false }
HttpTransferCancel :: (transfer: *Transfer) {
    if transfer.slot > 0 {
        busy[transfer.slot - 1] = false
        cancelled |= ifx transfer.slot == 1 then 16 else 32
        transfer.slot = 0
    }
}
ProviderOnlineForget :: (provider: *ManagementProvider) { cancelled |= 64 }
ProviderPasskeyForget :: (provider: *ManagementProvider) { cancelled |= 128 }
RecoveryClear :: (recovery: *Recovery) { recovery.present = false; cancelled |= 256 }
EntityFree :: (value: string) { if value != "" { cancelled |= 512 } }
'''
provider_source += function(root / 'src/native_management.zi', 'ProviderClose')
provider_source += '''
main :: () -> s32 {
    provider: ManagementProvider
    // Repeated reopen/dispose must release every job before losing its handle.
    // More than eight cycles catches the simulated browser slot exhaustion.
    for iteration: 0..11 {
        if busy[0] || busy[1] || busy[2] { return 1 }
        busy[0] = true
        busy[1] = true
        busy[2] = true
        provider = ManagementProvider.{.drive_pending = true, .handoff_pending = true,
            .bridge_operation = 1, .pending_request = Request.{true},
            .transfer = Transfer.{1}, .methods_transfer = Transfer.{2},
            .backup_status_request = Request.{true}, .backup_status_transfer = Transfer.{3},
            .incoming = Recovery.{true}, .document = "allocated"}
        cancelled = 0
        ProviderClose(*provider)
        if cancelled != 1023 || busy[0] || busy[1] || busy[2] { return 2 }
        if provider.transfer.slot != 0 || provider.methods_transfer.slot != 0 ||
            provider.backup_status_transfer.slot != 0 || provider.backup_status_request.active ||
            provider.pending_request.active || provider.incoming.present || provider.document != "" { return 3 }
        ProviderClose(*provider)
        if busy[0] || busy[1] || busy[2] { return 4 }
    }
    return 0
}
'''
provider_fixture = work / 'provider_close.zi'
provider_fixture.write_text(provider_source)
subprocess.run([ziran, 'build', '--target=c', '--exe', '--root', str(work), '--entry', 'provider_close:main',
                '-o', str(work / 'provider-native'), str(provider_fixture)], cwd=root, check=True)
subprocess.run([str(work / 'provider-native/provider_close')], cwd=root, check=True)
print('ProviderClose local tests passed: independent request/methods/backup-status transfers, repeated close/reopen, no retained jobs')
