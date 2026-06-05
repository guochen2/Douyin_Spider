import hashlib
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import gzip
import json
import threading
import time
from urllib.parse import urlencode

from websocket import WebSocketApp

import static.Live_pb2 as Live_pb2
from dy_apis.douyin_api import DouyinAPI
from builder.header import HeaderBuilder
from builder.params import Params
import utils.common_util as common_util
from utils.dy_util import generate_signature
import utils.redis_util as redis_util

class DouyinLive:
    def __init__(self, live_id, auth_):
        self.auth_ = auth_
        self.live_id = live_id
        self.ws = None
        self._stop_event = threading.Event()
        self._ping_thread = None

    def stop(self):
        self._stop_event.set()
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def is_stopped(self):
        return self._stop_event.is_set()

    def ping(self, ws):
        while not self._stop_event.is_set():
            frame = Live_pb2.PushFrame()
            frame.payloadType = "hb"
            try:
                ws.send(frame.SerializeToString(), opcode=0x02)
            except Exception:
                ws.close()
                break
            if self._stop_event.wait(5):
                break

    def on_open(self, ws):
        print(f"\033[32m### opened [{self.live_id}] ###\033[m")
        self._ping_thread = threading.Thread(target=self.ping, args=(ws,), daemon=True)
        self._ping_thread.start()

    def on_message(self, ws, message):
        pdid=f"zbjpd_{self.live_id}"
        try:
            frame = Live_pb2.PushFrame()
            frame.ParseFromString(message)
            origin_bytes = gzip.decompress(frame.payload)
            response = Live_pb2.LiveResponse()
            response.ParseFromString(origin_bytes)
            if response.needAck:
                s = Live_pb2.PushFrame()
                s.payloadType = "ack"
                # s.payload = frame.headersList[1].value.encode('utf-8')
                s.payload = response.internalExt.encode('utf-8')
                s.logId = frame.logId
                ws.send(s.SerializeToString(), opcode=0x02)
            for item in response.messagesList:
                if item.method == 'WebcastGiftMessage':
                    message = Live_pb2.GiftMessage()
                    message.ParseFromString(item.payload)
                    # print(item)
                    # print(message)
                    # print(frame.logId)
                    # print(f'\033[1;37;40m[礼物]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 送出 \033[4;30;44m{message.gift.name}\033[m x {message.comboCount}')
                    # 谁给谁送了什么礼物
                    # 礼物会重复 不知道为什么 会有两条一样的 所以需要特殊处理  如果上一条同一个人 同一个礼物存在 则不播放并且清除掉
                    # key=f"{message.user.id}_{message.user.sec_uid}_{pdid}_{message.user.short_id}_{message.gift.id}_{message.comboCount}"
            
                    # print(message)
                    key_md5=f"mc:{pdid}_{message.traceId}"
                    if redis_util.redis_util.exists(key_md5):
                        # redis_util.redis_util.delete(key_md5)
                        print('礼物消息处理过了')
                        # print(f'\033[1;37;40m[礼物]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 送给 \033[1;37;40m{message.toUser.sec_uid} - {message.toUser.nickname}\033[m \033[1;37;41m{message.gift.name}\033[m x {message.totalCount}')
                        return
                    redis_util.redis_util.set(key_md5,1,60)
                    # print(message.gift.combo)
                    # print(f'\033[1;37;40m[礼物]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 送给 \033[1;37;40m{message.toUser.sec_uid} - {message.toUser.nickname}\033[m \033[1;37;41m{message.gift.name}\033[m x {message.totalCount}')
                    redis_util.redis_util.publish(pdid,json.dumps({
                        'type': 'gift',
                        'from_sec_uid': message.user.sec_uid,
                        'from_nickname': message.user.nickname,
                        'to_sec_uid': message.toUser.sec_uid,
                        'to_nickname': message.toUser.nickname,
                        'gift_name': message.gift.name,
                        'gift_count': message.totalCount
                    }, ensure_ascii=False))
                elif item.method == "WebcastChatMessage":
                    message = Live_pb2.ChatMessage()
                    message.ParseFromString(item.payload)
                    # 用户等级
                    # print(message.user.badge_image_list[0])
                    # print(f'\033[1;37;40m[消息]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m : \033[4;30;44m{message.content}\033[m')
                    redis_util.redis_util.publish(pdid,json.dumps({
                        'type': 'chat',
                        'from_sec_uid': message.user.sec_uid,
                        'from_nickname': message.user.nickname,
                        'content': message.content
                    }, ensure_ascii=False))
                        
                elif item.method == "WebcastMemberMessage":
                    message = Live_pb2.MemberMessage()
                    message.ParseFromString(item.payload)
                    # print(f'\033[1;37;40m[进入]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 进入直播间')
                    redis_util.redis_util.publish(pdid,json.dumps({
                        'type': 'enter',
                        'from_sec_uid': message.user.sec_uid,
                        'from_nickname': message.user.nickname,
                    }, ensure_ascii=False))
                elif item.method == "WebcastLikeMessage":
                    message = Live_pb2.LikeMessage()
                    message.ParseFromString(item.payload)
                    # print(f'\033[1;37;40m[点赞]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 点赞了 {message.count} 次')
                    redis_util.redis_util.publish(pdid,json.dumps({
                        'type': 'like',
                        'from_sec_uid': message.user.sec_uid,
                        'from_nickname': message.user.nickname,
                        'count': message.count
                    }, ensure_ascii=False))
                    print(f'\033[1;37;40m[点赞]点赞总数 = {message.total}\033[m')
                elif item.method == "WebcastSocialMessage":
                    message = Live_pb2.SocialMessage()
                    message.ParseFromString(item.payload)
                    if message.action == 1:
                        # print(f'\033[1;37;40m[关注]SEC_UID = {message.user.sec_uid} - {message.user.nickname}\033[m 关注主播')
                        redis_util.redis_util.publish(pdid,json.dumps({
                            'type': 'follow',
                            'from_sec_uid': message.user.sec_uid,
                            'from_nickname': message.user.nickname
                        }, ensure_ascii=False))
                elif item.method == "WebcastRoomStatsMessage":
                    message = Live_pb2.RoomStatsMessage()
                    message.ParseFromString(item.payload)
                    # print(f'\033[1;37;40m[房间信息] {message.displayLong}')
                    redis_util.redis_util.publish(pdid,json.dumps({
                        'type': 'room_stats',
                        'display_long': message.displayLong
                    }, ensure_ascii=False))

            # s = zlib.decompress(decode_str).decode()
        except Exception as e:
            print('error')
            print(str(e))

    def on_error(self, ws, error):
        print("\033[31m### error ###")
        print(error)
        print("### ===error=== ###\033[m")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"\033[31m### closed [{self.live_id}] ###")
        print(f"status_code: {close_status_code}, msg: {close_msg}")
        print("### ===closed=== ###\033[m")

    def _build_ws(self):
        room_info = DouyinAPI.get_live_info(self.auth_, self.live_id)
        if room_info is None or isinstance(room_info, tuple):
            print(f"\033[31m### [{self.live_id}] 获取直播间信息失败 ###\033[m")
            return None
        room_id = room_info['room_id']
        user_id = room_info['user_id']
        params = Params()

        res = DouyinAPI.get_webcast_detail(self.auth_, str(user_id), room_id, f"https://live.douyin.com/{self.live_id}")
        frame = Live_pb2.LiveResponse()
        frame.ParseFromString(res)
        (params
         .add_param('app_name', 'douyin_web')
         .add_param('version_code', '180800')
         .add_param('webcast_sdk_version', '1.0.15')
         .add_param('update_version_code', '1.0.15')
         .add_param('compress', 'gzip')
         .add_param('device_platform', 'web')
         .add_param('cookie_enabled', 'true')
         .add_param('screen_width', '3440')
         .add_param('screen_height', '1440')
         .add_param('browser_language', 'zh-CN')
         .add_param('browser_platform', 'Win32')
         .add_param('browser_name', 'Mozilla')
         .add_param('browser_version',
                    HeaderBuilder.ua.split('Mozilla/')[-1])
         .add_param('browser_online', 'true')
         .add_param('tz_name', 'Asia/Shanghai')
         .add_param('cursor', str(frame.cursor))
         .add_param('internal_ext', frame.internalExt)
         .add_param('host', 'https://live.douyin.com')
         .add_param('aid', '6383')
         .add_param('live_id', '1')
         .add_param('did_rule', '3')
         .add_param('endpoint', 'live_pc')
         .add_param('support_wrds', '1')
         .add_param('user_unique_id', str(user_id))
         .add_param('im_path', '/webcast/im/fetch/')
         .add_param('identity', 'audience')
         .add_param('need_persist_msg_count', '15')
         .add_param('insert_task_id', '')
         .add_param('live_reason', '')
         .add_param('room_id', room_id)
         .add_param('heartbeatDuration', '0')
         .add_param('signature', generate_signature(room_id, user_id))
         )
        wss_url = f"wss://webcast100-ws-web-hl.douyin.com/webcast/im/push/v2/?{urlencode(params.get())}"
        return WebSocketApp(
            url=wss_url,
            header={
                'Pragma': 'no-cache',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                'User-Agent': HeaderBuilder.ua,
                'Upgrade': 'websocket',
                'Cache-Control': 'no-cache',
                'Connection': 'Upgrade',
            },
            cookie=self.auth_.cookie_str,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

    def start_ws(self, reconnect=True, reconnect_delay=5):
        while not self._stop_event.is_set():
            self.ws = self._build_ws()
            if self.ws is None:
                if not reconnect or self._stop_event.wait(reconnect_delay):
                    break
                continue
            try:
                self.ws.run_forever(origin='https://live.douyin.com')
            except Exception as e:
                print(f"[{self.live_id}] ws error: {e}")
                if self.ws:
                    try:
                        self.ws.close()
                    except Exception:
                        pass
            if self._stop_event.is_set():
                break
            if not reconnect:
                break
            print(f"[{self.live_id}] {reconnect_delay}s 后重连...")
            if self._stop_event.wait(reconnect_delay):
                break

def get_config_file():
    if getattr(sys, 'frozen', None):
        exe_dir = os.path.dirname(sys.executable)
        config_file = os.path.join(exe_dir, 'launcher_config.json')
        if os.path.exists(config_file):
            return config_file
        return os.path.join(os.getcwd(), 'launcher_config.json')
    # 与 launcher.py 一致：优先读取项目根目录配置
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root_config = os.path.join(project_root, 'launcher_config.json')
    if os.path.exists(root_config):
        return root_config
    return os.path.join(os.path.dirname(__file__), 'launcher_config.json')

CONFIG_FILE = get_config_file()
def get_md5(s: str) -> str:
    # 1. 字符串必须转成 bytes 才能计算 md5
    # 2. 使用 utf-8 编码最通用
    md5_obj = hashlib.md5(s.encode("utf-8"))
    # 返回 32 位小写 md5
    return md5_obj.hexdigest()
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}
if __name__ == '__main__':
    print(CONFIG_FILE)
    config = load_config()
    # 写入环境变量 
    if config.get('live_cookies', ''):        
        os.environ['DY_LIVE_COOKIES'] = config.get('live_cookies', '')
    if config.get('cookies', ''):        
        os.environ['DY_COOKIES'] = config.get('cookies', '')
    if config.get('live_id', ''):
        os.environ['DY_LIVE_ID'] = config.get('live_id', '')
 
    common_util.load_env()
    live_id = os.getenv('DY_LIVE_ID', "")
    live = DouyinLive(live_id, common_util.dy_live_auth) 
    live.start_ws()
