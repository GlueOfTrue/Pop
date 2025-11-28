from __future__ import annotations

"""
macOS local authentication hook.
Tries biometrics via LocalAuthentication (Touch ID) using osascript -l JavaScript,
falls back to sudo -v prompt if biometrics unavailable.
Returns True on successful auth, False otherwise.
"""

import os
import subprocess
from typing import Optional


def _auth_via_local_auth(reason: str, timeout: int) -> Optional[bool]:
    """
    Use JavaScript for Automation to call LocalAuthentication.
    Returns True/False, or None if failed/unavailable so we can fall back.
    """
    script = r'''
ObjC.import('LocalAuthentication');
ObjC.import('dispatch');
ObjC.import('Foundation');

function println(s) { $.NSFileHandle.fileHandleWithStandardOutput.writeData($.NSString.alloc.initWithString(s + "\n").dataUsingEncoding($.NSUTF8StringEncoding)); }

var ctx = $.LAContext.alloc.init();
var err = Ref();
// Allow biometrics OR password in the system sheet.
var policy = $.LAPolicyDeviceOwnerAuthentication;

if (!ctx.canEvaluatePolicyError(policy, err)) {
  println("NO_BIOMETRICS");
  $.exit(3);
}

var ok = false;
var sem = $.dispatch_semaphore_create(0);
ctx.evaluatePolicyLocalizedReasonReply(policy, ObjC.wrap("Authenticate to %(reason)s"), function(success, error){
  ok = success;
  $.dispatch_semaphore_signal(sem);
});

$.dispatch_semaphore_wait(sem, $.DISPATCH_TIME_FOREVER);
println(ok ? "OK" : "DENY");
$.exit(ok ? 0 : 1);
'''.replace("%(reason)s", reason.replace('"', '\\"'))

    try:
        proc = subprocess.run(
            ["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if proc.returncode == 0:
        return True
    # 3 -> cannot evaluate; fall back to sudo
    if proc.returncode == 3:
        return None
    # 1 or others -> user denied/canceled
    return False


def _auth_via_sudo(reason: str, timeout: int) -> bool:
    sudo = "/usr/bin/sudo"
    if not os.path.exists(sudo):
        return False
    prompt = f"[gs-backup] Authenticate to {reason}: "
    subprocess.run([sudo, "-k"], check=False)
    try:
        proc = subprocess.run(
            [sudo, "-p", prompt, "-v"],
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def require_local_auth(action: str, timeout: int = 20) -> bool:
    """
    Attempt Touch ID biometric prompt; fall back to sudo password prompt.
    """
    bio = _auth_via_local_auth(action, timeout)
    if bio is True:
        return True
    # On failure or unavailability, fall back to sudo prompt.
    return _auth_via_sudo(action, timeout)
