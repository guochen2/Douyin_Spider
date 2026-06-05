import io
import sys

_CONFIGURED = False


def setup_console_utf8():
    """Windows 控制台默认 GBK，强制使用 UTF-8 避免中文乱码。"""
    global _CONFIGURED
    if _CONFIGURED or sys.platform != 'win32':
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass

    for name in ('stdout', 'stderr'):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        encoding = getattr(stream, 'encoding', None)
        if encoding and encoding.lower().replace('-', '') == 'utf8':
            continue
        try:
            buffer = stream.buffer
        except AttributeError:
            continue
        try:
            setattr(
                sys,
                name,
                io.TextIOWrapper(
                    buffer,
                    encoding='utf-8',
                    errors='replace',
                    line_buffering=True,
                ),
            )
        except Exception:
            pass

    _CONFIGURED = True
