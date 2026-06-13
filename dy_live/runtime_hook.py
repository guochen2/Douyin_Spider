import os
import sys

import warnings

warnings.filterwarnings('ignore', message='.*doesn\'t match a supported version.*')

if sys.platform == 'win32' and getattr(sys, 'frozen', False):
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(936)
        ctypes.windll.kernel32.SetConsoleCP(936)
    except Exception:
        pass

    base = os.path.dirname(getattr(sys, '_MEIPASS', sys.executable))
    if not os.path.isdir(base):
        base = os.path.dirname(sys.executable)
    node_dir = os.path.join(os.path.dirname(sys.executable), 'tools', 'node')
    if os.path.isdir(node_dir):
        os.environ['PATH'] = node_dir + os.pathsep + os.environ.get('PATH', '')


def set_static_path():
    if hasattr(sys, '_MEIPASS'):
        os.environ['APP_STATIC_PATH'] = sys._MEIPASS
    else:
        os.environ['APP_STATIC_PATH'] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


set_static_path()

try:
    from utils.console_util import setup_console_utf8
    setup_console_utf8()
except Exception:
    pass
