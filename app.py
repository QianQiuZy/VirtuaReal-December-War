import time
import json
import requests
from flask import Flask, render_template, jsonify
from threading import Thread
import os
from flask import send_file  # 用于发送文件响应
from io import BytesIO  # 用于字节流操作

# 初始化 Flask 应用
app = Flask(__name__, template_folder=os.getcwd())

# API URLs
ranking_url = "https://api.live.bilibili.com/xlive/fuxi-interface/RankingController/getRanking?_ts_rpc_args_=[%7B%22id%22:15540,%22type%22:1,%22cursor%22:0,%22length%22:100,%22teamDimensionValue%22:1%7D]"
user_info_url = "https://api.live.bilibili.com/xlive/fuxi-interface/UserService/getUserInfo?_ts_rpc_args_=[[1542516095,1827139579,56748733,7706705,690608698,1932862336,2039332008,434334701,1954091502,2124647716,1048135385,690608704,666726799,1609526545,6853766,14387072,529249,1323355750,690608691,477317922,434401868,392505232,1609795310,1711724633,1789460279,61639371,690608693,1116072703,2040984069,690608709,421267475,1570525137,472877684,558070433,1978590132,1296515170,2080519347,1297910179,12485637,2057377595,690608688,1694351351,1567394869,690608710,1405589619,176836079,480675481],false,%22%22]"
live_status_url = "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids"

# 全局数据存储
ranking_data = []
user_data = {}

# 请求头
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}


def fetch_data():
    global ranking_data, user_data

    # 获取用户信息
    user_response = requests.get(user_info_url, headers=headers)
    user_json = user_response.json()
    user_data = user_json['_ts_rpc_return_']['data']

    while True:
        try:
            # 获取排名数据
            ranking_response = requests.get(ranking_url, headers=headers)
            ranking_json = ranking_response.json()
            ranking_list = ranking_json['_ts_rpc_return_']['data']['list'] if ranking_json['_ts_rpc_return_']['code'] == 0 else []

            # 整理 UID 列表
            uids = [rank['uid'] for rank in ranking_list]

            # 获取直播状态
            live_status_response = requests.post(live_status_url, json={"uids": uids}, headers=headers)
            live_status_data = live_status_response.json()['data']

            # 整合数据
            ranking_data = []
            for rank in ranking_list:
                uid = rank['uid']
                rank_info = {
                    "uid": uid,
                    "rank": rank['number'],
                    "score": int(rank['score']),
                    "uname": user_data[uid]['uname'],
                    "face": user_data[uid]['face'],  # 保留相对路径
                    "live_status": live_status_data.get(uid, {}).get('live_status', 0),
                    "room_id": live_status_data.get(uid, {}).get('room_id', None),
                    "live_title": live_status_data.get(uid, {}).get('title', ""),
                    "area_name": live_status_data.get(uid, {}).get('area_v2_name', "")
                }
                ranking_data.append(rank_info)

            time.sleep(3)
        except Exception as e:
            print(f"Error in fetch_data: {e}")



# 启动后台数据线程
thread = Thread(target=fetch_data)
thread.daemon = True
thread.start()


@app.route('/')
def index():
    return render_template('vr.html')


@app.route('/get_ranking')
def get_ranking():
    return jsonify({'ranking': ranking_data})

@app.route('/avatar///<path:url>')
def get_avatar(url):
    try:
        # 图片 URL 需要解码，因为传递的是 URL 编码后的字符串
        img_url = f"https://{url}"
        response = requests.get(img_url)
        image = BytesIO(response.content)
        return send_file(image, mimetype='image/jpeg')
    except Exception as e:
        print(f"Error fetching avatar: {e}")
        return '', 404

# 启动 Flask 应用
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=2992)
