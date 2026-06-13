import os
import sys
import traceback


def app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def setup_runtime_paths():
    if not getattr(sys, 'frozen', False):
        return
    base = app_dir()
    node_dir = os.path.join(base, 'tools', 'node')
    if os.path.isdir(node_dir):
        os.environ['PATH'] = node_dir + os.pathsep + os.environ.get('PATH', '')


def write_crash_log(text):
    log_path = os.path.join(app_dir(), 'DouyinLive.error.log')
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(text)
    except OSError:
        pass
    return log_path


def show_fatal_error(exc):
    text = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log_path = write_crash_log(text)

    try:
        print(text, file=sys.stderr)
    except Exception:
        pass

    try:
        if sys.platform == 'win32':
            import ctypes
            msg = f'{exc}\n\n详情已写入:\n{log_path}'
            ctypes.windll.user32.MessageBoxW(0, msg, 'DouyinLive 启动失败', 0x10)
    except Exception:
        pass

    if getattr(sys, 'frozen', False):
        try:
            input('\n按回车键退出...')
        except Exception:
            pass


def run_main(main_func):
    setup_runtime_paths()
    try:
        main_func()
    except SystemExit:
        raise
    except Exception as exc:
        show_fatal_error(exc)
        sys.exit(1)
