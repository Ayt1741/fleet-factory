#!/usr/bin/env python3
"""Гостевой (без логина) движок боёв Arena.

Прошлый движок ждал `textarea` — на arena.ai его нет (скрытый g-recaptcha-response),
композер — это div[contenteditable=true] (tiptap/ProseMirror), а после первой отправки
всплывает модалка Terms of Use с кнопкой Agree. Turnstile проходит кликом по iframe
challenges.cloudflare.com.

  submit  --prompt P --count N [--file F]
  harvest --in sessions.jsonl --wait 600
  check
"""
import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright

STATE = os.environ.get('ARENA_STATE', 'state.json')
UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/131.0.0.0 Safari/537.36')
ARGS = ['--no-sandbox', '--disable-dev-shm-usage',
        '--disable-blink-features=AutomationControlled']
MASK = ("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")


def log(*a):
    print(time.strftime('%H:%M:%S', time.gmtime()), *a, flush=True)


def new_ctx(browser):
    kw = dict(locale='en-US', user_agent=UA, viewport={'width': 1400, 'height': 950})
    if os.path.exists(STATE):
        try:
            kw['storage_state'] = STATE
        except Exception:
            pass
    ctx = browser.new_context(**kw)
    ctx.add_init_script(MASK)
    return ctx


def turnstile(pg, tag='', tries=6):
    for i in range(tries):
        try:
            for f in pg.frames:
                if 'challenges.cloudflare.com' in (f.url or ''):
                    f.locator('body').first.click(timeout=5000, force=True)
                    pg.wait_for_timeout(4000)
                    break
        except Exception:
            pass
        try:
            t = pg.inner_text('body')
        except Exception:
            pg.wait_for_timeout(2000)
            continue
        if ('Security Verification' not in t and 'Verify you are human' not in t
                and 'Подтвердите' not in t):
            return True
        pg.wait_for_timeout(3000)
    log(f'  [{tag}] Turnstile не пройден')
    return False


def agree(pg):
    """Модалка Terms of Use: кнопка Agree / Enter."""
    for _ in range(3):
        try:
            if 'Terms of Use & Privacy Policy' in pg.inner_text('body'):
                b = pg.locator('button:has-text("Agree")').first
                if b.count():
                    b.click(timeout=5000)
                    pg.wait_for_timeout(2000)
                    return True
                pg.keyboard.press('Enter')
                pg.wait_for_timeout(2000)
                return True
        except Exception:
            pass
        pg.wait_for_timeout(1500)
    return False


def composer(pg):
    for sel in ('div[contenteditable="true"].tiptap',
                'div[contenteditable="true"]',
                '[role="textbox"][contenteditable="true"]'):
        loc = pg.locator(sel)
        if loc.count():
            try:
                if loc.first.is_visible():
                    return loc.first, sel
            except Exception:
                pass
    return None, None


def submit_one(browser, prompt, idx, tag, file=None):
    rec = {'idx': idx, 'tag': tag, 't': time.strftime('%H:%M:%S', time.gmtime())}
    t0 = time.time()
    ctx = new_ctx(browser)
    pg = ctx.new_page()
    try:
        pg.goto('https://arena.ai/text', timeout=120000)
        pg.wait_for_timeout(6000)
        turnstile(pg, tag)
        agree(pg)
        box, sel = composer(pg)
        if not box:
            rec['error'] = 'нет композера'
            return rec
        box.click(timeout=10000)
        pg.wait_for_timeout(400)
        if file:
            try:
                pg.set_input_files('input[type=file]', file, timeout=60000)
                rec['attach'] = 'sent'
                pg.wait_for_timeout(6000)
            except Exception as e:
                rec['attach'] = 'fail: ' + repr(e)[:100]
        pg.keyboard.type(prompt, delay=2)
        pg.wait_for_timeout(800)
        # отправка: Enter
        pg.keyboard.press('Enter')
        pg.wait_for_timeout(2500)
        rec['terms'] = agree(pg)
        # если Enter не отправил — поискать кнопку отправки
        try:
            body = pg.inner_text('body')
            if prompt[:40] in body and 'Thinking' not in body and 'is better' not in body:
                for sel2 in ('button[aria-label*="Send"]', 'button[type="submit"]',
                             'button:has(svg[class*="send"])'):
                    b = pg.locator(sel2)
                    if b.count():
                        b.first.click(timeout=8000)
                        rec['via'] = sel2
                        agree(pg)
                        break
        except Exception:
            pass
        rec['sent'] = True
        try:
            pg.wait_for_url(re.compile(r'/c/[0-9a-f-]{8,}'), timeout=90000)
        except Exception:
            pass
        rec['url'] = pg.url
        rec['url_ok'] = bool(re.search(r'/c/[0-9a-f-]{8,}', pg.url))
        # сколько текста уже есть
        try:
            rec['chars'] = len(pg.inner_text('body'))
        except Exception:
            rec['chars'] = 0
        try:
            pg.screenshot(path=f'/tmp/shots/отпр-{idx}.png')
        except Exception:
            pass
    except Exception as e:
        rec['sent'] = False
        rec['error'] = repr(e)[:300]
    finally:
        rec['sec'] = round(time.time() - t0, 1)
        try:
            pg.close(); ctx.close()
        except Exception:
            pass
    return rec


def harvest_one(browser, rec, wait_s):
    out = dict(rec)
    if not rec.get('url_ok'):
        out['status'] = 'no_url'
        return out
    ctx = new_ctx(browser)
    pg = ctx.new_page()
    t0 = time.time()
    try:
        pg.goto(rec['url'], timeout=90000)
        pg.wait_for_timeout(6000)
        turnstile(pg, 'harvest')
        agree(pg)
        status = 'timeout'
        while time.time() - t0 < wait_s:
            try:
                body = pg.inner_text('body')
            except Exception:
                pg.wait_for_timeout(5000)
                continue
            if 'is better' in body or 'Which response' in body or 'Vote' in body:
                status = 'answer'
                out['answer'] = body
                break
            if 'Something went wrong' in body:
                status = 'refused'
                out['answer'] = body
                break
            pg.wait_for_timeout(7000)
        out['status'] = status
        if 'answer' not in out:
            try:
                out['answer'] = pg.inner_text('body')
            except Exception:
                pass
        try:
            pg.screenshot(path=f"/tmp/shots/урожай-{rec.get('idx')}.png")
        except Exception:
            pass
    except Exception as e:
        out['status'] = 'error'
        out['error'] = repr(e)[:250]
    finally:
        out['sec'] = round(time.time() - t0, 1)
        try:
            pg.close(); ctx.close()
        except Exception:
            pass
    return out


def cmd_submit(a):
    prompt = open(a.prompt, encoding='utf-8').read() if os.path.exists(a.prompt) else a.prompt
    res = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=not a.headed, args=ARGS)
        for i in range(a.count):
            r = submit_one(b, prompt, i + 1, a.tag, a.file)
            log('submit', json.dumps({k: r.get(k) for k in ('idx', 'sent', 'url_ok', 'sec', 'error', 'attach')}, ensure_ascii=False))
            res.append(r)
            time.sleep(a.pause)
        b.close()
    with open(a.out, 'a', encoding='utf-8') as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    log('итог submit:', sum(1 for r in res if r.get('url_ok')), '/', len(res), 'сбоев', sum(1 for r in res if not r.get('sent')))


def cmd_harvest(a):
    recs = [json.loads(l) for l in open(a.inp, encoding='utf-8') if l.strip()]
    recs = [r for r in recs if r.get('url_ok')]
    log('урожай по', len(recs), 'боям')
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=not a.headed, args=ARGS)
        def w(r):
            return harvest_one(b, r, a.wait)
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for r in ex.map(w, recs):
                log('harvest', r.get('idx'), r.get('status'), r.get('sec'))
                out.append(r)
        b.close()
    with open(a.out, 'w', encoding='utf-8') as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    log('готово:', sum(1 for r in out if r.get('status') == 'answer'), 'ответов из', len(out))


def cmd_check(a):
    with sync_playwright() as p:
        b = p.chromium.launch(headless=not a.headed, args=ARGS)
        ctx = new_ctx(b)
        pg = ctx.new_page()
        pg.goto('https://arena.ai/text', timeout=120000)
        pg.wait_for_timeout(6000)
        turnstile(pg, 'check')
        agree(pg)
        t = pg.inner_text('body')
        box, sel = composer(pg)
        print('композер:', sel)
        print('гость:', box is not None)
        print('куки:', [c['name'] for c in ctx.cookies()])
        print(t[:300].replace('\n', ' | '))
        b.close()


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd')
    s = sp.add_parser('submit')
    s.add_argument('--prompt', required=True)
    s.add_argument('--file')
    s.add_argument('--count', type=int, default=1)
    s.add_argument('--pause', type=int, default=10)
    s.add_argument('--tag', default='guest')
    s.add_argument('--out', default='sessions.jsonl')
    s.add_argument('--headed', action='store_true')
    h = sp.add_parser('harvest')
    h.add_argument('--in', dest='inp', default='sessions.jsonl')
    h.add_argument('--out', default='answers.jsonl')
    h.add_argument('--wait', type=int, default=600)
    h.add_argument('--workers', type=int, default=2)
    h.add_argument('--headed', action='store_true')
    c = sp.add_parser('check')
    c.add_argument('--headed', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'submit':
        return cmd_submit(a)
    if a.cmd == 'harvest':
        return cmd_harvest(a)
    if a.cmd == 'check':
        return cmd_check(a)
    ap.print_help()


if __name__ == '__main__':
    main()
