# 🌐 Деплой веб-приложения на Railway

## 📋 Описание

Инструкции по развертыванию веб-приложения для администрирования бота-финансиста на Railway.

## 🚀 Вариант 1: Отдельный веб-сервис (Рекомендуемый)

### Шаг 1: Подготовка репозитория

1. **Создайте новую ветку для веб-приложения:**
```bash
git checkout -b web-app
```

2. **Добавьте необходимые файлы:**
- `web_app.py` - основное приложение
- `Procfile.web` - команда запуска
- `requirements-web.txt` - зависимости
- `templates/` - HTML шаблоны
- `.env` - переменные окружения

### Шаг 2: Создание нового проекта на Railway

1. **Перейдите на Railway.app**
2. **Создайте новый проект**
3. **Выберите "Deploy from GitHub repo"**
4. **Выберите репозиторий и ветку `web-app`**

### Шаг 3: Настройка переменных окружения

В Railway Dashboard добавьте:

**Обязательные:**
```
BOT_TOKEN=ваш_токен_бота
ADMIN_USER_ID=ваш_id_администратора
WEB_SECRET_KEY=секретный_ключ_для_веб_приложения
```

**Опциональные:**
```
METALPRICEAPI_KEY=demo
API_NINJAS_KEY=demo
FMP_API_KEY=demo
ALPHA_VANTAGE_KEY=demo
EIA_API_KEY=demo
```

### Шаг 4: Настройка сервиса

1. **Build Command:** `pip install -r requirements-web.txt`
2. **Start Command:** `python web_app.py`
3. **Port:** Railway автоматически установит переменную `PORT`

### Шаг 5: Деплой

Railway автоматически развернет веб-приложение!

## 🔗 Интеграция с Telegram ботом

### Добавление команды в бота

Добавьте в `admin_bot.py`:

```python
async def web_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для доступа к веб-панели"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if str(user_id) == os.getenv('ADMIN_USER_ID'):
        web_url = os.getenv('WEB_APP_URL', 'https://your-app.railway.app')
        
        message = (
            "🌐 <b>Веб-панель администратора</b>\n\n"
            f"🔗 <a href='{web_url}'>Открыть веб-панель</a>\n\n"
            "📊 <b>Возможности:</b>\n"
            "• Управление пользователями\n"
            "• Настройки бота\n"
            "• Просмотр логов\n"
            "• Статистика в реальном времени\n\n"
            "⚠️ <i>Доступно только администраторам</i>"
        )
        
        await update.message.reply_text(message, parse_mode='HTML', disable_web_page_preview=True)
    else:
        await update.message.reply_text("❌ У вас нет прав для доступа к веб-панели.")
```

### Регистрация команды

В функции `main()` добавьте:

```python
# Добавляем обработчики команд
application.add_handler(CommandHandler("webadmin", web_admin_command))
```

## 🔧 Вариант 2: Интеграция с существующим ботом

### Шаг 1: Объединение сервисов

1. **Обновите `requirements.txt`:**
```txt
python-telegram-bot==20.7
python-dotenv==1.0.0
flask==3.0.0
flask-socketio==5.3.6
# ... остальные зависимости
```

2. **Создайте объединенное приложение:**
```python
# bot_with_web.py
import threading
from admin_bot import main as bot_main
from web_app import app, socketio

def run_bot():
    bot_main()

def run_web():
    port = int(os.getenv('PORT', 5001))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем веб-приложение
    run_web()
```

3. **Обновите Procfile:**
```procfile
web: python bot_with_web.py
```

## 🌍 Доступ к веб-приложению

### После деплоя на Railway:

1. **Получите URL приложения** из Railway Dashboard
2. **Добавьте переменную окружения:**
```
WEB_APP_URL=https://your-app-name.railway.app
```

### Команды в Telegram:

- `/webadmin` - получить ссылку на веб-панель (только для админов)

## 🔒 Безопасность

### Рекомендации:

1. **Настройте аутентификацию** для веб-панели
2. **Используйте HTTPS** (Railway предоставляет автоматически)
3. **Ограничьте доступ** по IP (опционально)
4. **Регулярно обновляйте** зависимости

### Переменные безопасности:

```env
WEB_SECRET_KEY=очень_сложный_секретный_ключ
ADMIN_USER_ID=ваш_telegram_id
BOT_TOKEN=токен_вашего_бота
```

## 📊 Мониторинг

### Railway Dashboard:

- **Логи приложения** - для отладки
- **Метрики** - использование ресурсов
- **Переменные окружения** - конфигурация
- **Домены** - URL приложения

### Веб-панель:

- **Статистика пользователей**
- **Статус системы**
- **Логи в реальном времени**
- **Настройки бота**

## 🚀 Преимущества Railway

1. **Автоматический HTTPS** - безопасное соединение
2. **Автоскейлинг** - адаптация к нагрузке
3. **Простой деплой** - из GitHub
4. **Мониторинг** - встроенные метрики
5. **Переменные окружения** - безопасная конфигурация

---

**Веб-приложение готово к деплою на Railway!** 🎉

Выберите подходящий вариант и следуйте инструкциям. 