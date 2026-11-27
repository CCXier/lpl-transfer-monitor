import re  # 确保文件最顶部有这行 import
import json
import os
import logging
from datetime import datetime
from wxpusher import WxPusher
from crawl4weibo import WeiboClient
import requests

def format_with_ai(raw_text):
    """调用 DeepSeek API 将长文转换为播主专属格式"""
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("  ⚠️ 未配置 LLM_API_KEY，退回原始文本")
        return raw_text 
        
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    你是一个LPL电竞资讯播主。请从以下微博原文中提取转会信息，并严格按照指定模板输出。
    【微博原文】：{raw_text}
    
    【要求】：
    1. 如果原文没有提到具体选手/教练的变动（比如只是日常微博），请直接输出 "无转会信息"。
    2. 提取战队名（如WBG）、职位（教练/上单/打野等）、ID、本名。
    3. 格式必须严格如下（不要加多余的废话）：
    
    ■战队名
    官宣X名[职位][离队/加入]：
    [职位] [ID]（[本名]）

    ——————分界线——————

    「广播历史」查看转会历史信息。
    「投喂」猫粮支持播主为爱发电～
    猫粮免费获取：「我的」 右上角图标「签到活动」
    """
    
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        result = resp.json()
        
        # ★ 修复1：防止 API 报错导致程序崩溃
        if 'choices' not in result:
            print(f"  ❌ DeepSeek API 返回异常: {result}")
            return None # 返回 None 表示处理失败，直接跳过
            
        ai_text = result['choices'][0]['message']['content'].strip()
        
        # ★ 修复2：清洗 AI 可能自带的 Markdown 代码块符号
        ai_text = ai_text.replace("```markdown", "").replace("```", "").strip()
        
        if "无转会信息" in ai_text:
            return None 
            
        return ai_text
        
    except Exception as e:
        print(f"  ⚠️ AI 请求或解析失败: {e}")
        return None # 出错就跳过，不要推原文，以免排版错乱

# 关闭底层烦人的 INFO 日志
logging.getLogger("crawl4weibo").setLevel(logging.WARNING)

# ================= 配置区 =================
WXPUSHER_TOKEN = os.environ.get("WXPUSHER_TOKEN")
WXPUSHER_UID = os.environ.get("WXPUSHER_UID")

# 监控的战队官微 UID (目前是 LPL 的，如果你加了 LCK 可以继续在下面加)
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
            # 核心修改：如果是视频，直接跳过
            if getattr(post, 'video_url', None):
                continue 
                
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
    """
    判断文本是否包含转会信息。
    优先检查 #话题#，如果话题没命中，再检查正文。
    """
    # 1. 提取所有的话题标签 (匹配两个 # 之间的内容)
    hashtags = re.findall(r'#([^#]+)#', text)
    
    # 2. 检查话题标签中是否命中关键词
    for tag in hashtags:
        for keyword in TRANSFER_KEYWORDS:
            if keyword in tag:
                # 返回：是否命中, 触发词, 触发方式(用于推送展示)
                return True, keyword, f"话题: #{tag}#"
                
    # 3. 如果话题没命中，退而求其次检查正文（清理掉话题，防止正文被话题误伤）
    clean_text = re.sub(r'#[^#]+#', '', text)
    for keyword in TRANSFER_KEYWORDS:
        if keyword in clean_text:
            return True, keyword, "正文内容"
            
    return False, "", ""

def push_to_wechat(club_name, weibo_text, weibo_id, matched_keyword):
    summary_text = weibo_text
    content = f"**【{club_name} 转会动态】**\n\n{summary_text}\n\n[点击查看微博原文](https://m.weibo.cn/detail/{weibo_id})"
    
    try:
        resp = WxPusher.send_message(
            content=content,
            summary=f"📝 {club_name} 转会文案已生成（点击复制）",
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
                is_transfer, matched_kw, trigger_type = is_transfer_news(weibo['text'])
                
                if is_transfer:
                    print(f"  🔔 {club_name} 发现新微博！触发: {trigger_type}")
                    
                    # 让 AI 洗稿
                    formatted_text = format_with_ai(weibo['text'])
                    
                    if formatted_text: # 如果不是 None，说明 AI 确认是转会并排好版了
                        push_to_wechat(club_name, formatted_text, weibo['id'], f"{trigger_type} ({matched_kw})")
                        new_count += 1
                    else:
                        print(f"  💤 AI 判定非实质性转会变动，已忽略。")
                
        if new_count == 0 and len(current_weibos) > 0:
            # 如果检查了但没新消息（或者过滤了），这里静默，或者你想看可以打印无新动态
            pass
            
        new_snapshot[club_name] = [w['id'] for w in current_weibos]
        
    save_snapshot(new_snapshot)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 检查完成\n")

if __name__ == "__main__":
    main()
