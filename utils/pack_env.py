import os
import sys


def is_packaged():
    if getattr(sys, 'frozen', False):
        return True
    try:
        import __main__
        if getattr(__main__, '__compiled__', None) is not None:
            return True
    except Exception:
        pass
    return bool(os.getenv('NUITKA_PACKAGE'))


def app_dir():
    if is_packaged() or getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return app_dir()
