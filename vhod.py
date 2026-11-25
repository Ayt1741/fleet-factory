import os, sys, json, re, time
from playwright.sync_api import sync_playwright

def turnstile(pg, tag=''):
    for i in range(6):
        try:
            for f in pg.frames:
                if 'challenges.cloudflare.com' in (f.url or ''):
                    f.locator('body').first.click(timeout=4000, force=True)
                    pg.wait_for_timeout(3500)
                    break
        except Exception: pass
        try: t = pg.inner_text('body')
        except Exception:
            pg.wait_for_timeout(1500); continue
        if 'Security Verification' not in t and 'Verify you are human' not in t:
            return True
        pg.wait_for_timeout(2500)
    return False

with sync_playwright() as p:
    b = p.chromium.launch(headless=False, args=['--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled'])
    ctx = b.new_context(viewport={'width':1400,'height':950}, locale='ru-RU',
                        user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined}); window.chrome={runtime:{}};")
    pg = ctx.new_page()
    pg.goto('https://arena.ai/login', timeout=120000)
    pg.wait_for_timeout(7000)
    print("URL:", pg.url)
    print("текст:", pg.inner_text('body')[:400].replace('\n',' | '))
    print("iframe'ы:", [f.url[:70] for f in pg.frames])
    print("поля:", [(i.get_attribute('type'), i.get_attribute('name') or i.get_attribute('placeholder')) for i in pg.locator('input').all()][:8])
    print("кнопки:", [x.inner_text()[:30] for x in pg.locator('button').all() if x.is_visible()][:12])
    pg.screenshot(path='/tmp/shots/vhod-01.png')
    # пробуем ввести аккаунт 01
    for с, знач, тег in (('input[type="email"]',os.environ['EMAIL'],'почта'),
                          ('input[type="password"]',os.environ['PASSW'],'пароль')):
        try:
            э = pg.locator(с).first
            if э.count():
                э.click(timeout=5000); э.fill(знач, timeout=5000)
                print(f"{тег}: введено")
        except Exception as e:
            print(f"{тег}: {repr(e)[:80]}")
    print("значения:", [i.input_value() for i in pg.locator('input').all()][:5])
    pg.screenshot(path='/tmp/shots/vhod-02-заполнено.png')
    # нажимаем кнопку входа
    for с in ('button:has-text("Continue with email")','button:has-text("Log In")','button[type="submit"]','button:has-text("Log in")','button:has-text("Continue")'):
        try:
            э = pg.locator(с).first
            if э.count() and э.is_visible():
                э.click(timeout=8000); print("нажал:", с); break
        except Exception: pass
    pg.wait_for_timeout(12000)
    print("после входа URL:", pg.url)
    print("текст:", pg.inner_text('body')[:500].replace('\n',' | '))
    print("куки:", [c['name'] for c in ctx.cookies()])
    pg.screenshot(path='/tmp/shots/vhod-03-после.png')
    ctx.storage_state(path='/tmp/shots/vhod-state.json')
    print("state:", os.path.getsize('/tmp/shots/vhod-state.json'), "Б")
    b.close()
