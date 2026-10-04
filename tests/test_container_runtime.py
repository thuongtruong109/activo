from __future__ import annotations

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from license_admin.container_runtime import config, desktop, healthcheck
from tests.workspace_temp import workspace_temp_dir


class ContainerConfigurationTests(unittest.TestCase):
    def test_missing_password_fails_closed(self) -> None:
        for environment in ({}, {"ACTIVO_VNC_PASSWORD": ""}):
            with self.subTest(environment=environment), self.assertRaises(config.ContainerConfigurationError):
                config.load_config(environment)

    def test_rejects_truncation_unicode_whitespace_and_default_passwords(self) -> None:
        for password in ("short", "long-password", "abcdefgh9", "12345678", "password", "CHANGEme", "qwertyui", "ab cd123", "abcdefg\n", "abcdefgé"):
            with self.subTest(password=password), self.assertRaises(config.ContainerConfigurationError) as caught:
                config.load_config({"ACTIVO_VNC_PASSWORD": password})
            self.assertNotIn(password, str(caught.exception))

    def test_valid_password_is_not_in_repr(self) -> None:
        result = config.load_config({"ACTIVO_VNC_PASSWORD": "q9#Vs7!B"})
        self.assertNotIn(result.password, repr(result))
        self.assertEqual(result.display, ":99")
        self.assertEqual(result.screen, "1440x900x24")

    def test_rejects_remote_display_and_invalid_screen(self) -> None:
        for key, values in {
            "DISPLAY": ("", "host:99", ":99.0", ":-1", ":9999"),
            "ACTIVO_SCREEN": ("", "8193x900x24", "63x900x24", "1440x900x32", "900x900x24 -ac", "99999x99999x24"),
        }.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(config.ContainerConfigurationError):
                    config.load_config({"ACTIVO_VNC_PASSWORD": "q9#Vs7!B", key: value})

    def test_configuration_cli_does_not_print_secret(self) -> None:
        output = io.StringIO()
        secret = "never-print-this"
        with patch.dict(os.environ, {"ACTIVO_VNC_PASSWORD": secret}, clear=True), redirect_stderr(output):
            self.assertEqual(config.main(), 78)
        self.assertNotIn(secret, output.getvalue())


class DesktopSupervisorTests(unittest.TestCase):
    def test_direct_start_without_password_creates_nothing_and_spawns_nothing(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(desktop.tempfile, "mkstemp") as create, patch.object(desktop.subprocess, "Popen") as spawn, redirect_stderr(io.StringIO()):
            self.assertEqual(desktop.main(), 78)
        create.assert_not_called()
        spawn.assert_not_called()

    def test_failed_password_store_is_cleaned_without_secret_in_log(self) -> None:
        with workspace_temp_dir() as directory:
            output = io.StringIO()
            with patch.dict(os.environ, {"ACTIVO_VNC_PASSWORD": "q9#Vs7!B", "XDG_RUNTIME_DIR": directory}, clear=True), patch.object(desktop.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), patch.object(desktop.subprocess, "Popen") as spawn, redirect_stderr(output):
                self.assertEqual(desktop.main(), 1)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertNotIn("q9#Vs7!B", output.getvalue())
            spawn.assert_not_called()

    def test_store_timeout_exception_does_not_leak_argv(self) -> None:
        with workspace_temp_dir() as directory:
            output = io.StringIO()
            with patch.dict(os.environ, {"ACTIVO_VNC_PASSWORD": "q9#Vs7!B", "XDG_RUNTIME_DIR": directory}, clear=True), patch.object(desktop.subprocess, "run", side_effect=subprocess.TimeoutExpired(["x11vnc", "q9#Vs7!B"], 10)), redirect_stderr(output):
                self.assertEqual(desktop.main(), 1)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertNotIn("q9#Vs7!B", output.getvalue())

    def test_dead_service_stops_everything_and_cleans_auth(self) -> None:
        with workspace_temp_dir() as directory:
            processes = [MagicMock() for _ in range(5)]
            for process in processes:
                process.poll.return_value = None
            processes[2].poll.return_value = 1  # VNC exits after starting.
            with patch.dict(os.environ, {"ACTIVO_VNC_PASSWORD": "q9#Vs7!B", "XDG_RUNTIME_DIR": directory}, clear=True), patch.object(desktop.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), patch.object(desktop.subprocess, "Popen", side_effect=processes) as spawn, patch.object(Path, "is_socket", return_value=True), patch.object(desktop, "stop_processes") as stop, redirect_stderr(io.StringIO()):
                self.assertEqual(desktop.main(), 1)
            stop.assert_called_once_with(processes)
            self.assertEqual(list(Path(directory).iterdir()), [])
            for call in spawn.call_args_list:
                self.assertNotIn("ACTIVO_VNC_PASSWORD", call.kwargs["env"])
                self.assertTrue(call.kwargs["start_new_session"])
            vnc_command = spawn.call_args_list[2].args[0]
            self.assertIn("-rfbauth", vnc_command)
            self.assertIn("-localhost", vnc_command)
            self.assertNotIn("-nopw", vnc_command)

    def test_cleanup_terminates_all_before_waiting_then_force_kills_timeout(self) -> None:
        processes = [MagicMock(), MagicMock()]
        processes[0].wait.side_effect = [subprocess.TimeoutExpired([], 5), 0]
        with patch.object(desktop, "signal_process_group") as signal_group:
            desktop.stop_processes(processes)
        self.assertEqual(signal_group.call_args_list[0].args, (processes[1],))
        self.assertEqual(signal_group.call_args_list[1].args, (processes[0],))
        self.assertEqual(signal_group.call_args_list[2].kwargs, {"force": True})


class DesktopHealthTests(unittest.TestCase):
    def test_rfb_allows_only_authenticated_security(self) -> None:
        for types, allowed in ((b"\x02", True), (b"\x01", False), (b"\x01\x02", False), (b"", False), (b"\x13", False)):
            connection = MagicMock()
            connection.recv.side_effect = [b"RFB 003.008\n", bytes([len(types)]), types]
            with self.subTest(types=types), patch.object(healthcheck.socket, "create_connection") as connect:
                connect.return_value.__enter__.return_value = connection
                if allowed:
                    healthcheck.require_vnc_authentication()
                else:
                    with self.assertRaises(RuntimeError):
                        healthcheck.require_vnc_authentication()
            connection.sendall.assert_called_once_with(b"RFB 003.008\n")

    def test_partial_rfb_reads_and_disconnect(self) -> None:
        connection = MagicMock()
        connection.recv.side_effect = [b"abc", b"d"]
        self.assertEqual(healthcheck.receive_exact(connection, 4), b"abcd")
        connection.recv.side_effect = [b"abc", b""]
        with self.assertRaises(RuntimeError):
            healthcheck.receive_exact(connection, 4)

    def test_unexpected_rfb_version_fails_closed(self) -> None:
        with patch.object(healthcheck.socket, "create_connection") as connect:
            connect.return_value.__enter__.return_value.recv.return_value = b"RFB 003.003\n"
            with self.assertRaises(RuntimeError):
                healthcheck.require_vnc_authentication()

    def test_health_requires_vnc_and_http_without_ambient_proxy(self) -> None:
        for status, expected in ((200, 0), (401, 1), (503, 1)):
            with self.subTest(status=status), patch.object(healthcheck, "require_vnc_authentication"), patch.object(healthcheck, "ProxyHandler") as proxy, patch.object(healthcheck, "build_opener") as opener:
                opener.return_value.open.return_value.__enter__.return_value.status = status
                self.assertEqual(healthcheck.main(), expected)
                proxy.assert_called_once_with({})
        with patch.object(healthcheck, "require_vnc_authentication", side_effect=RuntimeError), patch.object(healthcheck, "build_opener") as opener:
            self.assertEqual(healthcheck.main(), 1)
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
