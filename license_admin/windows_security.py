"""Per-user filesystem protection for mutable application data."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path

from issue_license import LicenseIssueError


_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_SDDL_REVISION_1 = 1
_DACL_SECURITY_INFORMATION = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000


class _SidAndAttributes(ctypes.Structure):
    _fields_ = [("sid", ctypes.c_void_p), ("attributes", wintypes.DWORD)]


class _TokenUser(ctypes.Structure):
    _fields_ = [("user", _SidAndAttributes)]


def _windows_error(message: str, code: int | None = None) -> LicenseIssueError:
    error_code = code if code is not None else ctypes.get_last_error()
    return LicenseIssueError(
        f"{message}: {ctypes.FormatError(error_code).strip()} (Windows error {error_code})."
    )


def _current_user_sid() -> str:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        raise _windows_error("Unable to open the current Windows access token")
    try:
        required = wintypes.DWORD()
        advapi32.GetTokenInformation(
            token, _TOKEN_USER, None, 0, ctypes.byref(required)
        )
        if required.value == 0:
            raise _windows_error("Unable to size the current Windows user SID")
        buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token,
            _TOKEN_USER,
            buffer,
            required,
            ctypes.byref(required),
        ):
            raise _windows_error("Unable to read the current Windows user SID")
        token_user = ctypes.cast(buffer, ctypes.POINTER(_TokenUser)).contents
        sid_text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(
            token_user.user.sid, ctypes.byref(sid_text)
        ):
            raise _windows_error("Unable to format the current Windows user SID")
        try:
            return str(sid_text.value)
        finally:
            kernel32.LocalFree(sid_text)
    finally:
        kernel32.CloseHandle(token)


def _restrict_windows_dacl(path: Path, *, directory: bool) -> None:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.ULONG),
    ]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = (
        wintypes.BOOL
    )
    advapi32.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi32.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi32.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD
    sid = _current_user_sid()
    inheritance = "OICI" if directory else ""
    descriptor_text = f"D:P(A;{inheritance};FA;;;{sid})"
    descriptor = ctypes.c_void_p()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        descriptor_text,
        _SDDL_REVISION_1,
        ctypes.byref(descriptor),
        None,
    ):
        raise _windows_error("Unable to build a private Windows DACL")
    try:
        present = wintypes.BOOL()
        defaulted = wintypes.BOOL()
        dacl = ctypes.c_void_p()
        if not advapi32.GetSecurityDescriptorDacl(
            descriptor,
            ctypes.byref(present),
            ctypes.byref(dacl),
            ctypes.byref(defaulted),
        ) or not present.value:
            raise _windows_error("Unable to read the private Windows DACL")
        result = advapi32.SetNamedSecurityInfoW(
            str(path),
            1,  # SE_FILE_OBJECT
            _DACL_SECURITY_INFORMATION | _PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            dacl,
            None,
        )
        if result != 0:
            raise _windows_error(
                f"Unable to restrict access to {path}", int(result)
            )
    finally:
        kernel32.LocalFree(descriptor)


def restrict_to_current_user(path: Path) -> None:
    """Remove inherited access and grant only the current user full control."""
    try:
        is_directory = path.is_dir()
    except OSError as exc:
        raise LicenseIssueError(f"Unable to inspect security target {path}: {exc}") from exc
    if os.name == "nt":
        _restrict_windows_dacl(path, directory=is_directory)
        return
    try:
        path.chmod(0o700 if is_directory else 0o600)
    except OSError as exc:
        raise LicenseIssueError(f"Unable to restrict access to {path}: {exc}") from exc


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction()) if callable(is_junction) else False


def restrict_tree_to_current_user(root: Path) -> None:
    """Apply the per-user DACL to an existing directory and all descendants."""
    if _is_link_like(root) or not root.is_dir():
        raise LicenseIssueError(f"Security root is not a directory: {root}")
    descendants: list[Path] = []
    try:
        for directory, directory_names, file_names in os.walk(
            root,
            topdown=True,
            followlinks=False,
        ):
            current = Path(directory)
            for name in (*directory_names, *file_names):
                child = current / name
                if _is_link_like(child):
                    raise LicenseIssueError(
                        f"Refusing to change security through a link: {child}"
                    )
                descendants.append(child)
    except OSError as exc:
        raise LicenseIssueError(f"Unable to enumerate security root {root}: {exc}") from exc
    for path in sorted(
        descendants,
        key=lambda candidate: (len(candidate.parts), str(candidate)),
        reverse=True,
    ):
        restrict_to_current_user(path)
    restrict_to_current_user(root)

