import os, json, time, urllib.request, urllib.parse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8632966841:AAHVF4a1nLrHYk7Vgga2cpso8Eo5Y3l-VQs")
CHANNELS = os.environ.get("CHANNELS", "-1001574150270").split(",")
KEYWORDS = ["Казахтелеком","казахтелеком","kazakhtelecom","КТ ","#КТ","telecomkz","@telecomkz","@telecom_kz","сбой интернет","тариф КТ","КТ не работает"]
PORT = int(os.environ.get("PORT", 8080))

posts = []
last_id = 0
running = True

def log(msg):
    print(f"{datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)

def api(method, params=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        data = urllib.parse.urlencode(params).encode() if params else None
        with urllib.request.urlopen(urllib.request.Request(url, data), timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log(f"❌ {e}")
        return None

def tone(text):
    t = text.lower()
    n = sum(1 for w in ["не работает","сломал","ужас","плохо","медленно","кошмар","ошибка","проблема","сбой","жалоба","обман","дорого","монополи","безобраз","мошен"] if w in t)
    p = sum(1 for w in ["спасибо","отлично","хорошо","быстро","помогли","решили","рекомендую","лучший","супер","молодцы","класс","доволен","благодар"] if w in t)
    return "negative" if n>p else "positive" if p>n else "neutral"

def poll():
    global last_id, posts
    r = api("getUpdates", {"offset": last_id+1, "limit": 100, "timeout": 10})
    if not r or not r.get("ok"): return
    for u in r["result"]:
        last_id = u["update_id"]
        msg = u.get("message") or u.get("channel_post") or u.get("edited_message") or u.get("edited_channel_post")
        if not msg: continue
        txt = msg.get("text") or msg.get("caption") or ""
        if not txt: continue
        kw = next((k for k in KEYWORDS if k.lower() in txt.lower()), None)
        if not kw:
            cid = str(msg.get("chat",{}).get("id",""))
            cu = "@"+msg.get("chat",{}).get("username","") if msg.get("chat",{}).get("username") else ""
            if not (cid in CHANNELS or cu in CHANNELS): continue
        t_ = tone(txt)
        src = msg.get("chat",{}).get("title") or msg.get("chat",{}).get("username") or "Telegram"
        un = msg.get("chat",{}).get("username","")
        posts.insert(0, {
            "id": u["update_id"],
            "author": "@"+msg.get("from",{}).get("username","") if msg.get("from",{}).get("username") else src,
            "url": f"https://t.me/{un}/{msg.get('message_id','')}" if un else "#",
            "text": txt,
            "publication_time": datetime.fromtimestamp(msg.get("date",0)).isoformat(),
            "source_type": "telegram", "source_name": src,
            "emotional_tone": t_,
            "views_count": msg.get("views",0), "shares_count": msg.get("forward_count",0),
            "likes_count": 0, "comments_count": 0, "subscribers_count": 0,
            "topic_id": 0, "topic_name": kw or "", "matched_keyword": kw or "канал",
            "created_at": datetime.now().isoformat()
        })
        log(f"{'🔴' if t_=='negative' else '🟢' if t_=='positive' else '⚪'} [{t_}] {src}: {txt[:50]}")
    if len(posts) > 2000: posts[:] = posts[:2000]

def monitor():
    global last_id
    log("🚀 Мониторинг запущен")
    r = api("getMe")
    if r and r.get("ok"): log(f"✅ Бот: @{r['result']['username']}")
    api("deleteWebhook", {"drop_pending_updates": "true"})
    r = api("getUpdates", {"limit": 1, "offset": -1})
    if r and r.get("ok") and r["result"]: last_id = r["result"][-1]["update_id"]
    while running:
        try: poll()
        except Exception as e: log(f"❌ {e}")
        time.sleep(5)

DASHBOARD = open(os.path.join(os.path.dirname(__file__), "dashboard.html"), encoding="utf-8").read()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/api/posts":
            data = json.dumps({"ok": True, "posts": posts, "count": len(posts)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD.encode())

Thread(target=monitor, daemon=True).start()
log(f"🌐 Сервер запущен на порту {PORT}")
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
