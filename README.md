# Coffee Desire Bot ☕

A private, invite-only Telegram bot to coordinate coffee breaks. Users set a desire level (0–10) and pick a drink; when everyone is above the threshold, the bot notifies the group.

## Features
- Invite-only access (default invite code is created on startup).
*- One-tap flow:* “I want coffee” → select level → select drink (Coffee, Latte, Milk, Espresso).
- Group notifications when someone with a chosen drink is above threshold; manual “Coffee consumed” reset.
- Quiet hours, reminder interval, threshold tuning, anti-spam for motivational pings.
- Status and stats (7d and all-time), individual 7d reports.

## Quick start (Docker + Postgres)
1) Create `.env` in the repo root:
```
BOT_TOKEN=your_token_here
DEFAULT_INVITE_CODE=WELCOME123
# optional overrides:
# DB_HOST=db
# DB_PORT=5432
# DB_NAME=coffee_bot
# DB_USER=coffee
# DB_PASSWORD=coffee
# MESSAGE_TTL=3600   # set 0 to keep temp messages
```
2) Build and start:
```
docker compose build
docker compose up -d
```
3) First invite: default code is `WELCOME123` (from `DEFAULT_INVITE_CODE`). In Telegram: `/start WELCOME123`. Change the code via env if needed.
4) pgweb (DB UI): http://<host>:8081

## Group chats
To add the bot to a group:
1. Open group info in Telegram.
2. Tap **Add Member**.
3. Find your bot username and add it.

Important:
- Every user should also start the bot in a private DM so it can send personal notifications.
- Global state is shared across all chats (one pool of users).

## Troubleshooting
### ModuleNotFoundError: No module named 'aiogram'
You’re likely outside the virtual environment.
Fix:
```bash
./venv/bin/python bot.py
# or
source venv/bin/activate
python bot.py
```
