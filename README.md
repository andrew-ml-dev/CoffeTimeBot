# Coffee Desire Bot ☕

A simple Telegram bot to coordinate coffee breaks with your colleagues. The bot notifies everyone when all participants have a high enough desire for coffee.

## Features

- **User Registration**: simple `/start` command.
- **Desire Level**: Set your current desire for coffee (0-10).
- **Auto-Notification**: When **ALL** registered users have a desire level of **7 or higher**, the bot alerts everyone.
- **Status Check**: See who wants coffee and who doesn't.

## Quick start (Docker + Postgres)

1) Создай `.env` в корне:
```
BOT_TOKEN=your_token_here
DEFAULT_INVITE_CODE=WELCOME123
# опционально, если нужно переопределить:
# DB_HOST=db
# DB_PORT=5432
# DB_NAME=coffee_bot
# DB_USER=coffee
# DB_PASSWORD=coffee
```

2) Собрать и поднять:
```
docker compose build
docker compose up -d
```

3) Первый инвайт: по умолчанию при старте создаётся `DEFAULT_INVITE_CODE` (в compose = `WELCOME123`). Просто в Telegram отправь `/start WELCOME123`. Код можно сменить через переменную окружения.

4) pgweb (GUI для БД): http://<host>:8081

## Что делает бот сейчас
- Приватный доступ по инвайтам.
- Один основной поток действий: «☕️ Я хочу кофе» → выбрать уровень → выбрать напиток (кофе/латте/молоко/эспрессо).
- Уведомления группе, если кто-то выбрал напиток и уровень ≥ порога.
- Статусы и статистика (7д и всё время), индивидуальные 7д-отчёты.
- Настройки: порог, интервал напоминаний, тихие часы, инвайты, сброс.

## Group Chats

To add the bot to a group:
1. Open your group info in Telegram.
2. Click **Add Member**.
3. Search for your bot's username and add it.

**Important**:
- All users in the group interaction should also start the bot privately (in a DM) so the bot can send them private "Coffee Time" notifications.
- Currently, the bot shares one global state. If you use it in multiple groups, all users across all groups are pooled together.

## Troubleshooting

### ModuleNotFoundError: No module named 'aiogram'
If you see this error, you are not running the bot in the virtual environment.

**Fix**:
Run using the venv python executable:
```bash
./venv/bin/python bot.py
```
Or activate the venv first:
```bash
source venv/bin/activate
python bot.py
```
