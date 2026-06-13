import atexit
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

_redis_process = None
_temp_conf_path = None
_we_started_redis = False
_redis_endpoint = None
_redis_stopped = False
_stop_lock = threading.Lock()

DEFAULT_EMBEDDED_REDIS_PORT = 16380
DEFAULT_EMBEDDED_REDIS_PASSWORD = 'douyin_local_redis'
FALLBACK_REDIS_PORTS = (16380, 16381, 6380, 6381, 16379)


def app_dir():
    from utils.pack_env import app_dir as _app_dir
    return Path(_app_dir())


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


def probe_redis(host, port, password, timeout=2):
    """
    探测端口上的 Redis 是否可用、是否需要密码。
    返回: ok_with_password | ok_no_password | foreign_no_password | auth_mismatch | closed | error
    """
    if not is_port_open(host, port, timeout=timeout):
        return 'closed'

    try:
        import redis
        from redis.exceptions import AuthenticationError, RedisError

        client = redis.Redis(
            host=host,
            port=int(port),
            password=password or None,
            db=0,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
        )
        client.ping()
        return 'ok_with_password' if password else 'ok_no_password'
    except AuthenticationError as exc:
        msg = str(exc).lower()
        if password and 'no password is set' in msg:
            try:
                client = redis.Redis(
                    host=host,
                    port=int(port),
                    password=None,
                    db=0,
                    socket_connect_timeout=timeout,
                    socket_timeout=timeout,
                )
                client.ping()
                return 'foreign_no_password'
            except RedisError:
                return 'error'
        return 'auth_mismatch'
    except Exception:
        return 'error'


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
        cmd = [str(cli), '-h', host, '-p', str(port)]
        if password:
            cmd.extend(['-a', password])
        cmd.append('shutdown')
        result = subprocess.run(
            cmd,
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


def _resolve_embedded_port(host, preferred_port, password):
    """选择可复用或可用于启动内置 Redis 的端口。"""
    status = probe_redis(host, preferred_port, password)
    if status == 'ok_with_password':
        print(f'[redis] 复用已有 Redis（密码匹配）: {host}:{preferred_port}')
        return preferred_port, False

    if status == 'closed':
        return preferred_port, True

    if status in ('foreign_no_password', 'auth_mismatch', 'error'):
        print(
            f'[redis] 端口 {preferred_port} 已被其他 Redis 占用'
            f'（{"无密码" if status == "foreign_no_password" else "密码不匹配或不可连接"}），'
            f'将尝试其他端口启动内置 Redis'
        )

    candidates = []
    for port in (preferred_port, *FALLBACK_REDIS_PORTS):
        if port not in candidates:
            candidates.append(port)

    for port in candidates:
        if port == preferred_port and status not in ('foreign_no_password', 'auth_mismatch', 'error'):
            continue
        port_status = probe_redis(host, port, password)
        if port_status == 'ok_with_password':
            print(f'[redis] 复用已有 Redis（密码匹配）: {host}:{port}')
            return port, False
        if port_status == 'closed':
            return port, True

    return None, False


def _apply_redis_env(host, port, password, db):
    os.environ['REDIS_HOST'] = host
    os.environ['REDIS_PORT'] = str(port)
    os.environ['REDIS_PASSWORD'] = password
    os.environ['REDIS_DB'] = str(db)


def start_embedded_redis(config=None):
    global _redis_process, _we_started_redis, _redis_endpoint, _redis_stopped
    config = config or {}
    _redis_stopped = False

    from utils.redis_config import ensure_redis_password

    host = '127.0.0.1'
    preferred_port = int(
        config.get('redis_port')
        or os.getenv('REDIS_PORT')
        or DEFAULT_EMBEDDED_REDIS_PORT
    )
    password = str(ensure_redis_password(config))
    db = config.get('redis_db', os.getenv('REDIS_DB', '0'))

    port, should_start = _resolve_embedded_port(host, preferred_port, password)
    if port is None:
        print('[redis] 未找到可用端口启动内置 Redis，请关闭占用 Redis 或修改 launcher_config.json 中的 redis_port')
        return False

    _apply_redis_env(host, port, password, db)
    _redis_endpoint = (host, port, password)

    if not should_start:
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
        if probe_redis(host, port, password) == 'ok_with_password':
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
    global _redis_process, _temp_conf_path, _we_started_redis, _redis_endpoint, _redis_stopped

    with _stop_lock:
        if _redis_stopped:
            return

        proc = _redis_process
        endpoint = _redis_endpoint
        started = _we_started_redis
        conf_path = _temp_conf_path

        _redis_process = None
        _redis_endpoint = None
        _we_started_redis = False
        _temp_conf_path = None
        _redis_stopped = True

    if started and endpoint:
        host, port, password = endpoint
        if _graceful_shutdown(host, port, password):
            time.sleep(0.5)

    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass

    if conf_path and os.path.exists(conf_path):
        try:
            os.remove(conf_path)
        except OSError:
            pass

    try:
        import utils.redis_util as redis_util_module
        redis_util_module.redis_util.reset()
    except Exception:
        pass


atexit.register(stop_embedded_redis)
