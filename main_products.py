import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import asyncio
from datetime import datetime, time, timedelta
from aiogram.client.default import DefaultBotProperties
import os

# --- НАСТРОЙКИ ---

# Берём токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Не найден BOT_TOKEN в переменных окружения!")

# Разрешённые пользователи (ID берём из переменных окружения через запятую)
allowed_users_env = os.getenv("ALLOWED_USERS", "")
try:
    ALLOWED_USERS = {int(x) for x in allowed_users_env.split(",") if x}
except ValueError:
    raise ValueError("ALLOWED_USERS должны быть числами через запятую, например: 123456789,987654321")

# Важные продукты (не трогаем, остаются как есть)
IMPORTANT_PRODUCTS = {
    "туалетная бумага",
    "кофе",
    "сливки",
    "мусорные пакеты",
    "сахар"
}

# Словарь для хранения состояния пользователей
user_mode = {}  # user_id -> режим или данные напоминания


# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("products.db")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            name TEXT PRIMARY KEY
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            remind_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def add_product(name: str):
    name = name.strip().lower()
    conn = sqlite3.connect("products.db")
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO products (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def remove_product(name: str):
    name = name.strip().lower()
    conn = sqlite3.connect("products.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE name = ?", (name,))
    conn.commit()
    conn.close()


def list_products():
    conn = sqlite3.connect("products.db")
    cur = conn.cursor()
    cur.execute("SELECT name FROM products ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def has_product(name: str):
    name = name.strip().lower()
    conn = sqlite3.connect("products.db")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM products WHERE name = ?", (name,))
    res = cur.fetchone()
    conn.close()
    return bool(res)


# --- БАЗА ДЛЯ НАПОМИНАНИЙ ---

def add_reminder(user_id: int, text: str, remind_at: datetime):
    conn = sqlite3.connect("products.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO reminders (user_id, text, remind_at)
        VALUES (?, ?, ?)
    """, (user_id, text, remind_at.isoformat()))
    conn.commit()
    conn.close()


def get_user_reminders(user_id: int):
    conn = sqlite3.connect("products.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT id, text, remind_at FROM reminders
        WHERE user_id = ?
        ORDER BY remind_at
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_due_reminders():
    conn = sqlite3.connect("products.db")
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute("""
        SELECT id, user_id, text FROM reminders
        WHERE remind_at <= ?
    """, (now,))
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_reminder(reminder_id: int):
    conn = sqlite3.connect("products.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


# --- БОТ ---
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()


def check_access(user_id):
    return user_id in ALLOWED_USERS


def main_keyboard():
    kb = [
        [KeyboardButton(text="➕ Добавить")],
        [KeyboardButton(text="❌ Удалить")],
        [KeyboardButton(text="📋 Список")],
        [KeyboardButton(text="🔍 Статус")],
        [KeyboardButton(text="⏰ Мои напоминания")],
        [KeyboardButton(text="ℹ️ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not check_access(message.from_user.id):
        await message.answer("🚫 Доступ запрещён")
        return
    await message.answer(
        "Привет! Я бот для учёта продуктов дома.\nВыберите действие:",
        reply_markup=main_keyboard()
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    if not check_access(message.from_user.id):
        return
    help_text = (
        "🛒 <b>Команды бота:</b>\n\n"
        "• /add продукт — добавить продукт\n"
        "• /remove продукт — удалить продукт\n"
        "• /status продукт — проверить наличие\n"
        "• /list — список всех продуктов\n"
        "• /remind — создать напоминание\n"
        "• /reminders — показать напоминания\n"
        "• /help — помощь\n\n"
    )
    await message.answer(help_text)


@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    if not check_access(message.from_user.id):
        return
    items = list_products()
    if not items:
        await message.answer("Пока ничего нет дома.")
    else:
        await message.answer("Список продуктов:\n" + "\n".join(f"• {p}" for p in items))


# --- СПИСОК НАПОМИНАНИЙ ---
@dp.message(Command("reminders"))
async def cmd_reminders(message: types.Message):
    if not check_access(message.from_user.id):
        return

    rows = get_user_reminders(message.from_user.id)
    if not rows:
        await message.answer("У вас пока нет напоминаний.")
        return

    text = "<b>Ваши напоминания:</b>\n\n"
    for rid, rtext, rtime in rows:
        t = datetime.fromisoformat(rtime).strftime("%Y-%m-%d %H:%M")
        text += f"• <b>{rtext}</b> — {t}\n"

    await message.answer(text)


# --- СОЗДАНИЕ НАПОМИНАНИЯ ---
@dp.message(Command("remind"))
async def cmd_remind(message: types.Message):
    if not check_access(message.from_user.id):
        return
    user_mode[message.from_user.id] = "remind_text"
    await message.answer("Что мне напомнить?")


# --- ОБРАБОТКА ВСЕХ ТЕКСТОВ ---
@dp.message()
async def handle_messages(message: types.Message):
    if not check_access(message.from_user.id):
        return

    text = message.text.lower()
    user_id = message.from_user.id

    # Кнопки меню
    if text in ("⏰ мои напоминания", "напоминания"):
        await cmd_reminders(message)
        return

    if text in ("➕ добавить", "добавить"):
        user_mode[user_id] = "add"
        await message.answer("Напишите название продукта, который нужно добавить:")
        return

    if text in ("❌ удалить", "удалить"):
        user_mode[user_id] = "remove"
        await message.answer("Напишите название продукта, который нужно удалить:")
        return

    if text in ("📋 список", "список"):
        await cmd_list(message)
        return

    if text in ("🔍 статус", "статус"):
        user_mode[user_id] = "status"
        await message.answer("Какой продукт проверить?")
        return

    if text in ("ℹ️ помощь", "помощь"):
        await cmd_help(message)
        return

    # --- ЛОГИКА НАПОМИНАНИЙ ---
    if user_mode.get(user_id) == "remind_text":
        user_mode[user_id] = {"mode": "remind_time", "text": message.text}
        await message.answer("Когда напомнить? Формат: YYYY-MM-DD HH:MM")
        return

    if isinstance(user_mode.get(user_id), dict) and user_mode[user_id].get("mode") == "remind_time":
        reminder_text = user_mode[user_id]["text"]
        del user_mode[user_id]

        try:
            remind_time = datetime.strptime(message.text, "%Y-%m-%d %H:%M")
        except ValueError:
            await message.answer("Неверный формат времени! Используйте YYYY-MM-DD HH:MM")
            return

        add_reminder(user_id, reminder_text, remind_time)
        await message.answer(
            f"Напоминание сохранено!\n"
            f"Я напомню: «{reminder_text}» в {remind_time}."
        )
        return

    # --- ЛОГИКА add/remove/status ---
    if user_id in user_mode:
        mode = user_mode.pop(user_id)
        product = message.text.strip().lower()

        if mode == "add":
            add_product(product)
            await message.answer(f"Добавлено: {product}")

        elif mode == "remove":
            remove_product(product)
            await message.answer(f"Удалено: {product}")

        elif mode == "status":
            if has_product(product):
                await message.answer(f"Есть: {product} ✔️")
            else:
                await message.answer(f"Нет: {product} ❌")

        return


# --- АВТОЕЖЕДНЕВНОЕ НАПОМИНАНИЕ ---
async def reminder_task():
    while True:
        now = datetime.now()
        target = datetime.combine(now.date(), time(18, 0))
        if now > target:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        await asyncio.sleep(wait_seconds)

        missing = [p for p in IMPORTANT_PRODUCTS if not has_product(p)]
        if missing:
            text = "⏰ <b>Напоминание!</b>\nНет важных продуктов:\n" + "\n".join(f"• {i}" for i in missing)
        else:
            text = "✔️ Все важные продукты дома!"

        for user_id in ALLOWED_USERS:
            await bot.send_message(user_id, text)


# --- ЛИЧНЫЕ НАПОМИНАНИЯ ---
async def personal_reminders_task():
    while True:
        reminders = get_due_reminders()
        for rid, user_id, text in reminders:
            try:
                await bot.send_message(user_id, f"🔔 Напоминание: {text}")
            except:
                pass
            delete_reminder(rid)

        await asyncio.sleep(30)  # проверяем каждые 30 секунд


# --- ЗАПУСК ---
async def main():
    init_db()
    print("Бот запущен!")
    asyncio.create_task(reminder_task())
    asyncio.create_task(personal_reminders_task())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())