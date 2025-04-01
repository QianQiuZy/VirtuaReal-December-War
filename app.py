import os
import time
import json
import asyncio
import http.cookies
import logging
import threading
import requests
import calendar
from datetime import datetime, timedelta

import aiohttp
import blivedm
import blivedm.models.web as web_models
from flask import Flask, render_template, jsonify
from sqlalchemy import create_engine, Column, Integer, Float, String
from sqlalchemy.orm import declarative_base, sessionmaker
from PIL import Image
from io import BytesIO

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 数据库配置
# 请修改为对应的账号密码
DB_CONFIG = {
    "host": "localhost",
    "user": "user",
    "password": "password",
    "db": "db",
    "port": 3306,
}

engine = create_engine(
    f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['db']}",
    echo=False,
)
Session = sessionmaker(bind=engine)
db_session = Session()
Base = declarative_base()

# 当前统计数据表，每个直播间一条记录
class RoomStats(Base):
    __tablename__ = "room_stats"

    room_id = Column(Integer, primary_key=True)
    gift_total = Column(Float, default=0, nullable=False)         # 礼物总价：message.total_coin/100
    guard_total = Column(Float, default=0, nullable=False)          # 舰长总价：message.price * message.num / 100
    super_chat_total = Column(Float, default=0, nullable=False)     # 醒目留言总价：message.price * 10
    uname = Column(String(255), default='', nullable=False)
    face = Column(String(255), default='', nullable=False)          # 存放本地头像路径
    live_status = Column(Integer, default=0, nullable=False)

    @classmethod
    def update_or_create(cls, room_id, gift=0, guard=0, super_chat=0, uname=None, face=None, live_status=None):
        record = db_session.query(cls).get(room_id)
        if not record:
            record = cls(room_id=room_id, gift_total=0, guard_total=0, super_chat_total=0,
                         uname=uname or '', face=face or '', live_status=live_status or 0)
            db_session.add(record)
        else:
            if uname is not None:
                record.uname = uname
            if face is not None:
                record.face = face
            if live_status is not None:
                record.live_status = live_status
            record.gift_total += gift
            record.guard_total += guard
            record.super_chat_total += super_chat
        db_session.commit()
        return record

# 总统计表（每个月备份一次当前 RoomStats 数据）
class TotalStats(Base):
    __tablename__ = "total_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    month = Column(String(20), nullable=False)  # 格式如 "2025-03"
    room_id = Column(Integer, nullable=False)
    gift_total = Column(Float, default=0, nullable=False)
    guard_total = Column(Float, default=0, nullable=False)
    super_chat_total = Column(Float, default=0, nullable=False)
    total = Column(Float, default=0, nullable=False)
    uname = Column(String(255), default='', nullable=False)
    face = Column(String(255), default='', nullable=False)
    live_status = Column(Integer, default=0, nullable=False)

Base.metadata.create_all(engine)

# 直播间 UID 列表（用于获取直播状态）
uid_list = [
    1542516095, 1827139579, 56748733, 7706705, 690608698, 1932862336, 2039332008, 434334701,
    1954091502, 2124647716, 1048135385, 690608704, 666726799, 1609526545, 6853766, 14387072,
    529249, 1323355750, 690608691, 477317922, 434401868, 392505232, 1609795310, 1711724633,
    1789460279, 61639371, 690608693, 1116072703, 2040984069, 690608709, 421267475, 1570525137,
    472877684, 558070433, 1978590132, 1296515170, 2080519347, 1297910179, 12485637, 2057377595,
    690608688, 1694351351, 1567394869, 690608710, 1405589619, 176836079, 480675481, 474369808,
    480680646, 666726801, 490331391, 1217754423, 1900141897, 1660392980, 1878154667, 1526446007,
    1616183604, 1739085910, 1484169431,
]

# API URL，使用 GET 请求，传递参数形式为 ?uids[]=xxx
live_status_url = "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids"

# 确保存放头像的目录存在
AVATAR_DIR = os.path.join(os.getcwd(), "static", "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)

def download_avatar(uid, url):
    """
    下载头像图片，压缩为64x64的jpg后保存到 static/avatars 下，文件名为 {uid}.jpg
    返回相对路径供前端显示
    """
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        image = Image.open(BytesIO(resp.content))
        image = image.convert('RGB')
        # 使用 Image.LANCZOS 替换 Image.ANTIALIAS
        image = image.resize((64, 64), Image.LANCZOS)
        file_path = os.path.join(AVATAR_DIR, f"{uid}.jpg")
        image.save(file_path, format="JPEG")
        logging.info(f"下载并压缩头像成功: UID {uid}")
        return f"static/avatars/{uid}.jpg"
    except Exception as e:
        logging.error(f"下载头像失败 UID {uid}: {e}")
        return ""

def update_live_status():
    """
    每分钟调用 API 获取直播状态信息，
    并下载头像、更新 RoomStats 表（不累计礼物数据，仅更新直播信息）
    """
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/json'
    }
    while True:
        try:
            # 构造 GET 参数：uids[]=UID1&uids[]=UID2...
            params = [('uids[]', uid) for uid in uid_list]
            resp = requests.get(live_status_url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            res = resp.json()
            if res.get("code") != 0:
                logging.error(f"API返回错误: {res}")
            else:
                data = res.get("data", {})
                for uid_str, info in data.items():
                    uid = int(uid_str)
                    room_id = info.get("room_id")
                    uname = info.get("uname", "")
                    face_url = info.get("face", "")
                    live_status = info.get("live_status", 0)
                    # 下载头像并获取本地路径
                    local_face = download_avatar(uid, face_url) if face_url else ""
                    # 更新记录（不清空累计数据，只更新直播信息）
                    RoomStats.update_or_create(
                        room_id=room_id,
                        uname=uname,
                        face=local_face,
                        live_status=live_status
                    )
                    logging.info(f"更新直播状态: UID {uid} 房间 {room_id} {uname} 状态 {live_status}")
        except Exception as e:
            logging.error(f"更新直播状态失败: {e}")
        time.sleep(60)

# aiohttp session 全局变量，用于直播间事件监听（礼物、舰长、SC 事件累计）
aiohttp_session = None

def init_session():
    global aiohttp_session
    cookies = http.cookies.SimpleCookie()
    cookies['SESSDATA'] = "你的SESSDATA"
    cookies['SESSDATA']['domain'] = 'bilibili.com'
    connector = aiohttp.TCPConnector(ssl=False)
    aiohttp_session = aiohttp.ClientSession(connector=connector)
    aiohttp_session.cookie_jar.update_cookies(cookies)

# 直播间事件处理（累计礼物、舰长、SC 数据）
class MyHandler(blivedm.BaseHandler):
    def _on_heartbeat(self, client: blivedm.BLiveClient, message: web_models.HeartbeatMessage):
        logging.info(f"[{client.room_id}] 心跳")

    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
        logging.info(f"[{client.room_id}] {message.uname}: {message.msg}")

    def _on_gift(self, client: blivedm.BLiveClient, message: web_models.GiftMessage):
        try:
            gift_value = message.total_coin / 1000
            RoomStats.update_or_create(room_id=client.room_id, gift=gift_value)
            logging.info(f"[{client.room_id}] {message.uname} 赠送 {message.gift_name} x {message.num}, 价值 {gift_value}")
        except Exception as e:
            logging.error(f"处理礼物记录时出错: {e}")

    def _on_user_toast_v2(self, client: blivedm.BLiveClient, message: web_models.UserToastV2Message):
        try:
            guard_value = (message.price * message.num) / 1000
            RoomStats.update_or_create(room_id=client.room_id, guard=guard_value)
            logging.info(f"[{client.room_id}] {message.username} 上舰, guard_level={message.guard_level}, 价值 {guard_value}")
        except Exception as e:
            logging.error(f"处理舰长记录时出错: {e}")

    def _on_super_chat(self, client: blivedm.BLiveClient, message: web_models.SuperChatMessage):
        try:
            super_chat_value = message.price
            RoomStats.update_or_create(room_id=client.room_id, super_chat=super_chat_value)
            logging.info(f"[{client.room_id}] 醒目留言 ¥{message.price} {message.uname}: {message.message}, 价值 {super_chat_value}")
        except Exception as e:
            logging.error(f"处理醒目留言记录时出错: {e}")

async def run_multi_clients():
    """
    同时监听多个直播间事件，从数据库中获取 room_id 列表
    """
    # 从数据库查询所有 RoomStats 记录的 room_id
    room_ids = [r[0] for r in db_session.query(RoomStats.room_id).all()]
    if not room_ids:
        logging.error("数据库中无可用房间数据，等待更新...")
        await asyncio.sleep(10)
        return
    clients = [blivedm.BLiveClient(room_id, session=aiohttp_session) for room_id in room_ids]
    handler = MyHandler()
    for client in clients:
        client.set_handler(handler)
        client.start()
    try:
        await asyncio.gather(*(client.join() for client in clients))
    finally:
        await asyncio.gather(*(client.stop_and_close() for client in clients))

async def run_clients_loop():
    while True:
        try:
            await run_multi_clients()
        except Exception as e:
            logging.error(f"监听过程中出现异常: {e}")
        await asyncio.sleep(5)

async def live_main():
    init_session()
    try:
        await run_clients_loop()
    finally:
        if aiohttp_session:
            await aiohttp_session.close()

# 每月备份并清空 RoomStats 的功能
def is_last_day(dt):
    """判断 dt 是否为当月最后一天"""
    last_day = calendar.monthrange(dt.year, dt.month)[1]
    return dt.day == last_day

def backup_data(backup_month):
    """将 RoomStats 数据备份到 TotalStats 表，并清空 RoomStats 表"""
    try:
        records = db_session.query(RoomStats).all()
        for rec in records:
            total = rec.gift_total + rec.guard_total + rec.super_chat_total
            total_record = TotalStats(
                month=backup_month,
                room_id=rec.room_id,
                gift_total=rec.gift_total,
                guard_total=rec.guard_total,
                super_chat_total=rec.super_chat_total,
                total=total,
                uname=rec.uname,
                face=rec.face,
                live_status=rec.live_status
            )
            db_session.add(total_record)
        db_session.commit()
        # 清空 RoomStats 表
        db_session.query(RoomStats).delete()
        db_session.commit()
        logging.info(f"已备份并清空 RoomStats 数据，月份：{backup_month}")
    except Exception as e:
        logging.error(f"备份 RoomStats 失败: {e}")

def monthly_reset():
    """
    每10秒检测一次，如果当前时间为次日0点且前一天为当月最后一天，则备份 RoomStats 并清空
    """
    while True:
        now = datetime.now()
        # 判断当前时间是否在凌晨0点附近（0点0分～0点1分）
        if now.hour == 0 and now.minute < 1:
            yesterday = now - timedelta(days=1)
            if is_last_day(yesterday):
                backup_month = yesterday.strftime("%Y-%m")
                backup_data(backup_month)
                # 避免重复触发，休眠70秒
                time.sleep(70)
        time.sleep(30)

# Flask 网站部分，前端保持之前样式，显示礼物、舰长、SC 和总计
app = Flask(__name__, template_folder=os.getcwd())

@app.route('/')
def index():
    return render_template('vr.html')

@app.route('/get_ranking')
def get_ranking():
    try:
        records = db_session.query(RoomStats).all()
    except Exception as e:
        db_session.rollback()
        raise e
    ranking = []
    for rec in records:
        total = rec.gift_total + rec.guard_total + rec.super_chat_total
        ranking.append({
            'room_id': rec.room_id,
            'gift_total': rec.gift_total,
            'guard_total': rec.guard_total,
            'super_chat_total': rec.super_chat_total,
            'total': total,
            'uname': rec.uname,
            'face': rec.face,
            'live_status': rec.live_status
        })
    ranking.sort(key=lambda x: x['total'], reverse=True)
    for idx, item in enumerate(ranking):
        item['rank'] = idx + 1
    return jsonify({'ranking': ranking})

def start_live_listener():
    asyncio.run(live_main())

def start_status_updater():
    update_live_status()

def start_monthly_reset():
    monthly_reset()

if __name__ == '__main__':
    # 启动直播监听线程（后台运行）
    t1 = threading.Thread(target=start_live_listener, daemon=True)
    t1.start()
    # 启动直播状态更新线程（每分钟刷新一次）
    t2 = threading.Thread(target=start_status_updater, daemon=True)
    t2.start()
    # 启动每月数据备份重置线程
    t3 = threading.Thread(target=start_monthly_reset, daemon=True)
    t3.start()
    # 启动 Flask 网站
    app.run(host='0.0.0.0', port=2992)
