import json
import os
import queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

DEFAULT_REDIS_PORT = 16380
DEFAULT_CONTROL_CHANNEL = 'dy_live:control'

C = {
    'bg': '#0a0a0e',
    'surface': '#12121a',
    'toolbar': '#16161f',
    'toolbar_edge': '#1f1f2b',
    'card': '#1a1a24',
    'card_hover': '#22222e',
    'input': '#0e0e14',
    'input_focus': '#14141c',
    'border': '#2b2b3a',
    'border_light': '#353548',
    'border_focus': '#fe2c55',
    'text': '#f2f2f7',
    'text_secondary': '#9898ad',
    'text_muted': '#5a5a6e',
    'accent': '#fe2c55',
    'accent_soft': '#ff4d6d',
    'accent_dim': '#3a1520',
    'accent_glow': '#fe2c5533',
    'accent_text': '#ffffff',
    'success': '#34d399',
    'success_dim': '#102820',
    'warning': '#fbbf24',
    'warning_dim': '#2a2010',
    'danger': '#f87171',
    'danger_dim': '#2a1212',
    'log_bg': '#08080c',
    'log_fg': '#b4b8c4',
    'log_err': '#ff7070',
    'log_ok': '#6ee7a0',
    'log_tag': '#7eb8ff',
    'log_gui': '#c4b5fd',
    'titlebar': '#101016',
}


def _app_dir():
    from utils.pack_env import app_dir
    return app_dir()


def _config_file():
    return os.path.join(_app_dir(), 'launcher_config.json')


def load_config():
    path = _config_file()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(config):
    with open(_config_file(), 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _pick_font(preferred, fallback, size, weight='normal'):
    families = set(tkfont.families())
    for name in preferred:
        if name in families:
            return (name, size, weight)
    return (fallback, size, weight)


def _hex_to_bgr(hex_color):
    value = int(hex_color.lstrip('#'), 16)
    r = (value >> 16) & 0xFF
    g = (value >> 8) & 0xFF
    b = value & 0xFF
    return b | (g << 8) | (r << 16)


def apply_dark_titlebar(root, bg=C['titlebar'], text=C['text']):
    if sys.platform != 'win32':
        return

    def _apply():
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            if not hwnd:
                hwnd = root.winfo_id()

            dwm = ctypes.windll.dwmapi
            use_dark = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(use_dark), ctypes.sizeof(use_dark))

            caption = ctypes.c_int(_hex_to_bgr(bg))
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))

            caption_text = ctypes.c_int(_hex_to_bgr(text))
            dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(caption_text), ctypes.sizeof(caption_text))
        except Exception:
            pass

    root.after(20, _apply)


class BorderedBox(tk.Frame):
    """带描边与内边距的容器。"""

    def __init__(self, parent, bg=C['input'], border=C['border'], focus_border=C['border_focus'], **kwargs):
        outer_bg = kwargs.pop('outer_bg', parent['bg'] if isinstance(parent, tk.Frame) else C['toolbar'])
        padx = kwargs.pop('padx', 10)
        pady = kwargs.pop('pady', 7)
        super().__init__(parent, bg=border, **kwargs)
        self._border = border
        self._focus_border = focus_border
        self.inner = tk.Frame(self, bg=bg)
        self.inner.pack(fill='both', expand=True, padx=1, pady=1)
        self.content = tk.Frame(self.inner, bg=bg)
        self.content.pack(fill='both', expand=True, padx=padx, pady=pady)

    def set_focused(self, focused):
        self.configure(bg=self._focus_border if focused else self._border)


class FieldGroup(tk.Frame):
    """标签 + 输入框组合。"""

    def __init__(self, parent, label, width=None, **kwargs):
        super().__init__(parent, bg=C['toolbar'], **kwargs)
        tk.Label(
            self,
            text=label.upper(),
            font=_pick_font(['Segoe UI', 'Microsoft YaHei UI'], 'TkDefaultFont', 8),
            bg=C['toolbar'],
            fg=C['text_muted'],
        ).pack(anchor='w')

        self.box = BorderedBox(self, outer_bg=C['toolbar'])
        self.box.pack(fill='x', pady=(5, 0))

        self.var = tk.StringVar()
        self.entry = tk.Entry(
            self.box.content,
            textvariable=self.var,
            width=width or 18,
            bg=C['input'],
            fg=C['text'],
            insertbackground=C['accent'],
            disabledbackground=C['input'],
            disabledforeground=C['text_secondary'],
            readonlybackground=C['input'],
            relief='flat',
            highlightthickness=0,
            font=_pick_font(['Cascadia Mono', 'Consolas'], 'Consolas', 10),
        )
        self.entry.pack(fill='x')
        self.entry.bind('<FocusIn>', self._on_focus_in)
        self.entry.bind('<FocusOut>', self._on_focus_out)
        self._locked = False

    def _on_focus_in(self, _event=None):
        if not self._locked:
            self.box.set_focused(True)

    def _on_focus_out(self, _event=None):
        if not self._locked:
            self.box.set_focused(False)

    def get(self):
        return self.var.get()

    def set(self, value):
        self.var.set(value)

    def configure_state(self, state):
        locked = state == 'disabled'
        self._locked = locked
        if locked:
            self.box.set_focused(False)
            self.entry.configure(
                state='readonly',
                readonlybackground=C['input'],
                fg=C['text_secondary'],
                cursor='arrow',
            )
        else:
            self.entry.configure(
                state='normal',
                bg=C['input'],
                fg=C['text'],
                cursor='xterm',
            )
        for widget in (self.box.inner, self.box.content):
            widget.configure(bg=C['input'])


class PillLabel(tk.Frame):
    """密码/标签胶囊。"""

    def __init__(self, parent, text, fg=C['accent'], bg=C['accent_dim'], **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        tk.Label(
            self,
            text=text,
            bg=bg,
            fg=fg,
            font=_pick_font(['Cascadia Mono', 'Consolas'], 'Consolas', 10),
            padx=12,
            pady=8,
        ).pack()


class ToolButton(tk.Frame):
    """工具栏按钮。"""

    def __init__(
        self,
        parent,
        text,
        command=None,
        bg=C['accent'],
        fg=C['accent_text'],
        hover_bg=None,
        active_bg=None,
        disabled_bg=C['card'],
        disabled_fg=C['text_muted'],
        font=None,
        **kwargs,
    ):
        super().__init__(parent, bg=C['toolbar'], **kwargs)
        self._command = command
        self._bg = bg
        self._fg = fg
        self._hover_bg = hover_bg or bg
        self._active_bg = active_bg or self._hover_bg
        self._disabled_bg = disabled_bg
        self._disabled_fg = disabled_fg
        self._enabled = True

        self.wrap = tk.Frame(self, bg=bg, highlightthickness=0)
        self.wrap.pack()

        self.label = tk.Label(
            self.wrap,
            text=text,
            bg=bg,
            fg=fg,
            font=font,
            padx=18,
            pady=9,
            cursor='hand2',
        )
        self.label.pack()

        for widget in (self, self.wrap, self.label):
            widget.bind('<Button-1>', self._on_press)
            widget.bind('<ButtonRelease-1>', self._on_release)
            widget.bind('<Enter>', self._on_enter)
            widget.bind('<Leave>', self._on_leave)

    def _paint(self, bg, fg=None):
        self.wrap.configure(bg=bg)
        kw = {'bg': bg}
        if fg is not None:
            kw['fg'] = fg
        self.label.configure(**kw)

    def _on_press(self, _event=None):
        if self._enabled:
            self._paint(self._active_bg)

    def _on_release(self, _event=None):
        if self._enabled and self._command:
            self._command()
        if self._enabled:
            self._paint(self._hover_bg)

    def _on_enter(self, _event=None):
        if self._enabled:
            self._paint(self._hover_bg)

    def _on_leave(self, _event=None):
        if self._enabled:
            self._paint(self._bg, self._fg)

    def configure_state(self, state):
        self._enabled = state == 'normal'
        if self._enabled:
            self._paint(self._bg, self._fg)
            self.label.configure(cursor='hand2')
        else:
            self._paint(self._disabled_bg, self._disabled_fg)
            self.label.configure(cursor='arrow')


class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Douyin Live 服务端')
        self.root.geometry('940x640')
        self.root.minsize(800, 540)
        self.root.configure(bg=C['bg'])

        self.ui_font = _pick_font(['Segoe UI', 'Microsoft YaHei UI'], 'TkDefaultFont', 10)
        self.ui_font_sm = _pick_font(['Segoe UI', 'Microsoft YaHei UI'], 'TkDefaultFont', 9)
        self.ui_font_xs = _pick_font(['Segoe UI', 'Microsoft YaHei UI'], 'TkDefaultFont', 8)
        self.title_font = _pick_font(['Segoe UI', 'Microsoft YaHei UI'], 'TkDefaultFont', 15, 'bold')
        self.btn_font = _pick_font(['Segoe UI Semibold', 'Segoe UI', 'Microsoft YaHei UI'], 'TkDefaultFont', 10, 'bold')
        self.log_font = _pick_font(['Cascadia Mono', 'Consolas', 'Courier New'], 'Consolas', 10)

        self.log_queue = queue.Queue()
        self.service_thread = None
        self.running = False
        self.stopping = False
        self._ever_started = False
        self._status_state = 'idle'

        self._setup_styles()
        self._build_ui()
        self._load_settings()
        self._poll_logs()
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        apply_dark_titlebar(self.root)

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        style.configure(
            'Dark.Vertical.TScrollbar',
            background=C['card'],
            troughcolor=C['log_bg'],
            bordercolor=C['border'],
            arrowcolor=C['text_muted'],
            gripcount=0,
        )
        style.map(
            'Dark.Vertical.TScrollbar',
            background=[('active', C['border_light']), ('pressed', C['accent_dim'])],
        )

        style.configure(
            'Ghost.TButton',
            background=C['card'],
            foreground=C['text_secondary'],
            bordercolor=C['border'],
            focusthickness=0,
            padding=(14, 8),
            font=self.ui_font_sm,
        )
        style.map(
            'Ghost.TButton',
            background=[('active', C['card_hover']), ('pressed', C['border'])],
            foreground=[('active', C['text'])],
        )

    def _hline(self, parent, color=C['border'], height=1):
        line = tk.Frame(parent, bg=color, height=height)
        line.pack(fill='x')
        return line

    def _vline(self, parent, height=42):
        wrap = tk.Frame(parent, bg=C['toolbar'], padx=14)
        line = tk.Frame(wrap, bg=C['border'], width=1, height=height)
        line.pack()
        return wrap

    def _build_ui(self):
        # 顶部品牌色条
        tk.Frame(self.root, bg=C['accent'], height=2).pack(fill='x')

        # ── 标题区（与系统标题栏视觉衔接）──
        titlebar = tk.Frame(self.root, bg=C['titlebar'], padx=20, pady=14)
        titlebar.pack(fill='x')

        brand = tk.Frame(titlebar, bg=C['titlebar'])
        brand.pack(side='left')

        logo = tk.Frame(brand, bg=C['accent'], width=34, height=34)
        logo.pack(side='left')
        logo.pack_propagate(False)
        tk.Label(
            logo,
            text='DY',
            bg=C['accent'],
            fg=C['accent_text'],
            font=self.btn_font,
        ).place(relx=0.5, rely=0.5, anchor='center')

        text_block = tk.Frame(brand, bg=C['titlebar'])
        text_block.pack(side='left', padx=(12, 0))
        tk.Label(
            text_block,
            text='Douyin Live 服务端',
            font=self.title_font,
            bg=C['titlebar'],
            fg=C['text'],
        ).pack(anchor='w')
        tk.Label(
            text_block,
            text='Redis 监听 · 内置 Redis · 私有化部署',
            font=self.ui_font_sm,
            bg=C['titlebar'],
            fg=C['text_secondary'],
        ).pack(anchor='w', pady=(1, 0))

        self.status_frame = tk.Frame(titlebar, bg=C['success_dim'], highlightbackground=C['success'], highlightthickness=1)
        self.status_frame.pack(side='right')

        status_inner = tk.Frame(self.status_frame, bg=C['success_dim'], padx=12, pady=5)
        status_inner.pack()

        self.status_dot = tk.Label(status_inner, text='●', font=('Segoe UI', 9), bg=C['success_dim'], fg=C['success'])
        self.status_dot.pack(side='left', padx=(0, 6))
        self.status_var = tk.StringVar(value='就绪')
        self.status_label = tk.Label(status_inner, textvariable=self.status_var, font=self.ui_font_sm, bg=C['success_dim'], fg=C['success'])
        self.status_label.pack(side='left')

        self._hline(self.root, C['border'])

        # ── 工具栏主体 ──
        toolbar = tk.Frame(self.root, bg=C['toolbar'], padx=20, pady=16)
        toolbar.pack(fill='x')

        toolbar_head = tk.Frame(toolbar, bg=C['toolbar'])
        toolbar_head.pack(fill='x')

        tk.Label(
            toolbar_head,
            text='⚙',
            font=self.ui_font,
            bg=C['toolbar'],
            fg=C['accent'],
        ).pack(side='left')
        tk.Label(
            toolbar_head,
            text='  连接配置',
            font=self.btn_font,
            bg=C['toolbar'],
            fg=C['text'],
        ).pack(side='left')
        tk.Label(
            toolbar_head,
            text='客户端通过 Redis Pub/Sub 发送 start / stop 指令',
            font=self.ui_font_xs,
            bg=C['toolbar'],
            fg=C['text_muted'],
        ).pack(side='right')

        config_row = tk.Frame(toolbar, bg=C['toolbar'])
        config_row.pack(fill='x', pady=(14, 0))

        self.port_field = FieldGroup(config_row, 'Redis 端口', width=8)
        self.port_field.pack(side='left')
        self.port_field.set(str(DEFAULT_REDIS_PORT))

        self._vline(config_row).pack(side='left')

        self.channel_field = FieldGroup(config_row, '控制频道', width=24)
        self.channel_field.pack(side='left')
        self.channel_field.set(DEFAULT_CONTROL_CHANNEL)

        self._vline(config_row).pack(side='left')

        pwd_col = tk.Frame(config_row, bg=C['toolbar'])
        pwd_col.pack(side='left')

        self.password_field = FieldGroup(pwd_col, 'Redis 密码', width=14)
        self.password_field.pack(side='left')

        regen_wrap = tk.Frame(pwd_col, bg=C['toolbar'])
        regen_wrap.pack(side='left', padx=(8, 0), pady=(18, 0))
        self.regen_pwd_btn = ttk.Button(
            regen_wrap,
            text='↻ 重新生成',
            style='Ghost.TButton',
            command=self._on_regenerate_password,
        )
        self.regen_pwd_btn.pack()

        self._hline(toolbar, C['toolbar_edge'])
        toolbar.pack_configure(pady=0)
        tk.Frame(toolbar, bg=C['toolbar'], height=12).pack(fill='x')

        action_row = tk.Frame(toolbar, bg=C['toolbar'])
        action_row.pack(fill='x')

        btn_group = tk.Frame(
            action_row,
            bg=C['toolbar_edge'],
            highlightbackground=C['border'],
            highlightthickness=1,
        )
        btn_group.pack(side='left')

        btn_inner = tk.Frame(btn_group, bg=C['toolbar_edge'], padx=4, pady=4)
        btn_inner.pack()

        self.start_btn = ToolButton(
            btn_inner,
            text='▶  启动服务',
            command=self._on_start,
            bg=C['accent'],
            fg=C['accent_text'],
            hover_bg=C['accent_soft'],
            active_bg='#e02649',
            font=self.btn_font,
        )
        self.start_btn.pack(side='left', padx=(0, 4))

        self.stop_btn = ToolButton(
            btn_inner,
            text='■  停止服务',
            command=self._on_stop,
            bg=C['danger_dim'],
            fg=C['danger'],
            hover_bg='#351818',
            active_bg='#2a1010',
            disabled_bg=C['card'],
            disabled_fg=C['text_muted'],
            font=self.btn_font,
        )
        self.stop_btn.pack(side='left')
        self.stop_btn.configure_state('disabled')

        ttk.Button(action_row, text='清空日志', style='Ghost.TButton', command=self._clear_log).pack(side='left', padx=(12, 0))

        tk.Label(
            action_row,
            text='127.0.0.1  ·  使用上方端口与密码连接',
            font=self.ui_font_xs,
            bg=C['toolbar'],
            fg=C['text_muted'],
        ).pack(side='right')

        self._hline(self.root, C['border'])

        # ── 日志区 ──
        log_section = tk.Frame(self.root, bg=C['bg'])
        log_section.pack(fill='both', expand=True, padx=20, pady=(14, 18))

        log_header = tk.Frame(log_section, bg=C['bg'])
        log_header.pack(fill='x', pady=(0, 8))

        left = tk.Frame(log_header, bg=C['bg'])
        left.pack(side='left')
        tk.Label(left, text='运行日志', font=self.btn_font, bg=C['bg'], fg=C['text']).pack(side='left')
        tk.Label(
            left,
            text='  LIVE',
            font=self.ui_font_xs,
            bg=C['accent_dim'],
            fg=C['accent'],
            padx=6,
            pady=1,
        ).pack(side='left', padx=(8, 0))

        tk.Label(log_header, text='● 实时输出', font=self.ui_font_xs, bg=C['bg'], fg=C['text_muted']).pack(side='right')

        log_shell = tk.Frame(log_section, bg=C['border'], highlightthickness=0)
        log_shell.pack(fill='both', expand=True)

        log_frame = tk.Frame(log_shell, bg=C['log_bg'])
        log_frame.pack(fill='both', expand=True, padx=1, pady=1)

        self.log_text = tk.Text(
            log_frame,
            wrap='word',
            font=self.log_font,
            bg=C['log_bg'],
            fg=C['log_fg'],
            insertbackground=C['text'],
            selectbackground=C['accent_dim'],
            selectforeground=C['text'],
            relief='flat',
            padx=16,
            pady=14,
            state='disabled',
            spacing1=2,
            spacing3=2,
        )
        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview, style='Dark.Vertical.TScrollbar')
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.log_text.tag_configure('stderr', foreground=C['log_err'])
        self.log_text.tag_configure('success', foreground=C['log_ok'])
        self.log_text.tag_configure('tag', foreground=C['log_tag'])
        self.log_text.tag_configure('gui', foreground=C['log_gui'])

    def _set_status(self, state, text):
        self._status_state = state
        palettes = {
            'idle': (C['success_dim'], C['success'], C['success']),
            'running': (C['accent_dim'], C['accent'], C['accent']),
            'stopping': (C['warning_dim'], C['warning'], C['warning']),
            'stopped': (C['card'], C['text_secondary'], C['border']),
        }
        bg, fg, border = palettes.get(state, palettes['idle'])
        self.status_frame.configure(bg=bg, highlightbackground=border)
        for widget in self.status_frame.winfo_children():
            if isinstance(widget, tk.Frame):
                widget.configure(bg=bg)
                for child in widget.winfo_children():
                    child.configure(bg=bg, fg=fg)
            else:
                widget.configure(bg=bg, fg=fg)
        self.status_dot.configure(bg=bg, fg=fg)
        self.status_label.configure(bg=bg, fg=fg)
        self.status_var.set(text)

    def _load_settings(self):
        from utils.redis_config import ensure_redis_password

        config = load_config()
        self.port_field.set(str(config.get('redis_port', DEFAULT_REDIS_PORT)))
        self.channel_field.set(config.get('redis_control_channel', DEFAULT_CONTROL_CHANNEL))

        password = ensure_redis_password(config)
        if config.get('redis_password') != password:
            config['redis_password'] = password
            save_config(config)
        self.password_field.set(password)

    def _on_regenerate_password(self):
        if self.running:
            return
        from utils.redis_config import generate_redis_password

        password = generate_redis_password()
        self.password_field.set(password)
        config = load_config()
        config['redis_password'] = password
        save_config(config)

    def _append_log(self, text, stream_name='stdout'):
        self.log_text.configure(state='normal')
        tags = ()
        if stream_name == 'stderr':
            tags = ('stderr',)
        elif '[gui]' in text:
            tags = ('gui',)
        elif any(k in text for k in ('已就绪', '已全部停止', '已停止')):
            tags = ('success',)
        elif text.lstrip().startswith('['):
            tags = ('tag',)
        if tags:
            self.log_text.insert('end', text, tags)
        else:
            self.log_text.insert('end', text)
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _clear_log(self):
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    def _poll_logs(self):
        while True:
            try:
                stream_name, text = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(text, stream_name)
        self.root.after(100, self._poll_logs)

    def _sync_controls(self):
        running = self.running
        self.start_btn.configure_state('disabled' if running else 'normal')
        self.stop_btn.configure_state('normal' if running and not self.stopping else 'disabled')
        self.port_field.configure_state('disabled' if running else 'normal')
        self.channel_field.configure_state('disabled' if running else 'normal')
        self.password_field.configure_state('disabled' if running else 'normal')
        self.regen_pwd_btn.configure(state='disabled' if running else 'normal')

    def _refresh_status(self):
        if self.running:
            self._set_status('running', '运行中')
        elif self.stopping:
            self._set_status('stopping', '正在停止...')
        elif self._ever_started:
            self._set_status('stopped', '已停止')
        else:
            self._set_status('idle', '就绪')

    def _set_running(self, running):
        self.running = running
        self._sync_controls()
        self._refresh_status()

    def _parse_port(self):
        raw = self.port_field.get().strip()
        if not raw.isdigit():
            raise ValueError('Redis 端口必须是数字')
        port = int(raw)
        if port < 1024 or port > 65535:
            raise ValueError('Redis 端口范围应为 1024-65535')
        return port

    def _build_config(self):
        port = self._parse_port()
        channel = self.channel_field.get().strip() or DEFAULT_CONTROL_CHANNEL
        password = self.password_field.get().strip()
        if not password:
            raise ValueError('Redis 密码不能为空')
        if len(password) < 6:
            raise ValueError('Redis 密码至少 6 位')

        config = load_config()
        config.update({
            'embedded_redis': True,
            'redis_port': port,
            'redis_password': password,
            'redis_control_channel': channel,
        })
        save_config(config)
        return config, channel

    def _on_start(self):
        if self.running:
            return
        try:
            config, channel = self._build_config()
        except ValueError as exc:
            messagebox.showerror('参数错误', str(exc))
            return

        os.environ['DOUYIN_LIVE_GUI'] = '1'
        os.environ['DOUYIN_LIVE_FOREGROUND'] = '1'

        from utils.log_redirect import install_queue_logging
        install_queue_logging(self.log_queue)

        self._ever_started = True
        self._set_running(True)
        self._append_log('DouyinLive 启动中...\n')
        self._append_log(f'控制频道: {channel}\n')
        self._append_log(f'Redis: 127.0.0.1:{config["redis_port"]}  密码: {config["redis_password"]}\n')

        self.service_thread = threading.Thread(
            target=self._run_service,
            args=(config, channel),
            name='douyin-live-service',
            daemon=True,
        )
        self.service_thread.start()

    def _run_service(self, config, channel):
        try:
            from launcher import start_redis_listener
            start_redis_listener(channel, config)
        except Exception as exc:
            self.log_queue.put(('stderr', f'服务异常退出: {exc}\n'))
            import traceback
            self.log_queue.put(('stderr', traceback.format_exc()))
        finally:
            self.root.after(0, self._on_service_stopped)

    def _on_service_stopped(self):
        self.running = False
        if self.stopping:
            return
        self._sync_controls()
        self._refresh_status()
        self._append_log('[gui] 服务已停止\n')

    def _on_stop(self):
        if not self.running or self.stopping:
            return
        self.stopping = True
        self.stop_btn.configure_state('disabled')
        self._set_status('stopping', '正在停止...')
        self._append_log('[gui] 正在停止服务...\n')

        def stop_worker():
            try:
                from dy_live.live_manager import request_stop
                request_stop()
            except Exception as exc:
                self.log_queue.put(('stderr', f'停止 manager 失败: {exc}\n'))
            thread = self.service_thread
            if thread and thread.is_alive():
                thread.join(timeout=30)
            self.root.after(0, self._finish_stop)

        threading.Thread(target=stop_worker, name='gui-stop', daemon=True).start()

    def _finish_stop(self):
        self.running = False
        self.stopping = False
        self._sync_controls()
        self._refresh_status()
        self._append_log('[gui] 服务已停止\n')

    def _on_close(self):
        if self.running:
            if not messagebox.askyesno('确认退出', '服务仍在运行，确定要退出吗？'):
                return
            self._on_stop()
            if self.service_thread and self.service_thread.is_alive():
                self.service_thread.join(timeout=30)
        self.root.destroy()


def run_gui():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    LauncherApp(root)
    root.mainloop()
