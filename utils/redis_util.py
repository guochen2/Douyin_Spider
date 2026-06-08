import redis
from redis.exceptions import RedisError

# ======================
# 全局配置（改这里即可）
# ======================
REDIS_CONFIG = {
    "host": "39.98.176.249",
    "port": 3521,
    "db": 2,
    "password": 'bsUb8C2BrdkEHs6C637E4EENSuQ5e8',  # 有密码就填
    "decode_responses": True,  # 自动返回字符串，不用 decode
    "socket_timeout": 10,
    "socket_connect_timeout": 5,
    "retry_on_timeout": True,
    "health_check_interval": 30,
}

# ======================
# 单例 Redis 客户端
# ======================
class RedisUtil:
    _instance = None  # 单例

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # 初始化连接池 + 客户端
            cls._instance.pool = redis.ConnectionPool(**REDIS_CONFIG)
            cls._instance.client = redis.Redis(
                connection_pool=cls._instance.pool
            )
        return cls._instance

    # ======================
    # 通用方法
    # ======================
    def get(self, key):
        try:
            return self.client.get(key)
        except RedisError as e:
            print(f"Redis GET 错误: {e}")
            return None
        
    def exists(self, key):
        """判断 Redis 中是否存在某个 key。出错时返回 None，避免误判为不存在。"""
        try:
            # exists 返回 1=存在 0=不存在
            return self.client.exists(key) == 1
        except RedisError as e:
            print(f"Redis EXISTS 错误: {e}")
            return None
        

    def set(self, key, value, ex=None):
        try:
            return self.client.set(key, value, ex=ex)
        except RedisError as e:
            print(f"Redis SET 错误: {e}")
            return False

    def delete(self, key):
        try:
            return self.client.delete(key)
        except RedisError as e:
            print(f"Redis DEL 错误: {e}")
            return 0

    def lrange(self, key, start=0, end=-1):
        try:
            return self.client.lrange(key, start, end)
        except RedisError as e:
            print(f"Redis LRANGE 错误: {e}")
            return []

    def llen(self, key):
        try:
            return self.client.llen(key)
        except RedisError as e:
            print(f"Redis LLEN 错误: {e}")
            return 0

    def create_pubsub(self):
        return self.client.pubsub()

    # ======================
    # 发布订阅
    # ======================
    def publish(self, channel, message):
        """发布消息"""
        try:
            return self.client.publish(channel, message)
        except RedisError as e:
            print(f"Redis 发布失败: {e}")
            return 0

    def subscribe(self, channel):
        """订阅频道，返回 pubsub 对象"""
        pubsub = self.client.pubsub()
        pubsub.subscribe(channel)
        return pubsub

# ======================
# 导出全局单例
# ======================
redis_util = RedisUtil()