"""Exercise the public entry boundary without changing a desktop or agent."""
import configparser
import shlex
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from zcall_omarchy import cli


class PanelEntry(unittest.TestCase):
    def invoke(self, args):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['zcall-omarchy', *args]), contextlib.redirect_stdout(output):
            code = cli.main(ROOT)
        return code, json.loads(output.getvalue()) if output.getvalue() else None

    def test_desktop_launcher_uses_the_public_cli_and_its_own_icon(self):
        entry = configparser.ConfigParser(interpolation=None)
        entry.read(ROOT / 'share/zcall-omarchy.desktop')
        arguments = shlex.split(entry['Desktop Entry']['Exec'])
        self.assertEqual(arguments[0], 'zcall-omarchy')
        with patch.object(cli, 'show_panel') as show, patch.object(cli, 'Client') as client:
            code, value = self.invoke(arguments[1:])
            self.assertEqual((code, value), (0, None))
            show.assert_called_once_with(ROOT, None)
            client.assert_not_called()
        icon = entry['Desktop Entry']['Icon']
        self.assertEqual(icon, 'zcall-omarchy')
        self.assertTrue((ROOT / 'share/icons/hicolor/scalable/apps' / (icon + '.svg')).is_file())

    def test_snapshot_is_only_the_local_backend_contract(self):
        client = Mock()
        with patch.object(cli, 'Client', return_value=client), patch.object(cli.backend, 'snapshot', return_value={'schema_version': 1}) as snapshot:
            code, value = self.invoke(['--config', '/tmp/isolated.conf', 'panel', 'snapshot', '--period', '7d', '--provider', 'fixture'])
            self.assertEqual((code, value), (0, {'schema_version': 1}))
            snapshot.assert_called_once_with(client, '7d', 'fixture')
            client.call.assert_not_called()

    def test_action_payload_is_data_not_shell_or_global_arguments(self):
        payload = {'agent': 'fixture', 'route': 'literal;$(never)'}
        client = Mock()
        with patch.object(cli, 'Client', return_value=client), patch.object(cli.backend, 'action', return_value={'ok': False, 'error': 'Unsupported'}) as action:
            code, value = self.invoke(['panel', 'action', 'agent.route', '--payload', json.dumps(payload)])
            self.assertEqual(code, 0)
            self.assertFalse(value['ok'])
            action.assert_called_once_with(client, 'agent.route', payload)

    def test_quota_action_preserves_the_selected_opaque_account(self):
        payload = {'account': 'fixture:opaque#slot'}
        client = Mock()
        with patch.object(cli, 'Client', return_value=client), patch.object(cli.backend, 'action', return_value={'ok': False, 'error_code': 'timeout'}) as action:
            code, value = self.invoke(['panel', 'action', 'quota.refresh', '--payload', json.dumps(payload)])
            self.assertEqual((code, value['error_code']), (0, 'timeout'))
            action.assert_called_once_with(client, 'quota.refresh', payload)
            client.call.assert_not_called()

    def test_invalid_and_oversized_payloads_do_not_reach_action(self):
        for payload in ('{bad', ' ' * 4097):
            with self.subTest(payload=payload[:10]), patch.object(cli, 'Client'), patch.object(cli.backend, 'action') as action, contextlib.redirect_stderr(io.StringIO()):
                code, _ = self.invoke(['panel', 'action', 'agent.revert', '--payload', payload])
                self.assertEqual(code, 1)
                action.assert_not_called()

    def test_native_show_uses_one_existing_ipc_target(self):
        with patch.object(cli.shutil, 'which', return_value='/usr/bin/omarchy-shell'), patch.object(cli.subprocess, 'run', return_value=Mock(returncode=0, stdout='ok\n')) as run, patch.object(cli, 'launch') as launch:
            cli.show_panel(ROOT)
            self.assertEqual(run.call_args.args[0], ['/usr/bin/omarchy-shell', 'shell', 'summon', 'lightjunction.zcall', '{}'])
            self.assertNotIn('shell', run.call_args.kwargs)
            launch.assert_not_called()

    def test_unregistered_bar_widget_acknowledgement_uses_terminal_fallback(self):
        for reply in ('unknown\n', '', 'unexpected'):
            with self.subTest(reply=reply), patch.object(cli.shutil, 'which', return_value='/usr/bin/omarchy-shell'), patch.object(cli.subprocess, 'run', return_value=Mock(returncode=0, stdout=reply)), patch.object(cli, 'launch') as launch:
                cli.show_panel(ROOT)
                launch.assert_called_once_with(ROOT, 'menu', None)

    def test_missing_shell_or_custom_configuration_uses_terminal_fallback(self):
        for config, found, failure in [(None, None, False), (None, '/bin/shell', True), ('/tmp/other.conf', '/bin/shell', False)]:
            with self.subTest(config=config, found=found), patch.object(cli.shutil, 'which', return_value=found), patch.object(cli.subprocess, 'run', side_effect=subprocess.TimeoutExpired('test', 4) if failure else None) as run, patch.object(cli, 'launch') as launch:
                cli.show_panel(ROOT, config)
                launch.assert_called_once_with(ROOT, 'menu', config)
                if config or not found:
                    run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
