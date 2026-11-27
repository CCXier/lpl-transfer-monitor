import json
import os
import logging
from datetime import datetime
from wxpusher import WxPusher
from crawl4weibo import WeiboClient

# 关闭底层烦人的 INFO 日志
logging.getLogger("crawl4weibo").setLevel(logging.WARNING)

# ================= 配置区 =================
WXPUSHER_TOKEN = os.environ.get("WXPUSHER_TOKEN")
WXPUSHER_UID = os.environ.get("WXPUSHER_UID")

# 监控的战队官微 UID (目前是 LPL 的，如果你加了 LCK 可以继续在下面加)
CLUBS = {
    "AL": "6198774314",
    "BLG": "5926660141",
    "EDG": "7601012575",
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

# 转会相关的关键词列表
TRANSFER_KEYWORDS = [
    "人员变动", "人员调整", "正式加入", "转会", "离队", 
    "解约", "自由人", "续约", "退役", "上调", "下放",
    "断开连接", "恢复自由人", "加盟", "官宣", "大名单", "回归"
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
            
        # 如果是第一次运行
        if club_name not in old_snapshot:
            print(f"  📥 {club_name} 建立初始快照。")
            new_snapshot[club_name] = [w['id'] for w in current_weibos]
            continue
            
        old_ids = set(old_snapshot.get(club_name, []))
        new_count = 0
        
        # 倒序遍历，先推最早的，避免顺序错乱
        for weibo in reversed(current_weibos):
            if weibo['id'] not in old_ids:
                is_transfer, matched_kw = is_transfer_news(weibo['text'])
                
                # 【重点】这里用的是正常的判断逻辑
                if is_transfer:
                    print(f"  🔔 {club_name} 发现新微博！触发词: {matched_kw}")
                    push_to_wechat(club_name, weibo['text'], weibo['id'], matched_kw)
                    new_count += 1
                else:
                    print(f"  💤 {club_name} 有新微博，但非转会内容，已忽略。")
                
        if new_count == 0 and len(current_weibos) > 0:
            # 如果检查了但没新消息（或者过滤了），这里静默，或者你想看可以打印无新动态
            pass
            
        new_snapshot[club_name] = [w['id'] for w in current_weibos]
        
    save_snapshot(new_snapshot)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 检查完成\n")

if __name__ == "__main__":
    main()
