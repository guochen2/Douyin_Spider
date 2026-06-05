import json
import os
import sys
import threading
import time

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import utils.redis_util as redis_util
from builder.auth import DouyinAuth
from dy_live.server import DouyinLive, get_config_file, load_config


def create_live_auth(cookie_str):
    auth = DouyinAuth()
    auth.perepare_auth(cookie_str, "", "")
    return auth


def parse_room_entry(raw):
    """
    解析 Redis 列表项，必须同时包含 live_id 与 cookie。
    格式: {"live_id": "房间号", "cookie": "cookie字符串"}
    """
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print(f"[manager] 跳过无效条目（需 JSON 格式）: {text[:80]}...")
        return None
    if not isinstance(data, dict):
        return None
    live_id = str(data.get('live_id', '')).strip()
    cookie = str(data.get('cookie', '')).strip()
    if not live_id or not cookie:
        print(f"[manager] 跳过不完整条目（缺少 live_id 或 cookie）: {text[:80]}...")
        return None
    return live_id, cookie


class LiveRoomWorker:
    def __init__(self, live_id, cookie, reconnect_delay=5):
        self.live_id = live_id
        self.cookie = cookie
        self.live = DouyinLive(live_id, create_live_auth(cookie))
        self.reconnect_delay = reconnect_delay
        self.thread = threading.Thread(
            target=self._run,
            name=f"live-{live_id}",
            daemon=True,
        )

    def _run(self):
        self.live.start_ws(reconnect=True, reconnect_delay=self.reconnect_delay)

    def start(self):
        self.thread.start()

    def stop(self, timeout=15):
        self.live.stop()
        self.thread.join(timeout=timeout)
        return not self.thread.is_alive()


class LiveRoomManager:
    def __init__(
        self,
        list_key,
        poll_interval=3,
        start_batch_size=20,
        start_batch_delay=0.05,
        reconnect_delay=5,
        use_keyspace_notify=True,
    ):
        self.list_key = list_key
        self.poll_interval = poll_interval
        self.start_batch_size = start_batch_size
        self.start_batch_delay = start_batch_delay
        self.reconnect_delay = reconnect_delay
        self.use_keyspace_notify = use_keyspace_notify

        self._workers = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._sync_event = threading.Event()
        self._stats = {'started': 0, 'stopped': 0, 'sync_count': 0}

    def _fetch_target_rooms(self):
        items = redis_util.redis_util.lrange(self.list_key, 0, -1)
        target = {}
        for item in items:
            parsed = parse_room_entry(item)
            if parsed:
                live_id, cookie = parsed
                target[live_id] = cookie
        return target

    def _start_room(self, live_id, cookie):
        with self._lock:
            if live_id in self._workers:
                return
            worker = LiveRoomWorker(live_id, cookie, self.reconnect_delay)
            self._workers[live_id] = worker
        worker.start()
        self._stats['started'] += 1
        print(f"[manager] 启动监听: {live_id} (当前 {len(self._workers)} 个)")

    def _stop_room(self, live_id):
        with self._lock:
            worker = self._workers.pop(live_id, None)
        if not worker:
            return
        ok = worker.stop()
        self._stats['stopped'] += 1
        status = '已停止' if ok else '停止超时'
        print(f"[manager] {status}: {live_id} (当前 {len(self._workers)} 个)")

    def sync(self, reason='manual'):
        try:
            target = self._fetch_target_rooms()
        except Exception as e:
            print(f"[manager] 读取 Redis 列表失败: {e}")
            return

        with self._lock:
            current = dict(self._workers)

        current_ids = set(current.keys())
        target_ids = set(target.keys())

        to_remove = sorted(current_ids - target_ids)
        to_add = sorted(target_ids - current_ids)
        to_update = sorted(
            live_id for live_id in (current_ids & target_ids)
            if current[live_id].cookie != target[live_id]
        )

        if not to_remove and not to_add and not to_update:
            return

        parts = []
        if to_add:
            parts.append(f"+{len(to_add)}")
        if to_remove:
            parts.append(f"-{len(to_remove)}")
        if to_update:
            parts.append(f"~{len(to_update)}")
        print(
            f"[manager] 同步({reason}): {' '.join(parts)} "
            f"目标={len(target)} 运行中={len(current)}"
        )

        for live_id in to_remove:
            self._stop_room(live_id)

        for live_id in to_update:
            self._stop_room(live_id)

        to_start = [(live_id, target[live_id]) for live_id in sorted(set(to_add) | set(to_update))]
        if to_start:
            self._start_rooms_batch(to_start)

        self._stats['sync_count'] += 1

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

    def _poll_loop(self):
        while not self._stop_event.is_set():
            self.sync(reason='poll')
            self._stop_event.wait(self.poll_interval)

    def _keyspace_loop(self):
        db = redis_util.REDIS_CONFIG.get('db', 0)
        pattern = f'__keyspace@{db}__:{self.list_key}'
        pubsub = redis_util.redis_util.create_pubsub()
        try:
            pubsub.psubscribe(pattern)
            print(f"[manager] 已订阅 Redis keyspace: {pattern}")
        except Exception as e:
            print(f"[manager] keyspace 订阅失败，仅使用轮询: {e}")
            return

        while not self._stop_event.is_set():
            try:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get('type') in ('pmessage', 'message'):
                    self._sync_event.set()
            except Exception as e:
                print(f"[manager] keyspace 监听异常: {e}")
                if self._stop_event.wait(3):
                    break

        try:
            pubsub.close()
        except Exception:
            pass

    def _sync_dispatcher(self):
        while not self._stop_event.is_set():
            triggered = self._sync_event.wait(timeout=1.0)
            self._sync_event.clear()
            if triggered:
                self.sync(reason='keyspace')

    def start(self):
        print(f"[manager] 监听 Redis 列表: {self.list_key}")
        print(
            f"[manager] 列表项格式: "
            '{"live_id": "房间号", "cookie": "cookie字符串"}'
        )
        print(
            f"[manager] 轮询间隔={self.poll_interval}s, "
            f"批量启动={self.start_batch_size}, "
            f"keyspace={'开' if self.use_keyspace_notify else '关'}"
        )
        self.sync(reason='init')

        threads = [
            threading.Thread(target=self._poll_loop, name='live-poll', daemon=True),
            threading.Thread(target=self._sync_dispatcher, name='live-sync', daemon=True),
        ]
        if self.use_keyspace_notify:
            threads.append(
                threading.Thread(target=self._keyspace_loop, name='live-keyspace', daemon=True)
            )
        for t in threads:
            t.start()

        try:
            while not self._stop_event.is_set():
                time.sleep(10)
                with self._lock:
                    active = len(self._workers)
                print(
                    f"[manager] 心跳: 运行中={active}, "
                    f"累计启动={self._stats['started']}, "
                    f"累计停止={self._stats['stopped']}"
                )
        except KeyboardInterrupt:
            print("\n[manager] 收到退出信号")
        finally:
            self.stop()

    def stop(self):
        self._stop_event.set()
        self._sync_event.set()
        with self._lock:
            live_ids = list(self._workers.keys())
        for live_id in live_ids:
            self._stop_room(live_id)
        print("[manager] 已全部停止")


def run_from_config(config=None):
    config_path = get_config_file()
    if config is None:
        config = load_config()

    list_key = config.get('redis_list_key', 'dy_live:rooms')
    poll_interval = float(config.get('poll_interval', 3))
    start_batch_size = int(config.get('start_batch_size', 20))
    start_batch_delay = float(config.get('start_batch_delay', 0.05))
    reconnect_delay = float(config.get('reconnect_delay', 5))
    use_keyspace_notify = config.get('use_keyspace_notify', True)

    print(f"[manager] 配置文件: {config_path}")
    print(f"[manager] poll_interval={poll_interval}s")

    manager = LiveRoomManager(
        list_key=list_key,
        poll_interval=poll_interval,
        start_batch_size=start_batch_size,
        start_batch_delay=start_batch_delay,
        reconnect_delay=reconnect_delay,
        use_keyspace_notify=use_keyspace_notify,
    )
    manager.start()


if __name__ == '__main__':
    print(f"配置文件: {get_config_file()}")
    run_from_config()
