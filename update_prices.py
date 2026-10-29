"""Collect the two public price lists, validate them, then publish atomically.

Run: python update_prices.py --publish
Credentials stay in Git Credential Manager (or GITHUB_TOKEN); never in files.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import math
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
SHANGHAI = timezone(timedelta(hours=8))
SOURCE = 'https://daichongbijia.com'
SITE = 'https://kfly70418.github.io/ai-subscription-guide/'
REPO = 'kfly70418/ai-subscription-guide'
USER_AGENT = f'AI-Subscription-Guide/1.0 (+{SITE})'
PAGES = {'chatgpt': 'ChatGPT', 'claude': 'Claude'}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise ValueError(f'HTTP {response.status}: {url}')
        raw = response.read(3_000_001)
        if len(raw) > 3_000_000:
            raise ValueError('Source response too large')
        return raw.decode('utf-8')


def required_text(card, selector: str) -> str:
    element = card.select_one(selector)
    if element is None:
        raise ValueError(f'Source structure changed: missing {selector}')
    text = element.get_text(' ', strip=True)
    if not text or len(text) > 3000:
        raise ValueError(f'Invalid source text: {selector}')
    return text


def resolve_date(raw: str, source_date: date) -> date:
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
        result = date.fromisoformat(raw)
    elif re.fullmatch(r'\d{2}-\d{2}', raw):
        month, day = map(int, raw.split('-'))
        result = date(source_date.year, month, day)
        if result > source_date:
            result = date(source_date.year - 1, month, day)
    else:
        raise ValueError(f'Unknown quote date: {raw}')
    if result > source_date:
        raise ValueError('Quote date is later than source date')
    return result


def parse_page(raw: str, category: str, today: date) -> tuple[list[dict], dict]:
    soup = BeautifulSoup(raw, 'html.parser')
    footer = soup.find('footer')
    match = re.search(r'AI\s*会员数据抓取日期\s*(\d{4}-\d{2}-\d{2})', footer.get_text(' ', strip=True) if footer else '')
    if not match:
        raise ValueError('Missing source snapshot date')
    source_date = date.fromisoformat(match[1])
    if source_date > today:
        raise ValueError('Source snapshot date is in the future')
    cards = soup.select('article.xc[data-price][data-tier]')
    if not cards or len(cards) > 500:
        raise ValueError('Empty or oversized source list; retain published data')
    offers = []
    for card in cards:
        merchant = required_text(card, '.t > div > b')
        plan = required_text(card, '.t > div > span')
        tier = str(card['data-tier']).strip()
        if not tier or len(tier) > 100:
            raise ValueError('Invalid plan tier')
        price = float(card['data-price'])
        visible = required_text(card, '.pzr .p')
        visible_match = re.fullmatch(r'[¥￥]\s*([\d,.]+)', visible)
        if not visible_match or float(visible_match[1].replace(',', '')) != price:
            raise ValueError('Displayed price does not match structured price')
        if not math.isfinite(price) or not 0 < price <= 100000:
            raise ValueError('Invalid price')
        quote_date = resolve_date(required_text(card, '.ft > span > .num'), source_date)
        tags = [tag.get_text(' ', strip=True) for tag in card.select('.tags .tag')]
        delivery = tags[0] if tags else '未注明'
        notes = card.select_one('.note')
        note = notes.get_text(' ', strip=True) if notes else ''
        # Payment and trust scores are assertions by the source, not our verification.
        limitations = [tag for tag in tags[1:] if tag != '支付已核实']
        if note:
            limitations.append(note)
        # A 30-day warranty is not proof of a 30-day subscription term.
        period_text = plan
        if re.search(r'年付|年卡|年度|12\s*个月', period_text):
            period = '年付'
        elif re.search(r'季付|季卡|季度|多月|[2-9]\s*个月', period_text):
            period = '多月 / 见原文'
        elif re.search(r'月卡|月付|按月|/月|每月|30\s*天', period_text) or re.search(r'按月充值|/月|每月', note):
            period = '月付 / 30天'
        else:
            period = '周期未注明'
        historical = '历史报价' in note or (today - quote_date).days > 14
        identity = '|'.join([category, merchant, plan, tier, delivery])
        offers.append({
            'id': hashlib.sha256(identity.encode()).hexdigest()[:16],
            'product': PAGES[category], 'merchant': merchant, 'plan': plan,
            'tier': tier, 'price': price, 'currency': 'CNY', 'period': period,
            'delivery': delivery, 'note': '；'.join(limitations),
            'quote_date': quote_date.isoformat(), 'historical': historical,
            'source_url': f'{SOURCE}/{category}/',
        })
    if len({offer['id'] for offer in offers}) != len(offers):
        raise ValueError('Duplicate offers; source needs review')
    return offers, {'url': f'{SOURCE}/{category}/', 'source_date': source_date.isoformat(), 'sha256': hashlib.sha256(raw.encode()).hexdigest(), 'count': len(offers)}


def validate_changes(old: dict | None, new: dict) -> None:
    if not old:
        return
    previous = {offer['id']: offer for offer in old['offers']}
    for product in PAGES.values():
        before = sum(o['product'] == product for o in old['offers'])
        after = sum(o['product'] == product for o in new['offers'])
        if before and after < before * 0.6:
            raise ValueError(f'{product}: offer count fell by more than 40%; review before publishing')
    for offer in new['offers']:
        prior = previous.get(offer['id'])
        if prior and abs(offer['price'] / prior['price'] - 1) > 0.6:
            raise ValueError(f"Large price change for {offer['merchant']} {offer['plan']}; review before publishing")


def collect(today: date, old: dict | None = None) -> dict:
    robots = urllib.robotparser.RobotFileParser()
    robots.parse(fetch(SOURCE + '/robots.txt').splitlines())
    for category in PAGES:
        if not robots.can_fetch(USER_AGENT, f'{SOURCE}/{category}/'):
            raise ValueError('Source robots policy disallows collection')
    offers, sources = [], []
    for category in PAGES:
        rows, provenance = parse_page(fetch(f'{SOURCE}/{category}/'), category, today)
        offers.extend(rows)
        sources.append(provenance)
    data = {'schema_version': 1, 'collected_at': datetime.now(SHANGHAI).isoformat(timespec='seconds'), 'collected_date': today.isoformat(), 'source_name': '权益比价（daichongbijia.com）', 'sources': sources, 'offers': offers}
    validate_changes(old, data)
    # Same-day retries preserve the exact previously generated snapshot.
    if old and old['collected_date'] == data['collected_date'] and old['offers'] == offers and old['sources'] == sources:
        return old
    return data


def group_key(offer: dict) -> str:
    return ' · '.join([offer['product'], offer['tier'], offer['period'], offer['currency']])


def card_html(o: dict) -> str:
    e = html.escape
    status = '历史报价' if o['historical'] else '来源参考价'
    color = 'logo-green' if o['product'] == 'ChatGPT' else 'logo-amber'
    notes = o['note'] or '来源未注明更多售后条款，请查看原页面。'
    return f'''<article class="provider-card"><div class="provider-top"><div class="provider-id"><span class="provider-logo {color}">{e(o['merchant'][0])}</span><div><h3>{e(o['merchant'])}</h3><small>{e(o['product'])} · {e(o['tier'])}</small></div></div><span class="badge">{status}</span></div><p class="offer-plan">{e(o['plan'])}</p><div class="provider-tags"><span>{e(o['period'])}</span><span>{e(o['delivery'])}</span></div><p class="provider-desc">来源说明：{e(notes)}</p><div class="provider-price"><strong>¥{o['price']:g}</strong><small>来源标价 · CNY</small></div><div class="provider-meta"><span>来源报价日 {e(o['quote_date'])}</span></div><div class="provider-actions"><a class="primary-link" href="{e(o['source_url'])}" target="_blank" rel="noopener noreferrer">查看来源与商家入口 ↗</a></div></article>'''


def render_offers(data: dict) -> str:
    groups = {}
    for offer in data['offers']:
        if not offer['historical']:
            groups.setdefault(group_key(offer), []).append(offer)
    blocks = []
    for key in sorted(groups):
        cards = ''.join(card_html(o) for o in sorted(groups[key], key=lambda o: (o['price'], o['merchant'])))
        blocks.append(f'<section class="quote-group"><h3>{html.escape(key)}</h3><div class="provider-grid">{cards}</div></section>')
    return ''.join(blocks) or '<p>暂无近期报价，可切换查看历史报价。</p>'


def replace_block(page: str, marker: str, content: str) -> str:
    pattern = re.compile(r'<!-- ' + re.escape(marker) + r':START -->.*?<!-- ' + re.escape(marker) + r':END -->', re.S)
    if len(pattern.findall(page)) != 1:
        raise ValueError(f'Missing or duplicate page marker: {marker}')
    return pattern.sub(lambda _: f'<!-- {marker}:START -->{content}<!-- {marker}:END -->', page)


def write_snapshot(data: dict, root: Path = ROOT) -> None:
    page = (root / 'index.html').read_text(encoding='utf-8')
    recent = sum(not o['historical'] for o in data['offers'])
    history = len(data['offers']) - recent
    summary = f'{len(data["offers"])} 条来源报价 · {recent} 条近期 / {history} 条历史'
    page = replace_block(page, 'SUMMARY', html.escape(summary))
    page = replace_block(page, 'SYNC', f'最近成功采集：{html.escape(data["collected_at"].replace("T", " "))}（北京时间）。采集时间不等于商家核验时间。')
    page = replace_block(page, 'COUNT', f'显示 {recent} 条近期报价 · 历史报价 {history} 条，可切换查看')
    page = replace_block(page, 'OFFERS', render_offers(data))
    embedded = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    page = replace_block(page, 'DATA', f'<script type="application/json" id="quoteData">{embedded}</script>')
    payload = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    (root / 'data' / 'history').mkdir(parents=True, exist_ok=True)
    # Validation and rendering finish before any existing snapshot is replaced.
    for relative, text in [('data/prices.json', payload), (f'data/history/{data["collected_date"]}.json', payload), ('index.html', page)]:
        path = root / relative
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(text, encoding='utf-8', newline='\n')
        temporary.replace(path)


def token() -> str:
    if os.environ.get('GITHUB_TOKEN'):
        return os.environ['GITHUB_TOKEN']
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'}
    result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\nusername=kfly70418\n\n', capture_output=True, text=True, env=env, timeout=30)
    if result.returncode:
        raise RuntimeError('Saved GitHub sign-in unavailable; sign in again using Git Credential Manager')
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if not fields.get('password'):
        raise RuntimeError('No GitHub credential returned')
    return fields['password']


def api(path: str, credential: str, method: str = 'GET', body=None):
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + path, method=method, headers={'Authorization': 'Bearer ' + credential, 'Accept': 'application/vnd.github+json', 'User-Agent': USER_AGENT, 'X-GitHub-Api-Version': '2022-11-28'}, data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def publish(data: dict, root: Path = ROOT, include_site: bool = False, expected_head: str | None = None) -> dict:
    credential = token()
    head = api('/git/ref/heads/main', credential)['object']['sha']
    if expected_head is not None and head != expected_head:
        raise RuntimeError('Remote main changed during collection; rerun from the latest version')
    commit = api('/git/commits/' + head, credential)
    tree_sha = commit['tree']['sha']
    remote = api('/git/trees/' + tree_sha + '?recursive=1', credential)
    if remote.get('truncated'):
        raise RuntimeError('Remote tree truncated')
    files = {item['path']: item['sha'] for item in remote['tree'] if item['type'] == 'blob'}
    paths = ['index.html', 'data/prices.json', f'data/history/{data["collected_date"]}.json']
    if include_site:
        paths += ['styles.css', 'script.js', 'README.md', '.nojekyll', '.gitignore', 'sitemap.xml', 'requirements.txt', 'update_prices.py', 'test_update_prices.py']
    changes = []
    for path in paths:
        raw = (root / path).read_bytes()
        if files.get(path) != blob_sha(raw):
            changes.append({'path': path, 'mode': '100644', 'type': 'blob', 'content': raw.decode('utf-8')})
    if changes:
        tree = api('/git/trees', credential, 'POST', {'base_tree': tree_sha, 'tree': changes})
        new_commit = api('/git/commits', credential, 'POST', {'message': 'Update sourced subscription prices ' + data['collected_date'], 'tree': tree['sha'], 'parents': [head]})
        # Non-forced update fails safely if another writer advanced main.
        api('/git/refs/heads/main', credential, 'PATCH', {'sha': new_commit['sha'], 'force': False})
        head = new_commit['sha']
        api('/pages/builds', credential, 'POST', {})
    return {'commit': head, 'changed_files': [item['path'] for item in changes], 'url': SITE}


def verify_public(root: Path = ROOT, attempts: int = 12, include_site: bool = False) -> None:
    names = ['index.html', 'data/prices.json'] + (['script.js', 'styles.css'] if include_site else [])
    expected = {name: (root / name).read_bytes().decode('utf-8') for name in names}
    for attempt in range(attempts):
        try:
            if all(fetch(SITE + name) == value for name, value in expected.items()):
                return
        except (urllib.error.URLError, TimeoutError):
            pass
        if attempt + 1 < attempts:
            time.sleep(15)
    raise RuntimeError('Commit exists but public Pages content has not matched yet; verify later, do not claim published')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--include-site', action='store_true', help='Publish application changes too; omit for routine daily data updates')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        verify_public()
        print(json.dumps({'status': 'public_content_verified', 'url': SITE}))
        return
    expected_head = None
    previous_path = ROOT / 'data' / 'prices.json'
    old = json.loads(previous_path.read_text(encoding='utf-8')) if previous_path.exists() else None
    remote_page = None
    if args.publish and not args.include_site:
        credential = token()
        expected_head = api('/git/ref/heads/main', credential)['object']['sha']
        remote_page = base64.b64decode(api('/contents/index.html?ref=' + expected_head, credential)['content']).decode('utf-8')
        old = json.loads(base64.b64decode(api('/contents/data/prices.json?ref=' + expected_head, credential)['content']))
        for marker in ['SUMMARY', 'SYNC', 'COUNT', 'OFFERS', 'DATA']:
            replace_block(remote_page, marker, '')  # Check before modifying local files.
    data = collect(datetime.now(SHANGHAI).date(), old)
    if remote_page is not None:
        (ROOT / 'index.html').write_bytes(remote_page.encode('utf-8'))
    write_snapshot(data)
    result = {'status': 'collected', 'date': data['collected_date'], 'offers': len(data['offers']), 'historical': sum(o['historical'] for o in data['offers'])}
    if args.publish:
        result.update(publish(data, include_site=args.include_site, expected_head=expected_head))
        print(json.dumps({**result, 'status': 'committed_awaiting_pages'}, ensure_ascii=False), flush=True)
        verify_public(include_site=args.include_site)
        result['status'] = 'published_verified'
        (ROOT / '.local').mkdir(exist_ok=True)
        (ROOT / '.local' / 'last-run.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
