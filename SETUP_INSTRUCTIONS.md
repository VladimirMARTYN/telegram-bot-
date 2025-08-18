# 🚀 Инструкции по настройке веб-приложения

## 📋 Пошаговая настройка

### Шаг 1: Создание репозитория на GitHub

1. **Перейдите на GitHub.com**
2. **Нажмите "New repository"**
3. **Заполните форму:**
   - Repository name: `telegram-bot-web-admin`
   - Description: `Веб-панель администратора для Telegram бота-финансиста`
   - Visibility: Public (или Private)
   - НЕ ставьте галочки на README, .gitignore, license
4. **Нажмите "Create repository"**

### Шаг 2: Загрузка кода в репозиторий

После создания репозитория выполните:

```bash
# В папке telegram-bot-web-admin
git remote set-url origin https://github.com/VladimirMARTYN/telegram-bot-web-admin.git
git push -u origin main
```

### Шаг 3: Создание проекта на Railway

1. **Перейдите на Railway.app**
2. **Нажмите "Start a New Project"**
3. **Выберите "Deploy from GitHub repo"**
4. **Выберите репозиторий `telegram-bot-web-admin`**
5. **Нажмите "Deploy Now"**

### Шаг 4: Настройка переменных окружения на Railway

В Railway Dashboard добавьте переменные:

**Обязательные:**
```env
BOT_TOKEN=8075955278:AAEJCPlPFVzYR6A3snn8Q9RyqqSyBmcyQL8
ADMIN_USER_ID=34331814
WEB_SECRET_KEY=your-super-secret-key-for-web-app-2024
```

**Опциональные:**
```env
METALPRICEAPI_KEY=demo
API_NINJAS_KEY=demo
FMP_API_KEY=demo
ALPHA_VANTAGE_KEY=demo
EIA_API_KEY=demo
```

### Шаг 5: Получение URL приложения

После деплоя Railway даст вам URL вида:
`https://your-app-name.railway.app`

### Шаг 6: Интеграция с основным ботом

В основном репозитории бота добавьте переменную:
```env
WEB_APP_URL=https://your-app-name.railway.app
```

## 🔗 Команды для управления

### Локальный запуск
```bash
cd telegram-bot-web-admin
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python web_app.py
```

### Обновление кода
```bash
git add .
git commit -m "Описание изменений"
git push origin main
```

## 📊 Структура проекта

```
telegram-bot-web-admin/
├── web_app.py              # 🌐 Основное приложение
├── requirements.txt         # 📦 Зависимости
├── Procfile                # 🚀 Команда запуска
├── templates/              # 🎨 HTML шаблоны
│   ├── base.html          # Базовый шаблон
│   ├── dashboard.html     # Дашборд
│   ├── users.html         # Пользователи
│   ├── settings.html      # Настройки
│   └── logs.html          # Логи
├── notifications.json      # 📊 Данные пользователей
├── bot_settings.json       # ⚙️ Настройки бота
├── price_history.json      # 📈 История цен
├── README.md              # 📖 Документация
├── .gitignore             # 🚫 Игнорируемые файлы
└── env.example            # 📝 Пример переменных
```

## 🌐 Доступ к приложению

После настройки:
- **Веб-панель:** `https://your-app-name.railway.app`
- **Telegram бот:** команда `/webadmin`
- **API:** `https://your-app-name.railway.app/api/`

## 🔒 Безопасность

- Все API ключи хранятся в переменных окружения Railway
- Доступ к веб-панели только через команду `/webadmin` в боте
- Проверка прав администратора
- HTTPS автоматически предоставляется Railway

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи в Railway Dashboard
2. Убедитесь, что все переменные окружения настроены
3. Проверьте, что репозиторий подключен к Railway

---

**Веб-приложение готово к использованию!** 🎉 