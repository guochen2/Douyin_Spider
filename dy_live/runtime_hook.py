import sys
import os

from utils.console_util import setup_console_utf8

def set_static_path():
    if hasattr(sys, '_MEIPASS'):
        os.environ['APP_STATIC_PATH'] = sys._MEIPASS
    else:
        os.environ['APP_STATIC_PATH'] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

set_static_path()
setup_console_utf8()