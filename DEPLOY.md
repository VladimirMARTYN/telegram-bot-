# 🚀 Деплой Telegram бота

Ниже — короткий и рабочий вариант деплоя на Railway.

## Railway
1. Залейте репозиторий в GitHub.
2. В Railway создайте проект и выберите **Deploy from GitHub repo**.
3. В Settings → Environment добавьте:
   - `BOT_TOKEN`
   - `ADMIN_USER_ID`
   - (опционально) остальные API ключи из `env.example`
4. Railway сам запустит команду из `Procfile`.

## Локальный запуск
```bash
cp env.example .env
# заполните BOT_TOKEN и ADMIN_USER_ID
pip install -r requirements.txt
python admin_bot.py
```
