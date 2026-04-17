import sqlite3, json, threading, time, re
from datetime import datetime, timedelta
import telebot
from telebot import types

token = "8763756243:AAFiZka2uhPxNLS27QhkfApNLPsof-s_Miw"
chat_id = -1003839166129
channel_id = -1003931083697
channel_link = "https://t.me/+TFQjHfu-_KJiNDgy"
admin_id = 8016986918
payment = 4.0
hold = 5 * 60
timeout_phone = 60
timeout_kod = 3 * 60

local = threading.local()

def db():
    if not hasattr(local, "conn"):
        local.conn = sqlite3.connect("baza.db", check_same_thread=False)
        local.conn.row_factory = sqlite3.Row
    return local.conn

def setup():
    c = db().cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            bal REAL DEFAULT 0.0,
            role TEXT DEFAULT 'drop',
            state TEXT,
            temp TEXT,
            total_orders INTEGER DEFAULT 0,
            total_earned REAL DEFAULT 0.0,
            today_earned REAL DEFAULT 0.0,
            last_earning_date TEXT,
            sub INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cold_id INTEGER,
            drop_id INTEGER,
            phone TEXT,
            kod TEXT,
            status TEXT DEFAULT 'wait_drop',
            msg_grp INTEGER,
            msg_thread_id INTEGER,
            msg_kanal INTEGER,
            msg_drop INTEGER,
            hold_until TEXT,
            paid INTEGER DEFAULT 0,
            created TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS vyvod (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            summa REAL,
            status TEXT DEFAULT 'wait',
            created TEXT,
            admin_msg_id INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    try:
        c.execute("ALTER TABLE users ADD COLUMN sub INTEGER DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE vyvod ADD COLUMN admin_msg_id INTEGER")
    except: pass
    try:
        c.execute("ALTER TABLE orders ADD COLUMN msg_thread_id INTEGER")
    except: pass
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('price', ?)", (str(payment),))
    db().commit()

setup()
bot = telebot.TeleBot(token, parse_mode="HTML")

def get_price():
    c = db().cursor()
    c.execute("SELECT value FROM settings WHERE key='price'")
    r = c.fetchone()
    return float(r['value']) if r else payment

def fmt(n):
    if n is None: return "0"
    return str(int(n)) if n == int(n) else f"{n:.2f}"

def prof(u):
    return (
        f"> 👤 *Ваш ID:* `{u['id']}`\n"
        f"> 💳 *Баланс:* `{fmt(u['bal'] or 0)}$`\n\n"
        f"> — *📊 Статистика:*\n"
        f"> 💰 *Сегодня:* `{fmt(u['today_earned'] or 0)}$`\n"
        f"> 📦 *Сдано номеров:* `{u['total_orders'] or 0}`\n"
        f"> 💵 *Всего оплачено:* `{fmt(u['total_earned'] or 0)}$`"
    )

def prof_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💸 Вывод", callback_data="vyvod_zapros"))
    return kb

def menu_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add("Меню")
    return kb

def back_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_profile"))
    return kb

def hide_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Скрыть", callback_data="hide_msg"))
    return kb

def adm_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Изменение цены", callback_data="adm_price"),
           types.InlineKeyboardButton("Изменение баланса", callback_data="adm_balance"),
           types.InlineKeyboardButton("Рассылка", callback_data="adm_broadcast"),
           types.InlineKeyboardButton("Закрыть", callback_data="adm_close"))
    return kb

def sub_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Подписаться", url=channel_link),
           types.InlineKeyboardButton("Проверить подписку", callback_data="check_sub"))
    return kb

def check_phone(p):
    p = re.sub(r'[\s\-\(\)]', '', p)
    if p.startswith('+7') and len(p) == 12 and p[1:].isdigit(): return True, p
    if len(p) == 11 and p.isdigit() and p[0] in ['7','8']:
        if p[0] == '8': p = '+7' + p[1:]
        else: p = '+' + p
        return True, p
    return False, None

def check_subscription(uid):
    try:
        member = bot.get_chat_member(channel_id, uid)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def worker():
    while True:
        try:
            time.sleep(5)
            c = db().cursor()
            now = datetime.now()
            today = now.date().isoformat()
            pr = get_price()
            c.execute("""
                SELECT o.id, o.drop_id, o.phone, u.last_earning_date, u.bal
                FROM orders o JOIN users u ON o.drop_id = u.id
                WHERE o.status='done' AND o.paid=0 AND o.hold_until <= ?
            """, (now.isoformat(),))
            for r in c.fetchall():
                oid, drop, ph, ld, old = r['id'], r['drop_id'], r['phone'], r['last_earning_date'], r['bal'] or 0
                c.execute("UPDATE users SET bal = bal + ? WHERE id=?", (pr, drop))
                if ld != today:
                    c.execute("UPDATE users SET total_orders=total_orders+1, total_earned=total_earned+?, today_earned=?, last_earning_date=? WHERE id=?", (pr, pr, today, drop))
                else:
                    c.execute("UPDATE users SET total_orders=total_orders+1, total_earned=total_earned+?, today_earned=today_earned+? WHERE id=?", (pr, pr, drop))
                c.execute("UPDATE orders SET paid=1 WHERE id=?", (oid,))
                db().commit()
                try:
                    txt = f"> 💸 *Начисление\\!*\n> Номер `{ph}` успешно отстоял холд\n> *На ваш баланс было начислено:* `{int(pr)}$`\n> *Текущий баланс:* `{fmt(old+pr)}$`"
                    bot.send_message(drop, txt, parse_mode="MarkdownV2", reply_markup=hide_kb())
                except: pass
        except Exception as e: print(e); time.sleep(5)
threading.Thread(target=worker, daemon=True).start()

def phone_tm(oid, cid, mid):
    time.sleep(timeout_phone)
    try:
        c = db().cursor()
        c.execute("SELECT * FROM orders WHERE id=?", (oid,))
        o = c.fetchone()
        if o and o['status'] == 'wait_phone':
            c.execute("UPDATE orders SET status='cancel' WHERE id=?", (oid,))
            c.execute("UPDATE users SET state=NULL WHERE id=?", (o['drop_id'],))
            db().commit()
            try: bot.edit_message_text("⌛ Время вышло. Заявка отменена.", cid, mid, reply_markup=hide_kb())
            except: pass
            bot.send_message(chat_id, f"⏰ Дроп не ввёл номер за 1 мин. Заявка #{oid} отменена.", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
    except: pass

def code_tm(oid, cid, mid):
    time.sleep(timeout_kod)
    try:
        c = db().cursor()
        c.execute("SELECT * FROM orders WHERE id=?", (oid,))
        o = c.fetchone()
        if o and o['status'] == 'wait_kod':
            c.execute("UPDATE orders SET status='cancel' WHERE id=?", (oid,))
            c.execute("UPDATE users SET state=NULL WHERE id=?", (o['drop_id'],))
            db().commit()
            try: bot.edit_message_text("⌛ Время вышло. Заявка отменена.", cid, mid, reply_markup=hide_kb())
            except: pass
            bot.send_message(chat_id, f"⏰ Дроп не ввёл код за 3 мин. Заявка #{oid} отменена.", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
            bot.send_message(o['drop_id'], "> ❌ Время вышло\\. Заявка отменена\\.", parse_mode="MarkdownV2")
    except: pass

def add_u(uid, n, un):
    c = db().cursor()
    c.execute("INSERT OR IGNORE INTO users (id, name, username) VALUES (?, ?, ?)", (uid, n, un))
    db().commit()

def get_u(uid):
    c = db().cursor()
    c.execute("SELECT * FROM users WHERE id=?", (uid,))
    return c.fetchone()

def set_st(uid, s, t=None):
    c = db().cursor()
    c.execute("UPDATE users SET state=?, temp=? WHERE id=?", (s, t, uid))
    db().commit()

def new_o(cold, th=None):
    c = db().cursor()
    cr = datetime.now().isoformat()
    c.execute("INSERT INTO orders (cold_id, status, created, msg_thread_id) VALUES (?, 'wait_drop', ?, ?)", (cold, cr, th))
    db().commit()
    return c.lastrowid

def get_o(oid):
    c = db().cursor()
    c.execute("SELECT * FROM orders WHERE id=?", (oid,))
    return c.fetchone()

def upd_o(oid, **kw):
    c = db().cursor()
    f = ", ".join([f"{k}=?" for k in kw])
    v = list(kw.values()) + [oid]
    c.execute(f"UPDATE orders SET {f} WHERE id=?", v)
    db().commit()

def show_prof(uid, edit=None):
    u = get_u(uid)
    if not u: return
    t = prof(u)
    if edit:
        try: bot.edit_message_text(t, uid, edit, parse_mode="MarkdownV2", reply_markup=prof_kb())
        except: bot.send_message(uid, t, parse_mode="MarkdownV2", reply_markup=prof_kb())
    else:
        bot.send_message(uid, t, parse_mode="MarkdownV2", reply_markup=prof_kb())
    bot.send_message(uid, "*Используйте кнопку «Меню» для вызова профиля*", parse_mode="MarkdownV2", reply_markup=menu_kb())

@bot.message_handler(commands=['admin'])
def adm_cmd(m):
    if m.from_user.id != admin_id: return
    bot.send_message(m.chat.id, f"*Админ\\-панель*\n\nТекущая цена: `{get_price()}$`", parse_mode="MarkdownV2", reply_markup=adm_kb())

@bot.callback_query_handler(func=lambda c: c.data == "adm_close")
def adm_close(c):
    if c.from_user.id != admin_id: return
    bot.delete_message(c.message.chat.id, c.message.message_id)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "adm_price")
def adm_price(c):
    if c.from_user.id != admin_id: return
    bot.send_message(c.message.chat.id, "Введите новую цену за номер в $:")
    set_st(c.from_user.id, "adm_wait_price")
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "adm_balance")
def adm_balance(c):
    if c.from_user.id != admin_id: return
    bot.send_message(c.message.chat.id, "Введите ID пользователя и сумму через пробел\nПример: `123456789 10` — добавить 10$\n`123456789 -5` — забрать 5$", parse_mode="MarkdownV2")
    set_st(c.from_user.id, "adm_wait_balance")
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "adm_broadcast")
def adm_broadcast(c):
    if c.from_user.id != admin_id: return
    bot.send_message(c.message.chat.id, "Введите текст для рассылки:")
    set_st(c.from_user.id, "adm_wait_broadcast")
    bot.answer_callback_query(c.id)

@bot.message_handler(func=lambda m: m.from_user.id == admin_id and m.reply_to_message is not None)
def adm_reply(m):
    t = m.reply_to_message.text or ""
    if "Заявка на вывод #" not in t: return
    try: rid = int(t.split("#")[1].split("\n")[0])
    except: return
    c = db().cursor()
    c.execute("SELECT * FROM vyvod WHERE id=?", (rid,))
    r = c.fetchone()
    if not r or r['status'] != 'wait': bot.send_message(admin_id, "Заявка уже обработана"); return
    chk = m.text.strip()
    for x in ['_','*','[',']','(',')','~','`','>','#','+','-','=','|','{','}','.','!']: chk = chk.replace(x, f'\\{x}')
    txt = f"> 💳 *Чек на выплату:*\n> {chk}\n> \n> — 👨‍💻 *Спасибо за доверие к нашему сервису\\!*"
    bot.send_message(r['user_id'], txt, parse_mode="MarkdownV2")
    c.execute("UPDATE vyvod SET status='done' WHERE id=?", (rid,))
    c.execute("UPDATE users SET bal = bal - ? WHERE id=?", (r['summa'], r['user_id']))
    db().commit()
    bot.send_message(admin_id, f"✅ Чек отправлен, заявка #{rid} выполнена")

@bot.callback_query_handler(func=lambda c: c.data == "check_sub")
def check_sub_cb(c):
    uid = c.from_user.id
    if check_subscription(uid):
        c_obj = db().cursor()
        c_obj.execute("UPDATE users SET sub=1 WHERE id=?", (uid,))
        db().commit()
        bot.delete_message(uid, c.message.message_id)
        show_prof(uid)
    else:
        bot.answer_callback_query(c.id, "Вы не подписались на канал!", show_alert=True)

@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    add_u(uid, m.from_user.full_name, m.from_user.username)
    if m.chat.id != uid: return
    
    if not check_subscription(uid):
        txt = "> *Перед тем как начать использовать бота, подпишитесь на канал с заявками\\!*"
        bot.send_message(uid, txt, parse_mode="MarkdownV2", reply_markup=sub_kb())
        return
    
    c_obj = db().cursor()
    c_obj.execute("UPDATE users SET sub=1 WHERE id=?", (uid,))
    db().commit()
    
    t = m.text
    if t and 'order_' in t:
        try:
            oid = int(t.split('order_')[1])
            o = get_o(oid)
            if not o or o['status'] != 'wait_drop': show_prof(uid); return
            upd_o(oid, drop_id=uid, status='wait_phone')
            uinf = f"@{m.from_user.username}" if m.from_user.username else f"id{uid}"
            bot.send_message(chat_id, f"<b>Заявка #{oid}</b>\n\n<b>📥 {uinf} [<code>{uid}</code>]</b>\n<b>Ждём номер телефона...</b>", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
            if o['msg_kanal']:
                try: bot.delete_message(channel_id, o['msg_kanal'])
                except: pass
            msg = bot.send_message(uid, f"> *\\#{oid}*\n> \n> ✅ *Заявка успешно принята\\.*\n> — Пожалуйста, отправьте номер телефона в ответном сообщении\\.\n> \n> *Время на выполнение — 1 минута\\.*", parse_mode="MarkdownV2", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_phone_{oid}")))
            upd_o(oid, msg_drop=msg.message_id)
            set_st(uid, f"wait_phone_{oid}")
            threading.Thread(target=phone_tm, args=(oid, uid, msg.message_id), daemon=True).start()
            return
        except: pass
    show_prof(uid)

@bot.message_handler(func=lambda m: m.chat.id == m.from_user.id and m.text == "Меню")
def menu_cmd(m):
    if not check_subscription(m.from_user.id):
        txt = "> *Перед тем как начать использовать бота, подпишитесь на канал с заявками\\!*"
        bot.send_message(m.from_user.id, txt, parse_mode="MarkdownV2", reply_markup=sub_kb())
        return
    show_prof(m.from_user.id)

@bot.message_handler(func=lambda m: m.chat.id == chat_id and m.text and m.text.lower() == "ворк")
def work(m):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📞 Запросить номер", callback_data="req_number"))
    bot.send_message(m.chat.id, "Панель управления:", reply_markup=kb, message_thread_id=m.message_thread_id)

@bot.callback_query_handler(func=lambda c: c.data == "req_number")
def req_num(c):
    if c.message.chat.id != chat_id: bot.answer_callback_query(c.id, "❌ Не та группа", show_alert=True); return
    oid = new_o(c.from_user.id, c.message.message_thread_id)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📱 Сдать номер", url=f"https://t.me/{(bot.get_me().username)}?start=order_{oid}"))
    msg = bot.send_message(channel_id, "<b>🔥 Срочно нужен номер!</b>\n<i>⏳ Кто первый нажмет, того и заявка.</i>", reply_markup=kb)
    upd_o(oid, msg_kanal=msg.message_id)
    bot.answer_callback_query(c.id, f"✅ Заявка #{oid} создана", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "back_to_profile")
def back(c):
    set_st(c.from_user.id, None)
    show_prof(c.from_user.id, c.message.message_id)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cancel_phone_"))
def cancel_ph(c):
    oid = int(c.data.split("_")[2])
    o = get_o(oid)
    if not o or o['drop_id'] != c.from_user.id or o['status'] != 'wait_phone': bot.answer_callback_query(c.id, "❌ Не ваша заявка или уже не активна", show_alert=True); return
    upd_o(oid, status='cancel')
    set_st(c.from_user.id, None)
    bot.edit_message_text("> ❌ *Вы отменили номер\\.*\n> *Заявка закрыта\\.*", c.message.chat.id, c.message.message_id, parse_mode="MarkdownV2", reply_markup=hide_kb())
    bot.send_message(chat_id, f"❌ Дроп отменил ввод номера. Заявка #{oid} отменена.", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "hide_msg")
def hide(c): bot.delete_message(c.message.chat.id, c.message.message_id); bot.answer_callback_query(c.id)

@bot.message_handler(func=lambda m: True, content_types=['text'])
def text_h(m):
    uid = m.from_user.id
    u = get_u(uid)
    if not u and uid != admin_id: return
    
    if uid != admin_id and not check_subscription(uid):
        txt = "> *Перед тем как начать использовать бота, подпишитесь на канал с заявками\\!*"
        bot.send_message(uid, txt, parse_mode="MarkdownV2", reply_markup=sub_kb())
        return
    
    st = u['state'] if u else None
    tmp = u['temp'] if u else None

    if uid == admin_id:
        if st == "adm_wait_price":
            try:
                np = float(m.text.strip())
                if np <= 0: raise
            except: bot.send_message(uid, "❌ Введите положительное число"); return
            c = db().cursor()
            c.execute("UPDATE settings SET value=? WHERE key='price'", (str(np),))
            db().commit()
            bot.send_message(uid, f"✅ Цена изменена на {np}$")
            set_st(uid, None); return
        if st == "adm_wait_balance":
            p = m.text.strip().split()
            if len(p) != 2: bot.send_message(uid, "❌ Неверный формат. Пример: `123456789 10`"); return
            try:
                tid = int(p[0])
                amt = float(p[1])
            except: bot.send_message(uid, "❌ Неверные числа"); return
            tgt = get_u(tid)
            if not tgt: bot.send_message(uid, "❌ Пользователь не найден"); return
            c = db().cursor()
            c.execute("UPDATE users SET bal = bal + ? WHERE id=?", (amt, tid))
            db().commit()
            if amt > 0:
                act = "начислено"
                txt = f"> 💰 *На ваш баланс было начислено:* `{amt:.0f}$`\n> *Текущий баланс:* `{fmt(tgt['bal']+amt)}$`"
            else:
                act = "списано"
                txt = f"> 💸 *С вашего баланса было списано:* `{abs(amt):.0f}$`\n> *Текущий баланс:* `{fmt(tgt['bal']+amt)}$`"
            bot.send_message(uid, f"✅ Пользователю {tid} {act} {abs(amt)}$")
            try: bot.send_message(tid, txt, parse_mode="MarkdownV2")
            except: pass
            set_st(uid, None); return
        if st == "adm_wait_broadcast":
            txt = m.text.strip()
            c = db().cursor()
            c.execute("SELECT id FROM users")
            users = c.fetchall()
            sent = 0
            for uu in users:
                try: bot.send_message(uu['id'], txt, parse_mode="MarkdownV2"); sent += 1; time.sleep(0.05)
                except: pass
            bot.send_message(uid, f"✅ Рассылка завершена. Отправлено {sent} пользователям.")
            set_st(uid, None); return

    if not u: return

    if st and st.startswith("wait_phone_"):
        oid = int(st.split("_")[2])
        o = get_o(oid)
        if not o or o['drop_id'] != uid or o['status'] != 'wait_phone': bot.send_message(uid, "Заявка уже не активна."); set_st(uid, None); return
        ph = m.text.strip()
        ok, clean = check_phone(ph)
        if not ok: bot.send_message(uid, "> ❌ *Неверный формат номера\\! Попробуйте ещё раз\\.*", parse_mode="MarkdownV2"); return
        upd_o(oid, phone=clean, status='wait_kod')
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("📲 Отправил код", callback_data=f"c_kod_{oid}"),
               types.InlineKeyboardButton("✅ Встал", callback_data=f"c_ok_{oid}"),
               types.InlineKeyboardButton("❌ Слетел", callback_data=f"c_no_{oid}"))
        uinf = f"@{u['username']}" if u['username'] else f"id{uid}"
        try:
            msg = bot.send_message(chat_id, f"<b>📱 Заявка #{oid}</b>\n\n<b>{uinf} [<code>{uid}</code>]</b>\n<b>Номер:</b> <code>{clean}</code>", reply_markup=kb, message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
            upd_o(oid, msg_grp=msg.message_id)
        except: bot.send_message(uid, "❌ Ошибка связи с группой. Попробуйте позже."); return
        if o['msg_drop']:
            try: bot.edit_message_text(f"> ✅ Номер `{clean}` принят\\!\n> Ожидайте запрос кода в течении 3 мин\\.", uid, o['msg_drop'], parse_mode="MarkdownV2")
            except: bot.send_message(uid, f"> ✅ Номер `{clean}` принят\\!\n> Ожидайте запрос кода в течении 3 мин\\.", parse_mode="MarkdownV2")
        else: bot.send_message(uid, f"> ✅ Номер `{clean}` принят\\!\n> Ожидайте запрос кода в течении 3 мин\\.", parse_mode="MarkdownV2")
        set_st(uid, None); return

    if st and st.startswith("wait_sms_"):
        oid = int(st.split("_")[2])
        o = get_o(oid)
        if not o or o['drop_id'] != uid: bot.send_message(uid, "Заявка не найдена"); return
        kod = m.text.strip()
        upd_o(oid, kod=kod, status='kod_entered')
        uinf = f"@{u['username']}" if u['username'] else f"id{uid}"
        bot.send_message(chat_id, f"<b>📱 Заявка #{oid}</b>\n\n<b>{uinf} [<code>{uid}</code>]</b>\n<b>Код:</b> <code>{kod}</code>", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
        bot.send_message(uid, "> ✅ Код отправлен\\. Ожидайте подтверждения\\.", parse_mode="MarkdownV2")
        set_st(uid, None); return

    if st == "wait_sum":
        try:
            s = float(m.text.replace(',', '.'))
            if s <= 0: raise
        except: bot.send_message(uid, "❌ Введи число больше 0"); return
        if s > u['bal']: bot.send_message(uid, f"> ❌ *Недостаточно средств\\!*\n> Ваш баланс: `{fmt(u['bal'])}$`", parse_mode="MarkdownV2"); set_st(uid, None); return
        c = db().cursor()
        c.execute("INSERT INTO vyvod (user_id, summa, status, created) VALUES (?, ?, 'wait', ?)", (uid, s, datetime.now().isoformat()))
        db().commit()
        rid = c.lastrowid
        uinf = f"@{u['username']}" if u['username'] else f"id{uid}"
        msg = bot.send_message(admin_id, f"> 💰 *Заявка на вывод \\#{rid}*\n> \n> *Ник:* {uinf}\n> *Юз/айди:* `{uid}`\n> *Вывод:* `{fmt(s)}$`\n> \n> _Ответьте на это сообщение ссылкой на чек_", parse_mode="MarkdownV2")
        c.execute("UPDATE vyvod SET admin_msg_id=? WHERE id=?", (msg.message_id, rid))
        db().commit()
        bot.send_message(uid, f"> ✅ Заявка на вывод `{fmt(s)}$` создана\\. Ожидайте чек\\.", parse_mode="MarkdownV2")
        set_st(uid, None); return

    if m.chat.id == uid: show_prof(uid)

@bot.callback_query_handler(func=lambda c: c.data.startswith("c_"))
def cold_acts(c):
    d = c.data.split("_")
    act, oid = d[1], int(d[2])
    o = get_o(oid)
    if not o: bot.answer_callback_query(c.id, "❌ Заявка не найдена", show_alert=True); return
    if o['cold_id'] != c.from_user.id: bot.answer_callback_query(c.id, "❌ Только создатель заявки может управлять", show_alert=True); return
    if act == "kod":
        if o['status'] not in ('wait_kod','kod_entered'): bot.answer_callback_query(c.id, "❌ Статус не позволяет", show_alert=True); return
        upd_o(oid, status='wait_kod')
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("🔢 Ввести код", callback_data=f"d_kod_{oid}"),
               types.InlineKeyboardButton("🔄 Запросить повтор", callback_data=f"d_rep_{oid}"),
               types.InlineKeyboardButton("❌ Не могу дать код", callback_data=f"d_cancel_{oid}"))
        msg = bot.send_message(o['drop_id'], f"> *\\#{oid}*\n> \n> — Требуется смс\\-код для номера `{o['phone']}` в течении *3 минут*\n> \n> Выберите действие:", parse_mode="MarkdownV2", reply_markup=kb)
        upd_o(oid, msg_drop=msg.message_id)
        threading.Thread(target=code_tm, args=(oid, o['drop_id'], msg.message_id), daemon=True).start()
        bot.answer_callback_query(c.id, "✅ Запрос кода отправлен дропу", show_alert=True)
    elif act == "ok":
        if o['status'] not in ('wait_kod','kod_entered'): bot.answer_callback_query(c.id, "❌ Статус не позволяет", show_alert=True); return
        upd_o(oid, status='done', hold_until=(datetime.now()+timedelta(seconds=hold)).isoformat())
        pr = get_price()
        bot.send_message(o['drop_id'], f"> ✅ Номер встал\\. Через 5 минут на ваш баланс будет начислено `{int(pr)}$`", parse_mode="MarkdownV2")
        bot.send_message(chat_id, f"✅ Заявка #{oid} — номер встал.", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
        bot.answer_callback_query(c.id, "✅ Готово", show_alert=True)
    elif act == "no":
        upd_o(oid, status='cancel')
        set_st(o['drop_id'], None)
        bot.send_message(o['drop_id'], "> ❌ Номер слетел\\. Попробуйте другую заявку\\.", parse_mode="MarkdownV2")
        bot.send_message(chat_id, f"❌ Заявка #{oid} — номер слетел.", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
        bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("d_"))
def drop_acts(c):
    d = c.data.split("_")
    act, oid = d[1], int(d[2])
    o = get_o(oid)
    if not o or o['drop_id'] != c.from_user.id: bot.answer_callback_query(c.id, "❌ Не ваша заявка", show_alert=True); return
    if act == "kod":
        try: bot.delete_message(c.message.chat.id, c.message.message_id)
        except: pass
        msg = bot.send_message(c.from_user.id, f"> ✍️ *Жду код\\!*\n> Пожалуйста, отправьте код в ответ на это сообщение\\.", parse_mode="MarkdownV2")
        upd_o(oid, msg_drop=msg.message_id)
        set_st(c.from_user.id, f"wait_sms_{oid}")
        bot.answer_callback_query(c.id)
    elif act == "rep":
        o = get_o(oid)
        bot.send_message(chat_id, f"🔄 Дроп запросил повторную отправку кода для заявки #{oid}", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
        bot.answer_callback_query(c.id, "✅ Холодка уведомлена", show_alert=True)
    elif act == "cancel":
        upd_o(oid, status='cancel')
        set_st(c.from_user.id, None)
        try: bot.edit_message_text("> ❌ *Вы отменили номер\\.*\n> *Заявка закрыта\\.*", c.message.chat.id, c.message.message_id, parse_mode="MarkdownV2", reply_markup=hide_kb())
        except: bot.send_message(c.from_user.id, "> ❌ *Вы отменили номер\\.*\n> *Заявка закрыта\\.*", parse_mode="MarkdownV2", reply_markup=hide_kb())
        bot.send_message(chat_id, f"❌ Дроп отказался дать код. Заявка #{oid} отменена.", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
        bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "vyvod_zapros")
def vyvod(c):
    uid = c.from_user.id
    u = get_u(uid)
    if not u: return
    if u['bal'] <= 0: bot.answer_callback_query(c.id, "‼️ Баланс пуст", show_alert=True); return
    txt = f"> 💸 *Вывод средств*\n> \n> Доступно: `{fmt(u['bal'])}$`\n> \n> ✍️ *Введите сумму для вывода*"
    try: bot.edit_message_text(txt, uid, c.message.message_id, parse_mode="MarkdownV2", reply_markup=back_kb())
    except: bot.send_message(uid, txt, parse_mode="MarkdownV2", reply_markup=back_kb())
    set_st(uid, "wait_sum")
    bot.answer_callback_query(c.id)

if __name__ == "__main__":
    bot.infinity_polling()
