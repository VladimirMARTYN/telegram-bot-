#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import asyncio
import ipaddress
import re
import shutil
import time as time_module
from datetime import datetime, time, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, ApplicationHandlerStop, CallbackQueryHandler, CommandHandler,
    ContextTypes, JobQueue, MessageHandler, TypeHandler, filters,
)
import json
import http_compat  # Configure the Python 3.9 parser before importing aiohttp.
import aiohttp
import threading
from typing import Optional
from storage import data_path, read_json, write_json, migrate_to_data_dir
from quotes import resolve_currency_rates
from alerts import new_alert_state, observe_prices
from telegram_text import split_html

# Импорты конфигурации и утилит
from config import (
    BOT_TOKEN, ADMIN_USER_ID, DEFAULT_THRESHOLD, PRICE_CHECK_INTERVAL,
    DEFAULT_DAILY_TIME, DEFAULT_TIMEZONE, CACHE_TTL_CURRENCIES,
    CACHE_TTL_CRYPTO, CACHE_TTL_STOCKS, CACHE_TTL_COMMODITIES, CACHE_TTL_INDICES,
    SUPPORTED_CURRENCIES, SUPPORTED_CRYPTO, SUPPORTED_STOCKS,
    FALLBACK_USD_RUB_RATE, PING_TARGETS, TINVEST_API_TOKEN,
)
from utils import (
    is_admin, get_cached_data, fetch_with_retry, validate_positive_number,
    validate_asset, escape_html, format_price, clear_cache,
    save_last_known_rate, get_last_known_rate, positive_price, finite_number,
    is_estimated_quote, parse_timestamp
)
from data_sources import (
    get_cbr_rates, get_forex_rates, get_crypto_data, get_moex_stocks,
    get_commodities_data, get_indices_data
)

# Настройка логирования (должна быть перед импортом reportlab)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


class _SecretRedactionFilter(logging.Filter):
    """Не допускать попадания API-токенов в логи."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for secret in (BOT_TOKEN, TINVEST_API_TOKEN):
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


for log_handler in logging.getLogger().handlers:
    log_handler.addFilter(_SecretRedactionFilter())

# HTTP request URLs Telegram содержат токен бота в path.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Безопасный импорт reportlab (может отсутствовать)
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
    logger.info("✅ ReportLab доступен для PDF экспорта")
except ImportError:
    REPORTLAB_AVAILABLE = False
    # Создаем заглушки для типов
    letter = A4 = None
    SimpleDocTemplate = Paragraph = Spacer = Table = TableStyle = None
    getSampleStyleSheet = ParagraphStyle = None
    inch = None
    colors = None
    canvas = None
    logger.warning("⚠️ ReportLab недоступен - PDF экспорт отключен")

import io

# Безопасный импорт schedule (может отсутствовать)
try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False

# Логирование уже настроено выше

# Предупреждение о недоступности schedule
if not SCHEDULE_AVAILABLE:
    logger.warning("⚠️ Модуль 'schedule' не установлен. Альтернативная система задач будет использовать только Timer")

# Глобальная переменная для системы задач
GLOBAL_JOB_QUEUE = None
_data_file_lock = threading.RLock()

# Глобальная сессия aiohttp для переиспользования
_http_session: aiohttp.ClientSession = None

async def get_http_session() -> aiohttp.ClientSession:
    """Получить или создать глобальную HTTP сессию"""
    global _http_session
    import asyncio
    
    # Проверяем, что event loop активен (в async функции он всегда активен)
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        # Если event loop не запущен, это ошибка - мы должны быть в async контексте
        raise RuntimeError("get_http_session() должна вызываться из async функции")
    
    # Проверяем, нужно ли пересоздать сессию
    need_new_session = False
    
    if _http_session is None:
        need_new_session = True
    elif _http_session.closed:
        need_new_session = True
    else:
        # Проверяем, что сессия привязана к текущему event loop
        try:
            session_loop = _http_session._loop
            if session_loop is None or session_loop.is_closed() or session_loop != current_loop:
                need_new_session = True
        except (AttributeError, RuntimeError):
            # Если не можем проверить loop, пересоздаем сессию
            need_new_session = True
    
    if need_new_session:
        # Закрываем старую сессию, если она есть
        if _http_session is not None and not _http_session.closed:
            try:
                await _http_session.close()
            except Exception:
                pass
        
        # Создаем новую сессию - она автоматически использует текущий event loop
        _http_session = aiohttp.ClientSession()
    
    return _http_session

# Функция для получения московского времени
def get_moscow_time():
    """Возвращает текущее время в московском часовом поясе"""
    moscow_tz = pytz.timezone(DEFAULT_TIMEZONE)
    return datetime.now(moscow_tz)

# Старые функции удалены - используются функции из data_sources.py

# Время запуска бота
bot_start_time = get_moscow_time()

LTI_SBER_QUANTITY = 12_344
LTI_SBER_INITIAL_PRICE = 275.40
LTI_FIXATION_DATE = "31.07.2026"
LTI_FIXATION_VALUE = 3_400_000
LTI_PAYMENT_SCHEDULE = (
    ("31.07.2027", 3_086),
    ("31.07.2028", 3_086),
    ("31.07.2029", 6_172),
)
STOCK_NAMES = {
    'SBER': 'Сбер', 'YDEX': 'Яндекс', 'VKCO': 'ВК',
    'T': 'Т-Технологии', 'GAZP': 'Газпром', 'GMKN': 'Норникель',
    'ROSN': 'Роснефть', 'LKOH': 'ЛУКОЙЛ', 'MTSS': 'МТС',
    'PIKK': 'ПИК', 'SMLT': 'Самолёт', 'TGLD': 'TGLD',
    'TOFZ': 'TOFZ', 'DOMRF': 'ДОМ.РФ'
}
DAILY_STOCK_TICKERS = ['SBER', 'VKCO', 'DOMRF', 'T']
DETAIL_STOCK_TICKERS = [
    'YDEX', 'GAZP', 'GMKN', 'ROSN', 'LKOH', 'MTSS', 'TGLD', 'TOFZ'
]
REAL_ESTATE_TICKERS = ['PIKK', 'SMLT']
COMMODITY_ITEMS = ['gold', 'silver', 'brent', 'urals']
COMMODITY_NAMES = {
    'gold': 'Золото',
    'silver': 'Серебро',
    'brent': 'Нефть Brent',
    'urals': 'Нефть Urals',
}
INDEX_NAMES = {'imoex': 'IMOEX', 'sp500': 'S&P 500'}

# Данные пользователей (в памяти)
user_data = {}


def _atomic_write_json(file_path: str, data) -> None:
    write_json(file_path, data)

def load_user_data():
    """Загрузить данные пользователей из файла"""
    global user_data
    try:
        with _data_file_lock:
            if data_path('user_data.json').exists():
                with data_path('user_data.json').open('r', encoding='utf-8') as f:
                    raw_data = json.load(f)

                user_data = {}
                for key, value in raw_data.items():
                    try:
                        user_data[int(key)] = value
                    except (TypeError, ValueError):
                        logger.warning(f"Пропущен некорректный user_id в user_data.json: {key}")
                logger.info(f"📊 Загружено пользователей: {len(user_data)}")
            else:
                user_data = {}
                logger.info("📊 Файл пользователей не найден, создаю новый")
    except Exception as e:
        logger.error(f"Ошибка загрузки пользователей: {e}")
        user_data = {}

def save_user_data():
    """Сохранить данные пользователей в файл"""
    try:
        with _data_file_lock:
            serializable_data = {str(k): v for k, v in user_data.items()}
            _atomic_write_json('user_data.json', serializable_data)
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователей: {e}")


async def private_access_guard(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Остановить обработку любых updates не от владельца бота."""
    user = update.effective_user
    if user is not None and is_admin(user.id):
        return

    user_id = getattr(user, 'id', None)
    logger.warning("Заблокирован update от пользователя %s", user_id)
    raise ApplicationHandlerStop


# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    
    # Регистрируем пользователя
    if user_id not in user_data:
        user_data[user_id] = {
            'name': user.first_name,
            'username': user.username,
            'first_seen': get_moscow_time().isoformat(),
            'last_activity': get_moscow_time().isoformat()
        }
        logger.info(f"👤 Новый пользователь: {user.first_name} (ID: {user_id})")
        save_user_data()
    else:
        # Обновляем время последней активности
        user_data[user_id]['last_activity'] = get_moscow_time().isoformat()
        save_user_data()
    
    welcome_text = (
        f"👋 <b>Привет, {escape_html(user.first_name)}!</b>\n\n"
        f"🤖 <b>Вас приветствует бот-финансист с актуальными данными!</b>\n"
        f"Пожалуйста, ознакомьтесь:\n\n"
        f"📋 <b>Основные команды:</b>\n"
        f"/start - Главное меню\n"
        f"/help - Справка\n"
        f"/ping [IP[:PORT] ...] - Проверка задержки до серверов\n"
        f"/rates - Курсы валют, криптовалют и акций\n\n"
        f"🔔 <b>Уведомления:</b>\n"
        f"/subscribe - Подписаться на уведомления о резких изменениях\n"
        f"/unsubscribe - Отписаться от уведомлений\n"
        f"/set_alert - Установить пороговые алерты\n"
        f"/view_alerts - Посмотреть активные алерты\n\n"
        f"👤 <b>Статус:</b> Пользователь\n"
        f"📊 <b>Пользователей:</b> {len(user_data)}"
    )
    
    # Создаем клавиатуру с основными кнопками
    keyboard = [
        [InlineKeyboardButton("📊 Курсы валют", callback_data="rates")],
        [InlineKeyboardButton("🔔 Подписаться на уведомления", callback_data="subscribe")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(welcome_text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    daily_time = escape_html(load_bot_settings().get('daily_summary_time', DEFAULT_DAILY_TIME))
    help_text = (
        "🤖 <b>Справка по боту-финансисту</b>\n\n"
        "💱 <b>Основные функции:</b>\n"
        "• Курсы валют, криптовалют и акций\n"
        "• Товары (нефть Brent/Urals, золото, серебро)\n"
        "• Фондовые индексы\n"
        "• Уведомления о резких изменениях\n"
        "• Пороговые алерты\n"
        f"• Ежедневная сводка в {daily_time} МСК\n\n"
        "📋 <b>Команды:</b>\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n"
        "/ping [IP[:PORT] ...] - Проверка задержки до серверов\n"
        "/rates - Показать все курсы\n\n"
        "🔔 <b>Уведомления:</b>\n"
        "/subscribe - Подписаться на уведомления\n"
        "/unsubscribe - Отписаться\n"
        "/set_alert - Пороговые алерты\n"
        "/view_alerts - Посмотреть настройки\n\n"
    )
    
    # Добавляем админские команды только для администратора
    if is_admin(update.effective_user.id):
        help_text += (
            "🔧 <b>Админские команды:</b>\n"
            "/settings - Меню настроек бота\n"
            "/export_pdf - Экспорт отчета в PDF\n"
            "/test_daily - Тестовая ежедневная сводка\n"
            "/check_subscribers - Статус подписчиков\n"
            "/set_daily_time HH:MM - Настроить время сводки\n"
            "/get_daily_settings - Посмотреть настройки\n"
            "/restart_daily_job - Перезапустить задачу сводки\n\n"
        )
    
    help_text += (
        "🔄 <b>Источники данных:</b>\n"
        "• ЦБ РФ - курсы валют\n"
        "• CoinGecko/Coinbase/Binance/CryptoCompare - криптовалюты (с резервными источниками)\n" 
        "• MOEX - российские акции и индексы\n"
        "• Gold-API.com - драгоценные металлы\n"
        "• EIA API - точные цены нефти\n"
        "• Alpha Vantage - фондовые индексы\n\n"
        f"💡 <b>Совет:</b> Выполните /subscribe чтобы получать ежедневную сводку в {daily_time} МСК!"
    )
    
    await update.message.reply_html(help_text)

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /ping"""
    ping_binary = shutil.which("ping")
    default_tcp_ports = (443, 80, 53)

    def parse_host_specs(args):
        """Парсит аргументы /ping в список {'host': ip, 'port': optional_int}."""
        if not args:
            return [{"host": host, "port": None} for host in PING_TARGETS], []

        normalized_args = [arg.strip() for arg in args if arg.strip()]
        specs = []
        errors = []

        # Спец-случай: /ping <IP> <PORT>
        if len(normalized_args) == 2:
            first, second = normalized_args
            if second.isdigit():
                try:
                    ipaddress.ip_address(first)
                    port_value = int(second)
                    if not 1 <= port_value <= 65535:
                        errors.append(f"{first}:{second} (порт вне диапазона 1-65535)")
                    else:
                        return [{"host": first, "port": port_value}], []
                except ValueError:
                    pass

        for raw_item in normalized_args:
            try:
                ipaddress.ip_address(raw_item)
                specs.append({'host': raw_item, 'port': None})
                continue
            except ValueError:
                pass
            if ":" in raw_item:
                host_part, port_part = raw_item.rsplit(":", 1)
                host_part = host_part.strip().strip("[]")
                port_part = port_part.strip()
                try:
                    ipaddress.ip_address(host_part)
                except ValueError:
                    errors.append(f"{raw_item} (невалидный IP)")
                    continue
                if not port_part.isdigit():
                    errors.append(f"{raw_item} (порт должен быть числом)")
                    continue
                port_value = int(port_part)
                if not 1 <= port_value <= 65535:
                    errors.append(f"{raw_item} (порт вне диапазона 1-65535)")
                    continue
                specs.append({"host": host_part, "port": port_value})
                continue

            try:
                ipaddress.ip_address(raw_item)
                specs.append({"host": raw_item, "port": None})
            except ValueError:
                errors.append(f"{raw_item} (невалидный IP)")

        return specs, errors

    async def tcp_probe_port_once(host: str, port: int, timeout_seconds: int = 2):
        started = time_module.perf_counter()
        try:
            open_conn = asyncio.open_connection(host, port)
            _, writer = await asyncio.wait_for(open_conn, timeout=timeout_seconds)
            latency_ms = (time_module.perf_counter() - started) * 1000
            writer.close()
            await writer.wait_closed()
            return latency_ms, ""
        except Exception as exc:
            return None, f"{type(exc).__name__}: {exc}"

    async def ping_host(host: str, port: Optional[int], count: int = 4, timeout_seconds: int = 2) -> dict:
        result = {
            "host": host,
            "ok": False,
            "packet_loss": "100",
            "min_ms": None,
            "avg_ms": None,
            "max_ms": None,
            "raw_error": "",
            "mode": "tcp_fallback",
            "probe_port": port,
            "checked_ports": []
        }

        if ping_binary and port is None:
            cmd = [
                ping_binary,
                "-c", str(count),
                "-W", str(timeout_seconds),
                host
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), count * (timeout_seconds + 1) + 2)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                result['raw_error'] = 'таймаут ICMP'
                return result
            output = (stdout or b"").decode("utf-8", errors="ignore")
            error_text = (stderr or b"").decode("utf-8", errors="ignore").strip()

            packet_loss_match = re.search(r"([0-9]+(?:\.[0-9]+)?)% packet loss", output)
            rtt_match = re.search(
                r"(?:rtt|round-trip) min/avg/max(?:/(?:mdev|stddev))? = "
                r"([0-9]+(?:\.[0-9]+)?)/([0-9]+(?:\.[0-9]+)?)/([0-9]+(?:\.[0-9]+)?)/([0-9]+(?:\.[0-9]+)?) ms",
                output
            )

            result["mode"] = "icmp"
            result["ok"] = process.returncode == 0
            result["packet_loss"] = packet_loss_match.group(1) if packet_loss_match else "100"
            result["raw_error"] = error_text

            if rtt_match:
                result["min_ms"] = rtt_match.group(1)
                result["avg_ms"] = rtt_match.group(2)
                result["max_ms"] = rtt_match.group(3)
            return result

        ports_to_try = [port] if port is not None else list(default_tcp_ports)
        result["checked_ports"] = ports_to_try
        latencies = []
        failures = 0
        used_port = port
        last_error = ""

        for _ in range(count):
            sample_latency = None
            for candidate_port in ports_to_try:
                latency_ms, err = await tcp_probe_port_once(
                    host=host,
                    port=candidate_port,
                    timeout_seconds=timeout_seconds
                )
                if latency_ms is not None:
                    sample_latency = latency_ms
                    if used_port is None:
                        used_port = candidate_port
                    break
                if err:
                    last_error = err

            if sample_latency is None:
                failures += 1
            else:
                latencies.append(sample_latency)

        loss = (failures / count) * 100
        result["packet_loss"] = f"{loss:.1f}".rstrip("0").rstrip(".")
        result["ok"] = len(latencies) > 0
        result["raw_error"] = last_error
        if used_port is not None:
            result["probe_port"] = used_port

        if latencies:
            result["min_ms"] = f"{min(latencies):.2f}"
            result["avg_ms"] = f"{(sum(latencies) / len(latencies)):.2f}"
            result["max_ms"] = f"{max(latencies):.2f}"

        return result

    current_time = get_moscow_time().strftime("%d.%m.%Y %H:%M:%S")
    host_specs, parse_errors = parse_host_specs(context.args)

    if parse_errors:
        await update.message.reply_text(
            "❌ Ошибки в аргументах:\n" + "\n".join(f"• {err}" for err in parse_errors) + "\n\n"
            "Использование:\n"
            "/ping\n"
            "/ping 1.1.1.1 8.8.8.8\n"
            "/ping 77.221.148.155:22\n"
            "/ping 77.221.148.155 22"
        )
        return

    if not host_specs:
        await update.message.reply_text("❌ Не задано ни одного сервера для проверки.")
        return

    if len(host_specs) > 10:
        await update.message.reply_text("❌ Можно проверить не более 10 серверов за один вызов.")
        return

    await update.message.reply_text(f"📡 Проверяю {len(host_specs)} сервер(а)...")
    ping_results = await asyncio.gather(
        *(ping_host(item["host"], item["port"]) for item in host_specs),
        return_exceptions=True
    )

    lines = [f"🏓 <b>Ping report</b> ({current_time})"]
    if not ping_binary:
        lines.append("ℹ️ Системный ping недоступен, использую TCP‑проверку.")

    for spec, item in zip(host_specs, ping_results):
        host = spec["host"]
        if isinstance(item, Exception):
            lines.append(f"• <code>{host}</code>: ❌ ошибка ({escape_html(str(item))})")
            continue

        loss = item["packet_loss"]
        port_hint = ""
        if item.get("probe_port") is not None and item["mode"] != "icmp":
            port_hint = f", port {item['probe_port']}"
        elif item.get("checked_ports") and item["mode"] != "icmp":
            checked = ",".join(str(p) for p in item["checked_ports"])
            port_hint = f", ports {checked}"

        if item["avg_ms"] is not None:
            status = "✅" if float(loss) < 100 else "⚠️"
            lines.append(
                f"• <code>{host}</code>: {status} avg {item['avg_ms']} ms "
                f"(min {item['min_ms']}, max {item['max_ms']}), loss {loss}%{port_hint}"
            )
        else:
            err = escape_html(item["raw_error"] or "таймаут/недоступен")
            lines.append(f"• <code>{host}</code>: ❌ недоступен, loss {loss}%{port_hint} ({err})")

    lines.append("\n💡 Использование: <code>/ping 1.1.1.1 8.8.8.8</code>")
    lines.append("💡 С портом: <code>/ping 77.221.148.155:22</code> или <code>/ping 77.221.148.155 22</code>")
    await update.message.reply_html("\n".join(lines))


def _format_delta_html(price_history, asset_key, current_price):
    """Форматировать изменение относительно последней сохраненной цены."""
    if not positive_price(current_price):
        return ""
    previous_price = price_history.get(asset_key)
    if not positive_price(previous_price):
        return ""
    change_pct = ((current_price - previous_price) / previous_price) * 100
    return f" (Δ {change_pct:+.2f}% от последнего)"


def _quote_note_html(quote):
    notes = []
    if is_estimated_quote(quote):
        notes.append('расчётная оценка')
    if quote.get('note'):
        notes.append(str(quote['note']))
    as_of = quote.get('as_of')
    timestamp = parse_timestamp(as_of) if as_of else None
    if isinstance(as_of, str) and len(as_of) == 10:
        notes.append(as_of)
    elif timestamp:
        notes.append(timestamp.astimezone(pytz.timezone(DEFAULT_TIMEZONE)).strftime('%d.%m %H:%M'))
    return f" <i>({escape_html('; '.join(notes))})</i>" if notes else ''


def _format_stock_html(ticker, stocks_data, price_history):
    name = STOCK_NAMES[ticker]
    stock = stocks_data.get(ticker, {})
    price = stock.get('price')
    if not positive_price(price):
        note = stock.get('note') or "Данные временно недоступны"
        return f"• 🔴 {escape_html(name)}: <b>{escape_html(note)}</b>"

    change_pct = stock.get('change_pct')
    is_live = stock.get('is_live')
    status_icon = "🟢" if is_live else "🟡"
    change_str = ""
    if finite_number(change_pct) and change_pct != 0:
        change_str = f" ({change_pct:+.2f}% к предыдущему закрытию)"
    delta_str = _format_delta_html(price_history, ticker, price)
    return (
        f"• {status_icon} {escape_html(name)}: <b>{format_price(price)} ₽</b>"
        f"{change_str}{delta_str}{_quote_note_html(stock)}"
    )


def _format_commodity_html(commodity, commodities_data, usd_to_rub_rate, price_history):
    name = COMMODITY_NAMES[commodity]
    item = commodities_data.get(commodity, {})
    price = item.get('price')
    if not positive_price(price):
        return f"• {escape_html(name)}: <b>Н/Д</b>"

    rub_price = price * usd_to_rub_rate if usd_to_rub_rate > 0 else None
    delta_str = '' if is_estimated_quote(item) else _format_delta_html(price_history, commodity, price)
    note = _quote_note_html(item)
    if rub_price is not None:
        return (
            f"• {escape_html(name)}: <b>${format_price(price)}</b> "
            f"({format_price(rub_price)} ₽){delta_str}{note}"
        )
    return f"• {escape_html(name)}: <b>${format_price(price)}</b>{delta_str}{note}"


def _format_index_html(index, indices_data, price_history):
    item = indices_data.get(index, {})
    name = item.get('name') or INDEX_NAMES[index]
    price = item.get('price')
    if not positive_price(price):
        return f"• 🔴 {escape_html(name)}: <b>Данные временно недоступны</b>"

    is_live = item.get('is_live')
    change = item.get('change_pct')
    change_period = "к предыдущему закрытию"
    change_str = ""
    if finite_number(change) and change != 0:
        change_str = f" ({change:+.2f}% {change_period})"
    note_str = _quote_note_html(item)
    delta_str = '' if is_estimated_quote(item) else _format_delta_html(price_history, index, price)
    status_icon = "🟢" if is_live else "🟡"
    return (
        f"• {status_icon} {escape_html(name)}: <b>{format_price(price)}</b>"
        f"{change_str}{note_str}{delta_str}"
    )


def build_rates_message(
    usd_str,
    eur_str,
    cny_str,
    usd_to_rub_rate,
    crypto_strings,
    stocks_data,
    commodities_data,
    indices_data,
    price_history,
    current_time,
    conversion_note="",
    source_dates="",
):
    """Собрать компактный DAILY и нативный сворачиваемый блок Telegram."""
    daily_lines = [
        "📊 <b>DAILY</b>",
        "",
        "🏛️ <b>ВАЛЮТЫ</b>",
        f"• USD: <b>{escape_html(usd_str)}</b>",
        f"• EUR: <b>{escape_html(eur_str)}</b>",
        "",
        "💎 <b>КРИПТОВАЛЮТЫ</b>",
        f"• {escape_html(crypto_strings.get('bitcoin', 'Bitcoin: Н/Д'))}",
        f"• {escape_html(crypto_strings.get('the-open-network', 'TON: Н/Д'))}",
        f"• {escape_html(crypto_strings.get('tether', 'USDT: Н/Д'))}",
        "",
        "📈 <b>РОССИЙСКИЕ АКЦИИ</b>",
    ]
    daily_lines.extend(
        _format_stock_html(ticker, stocks_data, price_history)
        for ticker in DAILY_STOCK_TICKERS
    )

    sber_price = stocks_data.get('SBER', {}).get('price')
    lti_quantity = f"{LTI_SBER_QUANTITY:,}".replace(",", " ")
    daily_lines.extend([
        "",
        "💼 <b>Портфель LTI</b>",
        (
            f"Фиксация {LTI_FIXATION_DATE}: "
            f"{lti_quantity} акций, "
            f"{format_price(LTI_SBER_INITIAL_PRICE)} рублей/акция, "
            f"{format_price(LTI_FIXATION_VALUE, 0)} рублей"
        ),
    ])
    if positive_price(sber_price):
        lti_value = sber_price * LTI_SBER_QUANTITY
        lti_change = lti_value - LTI_FIXATION_VALUE
        lti_change_pct = (lti_change / LTI_FIXATION_VALUE) * 100
        signed_change = f"{lti_change:+,.2f}".replace(",", " ")
        daily_lines.extend(
            f"Выплата {payment_date}: "
            f"{format_price(quantity * sber_price)} рублей"
            for payment_date, quantity in LTI_PAYMENT_SCHEDULE
        )
        daily_lines.extend([
            "",
            f"Текущая цена акции: <b><i>{format_price(sber_price)} рублей</i></b>",
            f"Текущий общий объём: {format_price(lti_value)} рублей",
            (
                f"Изменение: <b><i>{signed_change} рублей "
                f"({lti_change_pct:+.2f}%)</i></b>"
            ),
        ])
    else:
        daily_lines.extend(
            f"Выплата {payment_date}: <b>Н/Д</b>"
            for payment_date, _quantity in LTI_PAYMENT_SCHEDULE
        )
        daily_lines.extend([
            "",
            "Текущая цена акции: <b><i>Н/Д</i></b>",
            "Текущий общий объём: <b>Н/Д</b>",
            "Изменение: <b><i>Н/Д</i></b>",
        ])

    daily_lines.extend(["", "🛠️ <b>ТОВАРЫ</b>"])
    daily_lines.extend(
        _format_commodity_html(
            commodity, commodities_data, usd_to_rub_rate, price_history
        )
        for commodity in COMMODITY_ITEMS
    )
    daily_lines.extend([
        "",
        "📊 <b>ИНДЕКСЫ</b>",
        _format_index_html('imoex', indices_data, price_history),
    ])

    detail_lines = [
        "🏛️ <b>ДРУГИЕ ВАЛЮТЫ</b>",
        f"• CNY: <b>{escape_html(cny_str)}</b>",
        "",
        "💎 <b>ДРУГИЕ КРИПТОВАЛЮТЫ</b>",
        f"• {escape_html(crypto_strings.get('solana', 'Solana: Н/Д'))}",
        "",
        "📈 <b>ДРУГИЕ РОССИЙСКИЕ АКЦИИ</b>",
    ]
    detail_lines.extend(
        _format_stock_html(ticker, stocks_data, price_history)
        for ticker in DETAIL_STOCK_TICKERS
    )
    detail_lines.extend(["", "🏠 <b>НЕДВИЖИМОСТЬ</b>"])
    detail_lines.extend(
        _format_stock_html(ticker, stocks_data, price_history)
        for ticker in REAL_ESTATE_TICKERS
    )
    detail_lines.extend([
        "",
        "📊 <b>ДРУГИЕ ИНДЕКСЫ</b>",
        _format_index_html('sp500', indices_data, price_history),
    ])

    detail_text = "\n".join(detail_lines)
    message = "\n".join(daily_lines)
    message += "\n\n🔎 <b>ПОДРОБНЕЕ</b>\n"
    message += f"<blockquote expandable>{detail_text}</blockquote>"
    if conversion_note:
        message += f"\n\n⚠️ {escape_html(conversion_note)}"
    if source_dates:
        message += f"\nДаты валют: {escape_html(source_dates)}"
    message += f"\n\n🕐 <b>Время:</b> {escape_html(current_time)}"
    message += (
        "\n📡 <b>Источники:</b> ЦБ РФ, CoinGecko/Coinbase/Binance, "
        "Т-Инвестиции API, MOEX, Gold-API, EIA, Alpha Vantage"
    )
    return message

async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Получить полные курсы валют, криптовалют, акций, товаров и индексов"""
    reply_target = update.effective_message
    status_message = None
    if reply_target is None:
        logger.error("rates_command: отсутствует message в update")
        return False

    try:
        status_message = await reply_target.reply_text("📊 Получаю информацию")
        
        session = await get_http_session()
        
        # Получаем все данные параллельно с кэшированием
        async def fetch_cbr():
            async def _fetch():
                return await get_cbr_rates(session)
            return await get_cached_data('cbr_rates', _fetch, CACHE_TTL_CURRENCIES)
        
        async def fetch_forex():
            async def _fetch():
                return await get_forex_rates(session)
            return await get_cached_data('forex_rates', _fetch, CACHE_TTL_CURRENCIES)
        
        async def fetch_crypto():
            async def _fetch():
                return await get_crypto_data(session)
            return await get_cached_data('crypto_data', _fetch, CACHE_TTL_CRYPTO)
        
        async def fetch_stocks():
            async def _fetch():
                return await get_moex_stocks(session)
            return await get_cached_data('moex_stocks', _fetch, CACHE_TTL_STOCKS)
        
        async def fetch_commodities():
            async def _fetch():
                return await get_commodities_data(session)
            return await get_cached_data('commodities', _fetch, CACHE_TTL_COMMODITIES)
        
        async def fetch_indices():
            async def _fetch():
                return await get_indices_data(session)
            return await get_cached_data('indices', _fetch, CACHE_TTL_INDICES)
        
        # Параллельный запрос всех данных
        cbr_data, forex_data, crypto_data, stocks_data, commodities_data, indices_data = await asyncio.gather(
            fetch_cbr(), fetch_forex(), fetch_crypto(), fetch_stocks(), fetch_commodities(), fetch_indices(),
            return_exceptions=True
        )
        
        fx = resolve_currency_rates(cbr_data, forex_data)
        usd_str, eur_str, cny_str = (fx['strings'][key] for key in ('USD', 'EUR', 'CNY'))
        usd_to_rub_rate = fx['usd_to_rub_rate']

        # Загружаем историю цен для динамики
        price_history = load_price_history()
        
        # Обработка криптовалют
        if isinstance(crypto_data, Exception):
            logger.error(f"Ошибка получения криптовалют: {crypto_data}")
            crypto_data = {}
        
        # Форматируем криптовалютные цены (доллары + рубли)
        crypto_strings = {}
        crypto_list = [
            {'id': 'bitcoin', 'name': 'Bitcoin', 'decimals': 0},
            {'id': 'the-open-network', 'name': 'TON', 'decimals': 2},
            {'id': 'solana', 'name': 'Solana', 'decimals': 2},
            {'id': 'tether', 'name': 'USDT', 'decimals': 2}
        ]
        
        for crypto in crypto_list:
            crypto_id = crypto['id']
            crypto_name = crypto['name']
            decimals = crypto['decimals']
            
            info = crypto_data.get(crypto_id, {}) if isinstance(crypto_data, dict) else {}
            if not isinstance(info, dict) or not positive_price(info.get('price')):
                crypto_strings[crypto_id] = f'{crypto_name}: Н/Д'
                continue
            price = info['price']
            change = info.get('change_24h')
            source = info.get('source', '')
            currency = info.get('currency', 'USD')
            amount = f'${format_price(price, decimals)}' if currency == 'USD' else f'{format_price(price, decimals)} {currency}'
            rub = f' ({format_price(price * usd_to_rub_rate, decimals)} ₽)' if usd_to_rub_rate > 0 and currency == 'USD' else ''
            change_str = f' ({change:+.2f}% за 24ч)' if finite_number(change) else ''
            source_str = f' [{source}]' if source and source != 'CoinGecko' else ''
            crypto_strings[crypto_id] = f'{crypto_name}: {amount}{rub}{change_str}{source_str}'

        # Обработка акций
        if isinstance(stocks_data, Exception):
            logger.error(f"Ошибка получения акций: {stocks_data}")
            stocks_data = {}
        
        # Обработка товаров
        if isinstance(commodities_data, Exception):
            logger.error(f"Ошибка получения товаров: {commodities_data}")
            commodities_data = {}
        
        # Обработка индексов
        if isinstance(indices_data, Exception):
            logger.error(f"Ошибка получения индексов: {indices_data}")
            indices_data = {}

        stocks_data, commodities_data, indices_data = [
            {key: quote for key, quote in payload.items() if isinstance(quote, dict)}
            if isinstance(payload, dict) else {}
            for payload in (stocks_data, commodities_data, indices_data)
        ]
        
        stock_items = list(STOCK_NAMES.keys())
        commodity_items = COMMODITY_ITEMS
        index_items = ['imoex', 'sp500']

        current_time = get_moscow_time().strftime("%d.%m.%Y %H:%M")
        message = build_rates_message(
            usd_str=usd_str,
            eur_str=eur_str,
            cny_str=cny_str,
            usd_to_rub_rate=usd_to_rub_rate,
            crypto_strings=crypto_strings,
            stocks_data=stocks_data,
            commodities_data=commodities_data,
            indices_data=indices_data,
            price_history=price_history,
            current_time=current_time,
            conversion_note=fx["conversion_note"], source_dates=fx["source_dates"],
        )
        
        # Обновляем историю цен для динамики (чтобы дельты появлялись в /rates)
        try:
            history_update = {}
            for ticker in stock_items:
                price = stocks_data.get(ticker, {}).get('price')
                if positive_price(price):
                    history_update[ticker] = price
            for commodity in commodity_items:
                if commodity in commodities_data:
                    price = commodities_data[commodity].get('price')
                    if positive_price(price) and not is_estimated_quote(commodities_data[commodity]):
                        history_update[commodity] = price
            for index in index_items:
                if index in indices_data:
                    price = indices_data[index].get('price')
                    if positive_price(price) and not is_estimated_quote(indices_data[index]):
                        history_update[index] = price
            if history_update:
                price_history.update(history_update)
                save_price_history(price_history)
        except Exception as e:
            logger.error(f"Ошибка обновления истории цен в /rates: {e}")
        
        parts = split_html(message)
        await status_message.edit_text(parts[0], parse_mode='HTML')
        for part in parts[1:]:
            await reply_target.reply_text(part, parse_mode='HTML')
        return True
        
    except Exception as e:
        logger.error(f"Общая ошибка в rates_command: {e}")
        import traceback
        logger.error(f"Трассировка ошибки: {traceback.format_exc()}")
        error_message = (
            f"❌ Ошибка получения курсов: {str(e)}\n\n"
            "🔄 Попробуйте позже или обратитесь к администратору."
        )
        if status_message is not None:
            await status_message.edit_text(error_message)
        else:
            await reply_target.reply_text(error_message)
        return False

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка всех остальных сообщений"""
    message_text = update.message.text
    user_id = update.effective_user.id
    
    # Обновляем активность пользователя
    if user_id in user_data:
        user_data[user_id]['last_activity'] = get_moscow_time().isoformat()
        save_user_data()
    
    # Если пользователь ввел только "/", показываем команды
    if message_text == "/":
        await command_suggestions(update, context)
        return
    
    # Для других сообщений - стандартная обработка
    await update.message.reply_text(
        "🤖 Я не понимаю эту команду. Используйте /help для списка доступных команд."
    )

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    target = update.effective_message
    try:
        notifications = load_notification_data()
        settings = load_bot_settings()
        prefs = notifications.setdefault(user_id, {
            'threshold': DEFAULT_THRESHOLD, 'alerts': {}, 'daily_summary': True,
        })
        prefs['subscribed'] = True
        save_notification_data(notifications)
    except (OSError, ValueError, TypeError) as exc:
        logger.error('Не удалось сохранить подписку: %s', exc)
        await target.reply_text('❌ Не удалось сохранить подписку. Попробуйте позже.')
        return
    when = escape_html(settings.get('daily_summary_time', DEFAULT_DAILY_TIME))
    await target.reply_html(
        f'✅ <b>Подписка активирована!</b>\n\n'
        f'Ежедневная сводка: {when} МСК.\n'
        'Пороговые алерты: /set_alert\nНастройки: /view_alerts\nОтписка: /unsubscribe'
    )


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    target = update.effective_message
    try:
        notifications = load_notification_data()
        if user_id in notifications:
            notifications[user_id]['subscribed'] = False
            save_notification_data(notifications)
    except (OSError, ValueError, TypeError) as exc:
        logger.error('Не удалось сохранить отписку: %s', exc)
        await target.reply_text('❌ Не удалось сохранить отписку. Попробуйте позже.')
        return
    await target.reply_html('🔕 <b>Подписка отключена.</b> Для включения: /subscribe')


async def set_alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Установить пороговые алерты"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_html(
            "⚙️ <b>Установка пороговых алертов</b>\n\n"
            "📝 Примеры использования:\n"
            "• <code>/set_alert USD 85</code> - доллар выше 85₽\n"
            "• <code>/set_alert BTC 115000</code> - биткоин выше 115K$\n"
            "• <code>/set_alert SBER 200</code> - Сбер выше 200₽\n\n"
            "💡 Поддерживаемые активы:\n"
            "• Валюты: USD, EUR, CNY\n"
            "• Криптовалюты: BTC, TON, SOL, USDT\n"
            "• Акции: SBER, YDEX, VKCO, T, GAZP, GMKN, ROSN, LKOH, MTSS, PIKK, SMLT, TGLD, TOFZ, DOMRF"
        )
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажите актив и пороговое значение")
        return
    
    asset = escape_html(context.args[0].upper())
    
    # Валидация актива
    if not validate_asset(asset):
        await update.message.reply_html(
            f"❌ <b>Неподдерживаемый актив:</b> {asset}\n\n"
            f"💡 Поддерживаемые активы:\n"
            f"• Валюты: {', '.join(SUPPORTED_CURRENCIES)}\n"
            f"• Криптовалюты: {', '.join(SUPPORTED_CRYPTO)}\n"
            f"• Акции: {', '.join(SUPPORTED_STOCKS)}"
        )
        return
    
    # Валидация порогового значения
    try:
        threshold = validate_positive_number(context.args[1])
    except ValueError as e:
        await update.message.reply_text(f"❌ {str(e)}")
        return
    
    notifications = load_notification_data()
    if str(user_id) not in notifications:
        notifications[str(user_id)] = {
            'subscribed': True,
            'threshold': DEFAULT_THRESHOLD,
            'alerts': {},
            'daily_summary': True
        }
    
    notifications[str(user_id)]['alerts'][asset] = threshold
    try:
        save_notification_data(notifications)
    except (OSError, ValueError) as exc:
        logger.error('Не удалось сохранить алерт: %s', exc)
        await update.effective_message.reply_text('❌ Не удалось сохранить алерт. Попробуйте позже.')
        return
    
    await update.message.reply_html(
        f"✅ <b>Алерт установлен!</b>\n\n"
        f"🎯 <b>Актив:</b> {asset}\n"
        f"📊 <b>Порог:</b> {threshold}\n\n"
        f"🔔 Вы получите уведомление при достижении этого значения"
    )

async def view_alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Посмотреть активные алерты"""
    user_id = update.effective_user.id
    notifications = load_notification_data()
    
    if str(user_id) not in notifications:
        await update.message.reply_html(
            "❌ У вас нет настроенных уведомлений.\n"
            "Используйте /subscribe для подписки."
        )
        return
    
    user_notifications = notifications[str(user_id)]
    
    status = "🔔 Включены" if user_notifications.get('subscribed', False) else "🔕 Отключены"
    threshold = user_notifications.get('threshold', 2.0)
    daily = "✅ Да" if user_notifications.get('daily_summary', False) else "❌ Нет"
    
    alerts_text = ""
    alerts = user_notifications.get('alerts', {})
    if alerts:
        alerts_text = "\n\n📊 <b>Пороговые алерты:</b>\n"
        for asset, value in alerts.items():
            alerts_text += f"• {asset}: {value}\n"
    else:
        alerts_text = "\n\n📊 <b>Пороговые алерты:</b> не установлены"
    
    message = (
        f"⚙️ <b>Ваши настройки уведомлений</b>\n\n"
        f"🔔 <b>Статус:</b> {status}\n"
        f"📈 <b>Порог изменений:</b> {threshold}%\n"
        f"🌅 <b>Ежедневная сводка:</b> {daily}"
        f"{alerts_text}"
    )
    
    await update.message.reply_html(message)

async def test_daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Тестовая команда для проверки ежедневной сводки (только для админа)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return
    
    await update.message.reply_text("🧪 Запускаю тестовую ежедневную сводку...")
    
    try:
        # Добавляем тестового подписчика если нет подписчиков
        notifications = load_notification_data()
        if not notifications:
            logger.info("📝 Создаю тестового подписчика для проверки...")
            notifications[str(user_id)] = {
                'subscribed': True,
                'daily_summary': True,
                'price_alerts': True,
                'alerts': {}
            }
            save_notification_data(notifications)
            await update.message.reply_text("✅ Добавлен тестовый подписчик")
        
        # Вызываем функцию ежедневной сводки вручную
        await daily_summary_job(context)
        await update.message.reply_text("✅ Тестовая ежедневная сводка завершена! Проверьте логи.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при выполнении тестовой сводки: {e}")
        logger.error(f"Ошибка тестовой ежедневной сводки: {e}")

async def check_subscribers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверить статус подписчиков (только для админа)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return
    
    try:
        notifications = load_notification_data()
        
        if not notifications:
            await update.message.reply_html(
                "📋 **СТАТУС ПОДПИСОК**\n\n"
                "❌ Нет подписчиков\n\n"
                "💡 Чтобы подписаться на ежедневную сводку, используйте /subscribe"
            )
            return
        
        message = "📋 **СТАТУС ПОДПИСОК**\n\n"
        
        total_users = len(notifications)
        active_subscribers = 0
        daily_summary_subscribers = 0
        
        for uid, data in notifications.items():
            if data.get('subscribed', False):
                active_subscribers += 1
            if data.get('daily_summary', True) and data.get('subscribed', False):
                daily_summary_subscribers += 1
        
        message += f"👥 **Всего пользователей:** {total_users}\n"
        message += f"🔔 **Активных подписчиков:** {active_subscribers}\n"
        message += f"🌅 **Подписано на ежедневную сводку:** {daily_summary_subscribers}\n\n"
        
        if daily_summary_subscribers > 0:
            message += "👤 **Детали подписчиков:**\n"
            for uid, data in notifications.items():
                if data.get('subscribed', False) and data.get('daily_summary', True):
                    alerts_count = len(data.get('alerts', {}))
                    threshold = data.get('threshold', 2.0)
                    message += f"├ ID: {uid}\n"
                    message += f"├ Порог: {threshold}%\n"
                    message += f"└ Алертов: {alerts_count}\n\n"
        
        # Проверяем наличие файла
        import os
        file_exists = data_path(NOTIFICATION_DATA_FILE).exists()
        message += f"💾 **Файл данных:** {'✅ Существует' if file_exists else '❌ Отсутствует'}\n"
        
        if file_exists:
            file_size = os.path.getsize(NOTIFICATION_DATA_FILE)
            message += f"📏 **Размер файла:** {file_size} байт"
        
        await update.message.reply_html(message)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка проверки подписчиков: {e}")
        logger.error(f"Ошибка check_subscribers: {e}")

# Старые функции get_commodities_data и get_indices_data удалены - используются из data_sources.py

# Файлы данных
NOTIFICATION_DATA_FILE = 'notifications.json'
PRICE_HISTORY_FILE = 'price_history.json'
SETTINGS_FILE = 'bot_settings.json'

ALERT_STATE_FILE = 'alert_state.json'
_price_check_lock = None


def load_notification_data():
    return read_json(NOTIFICATION_DATA_FILE)


def save_notification_data(data):
    _atomic_write_json(NOTIFICATION_DATA_FILE, data)


def load_price_history():
    try:
        return read_json(PRICE_HISTORY_FILE)
    except (OSError, ValueError) as exc:
        logger.error('Ошибка чтения истории отображения: %s', exc)
        return {}


def save_price_history(data):
    _atomic_write_json(PRICE_HISTORY_FILE, data)


def load_bot_settings():
    return read_json(SETTINGS_FILE, {
        'daily_summary_time': DEFAULT_DAILY_TIME, 'timezone': DEFAULT_TIMEZONE,
    })


def save_bot_settings(settings):
    _atomic_write_json(SETTINGS_FILE, settings)


def validate_time_format(time_str):
    """Проверить корректность формата времени HH:MM"""
    try:
        parts = time_str.split(':')
        if len(parts) != 2:
            return False
        
        hour = int(parts[0])
        minute = int(parts[1])
        
        if not (0 <= hour <= 23):
            return False
        if not (0 <= minute <= 59):
            return False
            
        return True
    except (ValueError, AttributeError):
        return False

# Старые функции удалены - перенесены в data_sources.py

# Функции проверки изменений и отправки уведомлений
async def check_price_changes(context: ContextTypes.DEFAULT_TYPE):
    """Persist observations and alert events before attempting delivery."""
    global _price_check_lock
    if _price_check_lock is None:
        _price_check_lock = asyncio.Lock()
    async with _price_check_lock:
        try:
            session = await get_http_session()
            async def fetch(key, function, ttl):
                return await get_cached_data(key, lambda: function(session), ttl)
            values = await asyncio.gather(
                fetch('cbr_rates', get_cbr_rates, CACHE_TTL_CURRENCIES),
                fetch('crypto_data', get_crypto_data, CACHE_TTL_CRYPTO),
                fetch('moex_stocks', get_moex_stocks, CACHE_TTL_STOCKS),
                fetch('commodities', get_commodities_data, CACHE_TTL_COMMODITIES),
                return_exceptions=True,
            )
            cbr, crypto, stocks, commodities = [value if isinstance(value, dict) else {} for value in values]
            quotes = {}
            for symbol in SUPPORTED_CURRENCIES:
                info = (cbr.get('Valute') or {}).get(symbol) or {}
                value, nominal = info.get('Value'), info.get('Nominal', 1)
                if positive_price(value) and positive_price(nominal):
                    quotes[symbol] = {'price': value / nominal, 'currency': 'RUB',
                                      'source': 'CBR', 'as_of': cbr.get('Date')}
            for coin, symbol in {'bitcoin': 'BTC', 'the-open-network': 'TON', 'solana': 'SOL', 'tether': 'USDT'}.items():
                if isinstance(crypto.get(coin), dict):
                    quotes[symbol] = dict(crypto[coin], currency=crypto[coin].get('currency', 'USD'))
            quotes.update({ticker: dict(value, currency='RUB') for ticker, value in stocks.items() if isinstance(value, dict)})
            quotes.update({key: value for key, value in commodities.items() if isinstance(value, dict)})
            notifications = load_notification_data()
            subscribers = {user_id: prefs for user_id, prefs in notifications.items() if is_admin(user_id)}
            state = read_json(ALERT_STATE_FILE, new_alert_state(load_price_history()))
            observe_prices(state, quotes, subscribers, DEFAULT_THRESHOLD)
            write_json(ALERT_STATE_FILE, state)
            # Keep events until a successful Telegram acknowledgement. IDs identify possible
            # duplicate deliveries when a network timeout hides a successful send.
            for user_id, events in list(state['pending'].items()):
                while events:
                    current_prefs = load_notification_data().get(user_id, {})
                    if not current_prefs.get('subscribed'):
                        state['pending'].pop(user_id, None)
                        write_json(ALERT_STATE_FILE, state)
                        break
                    event = events[0]
                    created = parse_timestamp(event['created_at'])
                    when = created.astimezone(pytz.timezone(DEFAULT_TIMEZONE)).strftime('%d.%m %H:%M')
                    text = (f'🔔 <b>УВЕДОМЛЕНИЕ О ЦЕНЕ</b>\n\n{event["text"]}\n'
                            f'Зафиксировано: {when} МСК · #{event["id"]}')
                    try:
                        await context.bot.send_message(chat_id=int(user_id), text=text, parse_mode='HTML')
                    except Exception as exc:
                        logger.error('Уведомление %s не доставлено, сохранено для повторной отправки: %s', event['id'], exc)
                        break
                    events.pop(0)
                    write_json(ALERT_STATE_FILE, state)
        except Exception as exc:
            logger.error('Ошибка проверки изменений цен: %s', exc)


async def daily_summary_job(context: ContextTypes.DEFAULT_TYPE):
    """Отправить ежедневную сводку в 9:00 МСК"""
    logger.info("🌅 Запуск ежедневной сводки...")
    
    try:
        notifications = load_notification_data()
        logger.info(f"📋 Загружено уведомлений: {len(notifications)}")
        
        if not notifications:
            logger.warning("⚠️ Нет подписчиков для ежедневной сводки")
            return
        
        # Подсчитываем активных подписчиков
        active_subscribers = 0
        for user_id, user_notifications in notifications.items():
            if not is_admin(user_id):
                continue
            if not user_notifications.get('subscribed', False):
                continue
            if not user_notifications.get('daily_summary', True):
                continue
            active_subscribers += 1
        
        logger.info(f"📊 Активных подписчиков на ежедневную сводку: {active_subscribers}")
        
        if active_subscribers == 0:
            logger.warning("⚠️ Нет активных подписчиков на ежедневную сводку")
            return
            
        # Получаем актуальные курсы для сводки
        logger.info("📡 Получаю данные для ежедневной сводки...")
        
        delivered = 0
        for user_id, user_notifications in notifications.items():
            if not is_admin(user_id):
                continue
            if not user_notifications.get('subscribed', False):
                continue
            if not user_notifications.get('daily_summary', True):
                continue
            
            try:
                logger.info(f"📤 Отправляю сводку пользователю {user_id}")
                
                # Отправляем заголовок
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text="🌅 **ЕЖЕДНЕВНАЯ СВОДКА**\n\n📊 Получаю актуальные курсы финансовых инструментов...",
                    parse_mode='Markdown'
                )
                
                # Создаем fake Update для вызова rates_command.
                # rates_command использует update.effective_message.reply_text(...)
                class FakeMessage:
                    def __init__(self, chat_id):
                        self.chat_id = chat_id

                    async def reply_text(self, text, parse_mode=None):
                        return await context.bot.send_message(
                            chat_id=self.chat_id,
                            text=text,
                            parse_mode=parse_mode
                        )

                class FakeUpdate:
                    def __init__(self, user_id):
                        self.effective_user = type('obj', (object,), {'id': user_id})
                        self.effective_message = FakeMessage(user_id)
                
                fake_update = FakeUpdate(int(user_id))
                
                # Вызываем rates_command для получения полной сводки
                success = await rates_command(fake_update, context)
                if success:
                    delivered += 1
                    logger.info(f"✅ Сводка отправлена пользователю {user_id}")
                else:
                    logger.error(f"Сводка пользователю {user_id} не сформирована")
                
            except Exception as e:
                logger.error(f"❌ Ошибка отправки ежедневной сводки пользователю {user_id}: {e}")
        
        logger.info(f"🎉 Ежедневная сводка завершена. Отправлено {delivered} из {active_subscribers} пользователям")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка ежедневной сводки: {e}")
        import traceback
        logger.error(f"📋 Трассировка: {traceback.format_exc()}")

async def set_daily_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Настроить время ежедневной сводки (только для админа)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return
    
    # Проверяем аргументы
    if not context.args:
        await update.message.reply_html(
            "⏰ <b>Настройка времени ежедневной сводки</b>\n\n"
            "<b>Использование:</b>\n"
            "/set_daily_time HH:MM\n\n"
            "<b>Примеры:</b>\n"
            "• /set_daily_time 09:00 - сводка в 9:00 МСК\n"
            "• /set_daily_time 21:30 - сводка в 21:30 МСК\n"
            "• /set_daily_time 06:15 - сводка в 6:15 МСК\n\n"
            "💡 Время указывается в московском часовом поясе"
        )
        return
    
    time_str = context.args[0]
    
    # Валидация формата времени
    if not validate_time_format(time_str):
        await update.message.reply_html(
            "❌ <b>Неверный формат времени!</b>\n\n"
            "Используйте формат <b>HH:MM</b> (24-часовой формат)\n"
            "Например: 09:00, 15:30, 21:45\n\n"
            "Часы: от 00 до 23\n"
            "Минуты: от 00 до 59"
        )
        return
    
    try:
        # Загружаем текущие настройки
        settings = load_bot_settings()
        old_time = settings.get('daily_summary_time', '09:00')
        
        # Обновляем время
        settings['daily_summary_time'] = time_str
        save_bot_settings(settings)
        
        # Пытаемся перезапустить задачу автоматически
        job_queue = get_job_queue(context)
        restart_success = False
        
        if job_queue:
            try:
                # Удаляем существующую задачу
                current_jobs = job_queue.get_jobs_by_name("daily_summary")
                if current_jobs:
                    for job in current_jobs:
                        job.schedule_removal()
                
                # Парсим новое время
                hour, minute = map(int, time_str.split(':'))
                moscow_tz = pytz.timezone('Europe/Moscow')
                daily_time = time(hour=hour, minute=minute, tzinfo=moscow_tz)
                
                # Создаем новую задачу
                job_queue.run_daily(
                    daily_summary_job,
                    time=daily_time,
                    name="daily_summary"
                )
                
                restart_success = True
                logger.info(f"🔄 Задача ежедневной сводки автоматически перезапущена на {time_str}")
                
            except Exception as restart_error:
                logger.error(f"❌ Ошибка автоматического перезапуска: {restart_error}")
        
        if restart_success:
            # Вычисляем время до следующего запуска
            from datetime import datetime
            moscow_tz = pytz.timezone('Europe/Moscow')
            current_moscow_time = datetime.now(moscow_tz)
            hour, minute = map(int, time_str.split(':'))
            next_run = current_moscow_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if current_moscow_time.hour > hour or (current_moscow_time.hour == hour and current_moscow_time.minute >= minute):
                next_run = next_run + timedelta(days=1)
            
            time_until = next_run - current_moscow_time
            hours_until = int(time_until.total_seconds() // 3600)
            minutes_until = int((time_until.total_seconds() % 3600) // 60)
            
            await update.message.reply_html(
                f"✅ <b>Время ежедневной сводки обновлено!</b>\n\n"
                f"🕐 <b>Было:</b> {old_time} МСК\n"
                f"🕐 <b>Стало:</b> {time_str} МСК\n\n"
                f"🔄 <b>Задача автоматически перезапущена!</b>\n"
                f"⏰ <b>До следующей сводки:</b> {hours_until}ч {minutes_until}мин\n"
                f"📊 <b>Следующая сводка:</b> {next_run.strftime('%H:%M %d.%m.%Y')}\n\n"
                f"🎉 Изменения вступили в силу немедленно!"
            )
        else:
            await update.message.reply_html(
                f"✅ <b>Время ежедневной сводки обновлено!</b>\n\n"
                f"🕐 <b>Было:</b> {old_time} МСК\n"
                f"🕐 <b>Стало:</b> {time_str} МСК\n\n"
                f"⚠️ <b>Внимание:</b> Не удалось автоматически перезапустить задачу.\n"
                f"🔄 Используйте /restart_daily_job или перезапустите бота на Railway."
            )
        
        logger.info(f"⏰ Админ {user_id} изменил время ежедневной сводки: {old_time} → {time_str}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при сохранении настроек: {e}")
        logger.error(f"Ошибка set_daily_time: {e}")

async def get_daily_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать текущие настройки ежедневной сводки (только для админа)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return
    
    try:
        settings = load_bot_settings()
        notifications = load_notification_data()
        
        # Подсчитываем подписчиков
        total_users = len(notifications)
        active_subscribers = 0
        daily_summary_subscribers = 0
        
        for uid, data in notifications.items():
            if data.get('subscribed', False):
                active_subscribers += 1
            if data.get('daily_summary', True) and data.get('subscribed', False):
                daily_summary_subscribers += 1
        
        # Получаем текущее московское время
        moscow_tz = pytz.timezone(settings.get('timezone', 'Europe/Moscow'))
        current_time = datetime.now(moscow_tz)
        
        # Вычисляем время до следующей сводки
        daily_time_str = settings.get('daily_summary_time', '09:00')
        hour, minute = map(int, daily_time_str.split(':'))
        
        next_run = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if current_time.hour > hour or (current_time.hour == hour and current_time.minute >= minute):
            # Если время уже прошло сегодня, планируем на завтра
            next_run = next_run + timedelta(days=1)
        
        time_until = next_run - current_time
        hours_until = int(time_until.total_seconds() // 3600)
        minutes_until = int((time_until.total_seconds() % 3600) // 60)
        
        message = (
            f"⚙️ <b>НАСТРОЙКИ ЕЖЕДНЕВНОЙ СВОДКИ</b>\n\n"
            f"🕐 <b>Время отправки:</b> {daily_time_str} МСК\n"
            f"🌍 <b>Часовой пояс:</b> {settings.get('timezone', 'Europe/Moscow')}\n"
            f"📅 <b>Текущее время:</b> {current_time.strftime('%H:%M:%S %d.%m.%Y')}\n\n"
            f"⏰ <b>До следующей сводки:</b> {hours_until}ч {minutes_until}мин\n"
            f"📊 <b>Следующая сводка:</b> {next_run.strftime('%H:%M %d.%m.%Y')}\n\n"
            f"👥 <b>СТАТИСТИКА ПОДПИСЧИКОВ:</b>\n"
            f"├ Всего пользователей: {total_users}\n"
            f"├ Активных подписчиков: {active_subscribers}\n"
            f"└ Подписано на сводку: {daily_summary_subscribers}\n\n"
            f"🔧 <b>Команды:</b>\n"
            f"• /set_daily_time HH:MM - изменить время\n"
            f"• /restart_daily_job - перезапустить задачу\n"
            f"• /test_daily - тестовый запуск\n"
            f"• /check_subscribers - детали подписчиков"
        )
        
        await update.message.reply_html(message)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка получения настроек: {e}")
        logger.error(f"Ошибка get_daily_settings: {e}")

async def restart_daily_job_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Перезапустить задачу ежедневной сводки с новыми настройками (только для админа)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return
    
    try:
        await update.message.reply_html("🔄 <b>Перезапускаю задачу ежедневной сводки...</b>")
        
        # Получаем job_queue из контекста или глобальной переменной
        job_queue = get_job_queue(context)
        if not job_queue:
            await update.message.reply_html("❌ Система задач недоступна")
            return
        
        logger.info(f"🔧 Используется система задач: {type(job_queue).__name__}")
        
        # Удаляем существующую задачу
        current_jobs = job_queue.get_jobs_by_name("daily_summary")
        if current_jobs:
            for job in current_jobs:
                job.schedule_removal()
            logger.info(f"🗑️ Удалено {len(current_jobs)} существующих задач ежедневной сводки")
        
        # Загружаем новые настройки
        settings = load_bot_settings()
        daily_time_str = settings.get('daily_summary_time', '09:00')
        timezone_str = settings.get('timezone', 'Europe/Moscow')
        
        # Парсим время из настроек
        hour, minute = map(int, daily_time_str.split(':'))
        moscow_tz = pytz.timezone(timezone_str)
        daily_time = time(hour=hour, minute=minute, tzinfo=moscow_tz)
        
        # Создаем новую задачу
        job_queue.run_daily(
            daily_summary_job,
            time=daily_time,
            name="daily_summary"
        )
        
        # Вычисляем время до следующего запуска
        from datetime import datetime
        current_moscow_time = datetime.now(moscow_tz)
        next_run = current_moscow_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if current_moscow_time.hour > hour or (current_moscow_time.hour == hour and current_moscow_time.minute >= minute):
            next_run = next_run + timedelta(days=1)
        
        time_until = next_run - current_moscow_time
        hours_until = int(time_until.total_seconds() // 3600)
        minutes_until = int((time_until.total_seconds() % 3600) // 60)
        
        await update.message.reply_html(
            f"✅ <b>Задача ежедневной сводки перезапущена!</b>\n\n"
            f"🕐 <b>Новое время:</b> {daily_time_str} МСК\n"
            f"📅 <b>Текущее время:</b> {current_moscow_time.strftime('%H:%M:%S')}\n"
            f"⏰ <b>До следующей сводки:</b> {hours_until}ч {minutes_until}мин\n"
            f"📊 <b>Следующая сводка:</b> {next_run.strftime('%H:%M %d.%m.%Y')}\n\n"
            f"🎉 Изменения вступили в силу немедленно!"
        )
        
        logger.info(f"🔄 Админ {user_id} перезапустил задачу ежедневной сводки на {daily_time_str}")
        
    except Exception as e:
        await update.message.reply_html(f"❌ <b>Ошибка перезапуска задачи:</b>\n{e}")
        logger.error(f"Ошибка restart_daily_job: {e}")

# Альтернативная реализация задач если JobQueue не работает
class AlternativeJob:
    """Эмуляция Job для совместимости"""
    
    def __init__(self, name, callback, job_queue):
        self.name = name
        self.callback = callback
        self.job_queue = job_queue
        self.removed = False
        logger.debug(f"🔧 Создана альтернативная задача: {name}")
    
    def schedule_removal(self):
        """Помечает задачу для удаления"""
        self.removed = True
        logger.info(f"🗑️ Альтернативная задача {self.name} помечена для удаления")

class AlternativeJobQueue:
    """Простая альтернативная реализация задач через threading"""
    
    def __init__(self, application):
        self.application = application
        # Constructed on the main thread, using the same loop as run_polling.
        self.loop = asyncio.get_event_loop()
        self.jobs = {}  # Словарь для хранения задач по именам
        self.running = False
        self.active_timers = {}  # Активные таймеры
        logger.info("🔄 Создана альтернативная система задач")
    
    def run_daily(self, callback, time, name):
        """Запустить ежедневную задачу"""
        import time as time_module
        
        # Удаляем существующую задачу с таким именем
        if name in self.jobs:
            old_job = self.jobs[name]
            old_job.schedule_removal()
            self._stop_timer(name)
        
        # Создаем новую задачу
        job = AlternativeJob(name, callback, self)
        self.jobs[name] = job
        
        time_str = time.strftime('%H:%M')
        logger.info(f"📅 Настраиваю альтернативную ежедневную задачу '{name}' на {time_str}")
        
        if SCHEDULE_AVAILABLE:
            # Удаляем предыдущие schedule задачи
            schedule.clear(name)
            
            # Используем schedule для ежедневных задач
            schedule.every().day.at(time_str, str(time.tzinfo or DEFAULT_TIMEZONE)).do(self._run_job, callback, name).tag(name)
            
            # Запускаем поток для выполнения задач
            if not self.running:
                self.running = True
                thread = threading.Thread(target=self._schedule_runner, daemon=True)
                thread.start()
                logger.info("✅ Альтернативный планировщик задач запущен (schedule)")
        else:
            # Используем простой Timer для ежедневных задач
            self._setup_timer_daily(callback, time, name)
            logger.info("✅ Альтернативный планировщик задач запущен (timer)")
    
    def run_repeating(self, callback, interval, first, name):
        """Запустить повторяющуюся задачу"""
        logger.info(f"⏰ Настраиваю альтернативную повторяющуюся задачу '{name}' каждые {interval}с")
        
        # Удаляем существующую задачу с таким именем
        if name in self.jobs:
            old_job = self.jobs[name]
            old_job.schedule_removal()
            self._stop_timer(name)
        
        # Создаем новую задачу
        job = AlternativeJob(name, callback, self)
        self.jobs[name] = job
        
        def run_job():
            self._run_job(callback, name)

        # Первый запуск
        timer = threading.Timer(first, run_job)
        timer.daemon = True
        timer.start()
        self.active_timers[name + "_first"] = timer
        
        # Повторяющиеся запуски
        def repeat_job():
            if name in self.jobs and not self.jobs[name].removed:
                run_job()
                if self.running and name in self.jobs and not self.jobs[name].removed:
                    timer = threading.Timer(interval, repeat_job)
                    timer.daemon = True
                    timer.start()
                    self.active_timers[name + "_repeat"] = timer
        
        # Запускаем повторяющиеся задачи после первого запуска
        repeat_timer = threading.Timer(first + interval, repeat_job)
        repeat_timer.daemon = True
        repeat_timer.start()
        self.active_timers[name + "_repeat_start"] = repeat_timer
    
    def _run_job(self, callback, name):
        """Выполнить задачу"""
        import asyncio
        try:
            # Проверяем, не была ли задача удалена
            if name in self.jobs and self.jobs[name].removed:
                logger.info(f"⏭️ Пропускаю выполнение удаленной задачи: {name}")
                return
                
            logger.info(f"▶️ Выполняю альтернативную задачу: {name}")
            
            # Создаем контекст для задачи
            context = type('obj', (object,), {
                'bot': self.application.bot,
                'job_queue': self
            })
            
            # Both HTTP clients stay on the main loop; a worker must not create
            # another loop or close the session used by commands and other jobs.
            if not self.loop.is_running():
                raise RuntimeError('Main event loop is not running')
            future = asyncio.run_coroutine_threadsafe(callback(context), self.loop)
            future.result()

            logger.info(f"✅ Альтернативная задача {name} выполнена")
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения альтернативной задачи {name}: {e}")
    
    def _setup_timer_daily(self, callback, target_time, name):
        """Настроить ежедневную задачу через Timer (без schedule)"""
        from datetime import datetime, timedelta
        import time as time_module
        
        def calculate_next_run():
            """Вычислить время до следующего запуска"""
            zone = target_time.tzinfo or pytz.timezone(DEFAULT_TIMEZONE)
            now = datetime.now(zone)
            
            # Парсим целевое время
            hour = target_time.hour
            minute = target_time.minute
            
            # Создаем время сегодня
            today_target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Если время уже прошло сегодня, планируем на завтра
            if now >= today_target:
                next_run = today_target + timedelta(days=1)
            else:
                next_run = today_target
            
            # Вычисляем секунды до запуска
            time_diff = next_run - now
            return time_diff.total_seconds(), next_run
        
        def run_and_reschedule():
            """Выполнить задачу и запланировать следующую"""
            try:
                # Проверяем, не была ли задача удалена
                if name in self.jobs and not self.jobs[name].removed:
                    self._run_job(callback, name)
            except Exception as e:
                logger.error(f"❌ Ошибка выполнения timer задачи {name}: {e}")
            
            # Планируем следующий запуск
            if self.running and name in self.jobs and not self.jobs[name].removed:
                seconds_until, next_run = calculate_next_run()
                logger.info(f"⏰ Следующий запуск задачи {name}: {next_run.strftime('%H:%M %d.%m.%Y')} (через {int(seconds_until/3600)}ч {int((seconds_until%3600)/60)}мин)")
                
                timer = threading.Timer(seconds_until, run_and_reschedule)
                timer.daemon = True
                timer.start()
                self.active_timers[name + "_daily"] = timer
        
        # Запускаем первую задачу
        seconds_until, next_run = calculate_next_run()
        logger.info(f"⏰ Первый запуск задачи {name}: {next_run.strftime('%H:%M %d.%m.%Y')} (через {int(seconds_until/3600)}ч {int((seconds_until%3600)/60)}мин)")
        
        timer = threading.Timer(seconds_until, run_and_reschedule)
        timer.daemon = True
        timer.start()
        self.active_timers[name + "_daily"] = timer
        
        self.running = True
    
    def _schedule_runner(self):
        """Запускает планировщик задач в отдельном потоке (только если schedule доступен)"""
        if not SCHEDULE_AVAILABLE:
            logger.error("❌ Попытка запустить schedule_runner без модуля schedule")
            return
            
        import time as time_module
        
        logger.info("🔄 Альтернативный планировщик задач запущен")
        while self.running:
            try:
                schedule.run_pending()
                time_module.sleep(60)  # Проверяем каждую минуту
            except Exception as e:
                logger.error(f"❌ Ошибка в планировщике задач: {e}")
                time_module.sleep(60)
    
    def get_jobs_by_name(self, name):
        """Получить задачи по имени"""
        if name in self.jobs and not self.jobs[name].removed:
            return [self.jobs[name]]
        return []

    def _stop_timer(self, name):
        """Остановить активные таймеры для задачи"""
        timers_to_remove = []
        for timer_name, timer in self.active_timers.items():
            if timer_name.startswith(name):
                try:
                    timer.cancel()
                    logger.debug(f"🛑 Остановлен таймер: {timer_name}")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка остановки таймера {timer_name}: {e}")
                timers_to_remove.append(timer_name)
        
        # Удаляем остановленные таймеры из словаря
        for timer_name in timers_to_remove:
            del self.active_timers[timer_name]

def get_job_queue(context=None):
    """Получить доступную систему задач"""
    global GLOBAL_JOB_QUEUE
    
    # Сначала пробуем получить из контекста
    if context and hasattr(context, 'job_queue') and context.job_queue:
        logger.debug("🔧 Используется job_queue из контекста")
        return context.job_queue
    
    # Если не получилось, используем глобальную
    if GLOBAL_JOB_QUEUE:
        logger.debug("🔧 Используется глобальная система задач")
        return GLOBAL_JOB_QUEUE
    
    logger.error("❌ Система задач недоступна")
    return None

def initialize_data_files():
    """Инициализировать файлы данных при первом запуске"""
    logger.info("🔧 Инициализация файлов данных...")
    
    migrate_to_data_dir([
        SETTINGS_FILE, NOTIFICATION_DATA_FILE, PRICE_HISTORY_FILE, ALERT_STATE_FILE,
        'last_known_rates.json', 'user_data.json',
    ])
    if not data_path(ALERT_STATE_FILE).exists():
        write_json(ALERT_STATE_FILE, new_alert_state(load_price_history()))

    # Инициализация настроек
    if not data_path(SETTINGS_FILE).exists():
        default_settings = {
            'daily_summary_time': '09:00',
            'timezone': 'Europe/Moscow'
        }
        save_bot_settings(default_settings)
        logger.info(f"✅ Создан файл настроек: {SETTINGS_FILE}")
    
    # Инициализация уведомлений
    if not data_path(NOTIFICATION_DATA_FILE).exists():
        default_notifications = {}
        save_notification_data(default_notifications)
        logger.info(f"✅ Создан файл уведомлений: {NOTIFICATION_DATA_FILE}")
    
    # Инициализация истории цен
    if not data_path(PRICE_HISTORY_FILE).exists():
        default_history = {}
        save_price_history(default_history)
        logger.info(f"✅ Создан файл истории цен: {PRICE_HISTORY_FILE}")
    
    logger.info("🎉 Инициализация файлов данных завершена")

def main() -> None:
    """Запуск бота - продвинутая версия с уведомлениями"""
    global GLOBAL_JOB_QUEUE
    
    logger.info("🚀 Запуск продвинутого финансового бота...")
    
    # Инициализируем файлы данных при первом запуске
    initialize_data_files()
    # Загружаем данные пользователей при старте
    load_user_data()
    
    # Создаем приложение с явно включенным JobQueue
    application = Application.builder().token(BOT_TOKEN).post_init(setup_bot_commands).build()
    
    # Проверяем доступность JobQueue и выводим детальную диагностику
    job_queue = application.job_queue
    logger.info(f"🔍 Диагностика JobQueue:")
    logger.info(f"   application.job_queue: {type(job_queue).__name__}")
    logger.info(f"   type: {type(job_queue)}")
    logger.info(f"   bool(job_queue): {bool(job_queue)}")
    
    if job_queue is None:
        logger.error("❌ JobQueue is None! Попробуем создать принудительно...")
        try:
            # Пробуем разные способы импорта JobQueue
            job_queue_created = False
            
            # Способ 1: прямой импорт
            try:
                from telegram.ext import JobQueue as TelegramJobQueue
                job_queue = TelegramJobQueue()
                application._job_queue = job_queue
                job_queue_created = True
                logger.info("✅ JobQueue создан (способ 1: прямой импорт)")
            except Exception as e1:
                logger.warning(f"⚠️ Способ 1 не сработал: {e1}")
            
            # Способ 2: через приватный модуль
            if not job_queue_created:
                try:
                    from telegram.ext._jobqueue import JobQueue as PrivateJobQueue
                    job_queue = PrivateJobQueue()
                    application._job_queue = job_queue
                    job_queue_created = True
                    logger.info("✅ JobQueue создан (способ 2: приватный модуль)")
                except Exception as e2:
                    logger.warning(f"⚠️ Способ 2 не сработал: {e2}")
            
            # Способ 3: через Application.builder()
            if not job_queue_created:
                try:
                    new_app = Application.builder().token(BOT_TOKEN).job_queue(None).build()
                    job_queue = new_app.job_queue
                    if job_queue:
                        application._job_queue = job_queue
                        job_queue_created = True
                        logger.info("✅ JobQueue создан (способ 3: через builder)")
                except Exception as e3:
                    logger.warning(f"⚠️ Способ 3 не сработал: {e3}")
            
            if not job_queue_created:
                logger.error("❌ Все способы создания JobQueue не сработали")
                logger.info("🔄 Переходим на альтернативную систему задач...")
                job_queue = AlternativeJobQueue(application)
                GLOBAL_JOB_QUEUE = job_queue
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при создании JobQueue: {e}")
            logger.info("🔄 Используем альтернативную систему задач как fallback...")
            job_queue = AlternativeJobQueue(application)
            GLOBAL_JOB_QUEUE = job_queue
    else:
        logger.info("✅ JobQueue инициализирован успешно")
        # Сохраняем успешную JobQueue в глобальную переменную
        GLOBAL_JOB_QUEUE = job_queue

    # JobQueue уже получен выше в диагностике

    # Глобальная проверка выполняется раньше обработчиков всех команд и кнопок.
    application.add_handler(TypeHandler(Update, private_access_guard), group=-1)

    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("rates", rates_command))
    
    # Команды уведомлений
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("set_alert", set_alert_command))
    application.add_handler(CommandHandler("view_alerts", view_alerts_command))
    application.add_handler(CommandHandler("test_daily", test_daily_command))
    application.add_handler(CommandHandler("check_subscribers", check_subscribers_command))
    application.add_handler(CommandHandler("set_daily_time", set_daily_time_command))
    application.add_handler(CommandHandler("get_daily_settings", get_daily_settings_command))
    application.add_handler(CommandHandler("restart_daily_job", restart_daily_job_command))
    
    # Новые команды
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("export_pdf", export_pdf_command))
    # Обработчик callback-запросов для меню настроек
    application.add_handler(CallbackQueryHandler(button_callback))

    # Обработчик всех текстовых сообщений (эхо)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    # Настройка периодических задач
    if job_queue:
        logger.info(f"🔧 Используется система задач: {type(job_queue).__name__}")
        # Проверка изменений цен каждые 30 минут
        job_queue.run_repeating(
            check_price_changes,
            interval=1800,  # 30 минут в секундах
            first=60,  # Первый запуск через 1 минуту
            name="price_changes_check"
        )
        logger.info("⏰ Настроена проверка изменений цен каждые 30 минут")
        
        # Ежедневная сводка - время из настроек
        settings = load_bot_settings()
        daily_time_str = settings.get('daily_summary_time', '09:00')
        timezone_str = settings.get('timezone', 'Europe/Moscow')
        
        try:
            # Парсим время из настроек
            hour, minute = map(int, daily_time_str.split(':'))
            moscow_tz = pytz.timezone(timezone_str)
            daily_time = time(hour=hour, minute=minute, tzinfo=moscow_tz)
            
            # Получаем текущее московское время для отладки
            from datetime import datetime
            current_moscow_time = datetime.now(moscow_tz)
            logger.info(f"🕐 Текущее московское время: {current_moscow_time.strftime('%H:%M:%S %d.%m.%Y')}")
            logger.info(f"📅 Настраиваю ежедневную сводку на: {daily_time_str} МСК (из настроек)")
            
            job_queue.run_daily(
                daily_summary_job,
                time=daily_time,
                name="daily_summary"
            )
            logger.info(f"✅ Ежедневная сводка в {daily_time_str} МСК настроена успешно")
            # Показываем сколько времени до следующего запуска
            next_run = current_moscow_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if current_moscow_time.hour > hour or (current_moscow_time.hour == hour and current_moscow_time.minute >= minute):
                next_run = next_run + timedelta(days=1)
            time_until = next_run - current_moscow_time
            hours_until = int(time_until.total_seconds() // 3600)
            minutes_until = int((time_until.total_seconds() % 3600) // 60)
            logger.info(f"⏰ До следующей ежедневной сводки: {hours_until}ч {minutes_until}мин")
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки времени ежедневной сводки: {e}")
            logger.info("🔄 Использую время по умолчанию: 09:00 МСК")
            
            # Fallback на время по умолчанию
            moscow_tz = pytz.timezone('Europe/Moscow')
            daily_time = time(hour=9, minute=0, tzinfo=moscow_tz)
            job_queue.run_daily(
                daily_summary_job,
                time=daily_time,
                name="daily_summary"
            )
            logger.info("✅ Ежедневная сводка в 09:00 МСК настроена (fallback)")
    else:
        logger.warning("⚠️ Система задач недоступна - уведомления отключены")
        logger.error("🚨 Критическая ошибка: job_queue не может быть None на этом этапе!")

    # Запуск бота
    logger.info("✅ Бот-финансист запущен и готов к работе")
    logger.info("📊 Доступные функции: курсы валют, криптовалют, акций, товаров, индексов")
    logger.info("🔔 Уведомления: резкие изменения, пороговые алерты, ежедневная сводка")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Меню настроек бота"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if not is_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только администратору.")
        return
    
    # Загружаем текущие настройки
    settings = load_bot_settings()
    notifications = load_notification_data()
    user_notifications = notifications.get(str(user_id), {})
    
    # Создаем клавиатуру с настройками
    keyboard = [
        [InlineKeyboardButton("⏰ Время сводки", callback_data="settings_time")],
        [InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications")],
        [InlineKeyboardButton("📋 Текущие настройки", callback_data="settings_current")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="settings_close")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем сообщение с текущими настройками
    current_time = settings.get('daily_summary_time', '09:00')
    timezone = settings.get('timezone', 'Europe/Moscow')
    is_subscribed = user_notifications.get('subscribed', False)
    threshold = user_notifications.get('threshold', 2.0)
    
    message = f"""
⚙️ **МЕНЮ НАСТРОЕК**

⏰ **Время ежедневной сводки:** {current_time} ({timezone})
🔔 **Подписка на уведомления:** {'✅ Включена' if is_subscribed else '❌ Отключена'}
📊 **Порог уведомлений:** {threshold}%

Выберите раздел для настройки:
"""
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки меню"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Обработка кнопок для всех пользователей
    if query.data == "rates":
        await rates_command(update, context)
        return
    elif query.data == "subscribe":
        await subscribe_command(update, context)
        return
    
    # Проверяем права администратора для админских функций
    if not is_admin(user_id):
        await query.edit_message_text("❌ Эта функция доступна только администратору.")
        return
    
    if query.data == "settings_close":
        await query.edit_message_text("✅ Меню настроек закрыто")
        return
    
    elif query.data == "settings_current":
        # Показываем текущие настройки
        settings = load_bot_settings()
        notifications = load_notification_data()
        user_notifications = notifications.get(str(user_id), {})
        
        current_time = settings.get('daily_summary_time', '09:00')
        timezone = settings.get('timezone', 'Europe/Moscow')
        is_subscribed = user_notifications.get('subscribed', False)
        threshold = user_notifications.get('threshold', 2.0)
        daily_summary = user_notifications.get('daily_summary', True)
        
        message = f"""
📋 **ТЕКУЩИЕ НАСТРОЙКИ**

⏰ **Время ежедневной сводки:** {current_time} ({timezone})
🔔 **Подписка на уведомления:** {'✅ Включена' if is_subscribed else '❌ Отключена'}
📊 **Порог уведомлений:** {threshold}%
📅 **Ежедневная сводка:** {'✅ Включена' if daily_summary else '❌ Отключена'}

Используйте /settings для изменения настроек
"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "settings_back":
        # Возвращаемся в главное меню настроек
        user_id = update.effective_user.id
        
        # Загружаем текущие настройки
        settings = load_bot_settings()
        notifications = load_notification_data()
        user_notifications = notifications.get(str(user_id), {})
        
        # Создаем клавиатуру с настройками
        keyboard = [
            [InlineKeyboardButton("⏰ Время сводки", callback_data="settings_time")],
            [InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications")],
            [InlineKeyboardButton("📋 Текущие настройки", callback_data="settings_current")],
            [InlineKeyboardButton("❌ Закрыть", callback_data="settings_close")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Формируем сообщение с текущими настройками
        current_time = settings.get('daily_summary_time', '09:00')
        timezone = settings.get('timezone', 'Europe/Moscow')
        is_subscribed = user_notifications.get('subscribed', False)
        threshold = user_notifications.get('threshold', 2.0)
        
        message = f"""
⚙️ **МЕНЮ НАСТРОЕК**

⏰ **Время ежедневной сводки:** {current_time} ({timezone})
🔔 **Подписка на уведомления:** {'✅ Включена' if is_subscribed else '❌ Отключена'}
📊 **Порог уведомлений:** {threshold}%

Выберите раздел для настройки:
"""
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "settings_time":
        message = """
⏰ **НАСТРОЙКА ВРЕМЕНИ СВОДКИ**

Используйте команду:
`/set_daily_time HH:MM`

Например:
• `/set_daily_time 09:00` - в 9 утра
• `/set_daily_time 18:30` - в 6:30 вечера

⚠️ Время указывается по Москве (UTC+3)
"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "settings_notifications":
        message = """
🔔 **НАСТРОЙКА УВЕДОМЛЕНИЙ**

Команды для управления:
• `/subscribe` - подписаться на уведомления
• `/unsubscribe` - отписаться от уведомлений
• `/set_alert АКТИВ ЦЕНА` - установить алерт

Примеры алертов:
• `/set_alert USD 85` - доллар выше 85₽
• `/set_alert BTC 115000` - биткоин выше 115K$
• `/set_alert SBER 200` - Сбер выше 200₽
"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "settings_favorites":
        message = """
⭐ **ИЗБРАННЫЕ АКТИВЫ**

Эта функция находится в разработке.

Планируется:
• Сохранение любимых активов
• Быстрый доступ к избранному
• Персональные дашборды
"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "settings_personal":
        message = """
📊 **ПЕРСОНАЛЬНЫЕ НАСТРОЙКИ**

Эта функция находится в разработке.

Планируется:
• Выбор предпочитаемых валют
• Настройка отображения данных
• Персональные портфели
• Языковые настройки
"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def export_pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Экспорт данных в PDF отчет"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if not is_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только администратору.")
        return
    
    # Проверяем доступность reportlab
    if not REPORTLAB_AVAILABLE:
        await update.message.reply_text(
            "❌ Функция экспорта PDF недоступна.\n\n"
            "Причина: библиотека reportlab не установлена.\n\n"
            "Для установки выполните:\n"
            "`pip install reportlab`"
        )
        return
    
    await update.message.reply_text("📊 Создаю PDF-отчёт...")
    try:
        from pdf_report import build_pdf_report
        session = await get_http_session()
        cbr, forex, crypto, stocks, commodities, indices = await asyncio.gather(
            get_cbr_rates(session), get_forex_rates(session), get_crypto_data(session),
            get_moex_stocks(session), get_commodities_data(session), get_indices_data(session),
            return_exceptions=True,
        )
        fx = resolve_currency_rates(cbr, forex)
        crypto, stocks, commodities, indices = [value if isinstance(value, dict) else {} for value in (crypto, stocks, commodities, indices)]
        current_time = get_moscow_time().strftime('%d.%m.%Y %H:%M')
        report = await asyncio.to_thread(build_pdf_report, fx, crypto, stocks, commodities, indices, current_time, list(STOCK_NAMES))
        await context.bot.send_document(
            chat_id=update.effective_chat.id, document=report,
            filename=f"financial_report_{current_time.replace(' ', '_').replace(':', '-')}.pdf",
            caption='📊 Финансовый отчёт: валюты, криптовалюты, акции, товары и индексы.',
        )
        await update.message.reply_text('✅ PDF-отчёт создан и отправлен.')
    except Exception as exc:
        logger.error('Ошибка создания PDF: %s', exc)
        await update.message.reply_text('❌ Не удалось создать или отправить PDF-отчёт. Попробуйте позже.')


async def setup_bot_commands(application):
    """Настройка команд бота для автодополнения в Telegram"""
    from telegram import BotCommand, BotCommandScopeChat

    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("help", "Справка по командам"),
        BotCommand("rates", "Курсы валют и индексы"),
    ]

    try:
        # У посторонних пользователей меню команд не отображается вообще.
        await application.bot.delete_my_commands()
        if ADMIN_USER_ID:
            await application.bot.set_my_commands(
                commands,
                scope=BotCommandScopeChat(chat_id=ADMIN_USER_ID),
            )
        logger.info("✅ Команды бота настроены для автодополнения")
    except Exception as e:
        logger.error(f"❌ Ошибка настройки команд: {e}")

async def command_suggestions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывать доступные команды при вводе '/'"""
    user_input = update.message.text
    
    if user_input == "/":
        # Список всех доступных команд
        commands = [
            "/start - Запустить бота",
            "/help - Справка по командам",
            "/rates - Курсы валют и индексы",
            "/ping [IP[:PORT] ...] - Ping до серверов",
            "/subscribe - Подписаться на уведомления",
            "/unsubscribe - Отписаться от уведомлений",
            "/set_alert - Установить алерт",
            "/view_alerts - Просмотр алертов",
            "/settings - Меню настроек",
            "/export_pdf - Экспорт в PDF"
        ]
        
        # Админские команды
        admin_commands = [
            "/set_daily_time - Установить время сводки",
            "/get_daily_settings - Настройки сводки",
            "/restart_daily_job - Перезапустить сводку",
            "/test_daily - Тест сводки",
            "/check_subscribers - Проверить подписчиков"
        ]
        
        message = "📋 **ДОСТУПНЫЕ КОМАНДЫ:**\n\n"
        
        for cmd in commands:
            message += f"• {cmd}\n"
        
        # Проверяем права администратора
        user_id = update.effective_user.id
        if is_admin(user_id):
            message += "\n🔧 **КОМАНДЫ АДМИНИСТРАТОРА:**\n\n"
            for cmd in admin_commands:
                message += f"• {cmd}\n"
        
        message += "\n💡 **Совет:** Введите команду полностью для выполнения"
        
        await update.message.reply_text(message, parse_mode='Markdown')

if __name__ == '__main__':
    main()
