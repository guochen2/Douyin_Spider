import builtins
import io
import os
import sys

_CONFIGURED = False
_ORIGINAL_PRINT = builtins.print

_STDOUT_HANDLE = -11
_STDERR_HANDLE = -12


def _write_console(text, stderr=False):
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(_STDERR_HANDLE if stderr else _STDOUT_HANDLE)
        if not handle or handle == ctypes.c_void_p(-1).value:
            return False
        written = wintypes.DWORD()
        ok = kernel32.WriteConsoleW(
            handle,
            text,
            len(text),
            ctypes.byref(written),
            None,
        )
        return bool(ok)
    except Exception:
        return False


def _set_console_codepage(codepage):
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(codepage)
        kernel32.SetConsoleCP(codepage)
    except Exception:
        pass


def _reconfigure_stream(stream, encoding):
    if stream is None:
        return None
    if hasattr(stream, 'reconfigure'):
        try:
            stream.reconfigure(encoding=encoding, errors='replace')
            return None
        except Exception:
            pass
    try:
        return io.TextIOWrapper(
            stream.buffer,
            encoding=encoding,
            errors='replace',
            line_buffering=True,
        )
    except Exception:
        return None


def _patch_print_winconsole():
    if getattr(builtins, '_douyin_print_patched', False):
        return

    def _win_print(*args, **kwargs):
        file = kwargs.get('file', sys.stdout)
        if file in (sys.stdout, sys.stderr):
            sep = kwargs.get('sep', ' ')
            end = kwargs.get('end', '\n')
            text = sep.join(str(a) for a in args) + end
            if _write_console(text, stderr=file is sys.stderr):
                return
        _ORIGINAL_PRINT(*args, **kwargs)

    builtins.print = _win_print
    builtins._douyin_print_patched = True


def setup_console_utf8():
    """Windows 控制台中文输出适配。"""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    if sys.platform != 'win32':
        return

    frozen = getattr(sys, 'frozen', False)
    try:
        from utils.pack_env import is_packaged
        frozen = frozen or is_packaged()
    except Exception:
        pass
    if frozen:
        _set_console_codepage(936)
        _patch_print_winconsole()
        return

    encoding = 'utf-8'
    _set_console_codepage(65001)
    os.environ['PYTHONIOENCODING'] = encoding
    for name in ('stdout', 'stderr'):
        stream = getattr(sys, name, None)
        wrapper = _reconfigure_stream(stream, encoding)
        if wrapper is not None:
            setattr(sys, name, wrapper)
