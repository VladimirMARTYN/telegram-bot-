# 🚀 Деплой Telegram бота на хостинг

## Вариант 1: Railway.app (бесплатно, проще всего)

### Шаг 1: Подготовка
1. Убедись, что все файлы проекта готовы
2. У тебя есть рабочий токен бота

### Шаг 2: Регистрация на Railway
1. Иди на https://railway.app
2. Нажми "Start a New Project"
3. Войди через GitHub

### Шаг 3: Создание GitHub репозитория
1. Иди на https://github.com
2. Создай новый репозиторий "telegram-bot"
3. Загрузи все файлы проекта

### Шаг 4: Подключение к Railway
1. В Railway выбери "Deploy from GitHub repo"
2. Выбери свой репозиторий "telegram-bot"
3. Railway автоматически начнет деплой

### Шаг 5: Настройка переменных окружения
1. В Railway перейди в Settings → Environment
2. Добавь переменную: `BOT_TOKEN` = твой токен
3. **Для ChatGPT функций** добавь: `OPENAI_API_KEY` = твой API ключ от OpenAI
4. Сохрани

> 💡 **Как получить OpenAI API ключ:**
> 1. Иди на https://platform.openai.com
> 2. Зарегистрируйся или войди
> 3. API → API Keys → Create new secret key
> 4. Скопируй ключ (начинается с sk-...)

### Шаг 6: Деплой
Railway автоматически развернет бота!

---

## 🤖 ChatGPT Функции

### Команды для пользователей:
- `/ai [вопрос]` - Короткий ответ от ChatGPT
- `/gpt [вопрос]` - Развернутый ответ от ChatGPT
- Умный режим: просто задавай вопросы в чате!

### Админские команды ChatGPT:
- `/reset_limits` - Сбросить лимиты пользователей
- `/chatgpt_settings` - Управление настройками AI
- `/stats` - Статистика использования ChatGPT

### Настройки по умолчанию:
- **Модель:** gpt-3.5-turbo (быстрая и дешевая)
- **Лимит:** 10 запросов на пользователя
- **Макс. токенов:** 1000 (примерно 750 слов)
- **Админ:** без лимитов

### Стоимость OpenAI:
- GPT-3.5-turbo: ~$0.002 за 1000 токенов
- 100 вопросов ≈ $0.20
- Новые аккаунты получают $5 бесплатно

## Вариант 2: Render.com (бесплатно, 750 часов/месяц)

### Шаг 1: Подготовка кода
```bash
# Создай эти файлы дополнительно:
echo "web: python bot.py" > Procfile
echo "python-3.9.0" > runtime.txt
```

### Шаг 2: Деплой на Render
1. Иди на https://render.com
2. Создай аккаунт
3. "New" → "Background Worker"
4. Подключи GitHub репозиторий
5. Добавь переменную `BOT_TOKEN`

## Вариант 3: VPS (DigitalOcean) - $6/месяц

### Подключение к серверу:
```bash
ssh root@твой-ip-адрес
```

### Установка на сервере:
```bash
# Обновление системы
apt update && apt upgrade -y

# Установка Python
apt install python3 python3-pip git -y

# Клонирование репозитория
git clone https://github.com/твой-username/telegram-bot.git
cd telegram-bot

# Установка зависимостей
pip3 install -r requirements.txt

# Настройка токена
echo "BOT_TOKEN=твой_токен" > .env

# Запуск в фоне
nohup python3 bot.py &
```

## ⚡ Автозапуск бота (systemd)

### Создание службы:
```bash
sudo nano /etc/systemd/system/telegrambot.service
```

### Содержимое файла:
```ini
[Unit]
Description=Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telegram-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10
Environment=PATH=/usr/bin:/usr/local/bin

[Install]
WantedBy=multi-user.target
```

### Активация:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telegrambot
sudo systemctl start telegrambot
```

## 📊 Мониторинг

### Проверка статуса:
```bash
sudo systemctl status telegrambot
```

### Просмотр логов:
```bash
journalctl -u telegrambot -f
```

## 🔄 Автообновление

### Webhook для GitHub:
Можно настроить автоматическое обновление кода при push в GitHub. 