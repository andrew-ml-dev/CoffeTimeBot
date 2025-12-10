import asyncio
import os
import logging
import random
import secrets
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import database

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_INVITE_CODE = os.getenv("DEFAULT_INVITE_CODE")
MESSAGE_TTL = int(os.getenv("MESSAGE_TTL", "3600"))

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
if not BOT_TOKEN:
    print("Error: BOT_TOKEN not found in .env file.")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DESIRE_THRESHOLD = 5  # fallback, overridden by settings
PROMPT_INTERVAL_SECONDS = 3600  # fallback for reminders
QUIET_HOURS_START = 0
QUIET_HOURS_END = 8
PEER_NOTIFY_COOLDOWN = 1800  # seconds
MOTIVATION_COOLDOWN = 1200   # seconds
DRINK_OPTIONS = {
    "coffee": "Кофе",
    "latte": "Кофе с молоком",
    "milk": "Только молоко",
    "espresso": "Эспрессо",
}

# rate-limit state (in-memory)
peer_notify_last = {}
motivation_last_at = 0
last_temp_message = {}
MOTIVATION_MESSAGES = [
    "Кофе ждёт вас! Заряд бодрости уже на подходе.",
    "Лучшие решения приходят с чашкой кофе. Вперёд!",
    "Пора сделать паузу и налить ароматный кофе.",
    "Командный кофе — командный успех. Не тормозим!",
    "Ещё чуть-чуть, и кофе поднимет настроение всем!",
]


def main_menu() -> InlineKeyboardMarkup:
    """Primary inline menu for all interactions."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="☕️ Я хочу кофе", callback_data="choose_level")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        ]
    )


def level_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard with levels 0-10 plus back button."""
    rows = [
        [InlineKeyboardButton(text=str(n), callback_data=f"level:{n}") for n in [0, 1, 2, 3]],
        [InlineKeyboardButton(text=str(n), callback_data=f"level:{n}") for n in [4, 5, 6, 7]],
        [InlineKeyboardButton(text=str(n), callback_data=f"level:{n}") for n in [8, 9, 10]],
    ]
    buttons = rows
    buttons.append(
        [
            InlineKeyboardButton(text="➖ -1", callback_data="adjust:-1"),
            InlineKeyboardButton(text="➕ +1", callback_data="adjust:+1"),
        ]
    )
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_status_text(users: list[dict]) -> str:
    threshold = current_threshold()
    text = "Текущий статус желания кофе:\n"
    for u in users:
        status_icon = "🟢" if u["desire"] >= threshold else "🔴"
        drink_part = ""
        if u["desire"] >= threshold:
            drink_part = f" ({drink_label(u.get('desire_type'))})"
        text += f"{status_icon} {u['username']}: {u['desire']}/10{drink_part}\n"
    return text


def drink_label(code: str | None) -> str:
    return DRINK_OPTIONS.get(code or "coffee", "Кофе")


def drink_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Кофе", callback_data="drink:coffee"),
                InlineKeyboardButton(text="Кофе с молоком", callback_data="drink:latte"),
            ],
            [
                InlineKeyboardButton(text="Только молоко", callback_data="drink:milk"),
                InlineKeyboardButton(text="Эспрессо", callback_data="drink:espresso"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
        ]
    )


def schedule_auto_delete(message: types.Message):
    if message is None:
        return

    async def _delete():
        try:
            await asyncio.sleep(MESSAGE_TTL)
            await bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass

    if MESSAGE_TTL > 0:
        asyncio.create_task(_delete())


async def answer_clean(message: types.Message, text: str, reply_markup=None):
    return await message.answer(text, reply_markup=reply_markup)


async def send_clean(chat_id: int, text: str, reply_markup=None):
    return await bot.send_message(chat_id, text, reply_markup=reply_markup)


async def send_temp(chat_id: int, text: str, reply_markup=None):
    prev_id = last_temp_message.get(chat_id)
    if prev_id:
        await delete_message_by_id(chat_id, prev_id)
    msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    last_temp_message[chat_id] = msg.message_id
    schedule_auto_delete(msg)
    return msg


async def delete_message_safe(message: types.Message | None):
    if not message:
        return
    try:
        await message.delete()
    except Exception:
        pass


async def delete_message_by_id(chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def current_threshold() -> int:
    try:
        return int(database.get_setting("threshold", database.DEFAULT_THRESHOLD))
    except Exception:
        return DESIRE_THRESHOLD


def current_prompt_interval() -> int:
    try:
        return int(database.get_setting("prompt_interval", database.DEFAULT_PROMPT_INTERVAL))
    except Exception:
        return PROMPT_INTERVAL_SECONDS


def is_quiet_hours() -> bool:
    hour = datetime.now().hour
    return QUIET_HOURS_START <= hour < QUIET_HOURS_END


def generate_invite_code() -> str:
    """Generate short invite code."""
    return secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]


async def ensure_member_message(message: types.Message) -> bool:
    """Ensure user is a member; otherwise inform and block."""
    if database.user_exists(message.from_user.id):
        return True
    await message.answer(
        "Бот приватный. Доступ только по приглашению. "
        "Попросите участника сгенерировать код через кнопку «Пригласить».",
    )
    return False


async def ensure_member_callback(callback: types.CallbackQuery) -> bool:
    """Ensure user is a member for callbacks."""
    if database.user_exists(callback.from_user.id):
        return True
    await callback.answer("Доступ только по приглашению.", show_alert=True)
    return False


def user_drink_code(user_id: int) -> str:
    return database.get_desire_type(user_id)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Registers user with invite code and shows main menu."""
    user = message.from_user
    args = message.text.split()
    invite_code = args[1] if len(args) > 1 else None

    if database.user_exists(user.id):
        database.add_user(user.id, user.full_name)
        database.log_event("start", user.id, user.full_name, info="existing_member")
        await answer_clean(
            message,
            f"С возвращением, {user.full_name}! Нажми «☕️ Я хочу кофе», выбери уровень и напиток. Остальное в «⚙️ Настройки».",
            reply_markup=main_menu(),
        )
        return

    if invite_code:
        if database.consume_invite(invite_code, user.id, user.full_name):
            database.add_user(user.id, user.full_name)
            database.log_event("invite_used", user.id, user.full_name, info=invite_code)
            await answer_clean(
                message,
                f"Приглашение принято, {user.full_name}! Нажми «☕️ Я хочу кофе», выбери уровень и напиток.",
                reply_markup=main_menu(),
            )
            return
        else:
            await answer_clean(message, "Код приглашения не подошёл или уже использован.")
            return

    await answer_clean(
        "Бот приватный. Доступ только по приглашению.\n"
        "Попросите текущего участника сгенерировать код через кнопку «Пригласить».",
    )


@dp.callback_query(F.data == "back_to_menu")
async def handle_back(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    await callback.answer()
    await answer_clean(callback.message, "Главное меню:", reply_markup=main_menu())
    await delete_message_safe(callback.message)


@dp.callback_query(F.data == "choose_level")
async def handle_choose_level(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    await callback.answer()
    await answer_clean(
        callback.message,
        "Шаг 1/2: выбери уровень желания кофе (0-10). После этого выбери напиток.",
        reply_markup=level_keyboard(),
    )
    await delete_message_safe(callback.message)


@dp.callback_query(F.data == "drink_menu")
async def handle_drink_menu(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    await callback.answer()
    await answer_clean(
        callback.message,
        "Выбери напиток:", reply_markup=drink_keyboard()
    )
    await delete_message_safe(callback.message)


@dp.callback_query(F.data.startswith("drink:"))
async def handle_drink(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    drink = callback.data.split(":", 1)[1]
    if drink not in DRINK_OPTIONS:
        await callback.answer("Неизвестный напиток.", show_alert=True)
        return
    database.add_user(callback.from_user.id, callback.from_user.full_name)
    database.set_desire_type(callback.from_user.id, drink)
    database.log_event("set_drink", callback.from_user.id, callback.from_user.full_name, info=drink)
    await callback.answer("Напиток обновлён")
    await answer_clean(
        callback.message,
        f"Твой выбор: {drink_label(drink)}.", reply_markup=main_menu()
    )
    await delete_message_safe(callback.message)
    user = database.get_user(callback.from_user.id)
    if user and user["desire"] >= current_threshold():
        await notify_peers_about_interest(
            callback.from_user.id, callback.from_user.full_name, user["desire"]
        )
    await check_coffee_status()


@dp.callback_query(F.data.startswith("level:"))
async def handle_set_level(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    parts = callback.data.split(":")
    try:
        level = int(parts[1])
    except (ValueError, IndexError):
        await callback.answer("Не получилось прочитать уровень.", show_alert=True)
        return

    if not (0 <= level <= 10):
        await callback.answer("Уровень должен быть от 0 до 10.", show_alert=True)
        return

    user_id = callback.from_user.id
    username = callback.from_user.full_name
    database.add_user(user_id, username)
    database.set_desire(user_id, level)
    database.log_event("set_desire", user_id, username, info=f"level:{level}")

    await callback.answer("Обновлено")
    await answer_clean(
        callback.message,
        f"Уровень желания установлен: {level}/10. Шаг 2/2: выбери напиток.",
        reply_markup=drink_keyboard(),
    )
    await delete_message_safe(callback.message)
    await check_coffee_status()


async def check_coffee_status():
    users = database.get_all_users()
    if not users:
        return

    ready_users = [u for u in users if u["desire"] >= current_threshold()]

    if len(ready_users) == len(users) and len(users) > 0:
        if is_quiet_hours():
            return
        text = "☕ ВРЕМЯ КОФЕ! ☕\n\nВсе хотят кофе:\n"
        for u in users:
            text += f"- {u['username']}: {u['desire']}/10 ({drink_label(u.get('desire_type'))})\n"

        text += f"\n{random.choice(MOTIVATION_MESSAGES)}"
        text += "\nПосле того как кофе будет выпито, нажмите «Кофе выпито», чтобы сбросить уровни."

        notify_markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✅ Кофе выпито", callback_data="reset")]]
        )

        for u in users:
            try:
                await send_temp(u["user_id"], text, reply_markup=notify_markup)
            except Exception as e:
                logging.error(f"Failed to send message to {u['user_id']}: {e}")


@dp.callback_query(F.data == "status")
async def handle_status(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    users = database.get_all_users()
    if not users:
        await callback.answer("Пока нет зарегистрированных участников.", show_alert=True)
        await answer_clean(
            callback.message,
            "Никого нет. Нажмите /start, чтобы зарегистрироваться.", reply_markup=main_menu()
        )
        await delete_message_safe(callback.message)
        return

    text = build_status_text(users)

    await callback.answer()
    await answer_clean(callback.message, text, reply_markup=main_menu())
    await delete_message_safe(callback.message)
    await delete_message_safe(callback.message)


@dp.callback_query(F.data == "weekly_stats")
async def handle_weekly_stats(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    stats = database.weekly_coffee_stats()

    count = stats["count"]
    if count == 0:
        text = "За последние 7 дней не было зарегистрировано ни одной кружки кофе."
    else:
        def format_gap(seconds):
            if seconds is None:
                return "—"
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}ч {minutes}м"

        text = (
            "Статистика за последние 7 дней:\n"
            f"• Выпито кружек: {count}\n"
            f"• Самый короткий перерыв: {format_gap(stats['shortest_gap'])}\n"
            f"• Самый длинный перерыв: {format_gap(stats['longest_gap'])}"
        )

    await callback.answer()
    await answer_clean(callback.message, text, reply_markup=main_menu())
    await delete_message_safe(callback.message)


def format_gap(seconds):
    if seconds is None:
        return "—"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}ч {minutes}м"


def format_datetime(dt_obj):
    if dt_obj is None:
        return "—"
    return dt_obj.strftime("%Y-%m-%d %H:%M")

def format_drink_counts(counts: dict) -> str:
    if not counts:
        return "—"
    parts = []
    for code, cnt in counts.items():
        parts.append(f"{drink_label(code)}: {cnt}")
    return "; ".join(parts)

@dp.callback_query(F.data == "settings")
async def handle_settings(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    threshold = current_threshold()
    interval = current_prompt_interval()
    text = (
        "⚙️ Настройки\n"
        f"• Порог готовности: {threshold}\n"
        f"• Интервал напоминаний: {interval // 60} мин\n"
        f"• Тихие часы: {QUIET_HOURS_START}:00–{QUIET_HOURS_END}:00\n"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статус", callback_data="status"),
                InlineKeyboardButton(text="✅ Кофе выпито", callback_data="reset"),
            ],
            [InlineKeyboardButton(text="🥤 Напиток", callback_data="drink_menu")],
            [
                InlineKeyboardButton(text="📈 7 дней", callback_data="weekly_stats"),
                InlineKeyboardButton(text="👤 7д по людям", callback_data="weekly_user_stats"),
            ],
            [InlineKeyboardButton(text="📊 Всё время", callback_data="all_stats")],
            [InlineKeyboardButton(text="🔑 Пригласить", callback_data="invite")],
            [
                InlineKeyboardButton(text="Порог -1", callback_data="set_threshold:-1"),
                InlineKeyboardButton(text="Порог +1", callback_data="set_threshold:+1"),
            ],
            [
                InlineKeyboardButton(text="Интервал 30м", callback_data="set_interval:1800"),
                InlineKeyboardButton(text="Интервал 60м", callback_data="set_interval:3600"),
                InlineKeyboardButton(text="Интервал 90м", callback_data="set_interval:5400"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
        ]
    )
    await callback.answer()
    await answer_clean(callback.message, text, reply_markup=kb)
    await delete_message_safe(callback.message)


@dp.callback_query(F.data.startswith("set_threshold:"))
async def handle_set_threshold(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    try:
        delta = int(callback.data.split(":")[1])
        new_value = max(1, min(10, current_threshold() + delta))
        database.set_setting("threshold", new_value)
        await callback.answer(f"Порог {new_value}")
    except Exception:
        await callback.answer("Не удалось изменить порог", show_alert=True)
        return
    await handle_settings(callback)


@dp.callback_query(F.data.startswith("set_interval:"))
async def handle_set_interval(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    try:
        value = int(callback.data.split(":")[1])
        database.set_setting("prompt_interval", value)
        await callback.answer(f"Интервал {value // 60} мин")
    except Exception:
        await callback.answer("Не удалось изменить интервал", show_alert=True)
        return
    await handle_settings(callback)


@dp.callback_query(F.data.startswith("adjust:"))
async def handle_adjust(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    delta = int(callback.data.split(":")[1])
    user = database.get_user(callback.from_user.id)
    current = user["desire"] if user else 0
    new_level = max(0, min(10, current + delta))
    database.add_user(callback.from_user.id, callback.from_user.full_name)
    database.set_desire(callback.from_user.id, new_level)
    database.log_event("set_desire", callback.from_user.id, callback.from_user.full_name, info=f"adjust:{new_level}")
    await callback.answer("Обновлено")
    await answer_clean(
        callback.message,
        f"Новый уровень: {new_level}/10.", reply_markup=main_menu()
    )
    await check_coffee_status()


@dp.callback_query(F.data == "all_stats")
async def handle_all_stats(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    weekly = database.weekly_coffee_stats()
    overall = database.all_time_coffee_stats()

    def block(label, stats):
        return (
            f"{label}\n"
            f"• Выпито кружек: {stats['count']}\n"
            f"• Самый короткий перерыв: {format_gap(stats['shortest_gap'])}\n"
            f"• Самый длинный перерыв: {format_gap(stats['longest_gap'])}\n"
            f"• Средний перерыв: {format_gap(stats['average_gap'])}\n"
            f"• Первая кружка: {format_datetime(stats['first_at'])}\n"
            f"• Последняя кружка: {format_datetime(stats['last_at'])}\n"
        )

    text = block("За 7 дней:", weekly) + "\n" + block("За всё время:", overall)

    await callback.answer()
    await answer_clean(callback.message, text, reply_markup=main_menu())


@dp.callback_query(F.data == "weekly_user_stats")
async def handle_weekly_user_stats(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return
    stats = database.user_weekly_stats()
    if not stats:
        await callback.answer()
        await answer_clean(callback.message, "За последние 7 дней нет данных.", reply_markup=main_menu())
        await delete_message_safe(callback.message)
        return

    lines = []
    for entry in stats:
        want = entry["want_count"]
        consumed = entry["consumed_total"]
        drinks_sel = format_drink_counts(entry["drink_selects"])
        drinks_cons = format_drink_counts(entry["consumed_by_drink"])
        lines.append(
            f"{entry['username']}:\n"
            f"• Хотел(а) напиток: {want} раз(а)\n"
            f"• Выбор напитков: {drinks_sel}\n"
            f"• Выпито кружек: {consumed} ({drinks_cons})"
        )

    text = "Индивидуальная статистика за 7 дней:\n\n" + "\n\n".join(lines)
    await callback.answer()
    await answer_clean(callback.message, text, reply_markup=main_menu())
    await delete_message_safe(callback.message)


@dp.callback_query(F.data == "reset")
async def handle_reset(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.full_name

    if not await ensure_member_callback(callback):
        return

    if not database.user_exists(user_id):
        await callback.answer("Сброс могут делать только участники.", show_alert=True)
        return

    database.reset_desires()
    users = database.get_all_users()
    drink = user_drink_code(user_id)
    database.log_event("coffee_consumed", user_id, username, info=f"drink:{drink}")

    info_text = f"{username} отметил(а), что кофе выпито ({drink_label(drink)}). Все уровни сброшены."
    for u in users:
        try:
            await send_clean(u["user_id"], info_text, reply_markup=main_menu())
        except Exception as e:
            logging.error(f"Failed to send message to {u['user_id']}: {e}")

    await callback.answer("Сброс выполнен.", show_alert=True)
    await delete_message_safe(callback.message)


async def notify_peers_about_interest(user_id: int, username: str, level: int):
    """Notify other members that someone wants coffee to prompt them to respond."""
    if is_quiet_hours():
        return
    users = database.get_all_users()
    drink = drink_label(user_drink_code(user_id))
    for u in users:
        if u["user_id"] == user_id:
            continue
        try:
            await send_temp(
                u["user_id"],
                (
                    f"{username} хочет {drink} ({level}/10).\n"
                    "Какое у тебя желание на этот напиток? Обнови свой уровень:"
                ),
                reply_markup=level_keyboard(),
            )
        except Exception as e:
            logging.error(f"Failed to notify {u['user_id']} about interest: {e}")


async def send_desire_prompts():
    """Send hourly prompt to users below threshold."""
    if is_quiet_hours():
        return
    users = database.get_all_users()
    for u in users:
        if u["desire"] < current_threshold():
            try:
                await send_temp(
                    u["user_id"],
                    "Напомни свой текущий уровень желания кофе:",
                    reply_markup=level_keyboard(),
                )
            except Exception as e:
                logging.error(f"Failed to prompt user {u['user_id']}: {e}")


async def send_motivation_if_ready():
    """Send motivational reminders while everyone is ready but кофе ещё не отмечено."""
    global motivation_last_at
    users = database.get_all_users()
    if not users:
        return

    ready_users = [u for u in users if u["desire"] >= current_threshold()]
    if len(ready_users) == len(users) and len(users) > 0:
        now = asyncio.get_event_loop().time()
        if now - motivation_last_at < MOTIVATION_COOLDOWN:
            return
        motivation_last_at = now
        if is_quiet_hours():
            return
        text = (
            f"{random.choice(MOTIVATION_MESSAGES)}\n\n"
            "Все хотят кофе, но кнопка «Кофе выпито» ещё не нажата. "
            "Быстро выпейте кофе для хорошего настроения!"
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✅ Кофе выпито", callback_data="reset")]]
        )
        for u in users:
            try:
                await send_temp(u["user_id"], text, reply_markup=markup)
            except Exception as e:
                logging.error(f"Failed to send motivation to {u['user_id']}: {e}")


async def scheduler():
    """Hourly scheduler for prompts and motivational reminders."""
    while True:
        await send_desire_prompts()
        await send_motivation_if_ready()
        await asyncio.sleep(current_prompt_interval())


@dp.message()
async def fallback(message: types.Message):
    """Fallback for any text: show main menu."""
    if not await ensure_member_message(message):
        return
    await answer_clean(
        message,
        "Нажми «☕️ Я хочу кофе», выбери уровень и напиток. Остальное — в «⚙️ Настройки».",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data == "invite")
async def handle_invite(callback: types.CallbackQuery):
    if not await ensure_member_callback(callback):
        return

    code = generate_invite_code()
    database.create_invite(code, callback.from_user.id)
    database.log_event("invite_created", callback.from_user.id, callback.from_user.full_name, info=code)

    await callback.answer("Инвайт сгенерирован")
    await answer_clean(
        callback.message,
        f"Отправьте этот код новому участнику:\n{code}\n"
        "Новый участник должен ввести: /start <код>",
        reply_markup=main_menu(),
    )
    await delete_message_safe(callback.message)


async def main():
    database.init_db()
    if DEFAULT_INVITE_CODE:
        database.create_invite(DEFAULT_INVITE_CODE, 0)
        logging.info(f"Default invite ensured: {DEFAULT_INVITE_CODE}")
    print("Database initialized.")
    scheduler_task = asyncio.create_task(scheduler())
    await dp.start_polling(bot)
    scheduler_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
