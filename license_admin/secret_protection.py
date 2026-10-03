"""Current-user secret encryption backed by Windows DPAPI."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os

from issue_license import LicenseIssueError


SECRET_MAGIC = b"ACTIVO-DPAPI\x00\x01"
_ENTROPY = b"Activo License Admin private key v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x00000001


class _DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(value, len(value))
    return (
        _DataBlob(
            len(value),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        ),
        buffer,
    )


def _dpapi(value: bytes, *, protect: bool) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    source, source_buffer = _blob(value)
    entropy, entropy_buffer = _blob(_ENTROPY)
    output = _DataBlob()
    if protect:
        succeeded = crypt32.CryptProtectData(
            ctypes.byref(source),
            "Activo License Admin",
            ctypes.byref(entropy),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output),
        )
    else:
        description = wintypes.LPWSTR()
        succeeded = crypt32.CryptUnprotectData(
            ctypes.byref(source),
            ctypes.byref(description),
            ctypes.byref(entropy),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output),
        )
        if description:
            kernel32.LocalFree(description)
    # Keep the input buffers alive until the native call has returned.
    _ = source_buffer, entropy_buffer
    if not succeeded:
        error_code = ctypes.get_last_error()
        operation = "protect" if protect else "unprotect"
        raise LicenseIssueError(
            f"Windows DPAPI could not {operation} the private key: "
            f"{ctypes.FormatError(error_code).strip()} (Windows error {error_code})."
        )
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel32.LocalFree(output.data)


def is_protected_secret(value: bytes) -> bool:
    return value.startswith(SECRET_MAGIC)


def protect_secret(value: bytes) -> bytes:
    if not value:
        raise LicenseIssueError("Refusing to protect an empty secret.")
    if is_protected_secret(value):
        return value
    if os.name != "nt":
        return value
    return SECRET_MAGIC + _dpapi(value, protect=True)


def unprotect_secret(value: bytes) -> bytes:
    if not is_protected_secret(value):
        return value
    if os.name != "nt":
        raise LicenseIssueError(
            "This private key is protected by Windows DPAPI and can only be opened "
            "by the Windows user that imported it."
        )
    payload = value[len(SECRET_MAGIC) :]
    if not payload:
        raise LicenseIssueError("The DPAPI private-key envelope is empty.")
    return _dpapi(payload, protect=False)

