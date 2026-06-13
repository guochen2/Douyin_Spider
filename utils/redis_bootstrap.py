import atexit
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_redis_process = None
_temp_conf_path = None
_we_started_redis = False
_redis_endpoint = None


def app_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def find_redis_tool(name):
    base = app_dir() / 'tools' / 'redis'
    if sys.platform == 'win32':
        names = [f'{name}.exe', name]
    else:
        names = [name]
    for item in names:
        candidate = base / item
        if candidate.is_file():
            return candidate
    return None


def is_port_open(host, port, timeout=0.5):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def should_start_embedded_redis(config=None):
    config = config or {}
    mode = os.getenv('EMBEDDED_REDIS', '').lower()
    if mode in ('0', 'false', 'no', 'off', 'external', 'docker'):
        return False
    if os.path.exists('/.dockerenv'):
        return False

    host = os.getenv('REDIS_HOST', '').strip().lower()
    if host and host not in ('127.0.0.1', 'localhost'):
        return False

    if 'embedded_redis' in config:
        return bool(config.get('embedded_redis'))
    return mode in ('1', 'true', 'yes', 'auto', '') or not host


def _popen_kwargs():
    kwargs = {
        'stdout': subprocess.DEVNULL,
        'stderr': subprocess.DEVNULL,
    }
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _graceful_shutdown(host, port, password):
    cli = find_redis_tool('redis-cli')
    if not cli:
        return False
    try:
        kwargs = {}
        if sys.platform == 'win32':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            [str(cli), '-h', host, '-p', str(port), '-a', password, 'shutdown'],
            capture_output=True,
            timeout=8,
            **kwargs,
        )
        return result.returncode == 0
    except Exception:
        return False


def _write_redis_conf(port, password, data_dir):
    global _temp_conf_path
    bundled = app_dir() / 'config' / 'redis.conf'
    if bundled.is_file():
        template = bundled.read_text(encoding='utf-8')
    else:
        template = '\n'.join([
            'port {port}',
            'bind 127.0.0.1',
            'protected-mode yes',
            'appendonly no',
            'dir {dir}',
            'requirepass {password}',
        ])

    content = template.format(port=port, password=password, dir=str(data_dir).replace('\\', '/'))
    fd, path = tempfile.mkstemp(suffix='.conf', prefix='douyin_redis_')
    os.close(fd)
    Path(path).write_text(content, encoding='utf-8')
    _temp_conf_path = path
    return path


def start_embedded_redis(config=None):
    global _redis_process, _we_started_redis, _redis_endpoint
    config = config or {}

    host = '127.0.0.1'
    port = int(config.get('redis_port') or os.getenv('REDIS_PORT') or 6379)
    password = str(config.get('redis_password') or os.getenv('REDIS_PASSWORD') or 'douyin_local_redis')

    os.environ.setdefault('REDIS_HOST', host)
    os.environ.setdefault('REDIS_PORT', str(port))
    os.environ.setdefault('REDIS_PASSWORD', password)
    os.environ.setdefault('REDIS_DB', str(config.get('redis_db', os.getenv('REDIS_DB', '0'))))
    _redis_endpoint = (host, port, password)

    if is_port_open(host, port):
        print(f'[redis] 检测到本地 Redis 已运行: {host}:{port}')
        _we_started_redis = False
        return True

    server = find_redis_tool('redis-server')
    if not server:
        print('[redis] 未找到内置 redis-server（tools/redis/），请安装 Redis 或配置 REDIS_HOST')
        return False

    data_dir = app_dir() / 'redis-data'
    data_dir.mkdir(parents=True, exist_ok=True)
    conf_path = _write_redis_conf(port, password, data_dir)

    print(f'[redis] 启动内置 Redis: {host}:{port}')
    _redis_process = subprocess.Popen(
        [str(server), conf_path],
        cwd=str(server.parent),
        **_popen_kwargs(),
    )
    _we_started_redis = True

    for _ in range(50):
        if is_port_open(host, port):
            print('[redis] 内置 Redis 已就绪')
            return True
        if _redis_process.poll() is not None:
            print('[redis] 内置 Redis 启动失败，进程已退出')
            _we_started_redis = False
            _redis_process = None
            return False
        time.sleep(0.2)

    print('[redis] 内置 Redis 启动超时')
    stop_embedded_redis()
    return False


def stop_embedded_redis():
    global _redis_process, _temp_conf_path, _we_started_redis, _redis_endpoint

    if _we_started_redis and _redis_endpoint:
        host, port, password = _redis_endpoint
        if _graceful_shutdown(host, port, password):
            time.sleep(0.5)

    if _redis_process and _redis_process.poll() is None:
        _redis_process.terminate()
        try:
            _redis_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _redis_process.kill()
            try:
                _redis_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass

    _redis_process = None
    _we_started_redis = False
    _redis_endpoint = None

    if _temp_conf_path and os.path.exists(_temp_conf_path):
        try:
            os.remove(_temp_conf_path)
        except OSError:
            pass
        _temp_conf_path = None


atexit.register(stop_embedded_redis)
