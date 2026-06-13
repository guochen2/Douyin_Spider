import os
import secrets
import string

REDIS_PASSWORD_LENGTH = 12
_PASSWORD_ALPHABET = string.ascii_letters + string.digits


def generate_redis_password(length=REDIS_PASSWORD_LENGTH):
    """生成 Redis 密码（默认 12 位字母数字）。"""
    size = max(8, int(length))
    return ''.join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(size))


def ensure_redis_password(config=None):
    """从环境变量、配置读取密码；缺失时自动生成。"""
    env_pwd = os.getenv('REDIS_PASSWORD', '').strip()
    if env_pwd:
        return env_pwd

    config = config or {}
    saved = str(config.get('redis_password', '')).strip()
    if saved:
        return saved
    return generate_redis_password()
