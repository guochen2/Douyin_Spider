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

def on_start(live_id, cookies):
    live_id = live_id.strip()
    cookies = cookies.strip()
    
    if not live_id:
        print("\n错误: 请输入房间号")
        input("按回车键退出...")
        return
    
    if not cookies:
        print("\n错误: 请输入cookie")
        input("按回车键退出...")
        return
    
    config = {
        'live_id': live_id,
        'cookies': '',
        'live_cookies': cookies
    }
    save_config(config)
    
    server_exe_path = os.path.join(os.path.dirname(__file__), 'server.exe')
    server_py_path = os.path.join(os.path.dirname(__file__), 'dy_live', 'server.py')
    
    if os.path.exists(server_exe_path):
        cmd_parts = [server_exe_path]
    elif os.path.exists(server_py_path):
        cmd_parts = [sys.executable, server_py_path]
    else:
        print("\n错误: 未找到 server.exe 或 server.py")
        input("按回车键退出...")
        return
    
    env = os.environ.copy()
    env['DY_LIVE_COOKIES'] = cookies
    env['DY_LIVE_ID'] = live_id
    env['DY_COOKIES'] = ''
    
    startupinfo = None
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= 1
        startupinfo.wShowWindow = 1
    
    try:
        subprocess.Popen(cmd_parts, env=env, startupinfo=startupinfo, 
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                        cwd=os.path.dirname(__file__))
        print("\n成功: 直播间已启动！")
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
    print("║           抖音直播启动器 v1.0          ║")
    print("╚════════════════════════════════════════╝")
    print()
    
    default_live_id = config.get('live_id', '')
    prompt = f"房间号 ({default_live_id}): " if default_live_id else "房间号: "
    live_id = input(prompt).strip()
    if not live_id:
        live_id = default_live_id
    
    print()
    print("请输入 Cookie (输入完成后按 Ctrl+Z 再按回车结束):")
    print("-" * 50)
    cookies_lines = []
    while True:
        try:
            line = input()
            cookies_lines.append(line)
        except EOFError:
            break
    cookies = '\n'.join(cookies_lines)
    if not cookies.strip():
        cookies = config.get('cookies', '')
    
    os.system('cls' if sys.platform == 'win32' else 'clear')
    
    print("╔════════════════════════════════════════╗")
    print("║              确认信息                  ║")
    print("╠════════════════════════════════════════╣")
    print(f"║ 房间号: {live_id[:30]}{'...' if len(live_id) > 30 else ''}")
    print(f"║ Cookie: {'已设置' if cookies else '未设置'}")
    print("╚════════════════════════════════════════╝")
    print()
    
    confirm = input("确认开播? (Y/N): ").strip().upper()
    if confirm == 'Y':
        on_start(live_id, cookies)
    else:
        print("\n取消操作")
        input("按回车键退出...")

if __name__ == '__main__':
    main()