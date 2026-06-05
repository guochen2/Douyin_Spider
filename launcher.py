import os
import sys
import subprocess
import json
import tkinter as tk
from tkinter import ttk, messagebox

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
    redis_list_key = entry_redis_key.get().strip() or 'dy_live:rooms'
    poll_interval = entry_poll_interval.get().strip() or '3'

    try:
        poll_interval_val = float(poll_interval)
        if poll_interval_val <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("错误", "轮询间隔必须是大于 0 的数字")
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
        messagebox.showerror("错误", "未找到 live_manager.exe 或 live_manager.py")
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
        messagebox.showinfo(
            "成功",
            f"Redis 监听服务已启动！\n列表 Key: {redis_list_key}\n"
            "Cookie 与房间号均从 Redis 列表读取。",
        )
        root.destroy()
    except Exception as e:
        messagebox.showerror("错误", f"启动失败: {str(e)}")

config = load_config()

root = tk.Tk()
root.title("抖音直播 Redis 监听启动器")
root.geometry("520x220")
root.resizable(False, False)

style = ttk.Style()
style.configure('TLabel', font=('微软雅黑', 10))
style.configure('TEntry', font=('微软雅黑', 10))
style.configure('TButton', font=('微软雅黑', 12, 'bold'))

main_frame = ttk.Frame(root, padding="20")
main_frame.pack(fill=tk.BOTH, expand=True)

ttk.Label(main_frame, text="Redis 列表 Key:", font=('微软雅黑', 10, 'bold')).grid(
    row=0, column=0, sticky=tk.W, pady=(0, 5)
)
entry_redis_key = ttk.Entry(main_frame, width=50)
entry_redis_key.insert(0, config.get('redis_list_key', 'dy_live:rooms'))
entry_redis_key.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))

ttk.Label(main_frame, text="轮询间隔(秒):", font=('微软雅黑', 10, 'bold')).grid(
    row=2, column=0, sticky=tk.W, pady=(0, 5)
)
entry_poll_interval = ttk.Entry(main_frame, width=20)
entry_poll_interval.insert(0, str(config.get('poll_interval', 3)))
entry_poll_interval.grid(row=3, column=0, sticky=tk.W, pady=(0, 15))

ttk.Label(
    main_frame,
    text='列表项格式: {"live_id": "房间号", "cookie": "..."}',
    font=('微软雅黑', 9),
    foreground='#666666',
).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

btn_frame = ttk.Frame(main_frame)
btn_frame.grid(row=5, column=0, columnspan=2, pady=(10, 0))

btn_start = ttk.Button(btn_frame, text="启动 Redis 监听服务", command=on_start, width=24)
btn_start.pack()

main_frame.columnconfigure(0, weight=1)

root.mainloop()
