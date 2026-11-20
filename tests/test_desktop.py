import fcntl
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from zcall_omarchy import desktop
from zcall_omarchy.core import Error

class DesktopActivation(unittest.TestCase):
    def test_existing_gui_is_focused_without_starting_another(self):
        with patch.object(desktop.shutil, 'which', side_effect=['/bin/gui','/bin/focus']), patch.object(desktop, '_focus', return_value=True), patch.object(desktop.subprocess, 'Popen') as spawn:
            self.assertTrue(desktop.open_gui())
            spawn.assert_not_called()

    def test_missing_gui_uses_fallback(self):
        with patch.object(desktop.shutil, 'which', return_value=None):
            self.assertFalse(desktop.open_gui())

    def test_concurrent_startup_does_not_spawn_and_existing_lock_is_kept(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {'XDG_RUNTIME_DIR':temporary}):
            directory=Path(temporary)/'zcall-omarchy';directory.mkdir(mode=0o700)
            path=directory/'gui-start.lock'
            fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch.object(desktop.shutil,'which',side_effect=['/bin/gui','/bin/focus']),patch.object(desktop,'_focus',return_value=False),patch.object(desktop.subprocess,'Popen') as spawn:
                    self.assertTrue(desktop.open_gui());spawn.assert_not_called()
                self.assertTrue(path.exists())
            finally: os.close(fd)

    def test_safe_argv_start_releases_lock_after_window_appears(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {'XDG_RUNTIME_DIR':temporary}),patch.object(desktop.shutil,'which',side_effect=['/path with space/gui','/bin/focus']),patch.object(desktop,'_focus',side_effect=[False,False,True]),patch.object(desktop.subprocess,'Popen',return_value=Mock()) as spawn:
            self.assertTrue(desktop.open_gui())
            self.assertEqual(spawn.call_args.args[0],['/path with space/gui'])
            self.assertTrue(spawn.call_args.kwargs['close_fds'])
            self.assertNotIn('shell',spawn.call_args.kwargs)
            fd=os.open(Path(temporary)/'zcall-omarchy/gui-start.lock',os.O_RDWR)
            try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally: os.close(fd)

    def test_symlink_runtime_directory_is_not_used(self):
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'XDG_RUNTIME_DIR':temporary}),patch.object(desktop.shutil,'which',return_value='/bin/mock'),patch.object(desktop,'_focus',return_value=False):
            target=Path(temporary)/'other';target.mkdir()
            (Path(temporary)/'zcall-omarchy').symlink_to(target,target_is_directory=True)
            with self.assertRaises(Error): desktop.open_gui()
