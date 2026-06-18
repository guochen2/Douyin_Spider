import hashlib
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import gzip
import json
import threading
import time
from collections import deque
from urllib.parse import urlencode

from google.protobuf.message import DecodeError
from websocket import WebSocketApp

import static.Live_pb2 as Live_pb2
from dy_apis.douyin_api import DouyinAPI
from builder.header import HeaderBuilder
from builder.params import Params
import utils.common_util as common_util
from utils.dy_util import generate_signature
import utils.redis_util as redis_util

GIFT_HANDLER_VERSION = 'v20260610'

class DouyinLive:
    def __init__(self, live_id, auth_):
        self.auth_ = auth_
        self.live_id = live_id
        self.ws = None
        self._stop_event = threading.Event()
        self._ping_thread = None
        self._fetch_thread = None
        self._room_id = ''
        self._user_id = ''
        self._cursor = ''
        self._internal_ext = ''
        self._live_page_url = ''
        self._live_aborted = False
        self._last_room_check_at = 0.0
        self._ws_connected = False
        self._seen_msg_keys = set()
        self._seen_msg_order = deque(maxlen=5000)
        self._seen_gift_keys = set()
        self._seen_gift_order = deque(maxlen=10000)

    LIVE_ROOM_STATUSES = {'2'}
    ROOM_CHECK_INTERVAL = 15.0
    COOKIE_ERROR_HINT = 'Cookie 无效或已过期，请重新登录获取 Cookie'

    def stop(self):
        self._stop_event.set()
        self._ws_connected = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def is_stopped(self):
        return self._stop_event.is_set()

    def _channel(self):
        return f"zbjpd_{self.live_id}"

    def _is_room_live(self, room_info):
        if not room_info or isinstance(room_info, tuple):
            return False
        status = str(room_info.get('room_status', '')).strip()
        return status in self.LIVE_ROOM_STATUSES

    def _abort_live(self, message):
        if self._live_aborted:
            return
        self._live_aborted = True
        print(f'\033[31m### {message}，关闭连接 ###\033[m')
        self._publish_live_error(message)
        self.stop()

    def _check_room_live_status(self):
        now = time.time()
        if now - self._last_room_check_at < self.ROOM_CHECK_INTERVAL:
            return True
        self._last_room_check_at = now
        room_info = DouyinAPI.get_live_info(self.auth_, self.live_id)
        if room_info is None or isinstance(room_info, tuple):
            return True
        if self._is_room_live(room_info):
            return True
        self._abort_live(f'[{self.live_id}] 直播间未开播或已下播')
        return False

    def _parse_control_status(self, payload):
        if not payload:
            return None
        index = 0
        while index < len(payload):
            tag = payload[index]
            index += 1
            field_number = tag >> 3
            wire_type = tag & 0x07
            if wire_type != 0:
                break
            value = 0
            shift = 0
            while index < len(payload):
                byte = payload[index]
                index += 1
                value |= (byte & 0x7F) << shift
                if not (byte & 0x80):
                    break
                shift += 7
            if field_number == 1:
                return value
        return None

    def _sync_auth_ttwid(self, ttwid):
        if not ttwid:
            return
        self.auth_.cookie['ttwid'] = ttwid
        self.auth_.cookie_str = '; '.join(f'{k}={v}' for k, v in self.auth_.cookie.items())

    def _update_fetch_state(self, response):
        if response.cursor:
            self._cursor = response.cursor
        if response.internalExt:
            self._internal_ext = response.internalExt

    def _send_ack(self, ws, log_id, internal_ext):
        if ws is None or not internal_ext:
            return
        ack = Live_pb2.PushFrame()
        ack.payloadType = 'ack'
        ack.payload = internal_ext.encode('utf-8')
        ack.logId = log_id
        ws.send(ack.SerializeToString(), opcode=0x02)

    def _should_dispatch_item(self, item):
        msg_id = getattr(item, 'msgId', 0) or 0
        if not msg_id:
            return True
        key = (item.method, msg_id)
        if key in self._seen_msg_keys:
            return False
        self._seen_msg_keys.add(key)
        self._seen_msg_order.append(key)
        while len(self._seen_msg_order) > 5000:
            old = self._seen_msg_order.popleft()
            self._seen_msg_keys.discard(old)
        return True

    def _gift_dedup_key(self, item, message):
        msg_id = int(getattr(item, 'msgId', 0) or 0)
        offset = int(getattr(item, 'offset', 0) or 0)
        if msg_id or offset:
            return ('msg', msg_id, offset)
        payload = bytes(item.payload or b'')
        if payload:
            return ('payload', hashlib.md5(payload).hexdigest())
        trace = str(message.traceId or '').strip()
        nickname = message.user.nickname if message.user else ''
        gift_id = str(message.giftId or '')
        log_id = str(message.logId or '')
        return (
            'fallback',
            trace,
            log_id,
            gift_id,
            nickname,
            int(message.totalCount or 0),
            int(message.repeatCount or 0),
        )

    def _remember_gift_key(self, dedup_key):
        if dedup_key in self._seen_gift_keys:
            return False
        self._seen_gift_keys.add(dedup_key)
        self._seen_gift_order.append(dedup_key)
        while len(self._seen_gift_order) > 10000:
            old = self._seen_gift_order.popleft()
            self._seen_gift_keys.discard(old)
        return True

    def _resolve_gift_publish_count(self, message):
        """
        repeatCount 为本次推送数量；连击礼物会多次推送且 repeatCount 通常为 1。
        无 repeatCount 时回退到 groupCount / totalCount。
        """
        repeat = max(int(message.repeatCount or 0), 0)
        if repeat > 0:
            return repeat
        group = max(int(message.groupCount or 0), 0)
        if group > 0:
            return group
        total = max(int(message.totalCount or 0), 0)
        if total > 0:
            return total
        combo = max(int(message.comboCount or 0), 0)
        if combo > 0:
            return combo
        return 1

    def _handle_gift_message(self, item):
        pdid = self._channel()
        message = Live_pb2.GiftMessage()
        message.ParseFromString(item.payload)

        dedup_key = self._gift_dedup_key(item, message)
        if not self._remember_gift_key(dedup_key):
            return

        gift_count = self._resolve_gift_publish_count(message)
        if gift_count <= 0:
            return

        nickname = message.user.nickname if message.user else ''
        to_nickname = message.toUser.nickname if message.toUser else ''
        gift_name = message.gift.name if message.gift else ''
        if not gift_name:
            return

        subs = redis_util.redis_util.publish(pdid, json.dumps({
            'type': 'gift',
            'from_sec_uid': message.user.sec_uid if message.user else '',
            'from_nickname': nickname,
            'to_sec_uid': message.toUser.sec_uid if message.toUser else '',
            'to_nickname': to_nickname,
            'gift_name': gift_name,
            'gift_count': gift_count,
            'trace_id': str(message.traceId or ''),
            'msg_id': getattr(item, 'msgId', 0) or 0,
        }, ensure_ascii=False))
        # print(
        #     f'[gift-pub][{GIFT_HANDLER_VERSION}] channel={pdid} '
        #     f'user={nickname} gift={gift_name} count={gift_count} subs={subs} '
        #     f'repeat={message.repeatCount} total={message.totalCount}'
        # )
        if subs <= 0:
            print(
                f'[{self.live_id}] 警告: 礼物已发布但 Redis 无订阅者 channel={pdid} '
                f'(请确认客户端与 Spider 连接同一 Redis)'
            )

    def _dispatch_message(self, item):
        pdid = self._channel()
        if item.method == 'WebcastChatMessage':
            message = Live_pb2.ChatMessage()
            message.ParseFromString(item.payload)
            # print(f'\033[1;37;40m[消息]{message.user.nickname}\033[m : {message.content}')
            redis_util.redis_util.publish(pdid, json.dumps({
                'type': 'chat',
                'from_sec_uid': message.user.sec_uid,
                'from_nickname': message.user.nickname,
                'content': message.content,
            }, ensure_ascii=False))
        elif item.method == 'WebcastMemberMessage':
            message = Live_pb2.MemberMessage()
            message.ParseFromString(item.payload)
            # print(f'\033[1;37;40m[进入]{message.user.nickname}\033[m 进入直播间')
            redis_util.redis_util.publish(pdid, json.dumps({
                'type': 'enter',
                'from_sec_uid': message.user.sec_uid,
                'from_nickname': message.user.nickname,
            }, ensure_ascii=False))
        elif item.method == 'WebcastLikeMessage':
            message = Live_pb2.LikeMessage()
            message.ParseFromString(item.payload)
            # print(f'\033[1;37;40m[点赞]{message.user.nickname}\033[m 点赞 {message.count} 次')
            redis_util.redis_util.publish(pdid, json.dumps({
                'type': 'like',
                'from_sec_uid': message.user.sec_uid,
                'from_nickname': message.user.nickname,
                'count': message.count,
            }, ensure_ascii=False))
        elif item.method == 'WebcastSocialMessage':
            message = Live_pb2.SocialMessage()
            message.ParseFromString(item.payload)
            if message.action == 1:
                # print(f'\033[1;37;40m[关注]{message.user.nickname}\033[m 关注主播')
                redis_util.redis_util.publish(pdid, json.dumps({
                    'type': 'follow',
                    'from_sec_uid': message.user.sec_uid,
                    'from_nickname': message.user.nickname,
                }, ensure_ascii=False))
        elif item.method == 'WebcastRoomStatsMessage':
            message = Live_pb2.RoomStatsMessage()
            message.ParseFromString(item.payload)
            # print(f'\033[1;37;40m[房间信息] {message.displayLong}')
            redis_util.redis_util.publish(pdid, json.dumps({
                'type': 'room_stats',
                'display_long': message.displayLong,
            }, ensure_ascii=False))
        elif item.method == 'WebcastControlMessage':
            status = self._parse_control_status(item.payload)
            if status in (3, 4):
                self._abort_live(f'[{self.live_id}] 直播间已结束 (status={status})')

    def _process_live_response(self, ws, response, log_id=0):
        if self._live_aborted:
            return 0
        self._update_fetch_state(response)
        if response.needAck:
            self._send_ack(ws, log_id, response.internalExt)
        if not response.messagesList:
            return 0
        for item in response.messagesList:
            if item.method == 'WebcastGiftMessage':
                try:
                    self._handle_gift_message(item)
                except Exception as e:
                    print(f'[{self.live_id}] 解析礼物失败: {e}')
                continue
            if not self._should_dispatch_item(item):
                continue
            try:
                self._dispatch_message(item)
            except Exception as e:
                print(f'[{self.live_id}] 解析消息失败 method={item.method}: {e}')
        return len(response.messagesList)

    def _fetch_im_messages(self):
        if not self._room_id or not self._user_id:
            return None
        res = DouyinAPI.get_webcast_detail(
            self.auth_,
            str(self._user_id),
            self._room_id,
            self._live_page_url,
            cursor=self._cursor,
            internal_ext=self._internal_ext,
        )
        if not res:
            return None
        response, err = self._parse_live_response_bytes(res)
        if err:
            self._fail_cookie_error(err)
            return None
        count = self._process_live_response(None, response)
        return response.fetchInterval, count

    def _fetch_loop(self):
        while not self._stop_event.is_set():
            if not self._check_room_live_status():
                break
            # WebSocket 已连接时由 on_message 推送，避免与 im/fetch 重复
            if self._ws_connected:
                if self._stop_event.wait(1.0):
                    break
                continue
            try:
                result = self._fetch_im_messages()
                if self._live_aborted:
                    break
                if result is None:
                    wait_seconds = 1.0
                else:
                    fetch_interval, _count = result
                    wait_seconds = fetch_interval / 1000 if fetch_interval else 1.0
                    wait_seconds = max(min(wait_seconds, 3.0), 0.5)
            except Exception as e:
                print(f'[{self.live_id}] im/fetch 轮询异常: {e}')
                wait_seconds = 3.0
            if self._stop_event.wait(wait_seconds):
                break

    def ping(self, ws):
        while not self._stop_event.is_set():
            frame = Live_pb2.PushFrame()
            frame.payloadType = 'hb'
            try:
                ws.send(frame.SerializeToString(), opcode=0x02)
            except Exception:
                ws.close()
                break
            if self._stop_event.wait(5):
                break

    def publish_listening(self):
        """向客户端频道重新发送 listening 确认（用于重连时服务端已在监听）。"""
        if self._live_aborted or self.is_stopped():
            return
        redis_util.redis_util.publish(self._channel(), json.dumps({
            'type': 'listening',
            'live_id': self.live_id,
        }, ensure_ascii=False))

    def on_open(self, ws):
        if self._live_aborted:
            ws.close()
            return
        self._ws_connected = True
        print(f'\033[32m### opened [{self.live_id}] ###\033[m')
        self.publish_listening()
        self._ping_thread = threading.Thread(target=self.ping, args=(ws,), name=f'ping-{self.live_id}', daemon=True)
        self._ping_thread.start()

    def on_message(self, ws, message):
        try:
            frame = Live_pb2.PushFrame()
            frame.ParseFromString(message)
            origin_bytes = gzip.decompress(frame.payload)
            response = Live_pb2.LiveResponse()
            response.ParseFromString(origin_bytes)
            count = self._process_live_response(ws, response, frame.logId)
            # if count:
                # print(f'[{self.live_id}] WS 收到 {count} 条消息')
        except Exception as e:
            print(f'[{self.live_id}] WS 消息解析失败: {e}')

    def on_error(self, ws, error):
        print('\033[31m### error ###')
        print(error)
        print('### ===error=== ###\033[m')

    def on_close(self, ws, close_status_code, close_msg):
        self._ws_connected = False
        print(f'\033[31m### closed [{self.live_id}] ###')
        print(f'status_code: {close_status_code}, msg: {close_msg}')
        print('### ===closed=== ###\033[m')

    def _publish_live_error(self, message):
        redis_util.redis_util.publish(self._channel(), json.dumps({
            'type': 'live_error',
            'live_id': self.live_id,
            'message': message,
        }, ensure_ascii=False))

    def _fail_cookie_error(self, detail=None):
        message = f'[{self.live_id}] {self.COOKIE_ERROR_HINT}'
        if detail:
            print(f'\033[31m### [{self.live_id}] {detail} ###\033[m')
        self._publish_live_error(message)
        self._live_aborted = True

    def _looks_like_non_protobuf_payload(self, data):
        if not data:
            return True
        sample = data[:256].lstrip()
        if not sample:
            return True
        if sample[:1] in (b'<', b'{', b'['):
            return True
        if b'html' in sample[:128].lower() or b'<!doctype' in sample[:128].lower():
            return True
        return False

    def _parse_live_response_bytes(self, data):
        if self._looks_like_non_protobuf_payload(data):
            return None, self.COOKIE_ERROR_HINT
        try:
            response = Live_pb2.LiveResponse()
            response.ParseFromString(data)
            return response, None
        except DecodeError:
            return None, self.COOKIE_ERROR_HINT
        except Exception as e:
            return None, f'解析直播数据失败: {e}'

    def _build_ws(self):
        try:
            room_info = DouyinAPI.get_live_info(self.auth_, self.live_id)
            if room_info is None or isinstance(room_info, tuple):
                err = f'[{self.live_id}] 获取直播间信息失败，请检查 Cookie 或直播间是否开播'
                print(f'\033[31m### {err} ###\033[m')
                self._publish_live_error(err)
                self._live_aborted = True
                return None

            if not self._is_room_live(room_info):
                self._abort_live(f'[{self.live_id}] 直播间未开播')
                return None

            self._sync_auth_ttwid(room_info.get('ttwid'))
            self._room_id = room_info['room_id']
            self._user_id = room_info['user_id']
            self._live_page_url = f'https://live.douyin.com/{self.live_id}'

            res = DouyinAPI.get_webcast_detail(
                self.auth_,
                str(self._user_id),
                self._room_id,
                self._live_page_url,
            )
            bootstrap, err = self._parse_live_response_bytes(res)
            if err:
                self._fail_cookie_error(err)
                return None
            bootstrap_count = self._process_live_response(None, bootstrap)
            print(
                f'[{self.live_id}] 初始 im/fetch: messages={bootstrap_count}, '
                f'cursor={self._cursor[:48] if self._cursor else "-"}'
            )
            self.publish_listening()
        except Exception as e:
            self._fail_cookie_error(f'启动监听失败: {e}')
            return None

        params = Params()
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
         .add_param('browser_version', HeaderBuilder.ua.split('Mozilla/')[-1])
         .add_param('browser_online', 'true')
         .add_param('tz_name', 'Asia/Shanghai')
         .add_param('cursor', str(self._cursor))
         .add_param('internal_ext', self._internal_ext)
         .add_param('host', 'https://live.douyin.com')
         .add_param('aid', '6383')
         .add_param('live_id', '1')
         .add_param('did_rule', '3')
         .add_param('endpoint', 'live_pc')
         .add_param('support_wrds', '1')
         .add_param('user_unique_id', str(self._user_id))
         .add_param('im_path', '/webcast/im/fetch/')
         .add_param('identity', 'audience')
         .add_param('need_persist_msg_count', '15')
         .add_param('insert_task_id', '')
         .add_param('live_reason', '')
         .add_param('room_id', self._room_id)
         .add_param('heartbeatDuration', '0')
         .add_param('signature', generate_signature(self._room_id, self._user_id))
         )
        wss_url = f'wss://webcast100-ws-web-hl.douyin.com/webcast/im/push/v2/?{urlencode(params.get())}'
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
            on_open=self.on_open,
        )

    def start_ws(self, reconnect=True, reconnect_delay=5):
        self._live_aborted = False
        while not self._stop_event.is_set():
            self.ws = self._build_ws()
            if self.ws is None:
                if self._live_aborted or not reconnect:
                    break
                if self._stop_event.wait(reconnect_delay):
                    break
                continue

            if not self._fetch_thread or not self._fetch_thread.is_alive():
                self._fetch_thread = threading.Thread(
                    target=self._fetch_loop,
                    name=f'fetch-{self.live_id}',
                    daemon=True,
                )
                self._fetch_thread.start()
                print(f'[{self.live_id}] im/fetch 轮询已启动')

            try:
                self.ws.run_forever(origin='https://live.douyin.com')
            except Exception as e:
                print(f'[{self.live_id}] ws error: {e}')
                if self.ws:
                    try:
                        self.ws.close()
                    except Exception:
                        pass
            if self._stop_event.is_set() or self._live_aborted:
                break
            if not reconnect:
                break
            print(f'[{self.live_id}] {reconnect_delay}s 后重连...')
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
    from utils.console_util import setup_console_utf8

    setup_console_utf8()
    # print(CONFIG_FILE)
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
