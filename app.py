import time
import json
import requests
from flask import Flask, render_template, jsonify
from threading import Thread
import os
from io import BytesIO  # 用于字节流操作
from flask import send_file  # 用于发送文件响应
# 设置Flask
app = Flask(__name__, template_folder=os.getcwd())

# API URL
ranking_url = "https://api.live.bilibili.com/xlive/fuxi-interface/RankingController/getRanking?_ts_rpc_args_=[%7B%22id%22:15540,%22type%22:1,%22cursor%22:0,%22length%22:100,%22teamDimensionValue%22:1%7D]"
user_info_url = "https://api.live.bilibili.com/xlive/fuxi-interface/UserService/getUserInfo?_ts_rpc_args_=[[56748733,7706705,690608698,1932862336,2039332008,434334701,1954091502,2124647716,1048135385,690608704,666726799,1609526545,6853766,14387072,529249,1323355750,690608691,477317922,434401868,392505232,1609795310,1711724633,1789460279,61639371,690608693,1116072703,2040984069,690608709,421267475,1570525137,472877684,558070433,1978590132,1296515170,2080519347,1297910179,12485637,2057377595,690608688,1694351351,1567394869,690608710,1405589619,176836079,480675481],false,%22%22]"

# 初始化排名信息和用户信息
ranking_data = []
user_data = {}

# 设置请求头
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

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

def fetch_data():
    global ranking_data, user_data
    user_response = requests.get(user_info_url, headers=headers)
    user_json = user_response.json()
    user_data = user_json['_ts_rpc_return_']['data']

    while True:
        # 获取排名信息
        ranking_response = requests.get(ranking_url, headers=headers)

        if ranking_response.status_code != 200:
            print(f"Error: {ranking_response.status_code}, {ranking_response.text}")
        else:
            try:
                ranking_json = ranking_response.json()
                if ranking_json['_ts_rpc_return_']['code'] == 0:
                    ranking_data = ranking_json['_ts_rpc_return_']['data']['list']
                else:
                    print(f"API Error: {ranking_json['_ts_rpc_return_']['message']}")
            except json.JSONDecodeError:
                print("Error parsing JSON response")

        # 获取用户信息
        # 每3秒刷新一次
        time.sleep(3)

# 启动线程来定期获取数据
thread = Thread(target=fetch_data)
thread.daemon = True
thread.start()

@app.route('/')
def index():
    return render_template('vr.html')

@app.route('/get_ranking')
def get_ranking():
    return jsonify({'ranking': ranking_data, 'users': user_data})

# 启动Flask应用
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=2992)
