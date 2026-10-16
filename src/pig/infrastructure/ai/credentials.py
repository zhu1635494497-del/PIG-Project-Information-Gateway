"""Windows Credential Manager boundary; API keys never enter Project SQLite."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys


class CredentialFailure(RuntimeError):
    pass


if sys.platform == "win32":
    class _FILETIME(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    class _CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
            ("LastWritten", _FILETIME), ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]


class WindowsCredentialStore:
    """Only fixed PIG provider targets; local-machine persistence for this Windows user."""

    @staticmethod
    def _target(provider: str) -> str:
        if provider not in ("openai", "deepseek"):
            raise CredentialFailure("unsupported provider")
        return f"PIG.ProjectInformationGateway.API.{provider}"

    @staticmethod
    def _api():
        if sys.platform != "win32":
            raise CredentialFailure("Windows Credential Manager is unavailable")
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
        api.CredReadW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        api.CredFree.restype = None
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        return api

    def put(self, provider: str, secret: str) -> None:
        target = self._target(provider)
        if not secret or len(secret) > 1024 or any(ord(char) < 32 for char in secret):
            raise CredentialFailure("invalid API key")
        api = self._api()
        blob = bytearray(secret.encode("utf-16-le"))
        try:
            raw = (ctypes.c_ubyte * len(blob)).from_buffer(blob)
            credential = _CREDENTIALW()
            credential.Type = 1
            credential.TargetName = target
            credential.CredentialBlobSize = len(blob)
            credential.CredentialBlob = ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte))
            credential.Persist = 2
            credential.UserName = "PIG"
            if not api.CredWriteW(ctypes.byref(credential), 0):
                raise CredentialFailure("credential store write failed")
        finally:
            blob[:] = b"\x00" * len(blob)

    def get(self, provider: str) -> str | None:
        target = self._target(provider)
        api = self._api()
        pointer = ctypes.POINTER(_CREDENTIALW)()
        if not api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:
                return None
            raise CredentialFailure("credential store read failed")
        try:
            value = pointer.contents
            if value.CredentialBlobSize > 8192 or value.CredentialBlobSize % 2:
                raise CredentialFailure("credential store entry is invalid")
            return ctypes.string_at(value.CredentialBlob,
                                    value.CredentialBlobSize).decode("utf-16-le")
        finally:
            api.CredFree(pointer)

    def delete(self, provider: str) -> None:
        api = self._api()
        if not api.CredDeleteW(self._target(provider), 1, 0):
            if ctypes.get_last_error() != 1168:
                raise CredentialFailure("credential store delete failed")
