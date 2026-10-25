#!/usr/bin/env python3
"""Флот боёв: отправка БЕЗ ОЖИДАНИЯ, сбор ответов отдельным проходом.

Главное отличие от прежнего воркера: бой не блокирует очередь.
Отправка 100 боёв идёт «очередью» (≈12–15 с на бой), ответы собираются позже по адресам чатов.
Можно запускать на многих машинах одновременно (GitHub Actions, несколько браузеров на каждой).

Команды:
  submit  --pdf F --prompt P --count N --workers K --out sessions.jsonl
  harvest --in sessions.jsonl --out answers.jsonl [--wait 300] [--workers K]
  check                       проверить, что вход в Arena жив

Состояние входа: файл из переменной ARENA_STATE (по умолчанию state_arena.json).
"""
import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0.0.0 Safari/537.36')
STATE = os.environ.get('ARENA_STATE', '/home/user/state_arena.json')
lock = threading.Lock()


def now():
    return time.strftime('%H:%M:%S', time.gmtime())


def new_ctx(browser):
    kw = dict(locale='ru-RU', user_agent=UA, viewport={'width': 1400, 'height': 950})
    if os.path.exists(STATE):
        kw['storage_state'] = STATE
    return browser.new_context(**kw)


def submit_one(ctx, pdf, prompt, idx, tag):
    """Один бой: прикрепить файл, ввести задание, нажать отправку, вернуть адрес. НЕ ЖДЁТ ОТВЕТА."""
    rec = {'t': now(), 'idx': idx, 'tag': tag}
    t0 = time.time()
    pg = ctx.new_page()
    try:
        pg.goto('https://arena.ai/text', timeout=90000)
        # ждём, пока интерфейс действительно отрисуется (Cloudflare + гидрация Next.js)
        pg.wait_for_selector('textarea', state='visible', timeout=60000)
        pg.wait_for_timeout(1500)
        if pdf:
            pg.wait_for_selector('input[type=file]', state='attached', timeout=60000)
            pg.set_input_files('input[type=file]', pdf, timeout=60000)
            rec['attach'] = 'sent'
            pg.wait_for_timeout(5000)          # дать загрузиться и показаться имени файла
        box = pg.locator('textarea').first
        box.click(timeout=20000)
        box.fill(prompt)
        pg.wait_for_timeout(900)
        pg.locator('button[aria-label*="Send"]').first.click(timeout=20000)
        rec['sent'] = True
        # адрес боя появляется только после того, как обе модели догенерируют ответ
        try:
            pg.wait_for_url(re.compile(r'/c/[0-9a-f-]{8,}'), timeout=120000)
        except Exception:
            pass
        pg.wait_for_timeout(1500)
        rec['url'] = pg.url
        rec['url_ok'] = bool(re.search(r'/c/[0-9a-f-]{8,}', pg.url))
    except Exception as e:
        rec['sent'] = False
        rec['error'] = str(e)[:180]
    finally:
        rec['sec'] = round(time.time() - t0, 1)
        pg.close()
    return rec


def harvest_one(ctx, rec, wait_s):
    """Сбор ответа по адресу чата: опрос до появления «A/B is better» или отказа."""
    out = dict(rec)
    pg = ctx.new_page()
    t0 = time.time()
    try:
        pg.goto(rec['url'], timeout=60000)
        pg.wait_for_timeout(5000)
        status = 'timeout'
        while time.time() - t0 < wait_s:
            body = pg.inner_text('body')
            if re.search(r'(A|B) is better', body):
                status = 'answer'
                out['answer'] = body
                break
            if 'Something went wrong' in body:
                status = 'refused'
                break
            pg.wait_for_timeout(6000)
        out['status'] = status
        out['sec'] = round(time.time() - t0, 1)
    except Exception as e:
        out['status'] = 'error'
        out['error'] = str(e)[:180]
    finally:
        pg.close()
    return out


def cmd_submit(a):
    prompt = open(a.prompt, encoding='utf-8').read().strip()
    results = []

    def worker(k):
        # свой браузер на поток: sync_playwright нельзя переиспользовать между потоками
        with sync_playwright() as p:
            b = p.chromium.launch(headless=not a.headed, args=['--no-sandbox', '--disable-dev-shm-usage',
                                                               '--disable-blink-features=AutomationControlled'])
            ctx = new_ctx(b)
            local = []
            for i in range(k, a.count, a.workers):
                r = submit_one(ctx, a.pdf, prompt, i + 1, a.tag)
                local.append(r)
                with lock:
                    print(json.dumps({'idx': r['idx'], 'sent': r['sent'], 'sec': r['sec'],
                                      'err': r.get('error', '')[:60]}, ensure_ascii=False), flush=True)
            ctx.close()
            b.close()
            return local

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for part in ex.map(worker, range(a.workers)):
            results.extend(part)
    wall = time.time() - t0
    results.sort(key=lambda r: r['idx'])
    with open(a.out, 'w', encoding='utf-8') as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    sent = sum(1 for r in results if r.get('sent'))
    print(f'отправлено {sent} из {a.count} за {wall:.0f} с (стенное время, {a.workers} браузера)', flush=True)
    return 0 if sent else 3


def cmd_harvest(a):
    recs = [json.loads(l) for l in open(a.inp, encoding='utf-8') if l.strip().startswith('{')]
    recs = [r for r in recs if r.get('url')]
    out = []

    def worker(k):
        with sync_playwright() as p:
            b = p.chromium.launch(headless=not a.headed, args=['--no-sandbox', '--disable-dev-shm-usage',
                                                               '--disable-blink-features=AutomationControlled'])
            ctx = new_ctx(b)
            local = []
            for i in range(k, len(recs), a.workers):
                r = harvest_one(ctx, recs[i], a.wait)
                local.append(r)
                with lock:
                    print(json.dumps({'idx': r['idx'], 'status': r.get('status'), 'sec': r['sec']}), flush=True)
            ctx.close()
            b.close()
            return local

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for part in ex.map(worker, range(a.workers)):
            out.extend(part)
    out.sort(key=lambda r: r['idx'])
    with open(a.out, 'w', encoding='utf-8') as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    ans = sum(1 for r in out if r.get('status') == 'answer')
    ref = sum(1 for r in out if r.get('status') == 'refused')
    print(f'собрано за {time.time()-t0:.0f} с: ответов {ans}, отказов {ref}, прочее {len(out)-ans-ref} из {len(out)}', flush=True)
    return 0


def cmd_check(a):
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = new_ctx(b)
        pg = ctx.new_page()
        pg.goto('https://arena.ai/text', timeout=60000)
        pg.wait_for_timeout(6000)
        t = pg.inner_text('body')
        logged = 'Get started' not in t
        print('вход в Arena жив:', logged)
        b.close()
        return 0 if logged else 3


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd')
    p = sub.add_parser('submit')
    p.add_argument('--pdf', default='')
    p.add_argument('--prompt', required=True)
    p.add_argument('--count', type=int, default=30)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--tag', default='F')
    p.add_argument('--out', default='sessions.jsonl')
    p.add_argument('--headed', action='store_true')
    q = sub.add_parser('harvest')
    q.add_argument('--in', dest='inp', required=True)
    q.add_argument('--out', default='answers.jsonl')
    q.add_argument('--wait', type=int, default=300)
    q.add_argument('--workers', type=int, default=2)
    q.add_argument('--headed', action='store_true')
    sub.add_parser('check')
    a = ap.parse_args()
    if a.cmd == 'submit':
        return cmd_submit(a)
    if a.cmd == 'harvest':
        return cmd_harvest(a)
    if a.cmd == 'check':
        return cmd_check(a)
    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
