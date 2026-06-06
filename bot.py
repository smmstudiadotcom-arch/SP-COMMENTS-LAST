"""
SocPublic Bot — мониторинг VK страницы smm.studia и автоматическое создание
заданий на SocPublic через официальное API (api_id + api_key).

Один запрос task_create создаёт задание, пополняет баланс и сразу включает его.
"""

import requests
import random
import time
import os
import json
from datetime import datetime, date

# ══════════════════════════════════════
#  VKONTAKTE
# ══════════════════════════════════════
VK_TOKEN   = "vk1.a.3l-M4WzpxupxkQ1LO5QEJKxhXtlyzgP6m9f7UnUXmtmOCGTp8Pj26J5cdb_hPqB8-wSrFsRTgUVIwcwZQK6iL-cx8p23NQnt65AcdJ1yWNnqj21ZKOWnSrPyKiUudvEjdCQjzBNoDSF2vq6AjPKbPtvP-kOGAo28Uhiet66MoYaXUU9UktA3zGcZfrf7V0nKu7eUkOqnHAU9a-GcfGIW0Q"
VK_API_URL = "https://api.vk.com/method"
VK_VERSION = "5.131"

# ══════════════════════════════════════
#  SOCPUBLIC API
# ══════════════════════════════════════
SP_API_URL    = "https://socpublic.com/api"
SP_API_ID     = os.environ.get("SP_API_ID",  "244")
SP_API_KEY    = os.environ.get("SP_API_KEY", "48A8B0D6-296D-6FC0-94B3-A9500751A704")

SP_PAGES          = [
    # (страница, мин_кол-во, макс_кол-во, дата_окончания или None для постоянных)
    ("smm.studia",         7, 14, None),
    ("pro_samorasvitie",   7, 14, None),
    ("cosmi_store",        3, 5,  None),
    ("secretsofthewallet", 7, 11, "2026-07-07"),
]
SP_CHECK_INTERVAL = 60             # проверка каждую минуту
SP_PRICE_USER     = 1.0            # цена за выполнение для исполнителя (руб)
SP_PRICE_ADV      = 1.3            # наценка/комиссия сверху за выполнение

# ══════════════════════════════════════
#  УТИЛИТЫ
# ══════════════════════════════════════

def log(tag, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{tag}] {msg}", flush=True)

def load_state(filename, default=""):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return f.read().strip()
    return default

def save_state(filename, value):
    with open(filename, "w") as f:
        f.write(str(value))

def load_state_dict(filename):
    """Читает состояние вида 'page id' по строкам в dict."""
    d = {}
    if os.path.exists(filename):
        with open(filename, "r") as f:
            for line in f:
                parts = line.strip().split(" ", 1)
                if len(parts) == 2:
                    d[parts[0]] = parts[1]
    return d

def save_state_dict(filename, d):
    with open(filename, "w") as f:
        for k, v in d.items():
            f.write(f"{k} {v}\n")

# ══════════════════════════════════════
#  VK
# ══════════════════════════════════════

def get_vk_post(page):
    """Последний пост со страницы VK. Возвращает (full_id, post_url) или (None, None)."""
    try:
        params = {
            "domain": page, "count": 1, "filter": "owner",
            "access_token": VK_TOKEN, "v": VK_VERSION,
        }
        resp = requests.get(f"{VK_API_URL}/wall.get", params=params, timeout=15)
        data = resp.json()
        if "error" in data:
            log("VK", f"❌ @{page}: {data['error'].get('error_msg', 'unknown')}")
            return None, None
        items = data.get("response", {}).get("items", [])
        if not items:
            return None, None
        post = items[0]
        owner_id = post["owner_id"]
        post_id  = post["id"]
        full_id  = f"{owner_id}_{post_id}"
        post_url = f"https://vk.com/wall{owner_id}_{post_id}"
        log("VK", f"✅ Последний пост @{page}: {post_url}")
        return full_id, post_url
    except Exception as e:
        log("VK", f"❌ @{page}: {e}")
        return None, None

# ══════════════════════════════════════
#  SOCPUBLIC API
# ══════════════════════════════════════

def sp_api(act, **params):
    """Базовый вызов SocPublic API. Возвращает распарсенный JSON (dict) или None."""
    data = {"api_id": SP_API_ID, "api_key": SP_API_KEY, "act": act}
    data.update(params)
    try:
        resp = requests.post(SP_API_URL, data=data, timeout=30)
        try:
            j = resp.json()
        except Exception:
            log("SP", f"❌ {act}: ответ не JSON (status {resp.status_code}): {resp.text[:200]}")
            return None
        return j
    except Exception as e:
        log("SP", f"❌ {act}: {e}")
        return None

def sp_build_description(post_url):
    """HTML-описание задания с подставленной ссылкой на пост."""
    return (
        '<pre style="font-family: SFMono-Regular, Menlo, Monaco, Consolas, &quot;Liberation Mono&quot;, &quot;Courier New&quot;, monospace; '
        'font-size: 14.4px; margin-top: 0px; color: rgb(33, 37, 41); background-color: rgb(240, 240, 240);">\r\n'
        '<strong style="color: rgb(51, 51, 51); font-family: sans-serif, Arial, Verdana, &quot;Trebuchet MS&quot;; font-size: 13px;">'
        '<span style="color: rgb(84, 84, 84); font-family: Tahoma, Arial, &quot;Times New Roman&quot;, &quot;Trebuchet MS&quot;, Impact, sans-serif; '
        'font-size: 12px; background-color: rgb(249, 249, 249);">1. Написать  коммент &nbsp;к  посту   &nbsp; ( минимум 7 слов)</span></strong>\r\n'
        '</pre>\r\n\r\n'
        '<pre style="font-family: SFMono-Regular, Menlo, Monaco, Consolas, &quot;Liberation Mono&quot;, &quot;Courier New&quot;, monospace; '
        'font-size: 14.4px; margin-top: 0px; color: rgb(33, 37, 41); background-color: rgb(240, 240, 240);">\r\n'
        f'{post_url}</pre>\r\n'
        '<u><strong style="color: rgb(84, 84, 84); font-family: Tahoma, Arial, &quot;Times New Roman&quot;, &quot;Trebuchet MS&quot;, Impact, sans-serif; '
        'font-size: 12px; background-color: rgb(249, 249, 249);">'
        'Пожалуйста пишите интересно и строго по теме поста, можете использовать ChatGpt :)</strong></u><br />\r\n'
        '<br />\r\n<br />\r\n'
        '2. Поставить реакцию на пост и подписаться<br />\r\n'
        '3. Поделиться постом<br />\r\n'
        '4. Лайкуть пару других комментов'
    )

def sp_build_approve_text():
    """HTML-текст требований к отчёту."""
    return (
        '<strong><span style="color: rgb(200, 0, 0); font-family: Tahoma, Arial, &quot;Times New Roman&quot;, &quot;Trebuchet MS&quot;, Impact, sans-serif; '
        'font-size: 12px; background-color: rgb(249, 249, 249);">'
        '1. Скрин&nbsp; коммента<br />\r\n'
        '2. Ваше имя в Вк</span></strong>'
    )

def sp_create_task(post_url, qmin, qmax):
    """Создаёт задание (с нашим текстом), сразу пополняет баланс и включает.
    Возвращает True при успехе."""
    quantity   = random.randint(qmin, qmax)
    price_adv  = round(SP_PRICE_USER * SP_PRICE_ADV, 2)   # цена 1 выполнения для нас
    balance    = round(quantity * price_adv, 2)           # покрыть quantity выполнений
    tail       = post_url.rstrip("/").split("/")[-1]      # напр. wall426046437_1696

    task = {
        "name": f"Написать в Вконтакте {tail}",
        "url": [post_url],
        "type": "social",
        "description": sp_build_description(post_url),
        "approve_type": "hand",
        "approve_text": sp_build_approve_text(),
        "price_user": SP_PRICE_USER,
        "balance": balance,
        "turn_on": 1,
    }

    log("SP", f"📤 Создаю задание: {post_url} | {quantity} вып. | баланс {balance} руб")
    resp = sp_api("task_create", data=json.dumps(task, ensure_ascii=True))
    if not resp:
        return False

    status = resp.get("status")
    if status == 0:
        d = resp.get("data", {})
        tid = d.get("id", "?")
        active = d.get("active", "?")
        bal = d.get("balance", "?")
        log("SP", f"🎉 Задание создано! id={tid} | статус={active} | баланс={bal} руб ({quantity} вып.)")
        if active != "yes" and tid != "?":
            r2 = sp_api("task_on", task_id=tid)
            if r2 and r2.get("status") == 0:
                log("SP", f"▶️  Задание {tid} включено")
            else:
                log("SP", f"⚠️  Не удалось включить {tid}: {r2.get('text') if r2 else 'нет ответа'}")
        return True
    else:
        log("SP", f"❌ Ошибка создания (status {status}): {resp.get('text', 'нет текста')}")
        log("SP", f"📄 Полный ответ: {json.dumps(resp, ensure_ascii=False)[:500]}")
        return False

def sp_check_balance():
    """Логирует рекламный баланс аккаунта при старте."""
    resp = sp_api("account_info")
    if resp and resp.get("status") == 0:
        adv = resp.get("data", {}).get("balance_rub_advert", "?")
        log("SP", f"💼 Рекламный баланс: {adv} руб")
    else:
        txt = resp.get("text", "нет ответа") if resp else "нет ответа"
        log("SP", f"⚠️  Не смог получить баланс: {txt}")

# ══════════════════════════════════════
#  ПОТОК
# ══════════════════════════════════════

def socpublic_bot():
    pages_str = ", ".join(p[0] for p in SP_PAGES)
    log("SocPublic", f"💬 Запущен | Страницы: {pages_str}")
    sp_check_balance()

    state_file = "sp_last_post.txt"
    state = load_state_dict(state_file)

    for page, qmin, qmax, expires in SP_PAGES:
        if page not in state:
            post_id, _ = get_vk_post(page)
            if post_id:
                state[page] = post_id
                log("SocPublic", f"📌 @{page} — последний пост: #{post_id}. Жду новые...")
    save_state_dict(state_file, state)

    while True:
        time.sleep(SP_CHECK_INTERVAL)
        try:
            today = date.today().isoformat()
            for page, qmin, qmax, expires in SP_PAGES:
                if expires and today > expires:
                    continue  # срок истёк — пропускаем
                latest_id, post_url = get_vk_post(page)
                if not latest_id:
                    continue
                if latest_id != state.get(page):
                    log("SocPublic", f"🆕 Новый пост @{page}: {post_url}")
                    ok = sp_create_task(post_url, qmin, qmax)
                    if ok:
                        state[page] = latest_id
                        save_state_dict(state_file, state)
                        log("SocPublic", f"💾 Запомнил пост #{latest_id}")
                    else:
                        log("SocPublic", f"⏸️  Задание не создалось — попробую снова через минуту")
                else:
                    log("SocPublic", f"🔍 @{page} — нет новых постов (последний: #{state.get(page)})")
                time.sleep(2)
        except Exception as e:
            log("SocPublic", f"❌ Ошибка: {e}")

# ══════════════════════════════════════
#  MAIN
# ══════════════════════════════════════

def main():
    log("MAIN", "🚀 SocPublic бот запущен (API режим)!")
    socpublic_bot()

if __name__ == "__main__":
    main()
