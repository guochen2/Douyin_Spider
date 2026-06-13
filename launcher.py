import sys
import warnings

warnings.filterwarnings('ignore', message='.*doesn\'t match a supported version.*')

import os
import subprocess
import json

DEFAULT_REDIS_PORT = 16380


def should_use_gui():
    if sys.platform != 'win32':
        return False
    if '--cli' in sys.argv or '--console' in sys.argv:
        return False
    if os.getenv('DOUYIN_LIVE_CLI', '').lower() in ('1', 'true', 'yes'):
        return False
    return True


if not should_use_gui():
    from utils.console_util import setup_console_utf8
    setup_console_utf8()


def _app_dir():
    from utils.pack_env import app_dir
    return app_dir()


CONFIG_FILE = os.path.join(_app_dir(), 'launcher_config.json')


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _ensure_embedded_redis(config):
    from utils.redis_bootstrap import should_start_embedded_redis, start_embedded_redis

    if not should_start_embedded_redis(config):
        return True
    if not start_embedded_redis(config):
        return False
    import utils.redis_util as redis_util_module
    redis_util_module.redis_util.reset()
    return True


def _pause_on_error():
    from utils.pack_env import is_packaged
    if is_packaged() or getattr(sys, 'frozen', False):
        if should_use_gui():
            return
        try:
            input('\n按回车键退出...')
        except Exception:
            pass


def start_redis_listener(control_channel, config=None):
    control_channel = control_channel.strip() or 'dy_live:control'
    config = config or load_config()

    try:
        import redis  # noqa: F401
    except ImportError:
        print(
            '错误: 当前 Python 环境缺少 redis 模块。\n'
            '请激活正确的 conda 环境（如 p310）后重试，或执行：pip install redis'
        )
        _pause_on_error()
        sys.exit(1)

    if not _ensure_embedded_redis(config):
        print('错误: 内置 Redis 启动失败，请检查 tools\\redis\\redis-server.exe 是否存在')
        _pause_on_error()
        sys.exit(1)

    config['embedded_redis'] = config.get('embedded_redis', True)
    config['redis_port'] = int(os.getenv('REDIS_PORT', config.get('redis_port', DEFAULT_REDIS_PORT)))

    from utils.redis_config import ensure_redis_password
    config['redis_password'] = ensure_redis_password(config)
    os.environ['REDIS_PASSWORD'] = config['redis_password']

    config.update({'redis_control_channel': control_channel})
    save_config(config)

    from utils.pack_env import is_packaged

    run_in_foreground = (
        os.getenv('DOUYIN_LIVE_FOREGROUND', '').lower() in ('1', 'true', 'yes')
        or os.getenv('DOUYIN_LIVE_GUI', '').lower() in ('1', 'true', 'yes')
        or is_packaged()
        or getattr(sys, 'frozen', False)
        or hasattr(sys, '_MEIPASS')
        or os.path.exists('/.dockerenv')
        or os.getenv('RUN_IN_FOREGROUND', '').lower() in ('1', 'true', 'yes')
        or sys.platform != 'win32'
    )

    try:
        if run_in_foreground:
            print('DouyinLive 启动中...')
            sys.stdout.flush()
            print('Redis 监听服务启动中...')
            print(f'控制频道: {control_channel}')
            print(f'Redis: {os.getenv("REDIS_HOST", "127.0.0.1")}:{os.getenv("REDIS_PORT", str(DEFAULT_REDIS_PORT))}')
            print('控制消息: {"action": "start"|"stop", "live_id": "房间号", "cookie": "..."}')
            sys.stdout.flush()
            try:
                from dy_live.live_manager import run_from_config
                run_from_config(config)
            finally:
                from utils.redis_bootstrap import stop_embedded_redis
                stop_embedded_redis()
                print('[redis] 内置 Redis 已停止')
            return

        manager_exe_path = os.path.join(_app_dir(), 'live_manager.exe')
        manager_py_path = os.path.join(_app_dir(), 'dy_live', 'live_manager.py')

        if not os.path.exists(manager_py_path) and not os.path.exists(manager_exe_path):
            print('错误: 未找到 live_manager.exe 或 live_manager.py')
            _pause_on_error()
            sys.exit(1)

        if os.path.exists(manager_exe_path):
            cmd_parts = [manager_exe_path]
        else:
            cmd_parts = [sys.executable, manager_py_path]

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= 1
        startupinfo.wShowWindow = 1
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        subprocess.Popen(
            cmd_parts,
            env=env,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            cwd=_app_dir(),
        )
        print('Redis 监听服务已启动')
        print(f'控制频道: {control_channel}')
        print('控制消息: {"action": "start"|"stop", "live_id": "房间号", "cookie": "..."}')
    except Exception as e:
        print(f'错误: 启动失败 - {e}')
        import traceback
        traceback.print_exc()
        _pause_on_error()
        sys.exit(1)


def main():
    if should_use_gui():
        os.environ['DOUYIN_LIVE_GUI'] = '1'
        os.environ['DOUYIN_LIVE_FOREGROUND'] = '1'
        from utils.launcher_gui import run_gui
        run_gui()
        return

    config = load_config()
    control_channel = config.get('redis_control_channel', 'dy_live:control')
    start_redis_listener(control_channel, config)


if __name__ == '__main__':
    from utils.app_bootstrap import run_main
    run_main(main)
