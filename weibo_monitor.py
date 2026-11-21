import json
import os
import logging
from datetime import datetime
from wxpusher import WxPusher
from crawl4weibo import WeiboClient

# 关掉 crawl4weibo 底层烦人的 INFO 日志
logging.getLogger("crawl4weibo").setLevel(logging.WARNING)

# ================= 配置区 =================
# ★ 修改这里：让 GitHub 在云端注入你的 Token 和 UID
WXPUSHER_TOKEN = os.environ.get("WXPUSHER_TOKEN")
WXPUSHER_UID = os.environ.get("WXPUSHER_UID")

CLUBS = {
    "AL": "6198774314",
    "BLG": "5926660141",
    "EDG": "5235726837",
    "JDG": "6174976862",
    "LGD": "5035639623",
    "TT": "5625501560",
    "TES": "5449734852",
    "WE": "1869429662",
    "IG": "2099708877",
    "LNG": "5511584320",
    "NIP": "6420953344",
    "WBG": "5937903233"
}
SNAPSHOT_FILE = "weibo_snapshot.json"

# ★ 新增：转会相关的关键词列表
TRANSFER_KEYWORDS = [
    "人员变动", "人员调整", "正式加入", "转会", "离队", "休息",
    "解约", "自由人", "续约", "退役", "上调", "下放","回归"，
    "断开连接", "恢复自由人", "加盟", "官宣", "大名单"
]
# ==========================================

client = WeiboClient()

def load_snapshot():
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_snapshot(snapshot):
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

def fetch_club_weibo(club_name, uid):
    try:
        posts = client.get_user_posts(uid, page=1, expand=True)
        weibos = []
        for post in posts[:5]:
            weibos.append({
                "id": str(post.id),
                "text": post.text.strip(),
                "created_at": post.created_at
            })
        return weibos
    except Exception as e:
        print(f"  ❌ [{club_name}] 获取失败: {e}")
        return []

def is_transfer_news(text):
    """判断文本中是否包含转会相关的关键词"""
    for keyword in TRANSFER_KEYWORDS:
        if keyword in text:
            return True, keyword
    return False, ""

def push_to_wechat(club_name, weibo_text, weibo_id, matched_keyword):
    summary_text = weibo_text[:80] + "..." if len(weibo_text) > 80 else weibo_text
    content = f"**【{club_name} 转会动态】**\n\n{summary_text}\n\n[点击查看微博原文](https://m.weibo.cn/detail/{weibo_id})"
    
    try:
        resp = WxPusher.send_message(
            content=content,
            summary=f"🚨 {club_name} 疑似官宣：{matched_keyword}",
            content_type=3,
            uids=[WXPUSHER_UID],
            token=WXPUSHER_TOKEN
        )
        if resp and resp.get('code') == 1000 and resp['data'][0]['code'] == 1000:
            print(f"  ✅ 推送成功: {club_name} (触发词: {matched_keyword})")
    except Exception as e:
        print(f"  ❌ 推送异常: {e}")

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始检查战队微博...")
    
    old_snapshot = load_snapshot()
    new_snapshot = {}
    
    for club_name, uid in CLUBS.items():
        current_weibos = fetch_club_weibo(club_name, uid)
        
        if not current_weibos:
            print(f"  ⚠️ {club_name} 未抓取到数据。")
            new_snapshot[club_name] = old_snapshot.get(club_name, [])
            continue
            
        # 首次运行建立快照
        if club_name not in old_snapshot:
            print(f"  📥 {club_name} 建立初始快照。")
            new_snapshot[club_name] = [w['id'] for w in current_weibos]
            continue
            
        old_ids = set(old_snapshot.get(club_name, []))
        new_count = 0
        
        for weibo in reversed(current_weibos):
            if weibo['id'] not in old_ids:
                # 发现新微博，先判断是否包含转会关键词
                is_transfer, matched_kw = is_transfer_news(weibo['text'])
                
                if is_transfer:
                    print(f"  🔔 {club_name} 发现疑似转会官宣！触发词: {matched_kw}")
                    push_to_wechat(club_name, weibo['text'], weibo['id'], matched_kw)
                    new_count += 1
                else:
                    # 如果是日常微博，只打印不推送
                    print(f"  💤 {club_name} 有新微博，但非转会内容，已忽略。")
                
        if new_count == 0:
            # 如果这轮有新微博但都被过滤了，也会走到这里
            pass
            
        new_snapshot[club_name] = [w['id'] for w in current_weibos]
        
    save_snapshot(new_snapshot)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 检查完成\n")

if __name__ == "__main__":
    main()
