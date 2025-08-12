#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_socketio import SocketIO, emit
import json
import os
import threading
import time
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('WEB_SECRET_KEY', 'your-secret-key-here')
socketio = SocketIO(app, cors_allowed_origins="*")

# Глобальные переменные для мониторинга бота
bot_status = {
    'is_running': False,
    'last_activity': None,
    'users_count': 0,
    'notifications_count': 0,
    'alerts_count': 0,
    'uptime': None,
    'start_time': None
}

def serialize_bot_status():
    """Сериализует bot_status для JSON"""
    status = bot_status.copy()
    if status['start_time']:
        status['start_time'] = status['start_time'].isoformat()
    if status['last_activity']:
        status['last_activity'] = status['last_activity']
    return status

# Функции для работы с данными бота
def load_bot_data():
    """Загружает данные бота из JSON файлов"""
    data = {}
    
    # Загружаем пользователей
    try:
        with open('notifications.json', 'r', encoding='utf-8') as f:
            users_data = json.load(f)
            # Убеждаемся, что это список
            if isinstance(users_data, list):
                data['users'] = users_data
            else:
                data['users'] = []
    except (FileNotFoundError, json.JSONDecodeError):
        data['users'] = []
    
    # Загружаем настройки бота
    try:
        with open('bot_settings.json', 'r', encoding='utf-8') as f:
            settings_data = json.load(f)
            # Убеждаемся, что это словарь
            if isinstance(settings_data, dict):
                data['settings'] = settings_data
            else:
                data['settings'] = {}
    except (FileNotFoundError, json.JSONDecodeError):
        data['settings'] = {}
    
    # Загружаем историю цен
    try:
        with open('price_history.json', 'r', encoding='utf-8') as f:
            history_data = json.load(f)
            # Убеждаемся, что это словарь
            if isinstance(history_data, dict):
                data['price_history'] = history_data
            else:
                data['price_history'] = {}
    except (FileNotFoundError, json.JSONDecodeError):
        data['price_history'] = {}
    
    return data

def save_bot_data(data_type, data):
    """Сохраняет данные бота в JSON файлы"""
    if data_type == 'users':
        with open('notifications.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    elif data_type == 'settings':
        with open('bot_settings.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def get_moscow_time():
    """Возвращает текущее время в московском часовом поясе"""
    moscow_tz = pytz.timezone('Europe/Moscow')
    return datetime.now(moscow_tz)

# Маршруты Flask
@app.route('/')
def dashboard():
    """Главная страница дашборда"""
    bot_data = load_bot_data()
    
    # Обновляем статистику
    bot_status['users_count'] = len(bot_data.get('users', []))
    bot_status['notifications_count'] = sum(1 for user in bot_data.get('users', []) if user.get('subscribed', False))
    bot_status['alerts_count'] = sum(len(user.get('alerts', [])) for user in bot_data.get('users', []))
    
    if bot_status['start_time']:
        uptime = datetime.now() - bot_status['start_time']
        bot_status['uptime'] = str(uptime).split('.')[0]  # Убираем микросекунды
    
    return render_template('dashboard.html', 
                         bot_status=bot_status, 
                         bot_data=bot_data,
                         current_time=get_moscow_time())

@app.route('/users')
def users():
    """Страница управления пользователями"""
    bot_data = load_bot_data()
    return render_template('users.html', 
                         users=bot_data.get('users', []),
                         current_time=get_moscow_time())

@app.route('/settings')
def settings():
    """Страница настроек бота"""
    bot_data = load_bot_data()
    return render_template('settings.html', 
                         settings=bot_data.get('settings', {}),
                         current_time=get_moscow_time())

@app.route('/logs')
def logs():
    """Страница логов бота"""
    return render_template('logs.html', current_time=get_moscow_time())

@app.route('/api/status')
def api_status():
    """API для получения статуса бота"""
    return jsonify(bot_status)

@app.route('/api/users')
def api_users():
    """API для получения списка пользователей"""
    bot_data = load_bot_data()
    return jsonify(bot_data.get('users', []))

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """API для работы с настройками"""
    if request.method == 'POST':
        data = request.json
        bot_data = load_bot_data()
        bot_data['settings'].update(data)
        save_bot_data('settings', bot_data['settings'])
        return jsonify({'status': 'success'})
    
    bot_data = load_bot_data()
    return jsonify(bot_data.get('settings', {}))

@app.route('/api/user/<int:user_id>', methods=['DELETE'])
def api_delete_user(user_id):
    """API для удаления пользователя"""
    bot_data = load_bot_data()
    users = bot_data.get('users', [])
    
    # Удаляем пользователя
    users = [user for user in users if user.get('user_id') != user_id]
    bot_data['users'] = users
    save_bot_data('users', users)
    
    return jsonify({'status': 'success'})

@app.route('/api/user/<int:user_id>/toggle_subscription', methods=['POST'])
def api_toggle_subscription(user_id):
    """API для переключения подписки пользователя"""
    bot_data = load_bot_data()
    users = bot_data.get('users', [])
    
    for user in users:
        if user.get('user_id') == user_id:
            user['subscribed'] = not user.get('subscribed', False)
            break
    
    save_bot_data('users', users)
    return jsonify({'status': 'success'})

# WebSocket события
@socketio.on('connect')
def handle_connect():
    """Обработка подключения клиента"""
    print('Client connected')
    emit('status_update', serialize_bot_status())

@socketio.on('disconnect')
def handle_disconnect():
    """Обработка отключения клиента"""
    print('Client disconnected')

# Функция для имитации обновления статуса бота
def update_bot_status():
    """Обновляет статус бота каждые 5 секунд"""
    while True:
        time.sleep(5)
        
        # Имитируем активность бота
        bot_status['last_activity'] = get_moscow_time().strftime('%H:%M:%S')
        
        # Отправляем обновление всем подключенным клиентам
        socketio.emit('status_update', serialize_bot_status())

# Запуск фонового потока для обновления статуса
def start_status_updater():
    """Запускает фоновый поток для обновления статуса"""
    thread = threading.Thread(target=update_bot_status, daemon=True)
    thread.start()

if __name__ == '__main__':
    # Инициализируем время запуска
    bot_status['start_time'] = datetime.now()
    bot_status['is_running'] = True
    
    # Запускаем обновление статуса
    start_status_updater()
    
    # Запускаем веб-приложение
    print("🌐 Веб-приложение для администрирования бота запущено!")
    print("📊 Дашборд доступен по адресу: http://localhost:5001")
    print("🔧 API доступен по адресу: http://localhost:5001/api/")
    
    # Получаем порт из переменных окружения (для Railway)
    port = int(os.getenv('PORT', 5001))
    
    # Запускаем в продакшн режиме на Railway
    socketio.run(app, host='0.0.0.0', port=port, debug=False) 