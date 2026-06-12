from __future__ import annotations

"""
macOS local authentication hook.
Tries biometrics via LocalAuthentication (Touch ID) using osascript -l JavaScript,
falls back to sudo -v prompt if biometrics unavailable.
Returns True on successful auth, False otherwise.
"""

import tempfile
import textwrap
import json
import os
import subprocess
from typing import Optional


def _auth_via_swift_la(reason: str, timeout: int) -> Optional[bool]:
    """
    Use Swift + LocalAuthentication to show the system Touch ID/password sheet.
    Returns True/False, or None if failed/unavailable so we can fall back.
    """
    script = textwrap.dedent(
        f"""
        import LocalAuthentication
        import Foundation

        let reason = CommandLine.arguments.dropFirst().joined(separator: " ")
        let context = LAContext()
        var error: NSError?

        let policy = LAPolicy.deviceOwnerAuthentication
        guard context.canEvaluatePolicy(policy, error: &error) else {{
            print("UNAVAILABLE")
            exit(3)
        }}

        let sem = DispatchSemaphore(value: 0)
        var ok = false

        context.evaluatePolicy(policy, localizedReason: reason) {{
            success, _ in
            ok = success
            sem.signal()
        }}

        // Wait up to 30 seconds
        _ = sem.wait(timeout: .now() + .seconds(30))
        exit(ok ? 0 : 1)
        """
    )

    with tempfile.NamedTemporaryFile("w", suffix=".swift", delete=False) as tmp:
        tmp.write(script)
        tmp_path = tmp.name

    swift_bin = "/usr/bin/swift"
    try:
        proc = subprocess.run(
            [swift_bin, tmp_path, reason],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    if proc.returncode == 0:
        return True
    if proc.returncode == 3:
        return None
    return False


def _auth_via_local_auth(reason: str, timeout: int) -> Optional[bool]:
    """
    Use JavaScript for Automation to call LocalAuthentication.
    Returns True/False, or None if failed/unavailable so we can fall back.
    """
    reason_literal = json.dumps(f"Authenticate to {reason}")
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
ctx.evaluatePolicyLocalizedReasonReply(policy, ObjC.wrap(%(reason_literal)s), function(success, error){
  ok = success;
  $.dispatch_semaphore_signal(sem);
});

$.dispatch_semaphore_wait(sem, $.DISPATCH_TIME_FOREVER);
println(ok ? "OK" : "DENY");
$.exit(ok ? 0 : 1);
'''.replace("%(reason_literal)s", reason_literal)

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
    # Try Swift LA first for a true system sheet.
    bio = _auth_via_swift_la(action, timeout)
    if bio is None:
        bio = _auth_via_local_auth(action, timeout)
    if bio is True:
        return True
    # On failure or unavailability, fall back to sudo prompt.
    return _auth_via_sudo(action, timeout)
