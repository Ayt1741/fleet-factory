import os, sys, json, re, time
from playwright.sync_api import sync_playwright

EMAIL = os.environ['EMAIL']; PASSW = os.environ['PASSW']; N = os.environ.get('N','01')
def save(pg, tag):
    pg.screenshot(path=f'/tmp/shots/{N}-{tag}.png')
    try: open(f'/tmp/shots/{N}-{tag}.txt','w').write(pg.inner_text('body')[:3000])
    except Exception: pass

with sync_playwright() as p:
    b = p.chromium.launch(headless=False, args=['--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled'])
    ctx = b.new_context(viewport={'width':1400,'height':950}, locale='en-US',
        user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined}); window.chrome={runtime:{}};")
    pg = ctx.new_page()
    pg.goto('https://arena.ai/', timeout=120000); pg.wait_for_timeout(6000)
    print("1) URL:", pg.url)
    кн = [x.inner_text().strip() for x in pg.locator('button').all() if x.is_visible()]
    print("кнопки:", кн[:15])

    нажал = False
    for сел in ('button:has-text("Log in"):visible','button:has-text("Log In"):visible','button:has-text("Login"):visible'):
        try:
            э = pg.locator(сел).first
            if э.count():
                э.click(timeout=8000); нажал = True; print("нажал:", сел); break
        except Exception as e: print("  не:", сел, repr(e)[:60])
    pg.wait_for_timeout(4000)
    save(pg, 'modal')
    print("2) модалка:", pg.inner_text('body')[:400].replace('\n',' | '))
    поля = [(i.get_attribute('type'), i.get_attribute('name'), i.get_attribute('placeholder'), i.is_visible()) for i in pg.locator('input').all()]
    print("поля:", поля[:10])
    кн2 = [x.inner_text().strip()[:28] for x in pg.locator('button').all() if x.is_visible()]
    print("кнопки модалки:", кн2[:15])

    # ввод почты
    ввёл = False
    for сел in ('input[type="email"]','input[name="email"]','input[placeholder*="mail" i]','input[type="text"]'):
        try:
            э = pg.locator(сел).first
            if э.count() and э.is_visible():
                э.click(); э.fill(EMAIL); ввёл = True; print("почта в поле:", сел, "=", э.input_value()); break
        except Exception as e: print("  почта не:", сел, repr(e)[:60])
    save(pg, 'email')
    # дальше / пароль
    for сел in ('button:has-text("Continue"):visible','button[type="submit"]:visible','button:has-text("Next"):visible','button:has-text("Log in"):visible','button:has-text("Log In"):visible'):
        try:
            э = pg.locator(сел).first
            if э.count() and э.is_visible():
                э.click(timeout=8000); print("нажал2:", сел); break
        except Exception: pass
    pg.wait_for_timeout(6000)
    save(pg, 'step2')
    print("3) URL:", pg.url, "| текст:", pg.inner_text('body')[:350].replace('\n',' | '))
    print("поля2:", [(i.get_attribute('type'), i.get_attribute('placeholder'), i.is_visible()) for i in pg.locator('input').all()][:8])

    for сел in ('input[type="password"]','input[name="password"]','input[placeholder*="assword" i]'):
        try:
            э = pg.locator(сел).first
            if э.count() and э.is_visible():
                э.click(); э.fill(PASSW); print("пароль введён"); break
        except Exception as e: print("  пароль не:", repr(e)[:60])
    save(pg, 'password')
    for сел in ('button[type="submit"]:visible','button:has-text("Log in"):visible','button:has-text("Log In"):visible','button:has-text("Continue"):visible','button:has-text("Sign in"):visible'):
        try:
            э = pg.locator(сел).first
            if э.count() and э.is_visible():
                э.click(timeout=8000); print("нажал3:", сел); break
        except Exception: pass
    pg.wait_for_timeout(15000)
    save(pg, 'after')
    print("4) ФИНАЛ URL:", pg.url)
    print("4) текст:", pg.inner_text('body')[:500].replace('\n',' | '))
    куки = [c['name'] for c in ctx.cookies()]
    print("куки:", куки)
    авторизован = not any(к in (' '.join([x.inner_text() for x in pg.locator('button').all() if x.is_visible()])) for к in ['Log in','Sign up'])
    print("ПРИЗНАК ВХОДА (нет кнопок Log in/Sign up):", авторизован)
    print("СЕССИЯ:", "ДА" if ('Login' not in pg.inner_text('body')[:200]) else "нет")
    ctx.storage_state(path=f'/tmp/shots/{N}-state.json')
    print("state:", os.path.getsize(f'/tmp/shots/{N}-state.json'), "Б")
    b.close()
