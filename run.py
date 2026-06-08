import requests
import json
import time
import os
from datetime import datetime
import hashlib
import hmac
import base64
import urllib.parse

# 从环境变量读取配置
DINGTALK_SECRET = os.environ.get('SECRET', '')
DINGTALK_TOKEN = os.environ.get('TOKEN', '')
UP_UIDS = os.environ.get('MIDS', '').split(',')

# 存储已发送的动态ID
sent_dynamics = set()

def get_dingtalk_signature(timestamp):
    """生成钉钉加签签名"""
    if not DINGTALK_SECRET:
        return ""
    secret_enc = DINGTALK_SECRET.encode('utf-8')
    string_to_sign = f"{timestamp}\n{DINGTALK_SECRET}"
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return sign

def send_dingtalk_message(title, text):
    """发送Markdown消息到钉钉群"""
    timestamp = str(round(time.time() * 1000))
    sign = get_dingtalk_signature(timestamp)
    
    url = f"https://oapi.dingtalk.com/robot/send?access_token={DINGTALK_TOKEN}"
    if sign:
        url += f"&timestamp={timestamp}&sign={sign}"
    
    headers = {"Content-Type": "application/json"}
    data = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": text
        }
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        result = response.json()
        if result.get("errcode") == 0:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 消息发送成功")
            return True
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 消息发送失败: {result}")
            return False
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送消息出错: {str(e)}")
        return False

def get_bilibili_dynamics(uid):
    """获取B站UP主最新动态"""
    url = f"https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?host_mid={uid}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://space.bilibili.com/{uid}/dynamic"
    }
    
    try:
        response = requests.get(url, headers=headers)
        result = response.json()
        
        if result.get("code") != 0:
            print(f"获取UP主{uid}动态失败: {result.get('message')}")
            return []
        
        items = result.get("data", {}).get("items", [])
        dynamics = []
        
        for item in items:
            dynamic_id = item.get("id_str")
            if dynamic_id in sent_dynamics:
                continue
                
            modules = item.get("modules", [])
            author_module = next((m for m in modules if m.get("module_type") == "module_author"), {})
            desc_module = next((m for m in modules if m.get("module_type") == "module_dynamic"), {})
            
            author = author_module.get("author", {}).get("name", "未知UP主")
            pub_time = author_module.get("pub_ts", 0)
            pub_time_str = datetime.fromtimestamp(pub_time).strftime("%Y-%m-%d %H:%M:%S")
            
            # 解析动态内容
            desc = desc_module.get("desc", {})
            content = desc.get("text", "无文字内容")
            
            # 处理不同类型的动态
            dynamic_type = item.get("type")
            if dynamic_type == "DYNAMIC_TYPE_AV":
                # 视频动态
                major = desc_module.get("major", {}).get("archive", {})
                title = major.get("title", "视频")
                bvid = major.get("bvid", "")
                content = f"**发布了新视频**\n\n标题：{title}\n\n{content}\n\n👉 [点击查看视频](https://www.bilibili.com/video/{bvid})"
            elif dynamic_type == "DYNAMIC_TYPE_ARTICLE":
                # 专栏动态
                major = desc_module.get("major", {}).get("article", {})
                title = major.get("title", "专栏")
                cvid = major.get("id", "")
                content = f"**发布了新专栏**\n\n标题：{title}\n\n{content}\n\n👉 [点击查看专栏](https://www.bilibili.com/read/cv{cvid})"
            elif dynamic_type == "DYNAMIC_TYPE_DRAW":
                # 图文动态
                content = f"**发布了新动态**\n\n{content}"
            elif dynamic_type == "DYNAMIC_TYPE_WORD":
                # 纯文字动态
                content = f"**发布了新动态**\n\n{content}"
            elif dynamic_type == "DYNAMIC_TYPE_FORWARD":
                # 转发动态
                orig = desc_module.get("orig", {})
                orig_type = orig.get("type")
                if orig_type == "DYNAMIC_TYPE_AV":
                    orig_title = orig.get("desc", {}).get("text", "转发了一个视频")
                    content = f"**转发了一个视频**\n\n{orig_title}\n\n{content}"
                else:
                    content = f"**转发了一条动态**\n\n{content}"
            
            dynamics.append({
                "id": dynamic_id,
                "author": author,
                "time": pub_time_str,
                "content": content
            })
            
            # 只取最新的3条
            if len(dynamics) >= 3:
                break
                
        return dynamics
        
    except Exception as e:
        print(f"获取UP主{uid}动态出错: {str(e)}")
        return []

def check_and_push():
    """检查并推送新动态"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始检查UP主动态...")
    
    for uid in UP_UIDS:
        if not uid.strip():
            continue
            
        dynamics = get_bilibili_dynamics(uid)
        
        # 按时间倒序发送
        for dynamic in reversed(dynamics):
            title = f"{dynamic['author']} 有新动态！"
            text = f"### {title}\n\n发布时间：{dynamic['time']}\n\n{dynamic['content']}"
            
            if send_dingtalk_message(title, text):
                sent_dynamics.add(dynamic["id"])
                # 避免发送太快触发限流
                time.sleep(2)
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查完成\n")

if __name__ == "__main__":
    print("B站动态推送机器人已启动！")
    print(f"监控的UP主UID: {', '.join(UP_UIDS)}")
    
    check_and_push()
