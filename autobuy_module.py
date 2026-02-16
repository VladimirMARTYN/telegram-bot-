#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Отдельный модуль автопокупки SBER через T-Invest API.
Можно отключить/откатить модуль, убрав его импорт и команды из admin_bot.py.
"""

import json
import logging
import os
import threading
from datetime import datetime, time
from typing import Any, Dict, Optional
from uuid import uuid4

import aiohttp
import pytz
from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_USER_ID, API_TIMEOUT, DEFAULT_TIMEZONE, TINVEST_API_TOKEN
from utils import is_admin

logger = logging.getLogger(__name__)

AUTOBUY_SETTINGS_FILE = "autobuy_settings.json"
AUTOBUY_JOB_NAME = "autobuy_sber_daily"
SBER_FIGI = "BBG004730N88"
DEFAULT_AUTOBUY_TIME = "10:00"
DEFAULT_QUANTITY = 1
_TINVEST_REST_BASE = "https://invest-public-api.tinkoff.ru/rest"

_settings_lock = threading.RLock()
_get_job_queue_func = None


def configure_autobuy(get_job_queue_func) -> None:
    """Подключить функцию получения job_queue из основного приложения."""
    global _get_job_queue_func
    _get_job_queue_func = get_job_queue_func


def _atomic_write_json(file_path: str, data: Dict[str, Any]) -> None:
    temp_path = f"{file_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, file_path)


def _default_settings() -> Dict[str, Any]:
    return {
        "enabled": False,
        "ticker": "SBER",
        "figi": SBER_FIGI,
        "quantity": DEFAULT_QUANTITY,
        "daily_time": DEFAULT_AUTOBUY_TIME,
        "timezone": DEFAULT_TIMEZONE,
        "last_run_date": None,
        "last_order_id": None,
    }


def initialize_autobuy_settings() -> None:
    if not os.path.exists(AUTOBUY_SETTINGS_FILE):
        save_autobuy_settings(_default_settings())


def load_autobuy_settings() -> Dict[str, Any]:
    with _settings_lock:
        if not os.path.exists(AUTOBUY_SETTINGS_FILE):
            return _default_settings()
        try:
            with open(AUTOBUY_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения {AUTOBUY_SETTINGS_FILE}: {e}")
            return _default_settings()

    settings = _default_settings()
    settings.update(data if isinstance(data, dict) else {})
    return settings


def save_autobuy_settings(settings: Dict[str, Any]) -> None:
    with _settings_lock:
        _atomic_write_json(AUTOBUY_SETTINGS_FILE, settings)


def _validate_time_format(time_str: str) -> bool:
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            return False
        hour = int(parts[0])
        minute = int(parts[1])
        return 0 <= hour <= 23 and 0 <= minute <= 59
    except Exception:
        return False


def _resolve_job_queue(context: ContextTypes.DEFAULT_TYPE):
    if _get_job_queue_func:
        return _get_job_queue_func(context)
    return getattr(context, "job_queue", None)


async def _safe_json(resp: aiohttp.ClientResponse) -> Dict[str, Any]:
    try:
        return await resp.json()
    except aiohttp.client_exceptions.ContentTypeError:
        text = await resp.text(encoding="utf-8")
        return json.loads(text)


async def _get_primary_account_id(session: aiohttp.ClientSession, headers: Dict[str, str]) -> str:
    async with session.post(
        f"{_TINVEST_REST_BASE}/tinkoff.public.invest.api.contract.v1.UsersService/GetAccounts",
        headers=headers,
        json={},
        timeout=API_TIMEOUT,
    ) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise RuntimeError(f"GetAccounts failed ({resp.status}): {body[:300]}")
        data = await _safe_json(resp)

    accounts = data.get("accounts", [])
    if not accounts:
        raise RuntimeError("У брокера не найдено доступных счетов")

    # Предпочитаем открытый аккаунт.
    for account in accounts:
        status = str(account.get("status", ""))
        if status == "ACCOUNT_STATUS_OPEN":
            return account.get("id")

    return accounts[0].get("id")


async def place_market_buy_sber(quantity: int) -> Dict[str, Any]:
    if not TINVEST_API_TOKEN:
        raise RuntimeError("TINVEST_API_TOKEN не задан")

    qty = max(1, int(quantity))
    headers = {
        "Authorization": f"Bearer {TINVEST_API_TOKEN}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        account_id = await _get_primary_account_id(session, headers)
        payload = {
            "instrumentId": SBER_FIGI,
            "quantity": str(qty),
            "direction": "ORDER_DIRECTION_BUY",
            "accountId": account_id,
            "orderType": "ORDER_TYPE_MARKET",
            "orderId": str(uuid4()),
        }

        async with session.post(
            f"{_TINVEST_REST_BASE}/tinkoff.public.invest.api.contract.v1.OrdersService/PostOrder",
            headers=headers,
            json=payload,
            timeout=API_TIMEOUT,
        ) as resp:
            body = await _safe_json(resp)
            if resp.status != 200:
                raise RuntimeError(f"PostOrder failed ({resp.status}): {str(body)[:500]}")

    return {
        "account_id": account_id,
        "request_order_id": payload["orderId"],
        "response_order_id": body.get("orderId"),
        "execution_report_status": body.get("executionReportStatus"),
    }


def ensure_autobuy_job(job_queue) -> None:
    if not job_queue:
        return

    for job in job_queue.get_jobs_by_name(AUTOBUY_JOB_NAME):
        job.schedule_removal()

    settings = load_autobuy_settings()
    if not settings.get("enabled", False):
        return

    time_str = settings.get("daily_time", DEFAULT_AUTOBUY_TIME)
    if not _validate_time_format(time_str):
        logger.error(f"Некорректное время автопокупки: {time_str}")
        return

    tz_name = settings.get("timezone", DEFAULT_TIMEZONE)
    tz = pytz.timezone(tz_name)
    hour, minute = map(int, time_str.split(":"))
    run_time = time(hour=hour, minute=minute, tzinfo=tz)

    job_queue.run_daily(
        autobuy_job,
        time=run_time,
        name=AUTOBUY_JOB_NAME,
    )
    logger.info(f"✅ Автопокупка SBER запланирована на {time_str} ({tz_name})")


async def autobuy_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_autobuy_settings()
    if not settings.get("enabled", False):
        return

    tz = pytz.timezone(settings.get("timezone", DEFAULT_TIMEZONE))
    today_str = datetime.now(tz).date().isoformat()
    if settings.get("last_run_date") == today_str:
        logger.info("⏭️ Автопокупка уже выполнена сегодня, пропуск")
        return

    try:
        result = await place_market_buy_sber(settings.get("quantity", DEFAULT_QUANTITY))
        settings["last_run_date"] = today_str
        settings["last_order_id"] = result.get("response_order_id") or result.get("request_order_id")
        save_autobuy_settings(settings)

        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=(
                "✅ Автопокупка SBER выполнена\n"
                f"Количество: {settings.get('quantity', DEFAULT_QUANTITY)} шт\n"
                f"Order ID: {settings.get('last_order_id')}\n"
                f"Статус: {result.get('execution_report_status', 'N/A')}"
            ),
        )
    except Exception as e:
        logger.error(f"Ошибка автопокупки SBER: {e}")
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"❌ Ошибка автопокупки SBER: {e}",
            )
        except Exception:
            pass


async def autobuy_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return

    settings = load_autobuy_settings()
    time_str = context.args[0] if context.args else settings.get("daily_time", DEFAULT_AUTOBUY_TIME)
    if not _validate_time_format(time_str):
        await update.message.reply_text("❌ Неверный формат времени. Используйте HH:MM")
        return

    settings["enabled"] = True
    settings["daily_time"] = time_str
    settings["timezone"] = DEFAULT_TIMEZONE
    settings["ticker"] = "SBER"
    settings["figi"] = SBER_FIGI
    settings["quantity"] = DEFAULT_QUANTITY
    save_autobuy_settings(settings)

    job_queue = _resolve_job_queue(context)
    if job_queue:
        ensure_autobuy_job(job_queue)

    await update.message.reply_text(
        "✅ Автопокупка включена\n"
        f"Инструмент: SBER\n"
        f"Количество: {DEFAULT_QUANTITY} шт ежедневно\n"
        f"Время: {time_str} (Europe/Moscow)"
    )


async def autobuy_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return

    settings = load_autobuy_settings()
    settings["enabled"] = False
    save_autobuy_settings(settings)

    job_queue = _resolve_job_queue(context)
    if job_queue:
        for job in job_queue.get_jobs_by_name(AUTOBUY_JOB_NAME):
            job.schedule_removal()

    await update.message.reply_text("🛑 Автопокупка SBER отключена")


async def autobuy_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return

    settings = load_autobuy_settings()
    status = "🟢 Включена" if settings.get("enabled") else "🔴 Выключена"
    await update.message.reply_text(
        "📋 Статус автопокупки SBER\n"
        f"Статус: {status}\n"
        f"Время: {settings.get('daily_time', DEFAULT_AUTOBUY_TIME)} ({settings.get('timezone', DEFAULT_TIMEZONE)})\n"
        f"Количество: {settings.get('quantity', DEFAULT_QUANTITY)} шт\n"
        f"Последний запуск: {settings.get('last_run_date') or 'не выполнялся'}\n"
        f"Последний order_id: {settings.get('last_order_id') or 'нет'}"
    )
