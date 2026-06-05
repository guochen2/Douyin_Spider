import os
import sys
import subprocess
import json
import tkinter as tk
from tkinter import ttk, messagebox

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

def on_start():
    control_channel = entry_control_channel.get().strip() or 'dy_live:control'

    try:
        import redis  # noqa: F401
    except ImportError:
        messagebox.showerror(
            "错误",
            "当前 Python 环境缺少 redis 模块。\n"
            "请激活正确的 conda 环境（如 p310）后重试，或执行：pip install redis",
        )
        return

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
        messagebox.showerror("错误", "未找到 live_manager.exe 或 live_manager.py")
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
        # messagebox.showinfo(
        #     "成功",
        #     f"Redis 监听服务已启动！\n控制频道: {control_channel}\n"
        #     "客户端通过发布订阅发送 start/stop 命令。",
        # )
        root.destroy()
    except Exception as e:
        messagebox.showerror("错误", f"启动失败: {str(e)}")

config = load_config()

root = tk.Tk()
root.title("抖音直播 Redis 监听启动器")
root.geometry("520x180")
root.resizable(False, False)

style = ttk.Style()
style.configure('TLabel', font=('微软雅黑', 10))
style.configure('TEntry', font=('微软雅黑', 10))
style.configure('TButton', font=('微软雅黑', 12, 'bold'))

main_frame = ttk.Frame(root, padding="20")
main_frame.pack(fill=tk.BOTH, expand=True)

ttk.Label(main_frame, text="Redis 控制频道:", font=('微软雅黑', 10, 'bold')).grid(
    row=0, column=0, sticky=tk.W, pady=(0, 5)
)
entry_control_channel = ttk.Entry(main_frame, width=50)
entry_control_channel.insert(0, config.get('redis_control_channel', 'dy_live:control'))
entry_control_channel.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))

ttk.Label(
    main_frame,
    text='控制消息: {"action": "start"|"stop", "live_id": "房间号", "cookie": "..."}',
    font=('微软雅黑', 9),
    foreground='#666666',
).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

btn_frame = ttk.Frame(main_frame)
btn_frame.grid(row=3, column=0, columnspan=2, pady=(10, 0))

btn_start = ttk.Button(btn_frame, text="启动 Redis 监听服务", command=on_start, width=24)
btn_start.pack()

main_frame.columnconfigure(0, weight=1)

root.mainloop()
