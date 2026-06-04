import sys
import os

def set_static_path():
    if hasattr(sys, '_MEIPASS'):
        os.environ['APP_STATIC_PATH'] = sys._MEIPASS
    else:
        os.environ['APP_STATIC_PATH'] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

set_static_path()