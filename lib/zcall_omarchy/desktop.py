"""Focus the optional GUI through Omarchy, or launch it once during startup."""
import fcntl
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

from .core import Error


def _focus(helper):
    try:
        return subprocess.run([helper, '^zcall-gui$'], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=2, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def open_gui():
    """Return False for a terminal fallback. No persistent process or lock owner."""
    binary = shutil.which('zcall-gui')
    helper = shutil.which('omarchy-hyprland-focus-app')
    if not binary or not helper:
        return False
    if _focus(helper):
        return True
    base = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid())))
    directory = base / 'zcall-omarchy'
    try:
        directory.mkdir(mode=0o700, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Error('The frontend runtime directory is not private.')
        fd = os.open(directory / 'gui-start.lock', os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    except OSError:
        return False
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Error('The frontend startup lock is not private.')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Another explicit click is already opening the GUI. Do not spawn.
            return True
        if _focus(helper):
            return True
        try:
            child = subprocess.Popen([binary], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        except OSError:
            return False
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if _focus(helper):
                return True
            if child.poll() is not None:
                return False
            time.sleep(0.1)
        return child.poll() is None
    finally:
        os.close(fd)
