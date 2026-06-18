import json
import os
import sys
import threading
import time

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

if os.getenv('DOUYIN_LIVE_GUI', '').lower() not in ('1', 'true', 'yes'):
    from utils.console_util import setup_console_utf8
    setup_console_utf8()

import utils.redis_util as redis_util
from builder.auth import DouyinAuth
from dy_live.server import DouyinLive, GIFT_HANDLER_VERSION, get_config_file, load_config

DEFAULT_CONTROL_CHANNEL = 'dy_live:control'
HEARTBEAT_KEY_PREFIX = 'dy_live:heartbeat:'
_active_manager = None
HEARTBEAT_CHECK_INTERVAL = 5
HEARTBEAT_START_GRACE_SECONDS = 15
HEARTBEAT_MISS_THRESHOLD = 3
SERVER_RUNNING_COUNT_KEY = 'dy_live:server:running_count'


def create_live_auth(cookie_str):
    auth = DouyinAuth()
    auth.perepare_auth(cookie_str, "", "")
    return auth


def build_heartbeat_key(live_id):
    return f'{HEARTBEAT_KEY_PREFIX}{live_id}'


def request_stop():
    mgr = _active_manager
    if mgr is not None:
        mgr.stop()
        return True
    return False


def parse_control_command(raw):
    """
    解析 Redis 控制频道消息。
    格式: {"action": "start"|"stop", "live_id": "房间号", "cookie": "..."}
    start 必须包含 cookie；stop 只需 live_id。
    """
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print(f'[manager] 跳过无效控制消息（需 JSON 格式）: {text[:80]}...')
        return None
    if not isinstance(data, dict):
        return None
    action = str(data.get('action', '')).strip().lower()
    live_id = str(data.get('live_id', '')).strip()
    if action not in ('start', 'stop') or not live_id:
        print(f'[manager] 跳过不完整控制消息: {text[:80]}...')
        return None
    if action == 'start':
        cookie = str(data.get('cookie', '')).strip()
        if not cookie:
            print(f'[manager] start 命令缺少 cookie: live_id={live_id}')
            return None
        return action, live_id, cookie
    return action, live_id, None


class LiveRoomWorker:
    def __init__(
        self,
        live_id,
        cookie,
        reconnect_delay=5,
        heartbeat_key=None,
        heartbeat_check_interval=HEARTBEAT_CHECK_INTERVAL,
        on_stopped=None,
    ):
        self.live_id = live_id
        self.cookie = cookie
        self.live = DouyinLive(live_id, create_live_auth(cookie))
        self.reconnect_delay = reconnect_delay
        self.heartbeat_key = heartbeat_key
        self.heartbeat_check_interval = heartbeat_check_interval
        self.on_stopped = on_stopped
        self.thread = threading.Thread(
            target=self._run,
            name=f'live-{live_id}',
            daemon=True,
        )

    def _heartbeat_loop(self):
        grace_until = time.time() + HEARTBEAT_START_GRACE_SECONDS
        miss_count = 0
        while not self.live.is_stopped():
            if time.time() >= grace_until:
                if self.heartbeat_key:
                    key_exists = redis_util.redis_util.exists(self.heartbeat_key)
                    if key_exists is None:
                        print(f'[manager] 心跳检测 Redis 异常，跳过本次: {self.live_id}')
                    elif key_exists:
                        miss_count = 0
                    else:
                        miss_count += 1
                        print(
                            f'[manager] 心跳 Key 未找到 ({miss_count}/{HEARTBEAT_MISS_THRESHOLD}): '
                            f'{self.live_id}'
                        )
                        if miss_count >= HEARTBEAT_MISS_THRESHOLD:
                            print(f'[manager] 心跳过期，主动关闭监听: {self.live_id}')
                            try:
                                self.live._publish_live_error('客户端心跳断开，监听已停止')
                            except Exception:
                                pass
                            self.live.stop()
                            break
            if self.live._stop_event.wait(self.heartbeat_check_interval):
                break

    def _run(self):
        heartbeat_thread = None
        if self.heartbeat_key:
            heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                name=f'heartbeat-{self.live_id}',
                daemon=True,
            )
            heartbeat_thread.start()
        try:
            self.live.start_ws(reconnect=True, reconnect_delay=self.reconnect_delay)
        except Exception as e:
            print(f'[manager] [{self.live_id}] 监听线程异常: {e}')
            if not self.live._live_aborted:
                self.live._fail_cookie_error(f'监听线程异常: {e}')
        finally:
            if self.on_stopped:
                self.on_stopped(self.live_id, self)

    def start(self):
        self.thread.start()

    def stop(self, timeout=15):
        self.live.stop()
        self.thread.join(timeout=timeout)
        return not self.thread.is_alive()


class LiveRoomManager:
    def __init__(
        self,
        control_channel=DEFAULT_CONTROL_CHANNEL,
        start_batch_size=20,
        start_batch_delay=0.05,
        reconnect_delay=5,
        heartbeat_check_interval=HEARTBEAT_CHECK_INTERVAL,
    ):
        self.control_channel = control_channel
        self.start_batch_size = start_batch_size
        self.start_batch_delay = start_batch_delay
        self.reconnect_delay = reconnect_delay
        self.heartbeat_check_interval = heartbeat_check_interval

        self._workers = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._stopped = False
        self._command_thread = None
        self._stats = {'started': 0, 'stopped': 0, 'commands': 0}

    def _on_worker_stopped(self, live_id, worker):
        with self._lock:
            current = self._workers.get(live_id)
            if current is not worker:
                return
            self._workers.pop(live_id, None)
            print(f'[manager] 监听线程已结束: {live_id} (当前 {len(self._workers)} 个)')

    def _finalize_worker_stop(self, worker, live_id, reason):
        ok = worker.stop()
        self._stats['stopped'] += 1
        status = '已停止' if ok else '停止超时'
        with self._lock:
            active = len(self._workers)
        print(f'[manager] {status}({reason}): {live_id} (当前 {active} 个)')

    def _stop_room(self, live_id, reason='command', wait=False):
        with self._lock:
            worker = self._workers.pop(live_id, None)
        if not worker:
            print(f'[manager] 无需停止（未在运行）: {live_id}')
            return
        worker.live.stop()
        if wait:
            self._finalize_worker_stop(worker, live_id, reason)
            return
        threading.Thread(
            target=self._finalize_worker_stop,
            args=(worker, live_id, reason),
            name=f'stop-{live_id}',
            daemon=True,
        ).start()

    def _start_room(self, live_id, cookie):
        with self._lock:
            old_worker = self._workers.pop(live_id, None)
        if old_worker:
            old_worker.live.stop()
            threading.Thread(
                target=old_worker.stop,
                name=f'stop-before-start-{live_id}',
                daemon=True,
            ).start()

        worker = LiveRoomWorker(
            live_id,
            cookie,
            self.reconnect_delay,
            heartbeat_key=build_heartbeat_key(live_id),
            heartbeat_check_interval=self.heartbeat_check_interval,
            on_stopped=self._on_worker_stopped,
        )
        with self._lock:
            self._workers[live_id] = worker
        worker.start()
        self._stats['started'] += 1
        print(f'[manager] 启动监听: {live_id} (当前 {len(self._workers)} 个)')

    def _publish_room_event(self, live_id, event_type, message=None):
        payload = {'type': event_type, 'live_id': live_id}
        if message is not None:
            payload['message'] = message
        try:
            redis_util.redis_util.publish(
                f'zbjpd_{live_id}',
                json.dumps(payload, ensure_ascii=False),
            )
        except Exception as e:
            print(f'[manager] 发布 {event_type} 失败: live_id={live_id}, err={e}')

    def _handle_command(self, raw):
        parsed = parse_control_command(raw)
        if not parsed:
            return
        action, live_id, cookie = parsed
        self._stats['commands'] += 1
        print(f'[manager] 收到控制命令: action={action}, live_id={live_id}')
        if action == 'stop':
            self._stop_room(live_id, reason='pubsub')
            return
        self._publish_room_event(live_id, 'starting')
        self._start_room(live_id, cookie)

    def _start_rooms_batch(self, rooms):
        """rooms: [(live_id, cookie), ...]"""
        for i in range(0, len(rooms), self.start_batch_size):
            batch = rooms[i:i + self.start_batch_size]
            for live_id, cookie in batch:
                if self._stop_event.is_set():
                    return
                self._start_room(live_id, cookie)
                if self.start_batch_delay > 0:
                    time.sleep(self.start_batch_delay)
            if i + self.start_batch_size < len(rooms):
                time.sleep(0.5)

    def _command_loop(self):
        pubsub = redis_util.redis_util.create_pubsub()
        try:
            pubsub.subscribe(self.control_channel)
            print(f'[manager] 已订阅控制频道: {self.control_channel}')
        except Exception as e:
            print(f'[manager] 控制频道订阅失败: {e}')
            return

        while not self._stop_event.is_set():
            try:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get('type') == 'message':
                    data = message.get('data')
                    if data is not None:
                        self._handle_command(data)
            except Exception as e:
                if self._stop_event.is_set():
                    break
                print(f'[manager] 控制频道监听异常: {e}')
                if self._stop_event.wait(3):
                    break

        try:
            pubsub.unsubscribe(self.control_channel)
        except Exception:
            pass
        try:
            pubsub.close()
        except Exception:
            pass

    def start(self):
        import dy_live.server as server_module

        redis_cfg = redis_util.redis_util.describe_connection()
        print(f'[manager] server.py={server_module.__file__}')
        print(f'[manager] gift_handler={GIFT_HANDLER_VERSION}')
        print(
            f'[manager] Redis={redis_cfg["host"]}:{redis_cfg["port"]} db={redis_cfg["db"]}'
        )
        print(f'[manager] 监听 Redis 控制频道: {self.control_channel}')
        print(
            '[manager] 控制消息格式: '
            '{"action": "start"|"stop", "live_id": "房间号", "cookie": "..."}'
        )
        print(
            f'[manager] 心跳 Key 前缀={HEARTBEAT_KEY_PREFIX}, '
            f'检测间隔={self.heartbeat_check_interval}s'
        )

        self._command_thread = threading.Thread(
            target=self._command_loop,
            name='live-command',
            daemon=True,
        )
        self._command_thread.start()

        try:
            while True:
                if self._stop_event.wait(10):
                    break
                if self._stop_event.is_set():
                    break
                with self._lock:
                    active = len(self._workers)
                try:
                    redis_util.redis_util.set(
                        SERVER_RUNNING_COUNT_KEY,
                        str(active),
                        ex=30,
                    )
                except Exception as e:
                    if not self._stop_event.is_set():
                        print(f'[manager] 写入服务端运行数失败: {e}')
                if self._stop_event.is_set():
                    break
                print(
                    f'[manager] 心跳: 运行中={active}, '
                    f'累计启动={self._stats["started"]}, '
                    f'累计停止={self._stats["stopped"]}, '
                    f'命令数={self._stats["commands"]}'
                )
        except KeyboardInterrupt:
            print('\n[manager] 收到退出信号')
        finally:
            if not self._stopped:
                self.stop()

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        self._stop_event.set()

        command_thread = self._command_thread
        if command_thread and command_thread.is_alive():
            command_thread.join(timeout=5)

        with self._lock:
            live_ids = list(self._workers.keys())
        for live_id in live_ids:
            self._stop_room(live_id, reason='shutdown', wait=True)
        try:
            redis_util.redis_util.set(SERVER_RUNNING_COUNT_KEY, '0', ex=30)
        except Exception:
            pass
        print('[manager] 已全部停止')


def run_from_config(config=None):
    global _active_manager
    config_path = get_config_file()
    if config is None:
        config = load_config()

    control_channel = config.get('redis_control_channel', DEFAULT_CONTROL_CHANNEL)
    start_batch_size = int(config.get('start_batch_size', 20))
    start_batch_delay = float(config.get('start_batch_delay', 0.05))
    reconnect_delay = float(config.get('reconnect_delay', 5))
    heartbeat_check_interval = float(
        config.get('heartbeat_check_interval', HEARTBEAT_CHECK_INTERVAL)
    )

    print(f'[manager] 配置文件: {config_path}')
    print(f'[manager] control_channel={control_channel}')

    manager = LiveRoomManager(
        control_channel=control_channel,
        start_batch_size=start_batch_size,
        start_batch_delay=start_batch_delay,
        reconnect_delay=reconnect_delay,
        heartbeat_check_interval=heartbeat_check_interval,
    )
    _active_manager = manager
    try:
        manager.start()
    finally:
        _active_manager = None


if __name__ == '__main__':
    print(f'配置文件: {get_config_file()}')
    run_from_config()
