import os
import sys
import subprocess
import json

from utils.console_util import setup_console_utf8

setup_console_utf8()

def _app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


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


def start_redis_listener(control_channel):
    control_channel = control_channel.strip() or 'dy_live:control'

    try:
        import redis  # noqa: F401
    except ImportError:
        print(
            "错误: 当前 Python 环境缺少 redis 模块。\n"
            "请激活正确的 conda 环境（如 p310）后重试，或执行：pip install redis"
        )
        sys.exit(1)

    config = load_config()
    config.update({'redis_control_channel': control_channel})
    save_config(config)

    manager_exe_path = os.path.join(_app_dir(), 'live_manager.exe')
    manager_py_path = os.path.join(_app_dir(), 'dy_live', 'live_manager.py')

    if not os.path.exists(manager_py_path) and not os.path.exists(manager_exe_path):
        print("错误: 未找到 live_manager.exe 或 live_manager.py")
        sys.exit(1)

    run_in_foreground = (
        os.path.exists('/.dockerenv')
        or os.getenv('RUN_IN_FOREGROUND', '').lower() in ('1', 'true', 'yes')
        or sys.platform != 'win32'
    )

    try:
        if run_in_foreground:
            print("Redis 监听服务启动中...")
            print(f"控制频道: {control_channel}")
            print('控制消息: {"action": "start"|"stop", "live_id": "房间号", "cookie": "..."}')
            from dy_live.live_manager import run_from_config
            run_from_config()
            return

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
            cwd=os.path.dirname(__file__),
        )
        print("Redis 监听服务已启动")
        print(f"控制频道: {control_channel}")
        print('控制消息: {"action": "start"|"stop", "live_id": "房间号", "cookie": "..."}')
    except Exception as e:
        print(f"错误: 启动失败 - {e}")
        sys.exit(1)


def main():
    config = load_config()
    control_channel = config.get('redis_control_channel', 'dy_live:control')
    start_redis_listener(control_channel)


if __name__ == '__main__':
    main()
