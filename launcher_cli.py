import os
import sys
import subprocess
import json

from utils.console_util import setup_console_utf8

setup_console_utf8()

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'launcher_config.json')

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def on_start(control_channel):
    control_channel = control_channel.strip() or 'dy_live:control'

    config = load_config()
    config.update({
        'redis_control_channel': control_channel,
    })
    save_config(config)

    manager_exe_path = os.path.join(os.path.dirname(__file__), 'live_manager.exe')
    manager_py_path = os.path.join(os.path.dirname(__file__), 'dy_live', 'live_manager.py')

    if os.path.exists(manager_exe_path):
        cmd_parts = [manager_exe_path]
    elif os.path.exists(manager_py_path):
        cmd_parts = [sys.executable, manager_py_path]
    else:
        print("\n错误: 未找到 live_manager.exe 或 live_manager.py")
        input("按回车键退出...")
        return

    startupinfo = None
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= 1
        startupinfo.wShowWindow = 1

    try:
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
        print("\n成功: Redis 监听服务已启动！")
        print(f"控制频道: {control_channel}")
        print('控制消息: {"action": "start"|"stop", "live_id": "房间号", "cookie": "..."}')
        print("启动器将在 3 秒后关闭...")
        import time
        time.sleep(3)
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: 启动失败 - {str(e)}")
        input("按回车键退出...")

def main():
    os.system('cls' if sys.platform == 'win32' else 'clear')

    config = load_config()

    print("╔════════════════════════════════════════╗")
    print("║     抖音直播 Redis 监听启动器 v2.2     ║")
    print("╚════════════════════════════════════════╝")
    print()

    default_channel = config.get('redis_control_channel', 'dy_live:control')
    prompt = f"Redis 控制频道 ({default_channel}): "
    control_channel = input(prompt).strip()
    if not control_channel:
        control_channel = default_channel

    os.system('cls' if sys.platform == 'win32' else 'clear')

    print("╔════════════════════════════════════════╗")
    print("║              确认信息                  ║")
    print("╠════════════════════════════════════════╣")
    print(f"║ 控制频道: {control_channel[:28]}{'...' if len(control_channel) > 28 else ''}")
    print("║ 客户端通过 pub/sub 发送 start/stop     ║")
    print("╚════════════════════════════════════════╝")
    print()

    confirm = input("确认启动? (Y/N): ").strip().upper()
    if confirm == 'Y':
        on_start(control_channel)
    else:
        print("\n取消操作")
        input("按回车键退出...")

if __name__ == '__main__':
    main()
