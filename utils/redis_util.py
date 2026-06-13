import os

import redis
from redis.exceptions import RedisError


def _load_redis_config():
    embedded = os.getenv('EMBEDDED_REDIS', '').lower() not in ('0', 'false', 'no', 'off', 'external')
    default_host = '127.0.0.1' if embedded or os.path.exists('/.dockerenv') else '39.98.176.249'
    default_port = '6379' if embedded or os.path.exists('/.dockerenv') else '3521'
    default_db = '0' if embedded or os.path.exists('/.dockerenv') else '2'
    default_password = 'douyin_local_redis' if embedded else 'bsUb8C2BrdkEHs6C637E4EENSuQ5e8'

    port = os.getenv('REDIS_PORT', default_port)
    db = os.getenv('REDIS_DB', default_db)
    password = os.getenv('REDIS_PASSWORD', default_password) or None
    return {
        'host': os.getenv('REDIS_HOST', default_host),
        'port': int(port),
        'db': int(db),
        'password': password,
        'decode_responses': True,
        'socket_timeout': 10,
        'socket_connect_timeout': 5,
        'retry_on_timeout': True,
        'health_check_interval': 30,
    }


class RedisUtil:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _ensure_connected(self):
        if self._initialized:
            return
        config = _load_redis_config()
        self.pool = redis.ConnectionPool(**config)
        self.client = redis.Redis(connection_pool=self.pool)
        self._initialized = True

    def reset(self):
        self._initialized = False
        self.pool = None
        self.client = None

    def get(self, key):
        self._ensure_connected()
        try:
            return self.client.get(key)
        except RedisError as e:
            print(f'Redis GET 错误: {e}')
            return None

    def exists(self, key):
        self._ensure_connected()
        try:
            return self.client.exists(key) == 1
        except RedisError as e:
            print(f'Redis EXISTS 错误: {e}')
            return None

    def set(self, key, value, ex=None):
        self._ensure_connected()
        try:
            return self.client.set(key, value, ex=ex)
        except RedisError as e:
            print(f'Redis SET 错误: {e}')
            return False

    def delete(self, key):
        self._ensure_connected()
        try:
            return self.client.delete(key)
        except RedisError as e:
            print(f'Redis DEL 错误: {e}')
            return 0

    def lrange(self, key, start=0, end=-1):
        self._ensure_connected()
        try:
            return self.client.lrange(key, start, end)
        except RedisError as e:
            print(f'Redis LRANGE 错误: {e}')
            return []

    def llen(self, key):
        self._ensure_connected()
        try:
            return self.client.llen(key)
        except RedisError as e:
            print(f'Redis LLEN 错误: {e}')
            return 0

    def create_pubsub(self):
        self._ensure_connected()
        return self.client.pubsub()

    def publish(self, channel, message):
        self._ensure_connected()
        try:
            return self.client.publish(channel, message)
        except RedisError as e:
            print(f'Redis 发布失败: {e}')
            return 0

    def subscribe(self, channel):
        self._ensure_connected()
        pubsub = self.client.pubsub()
        pubsub.subscribe(channel)
        return pubsub


redis_util = RedisUtil()
