import os
import sys
import subprocess
import json

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

def on_start(redis_list_key, poll_interval):
    redis_list_key = redis_list_key.strip() or 'dy_live:rooms'

    try:
        poll_interval_val = float(poll_interval)
        if poll_interval_val <= 0:
            raise ValueError
    except ValueError:
        print("\n错误: 轮询间隔必须是大于 0 的数字")
        input("按回车键退出...")
        return

    config = load_config()
    config.update({
        'redis_list_key': redis_list_key,
        'poll_interval': poll_interval_val,
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
        subprocess.Popen(
            cmd_parts,
            env=os.environ.copy(),
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            cwd=os.path.dirname(__file__),
        )
        print("\n成功: Redis 监听服务已启动！")
        print(f"列表 Key: {redis_list_key}")
        print('列表项格式: {"live_id": "房间号", "cookie": "..."}')
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
    print("║     抖音直播 Redis 监听启动器 v2.1     ║")
    print("╚════════════════════════════════════════╝")
    print()

    default_redis_key = config.get('redis_list_key', 'dy_live:rooms')
    prompt = f"Redis 列表 Key ({default_redis_key}): "
    redis_list_key = input(prompt).strip()
    if not redis_list_key:
        redis_list_key = default_redis_key

    default_poll = str(config.get('poll_interval', 3))
    poll_interval = input(f"轮询间隔/秒 ({default_poll}): ").strip()
    if not poll_interval:
        poll_interval = default_poll

    os.system('cls' if sys.platform == 'win32' else 'clear')

    print("╔════════════════════════════════════════╗")
    print("║              确认信息                  ║")
    print("╠════════════════════════════════════════╣")
    print(f"║ Redis Key: {redis_list_key[:28]}{'...' if len(redis_list_key) > 28 else ''}")
    print(f"║ 轮询间隔: {poll_interval}s")
    print("║ Cookie: 从 Redis 列表读取              ║")
    print("╚════════════════════════════════════════╝")
    print()

    confirm = input("确认启动? (Y/N): ").strip().upper()
    if confirm == 'Y':
        on_start(redis_list_key, poll_interval)
    else:
        print("\n取消操作")
        input("按回车键退出...")

if __name__ == '__main__':
    main()
