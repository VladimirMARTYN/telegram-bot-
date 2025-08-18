# 🌐 Telegram Bot Admin Web Dashboard

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0.0-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Railway](https://img.shields.io/badge/Deploy%20on-Railway-blue.svg)](https://railway.app)

## 📋 Описание

Современное веб-приложение для полного администрирования Telegram бота-финансиста. Предоставляет удобный интерфейс для мониторинга, управления пользователями, настройки бота и просмотра логов.

**🚀 Работает на Railway с ID проекта: `4d49fb15-67db-4808-9978-9391adb3aea6`**

## ✨ Возможности

### 📊 **Дашборд**
- Статистика пользователей в реальном времени
- Графики активности и распределения пользователей
- Статус системы и компонентов бота
- Быстрые действия для администрирования

### 👥 **Управление пользователями**
- Просмотр всех пользователей бота
- Фильтрация и поиск по различным критериям
- Управление подписками и алертами
- Массовые операции с пользователями
- Экспорт данных в CSV

### ⚙️ **Настройки бота**
- Основные настройки (название, язык, часовой пояс)
- Конфигурация уведомлений и алертов
- Управление API ключами
- Настройки производительности и безопасности
- Автосохранение изменений

### 📝 **Система логов**
- Просмотр всех логов бота
- Фильтрация по уровню, дате и содержимому
- Статистика по типам логов
- Экспорт логов в CSV
- Детальный просмотр записей

## 🚀 Быстрый старт

### 1. Клонирование и запуск
```bash
git clone https://github.com/your-username/telegram-bot-admin-web.git
cd telegram-bot-admin-web
pip install -r requirements.txt
python web_app.py
```

### 2. Настройка переменных окружения
```bash
cp env.example .env
# Отредактируйте .env файл с вашими настройками
```

### 3. Деплой на Railway
```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

## 🔧 Настройка переменных окружения

Создайте файл `.env` со следующими переменными:

```env
# Обязательные
BOT_TOKEN=ваш_токен_бота
ADMIN_USER_ID=ваш_telegram_id

# Опциональные
WEB_SECRET_KEY=секретный_ключ_для_сессий
WEB_HOST=0.0.0.0
WEB_PORT=5001
WEB_DEBUG=False
```

## 📱 Настройка как веб-приложение в Telegram

### 1. Создание веб-приложения через @BotFather

1. Отправьте команду `/newapp` боту @BotFather
2. Выберите вашего бота
3. Укажите название: "Admin Dashboard"
4. Добавьте описание: "Веб-панель для администрирования бота"
5. Загрузите иконку (512x512px)
6. Укажите URL: `https://your-app.railway.app`
7. Добавьте функциональность

### 2. Интеграция с ботом

Добавьте в вашего бота кнопку для открытия веб-приложения:

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

def show_admin_panel(update, context):
    """Показывает кнопку для открытия веб-панели"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if str(user_id) == os.getenv('ADMIN_USER_ID'):
        keyboard = [
            [InlineKeyboardButton(
                "🌐 Открыть веб-панель", 
                web_app=WebAppInfo(url="https://your-app.railway.app")
            )]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "🔧 Панель администратора\n\nОткройте веб-панель для управления ботом:",
            reply_markup=reply_markup
        )
    else:
        update.message.reply_text("❌ У вас нет прав для доступа к панели администратора.")

# Регистрация обработчика
application.add_handler(CommandHandler("admin", show_admin_panel))
```

## 🔧 API Endpoints

### Статус и данные
- `GET /api/status` - статус бота
- `GET /api/users` - список пользователей
- `GET /api/settings` - настройки бота

### Управление пользователями
- `POST /api/user/{id}/toggle_subscription` - переключение подписки
- `DELETE /api/user/{id}` - удаление пользователя

### Настройки
- `POST /api/settings` - сохранение настроек

## 📁 Структура проекта

```
telegram-bot-admin-web/
├── web_app.py              # Основное приложение Flask
├── requirements.txt         # Зависимости Python
├── Procfile                # Конфигурация для Railway
├── .env.example            # Пример переменных окружения
├── .gitignore              # Исключения Git
├── README.md               # Документация
├── templates/              # HTML шаблоны
│   ├── base.html           # Базовый шаблон
│   ├── dashboard.html      # Страница дашборда
│   ├── users.html          # Управление пользователями
│   ├── settings.html       # Настройки бота
│   └── logs.html           # Система логов
└── static/                 # Статические файлы
    ├── css/                # Стили
    └── js/                 # JavaScript файлы
```

## 🛠️ Технологии

### Backend
- **Flask 3.0.0** - веб-фреймворк
- **Flask-SocketIO 5.3.6** - WebSocket поддержка
- **Python 3.8+** - основной язык

### Frontend
- **Bootstrap 5** - CSS фреймворк
- **Font Awesome** - иконки
- **Chart.js** - графики
- **Socket.IO** - WebSocket клиент

## 🔒 Безопасность

### Защита данных
- API ключи хранятся в переменных окружения
- Валидация всех входных данных
- Защита от XSS и CSRF атак

### Доступ
- Рекомендуется настроить аутентификацию
- Ограничение доступа по IP (опционально)
- Логирование всех действий администратора

## 📈 Мониторинг

### Метрики
- Количество пользователей
- Активность подписчиков
- Статистика алертов
- Время работы бота

### Уведомления
- Статус системы в реальном времени
- Индикаторы ошибок
- Автоматические уведомления о проблемах

## 🔗 Интеграция с основным ботом

Веб-приложение интегрировано с основным Telegram ботом:
- 📊 Чтение данных из JSON файлов бота
- 🔄 Real-time обновления через WebSocket
- 📱 Поддержка Telegram Web Apps
- ⚙️ Управление настройками бота

## 📞 Поддержка

### Полезные команды
```bash
# Локальный запуск
python web_app.py

# Просмотр логов Railway
railway logs

# Перезапуск приложения
railway restart
```

### Полезные ссылки
- 📖 [Railway Documentation](https://docs.railway.app)
- 🔧 [Flask Documentation](https://flask.palletsprojects.com/)
- 📱 [Telegram Web Apps](https://core.telegram.org/bots/webapps)
- 🎨 [Bootstrap Documentation](https://getbootstrap.com/)

---

**Веб-приложение готово к использованию!** 🎉

Для начала работы запустите `python web_app.py` и откройте http://localhost:5001
