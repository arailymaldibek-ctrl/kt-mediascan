import os
import json
import threading
import time
import re
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.parse import quote
import xml.etree.ElementTree as ET

PORT = int(os.environ.get('PORT', 10000))

KEYWORDS = [
    'казахтелеком', 'kazakhtelecom', 'telecomkz',
    'кт интернет', 'itel', 'иттелеком',
    'сбой интернет', 'тариф кт', 'кт не работает',
    'казактелеком', 'kt internet', 'telecom kz'
]

RSS_SOURCES = [
    {'name': 'Tengri News', 'url': 'https://tengrinews.kz/rss/', 'lang': 'ru'},
    {'name': 'Informburo', 'url': 'https://informburo.kz/rss', 'lang': 'ru'},
    {'name': 'Nur.kz', 'url': 'https://www.nur.kz/rss.xml', 'lang': 'ru'},
    {'name': 'Kapital.kz', 'url': 'https://kapital.kz/rss/', 'lang': 'ru'},
    {'name': 'Forbes Kazakhstan', 'url': 'https://forbes.kz/rss/', 'lang': 'ru'},
    {'name': 'Profit.kz', 'url': 'https://profit.kz/rss/', 'lang': 'ru'},
]

posts = []
stats = {'total': 0, 'negative': 0, 'positive': 0, 'neutral': 0}
seen_urls = set()
monitoring_active = True

def detect_tone(text):
    text_lower = text.lower()
    neg = ['не работает', 'сбой', 'плохо', 'ужасно', 'жалоба', 'проблема',
           'медленно', 'дорого', 'обман', 'отключили', 'ошибка', 'медленный',
           'претензия', 'недовол', 'плохой', 'худший', 'отстой', 'кошмар']
    pos = ['спасибо', 'отлично', 'хорошо', 'молодцы', 'быстро', 'доволен',
           'рекомендую', 'супер', 'классно', 'помогли', 'решили', 'улучш',
           'новый', 'запуск', 'развити', 'инвестиц']
    neg_count = sum(1 for w in neg if w in text_lower)
    pos_count = sum(1 for w in pos if w in text_lower)
    if neg_count > pos_count:
        return 'negative'
    elif pos_count > neg_count:
        return 'positive'
    return 'neutral'

def has_keyword(text):
    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in KEYWORDS)

def add_post(source_name, title, text, url=''):
    global posts, stats
    if url and url in seen_urls:
        return
    if url:
        seen_urls.add(url)
    full_text = f"{title} {text}"
    tone = detect_tone(full_text)
    post = {
        'id': len(posts) + 1,
        'source': source_name,
        'title': title[:200] if title else '',
        'text': text[:500] if text else '',
        'url': url,
        'tone': tone,
        'time': datetime.now(timezone.utc).isoformat(),
        'type': 'news'
    }
    posts.insert(0, post)
    if len(posts) > 1000:
        posts = posts[:1000]
    stats['total'] += 1
    stats[tone] += 1
    print(f"[RSS] {tone.upper()} | {source_name} | {title[:60]}")

def fetch_rss(source):
    try:
        req = Request(source['url'], headers={
            'User-Agent': 'Mozilla/5.0 (compatible; KTMediaScan/1.0)'
        })
        with urlopen(req, timeout=15) as resp:
            content = resp.read()
        root = ET.fromstring(content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        items = root.findall('.//item') or root.findall('.//atom:entry', ns)
        count = 0
        for item in items:
            title = ''
            desc = ''
            link = ''
            title_el = item.find('title') or item.find('atom:title', ns)
            desc_el = item.find('description') or item.find('atom:summary', ns) or item.find('atom:content', ns)
            link_el = item.find('link') or item.find('atom:link', ns)
            if title_el is not None:
                title = re.sub('<[^>]+>', '', title_el.text or '')
            if desc_el is not None:
                desc = re.sub('<[^>]+>', '', desc_el.text or '')
            if link_el is not None:
                link = link_el.text or link_el.get('href', '')
            if has_keyword(title) or has_keyword(desc):
                add_post(source['name'], title, desc, link)
                count += 1
        if count > 0:
            print(f"[RSS] {source['name']}: найдено {count} упоминаний КТ")
    except Exception as e:
        print(f"[RSS ERROR] {source['name']}: {e}")

def monitor_loop():
    global monitoring_active
    print("[MONITOR] Запуск RSS мониторинга...")
    while True:
        if monitoring_active:
            for source in RSS_SOURCES:
                fetch_rss(source)
                time.sleep(2)
            print(f"[MONITOR] Цикл завершён. Всего постов: {len(posts)}")
        time.sleep(300)  # каждые 5 минут

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            with open('dashboard.html', 'rb') as f:
                self.wfile.write(f.read())
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        if self.path.startswith('/api/posts'):
            limit = 100
            tone_filter = None
            if '?' in self.path:
                params = self.path.split('?')[1]
                for p in params.split('&'):
                    if p.startswith('limit='):
                        limit = int(p.split('=')[1])
                    if p.startswith('tone='):
                        tone_filter = p.split('=')[1]
            filtered = posts
            if tone_filter:
                filtered = [p for p in posts if p['tone'] == tone_filter]
            self.wfile.write(json.dumps(filtered[:limit]).encode('utf-8'))
        elif self.path == '/api/stats':
            self.wfile.write(json.dumps(stats).encode('utf-8'))
        elif self.path == '/api/status':
            status = {
                'active': monitoring_active,
                'posts_count': len(posts),
                'sources': len(RSS_SOURCES),
                'seen_urls': len(seen_urls)
            }
            self.wfile.write(json.dumps(status).encode('utf-8'))
        elif self.path == '/api/start':
            monitoring_active = True
            self.wfile.write(json.dumps({'status': 'started'}).encode('utf-8'))
        elif self.path == '/api/stop':
            monitoring_active = False
            self.wfile.write(json.dumps({'status': 'stopped'}).encode('utf-8'))
        else:
            self.wfile.write(json.dumps({'error': 'not found'}).encode('utf-8'))

if __name__ == '__main__':
    print(f"[KT MediaScan v3 RSS] Запуск на порту {PORT}")
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f"[HTTP] Сервер запущен: http://0.0.0.0:{PORT}")
    server.serve_forever()
