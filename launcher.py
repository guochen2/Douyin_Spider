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
    live_id = entry_live_id.get().strip()
    cookies = entry_cookies.get("1.0", tk.END).strip()
    
    if not live_id:
        messagebox.showerror("错误", "请输入房间号")
        return
    
    if not cookies:
        messagebox.showerror("错误", "请输入cookie")
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
        messagebox.showerror("错误", "未找到 server.exe 或 server.py")
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
        proc = subprocess.Popen(cmd_parts, env=env, startupinfo=startupinfo, 
                              creationflags=subprocess.CREATE_NEW_CONSOLE,
                              cwd=os.path.dirname(__file__))
        messagebox.showinfo("成功", "直播间已启动！")
        root.destroy()
    except Exception as e:
        messagebox.showerror("错误", f"启动失败: {str(e)}")

config = load_config()

root = tk.Tk()
root.title("抖音直播启动器")
root.geometry("500x350")
root.resizable(False, False)

style = ttk.Style()
style.configure('TLabel', font=('微软雅黑', 10))
style.configure('TEntry', font=('微软雅黑', 10))
style.configure('TButton', font=('微软雅黑', 12, 'bold'))

main_frame = ttk.Frame(root, padding="20")
main_frame.pack(fill=tk.BOTH, expand=True)

ttk.Label(main_frame, text="房间号:", font=('微软雅黑', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
entry_live_id = ttk.Entry(main_frame, width=50)
entry_live_id.insert(0, config.get('live_id', ''))
entry_live_id.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 15))

ttk.Label(main_frame, text="Cookie:", font=('微软雅黑', 10, 'bold')).grid(row=2, column=0, sticky=tk.W, pady=(0, 5))
entry_cookies = tk.Text(main_frame, width=50, height=10, font=('微软雅黑', 10))
entry_cookies.insert("1.0", config.get('live_cookies', ''))
entry_cookies.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(0, 15))

btn_frame = ttk.Frame(main_frame)
btn_frame.grid(row=4, column=0, columnspan=2, pady=(10, 0))

btn_start = ttk.Button(btn_frame, text="确认开播", command=on_start, width=20)
btn_start.pack()

main_frame.columnconfigure(0, weight=1)
main_frame.columnconfigure(1, weight=1)
main_frame.rowconfigure(3, weight=1)

root.mainloop()