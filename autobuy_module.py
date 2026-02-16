#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Отдельный модуль автопокупки акций через T-Invest API.
Все настройки меняются командами бота, без новых деплоев.
"""

import json
import logging
import os
import threading
from datetime import datetime, time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiohttp
import pytz
from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_USER_ID, API_TIMEOUT, DEFAULT_TIMEZONE, TINVEST_API_TOKEN
from utils import is_admin

logger = logging.getLogger(__name__)

AUTOBUY_SETTINGS_FILE = "autobuy_settings.json"
AUTOBUY_JOB_NAME = "autobuy_daily"
DEFAULT_AUTOBUY_TIME = "10:00"
DEFAULT_TIMEZONE_NAME = DEFAULT_TIMEZONE
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
        "positions": [{"ticker": "SBER", "qty": 1}],
        "daily_time": DEFAULT_AUTOBUY_TIME,
        "timezone": DEFAULT_TIMEZONE_NAME,
        "last_run_date": None,
        "last_results": [],
    }


def _normalize_settings(raw: Any) -> Dict[str, Any]:
    settings = _default_settings()
    if isinstance(raw, dict):
        settings.update(raw)

    # Миграция со старого формата (ticker/quantity).
    positions: List[Dict[str, Any]] = []

    if isinstance(settings.get("positions"), list):
        for item in settings["positions"]:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker", "")).upper().strip()
            qty_raw = item.get("qty", item.get("quantity", 1))
            try:
                qty = int(qty_raw)
            except Exception:
                continue
            if ticker and qty > 0:
                positions.append({"ticker": ticker, "qty": qty})

    if not positions:
        legacy_ticker = str(settings.get("ticker", "")).upper().strip()
        if legacy_ticker:
            try:
                legacy_qty = int(settings.get("quantity", 1))
            except Exception:
                legacy_qty = 1
            positions.append({"ticker": legacy_ticker, "qty": max(1, legacy_qty)})

    # Удаляем дубликаты по тикеру, оставляя последнее значение qty.
    dedup: Dict[str, int] = {}
    for pos in positions:
        dedup[pos["ticker"]] = pos["qty"]
    settings["positions"] = [{"ticker": t, "qty": q} for t, q in dedup.items()]

    # Валидация времени.
    time_str = str(settings.get("daily_time", DEFAULT_AUTOBUY_TIME))
    if not _validate_time_format(time_str):
        settings["daily_time"] = DEFAULT_AUTOBUY_TIME

    tz_name = str(settings.get("timezone", DEFAULT_TIMEZONE_NAME))
    try:
        pytz.timezone(tz_name)
        settings["timezone"] = tz_name
    except Exception:
        settings["timezone"] = DEFAULT_TIMEZONE_NAME

    return settings


def initialize_autobuy_settings() -> None:
    if not os.path.exists(AUTOBUY_SETTINGS_FILE):
        save_autobuy_settings(_default_settings())


def load_autobuy_settings() -> Dict[str, Any]:
    with _settings_lock:
        if not os.path.exists(AUTOBUY_SETTINGS_FILE):
            return _default_settings()
        try:
            with open(AUTOBUY_SETTINGS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения {AUTOBUY_SETTINGS_FILE}: {e}")
            return _default_settings()
    return _normalize_settings(raw)


def save_autobuy_settings(settings: Dict[str, Any]) -> None:
    with _settings_lock:
        normalized = _normalize_settings(settings)
        _atomic_write_json(AUTOBUY_SETTINGS_FILE, normalized)


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


def _money_to_float(value: Any) -> Optional[float]:
    if not isinstance(value, dict):
        return None
    units = value.get("units")
    nano = value.get("nano")
    if units is None:
        return None
    try:
        return float(units) + float(nano or 0) / 1_000_000_000
    except Exception:
        return None


def _format_rub(value: Optional[float]) -> str:
    if value is None:
        return "н/д"
    return f"{value:,.2f} ₽".replace(",", " ")


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

    for account in accounts:
        if str(account.get("status", "")) == "ACCOUNT_STATUS_OPEN":
            account_id = account.get("id")
            if account_id:
                return account_id

    account_id = accounts[0].get("id")
    if not account_id:
        raise RuntimeError("Не удалось определить ID счета")
    return account_id


async def _get_account_snapshot(
    session: aiohttp.ClientSession,
    headers: Dict[str, str],
    account_id: str,
) -> Dict[str, Optional[float]]:
    """Вернуть стоимость портфеля и денежный остаток счета."""
    portfolio_total: Optional[float] = None
    cash_total: Optional[float] = None

    # Общая стоимость портфеля.
    try:
        async with session.post(
            f"{_TINVEST_REST_BASE}/tinkoff.public.invest.api.contract.v1.OperationsService/GetPortfolio",
            headers=headers,
            json={"accountId": account_id},
            timeout=API_TIMEOUT,
        ) as resp:
            if resp.status == 200:
                data = await _safe_json(resp)
                portfolio = data.get("totalAmountPortfolio") or {}
                portfolio_total = _money_to_float(portfolio)
    except Exception as e:
        logger.warning(f"Не удалось получить портфель: {e}")

    # Денежные остатки по счету.
    try:
        async with session.post(
            f"{_TINVEST_REST_BASE}/tinkoff.public.invest.api.contract.v1.OperationsService/GetPositions",
            headers=headers,
            json={"accountId": account_id},
            timeout=API_TIMEOUT,
        ) as resp:
            if resp.status == 200:
                data = await _safe_json(resp)
                money_items = data.get("money", [])
                cash_total = 0.0
                has_any = False
                for money in money_items:
                    if str(money.get("currency", "")).upper() == "RUB":
                        val = _money_to_float(money)
                        if val is not None:
                            cash_total += val
                            has_any = True
                if not has_any:
                    cash_total = None
    except Exception as e:
        logger.warning(f"Не удалось получить денежные остатки: {e}")

    return {"portfolio_total": portfolio_total, "cash_total": cash_total}


async def _resolve_share_by_ticker(
    session: aiohttp.ClientSession,
    headers: Dict[str, str],
    ticker: str,
) -> Dict[str, str]:
    payload = {"query": ticker}
    async with session.post(
        f"{_TINVEST_REST_BASE}/tinkoff.public.invest.api.contract.v1.InstrumentsService/FindInstrument",
        headers=headers,
        json=payload,
        timeout=API_TIMEOUT,
    ) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise RuntimeError(f"FindInstrument failed ({resp.status}): {body[:300]}")
        data = await _safe_json(resp)

    instruments = data.get("instruments", [])
    if not instruments:
        raise RuntimeError(f"Инструмент {ticker} не найден")

    ticker_upper = ticker.upper()

    def is_share(item: Dict[str, Any]) -> bool:
        instrument_type = str(item.get("instrumentType", "")).lower()
        return "share" in instrument_type or "акц" in instrument_type

    exact = [i for i in instruments if str(i.get("ticker", "")).upper() == ticker_upper]
    candidates = exact if exact else instruments
    shares = [i for i in candidates if is_share(i)]
    if shares:
        candidates = shares

    tradable = [i for i in candidates if i.get("apiTradeAvailableFlag", True)]
    if tradable:
        candidates = tradable

    for item in candidates:
        figi = item.get("figi")
        if figi:
            return {
                "ticker": ticker_upper,
                "figi": figi,
                "name": item.get("name", ticker_upper),
            }

    raise RuntimeError(f"Для {ticker_upper} не найден FIGI для торгов")


async def _place_market_buy(
    session: aiohttp.ClientSession,
    headers: Dict[str, str],
    account_id: str,
    figi: str,
    qty: int,
) -> Dict[str, Any]:
    payload = {
        "instrumentId": figi,
        "quantity": str(max(1, int(qty))),
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

    if not settings.get("positions"):
        logger.warning("⚠️ Автопокупка включена, но список инструментов пуст")
        return

    time_str = settings.get("daily_time", DEFAULT_AUTOBUY_TIME)
    if not _validate_time_format(time_str):
        logger.error(f"Некорректное время автопокупки: {time_str}")
        return

    tz_name = settings.get("timezone", DEFAULT_TIMEZONE_NAME)
    tz = pytz.timezone(tz_name)
    hour, minute = map(int, time_str.split(":"))
    run_time = time(hour=hour, minute=minute, tzinfo=tz)

    job_queue.run_daily(
        autobuy_job,
        time=run_time,
        name=AUTOBUY_JOB_NAME,
    )
    logger.info(f"✅ Автопокупка запланирована на {time_str} ({tz_name})")


async def autobuy_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_autobuy_settings()
    if not settings.get("enabled", False):
        return

    positions = settings.get("positions", [])
    if not positions:
        logger.info("⏭️ Автопокупка включена, но нет инструментов")
        return

    tz = pytz.timezone(settings.get("timezone", DEFAULT_TIMEZONE_NAME))
    today_str = datetime.now(tz).date().isoformat()
    if settings.get("last_run_date") == today_str:
        logger.info("⏭️ Автопокупка уже выполнена сегодня, пропуск")
        return

    if not TINVEST_API_TOKEN:
        err = "TINVEST_API_TOKEN не задан"
        logger.error(err)
        await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"❌ Ошибка автопокупки: {err}")
        return

    headers = {
        "Authorization": f"Bearer {TINVEST_API_TOKEN}",
        "Content-Type": "application/json",
    }

    results: List[Dict[str, Any]] = []

    try:
        async with aiohttp.ClientSession() as session:
            account_id = await _get_primary_account_id(session, headers)

            for pos in positions:
                ticker = str(pos.get("ticker", "")).upper().strip()
                qty = int(pos.get("qty", 1))
                if not ticker or qty <= 0:
                    continue

                try:
                    instrument = await _resolve_share_by_ticker(session, headers, ticker)
                    order_result = await _place_market_buy(
                        session=session,
                        headers=headers,
                        account_id=account_id,
                        figi=instrument["figi"],
                        qty=qty,
                    )
                    results.append(
                        {
                            "ticker": ticker,
                            "qty": qty,
                            "ok": True,
                            "order_id": order_result.get("response_order_id") or order_result.get("request_order_id"),
                            "status": order_result.get("execution_report_status"),
                        }
                    )
                except Exception as e:
                    logger.error(f"Ошибка покупки {ticker}: {e}")
                    results.append({"ticker": ticker, "qty": qty, "ok": False, "error": str(e)})

        settings["last_run_date"] = today_str
        settings["last_results"] = results
        save_autobuy_settings(settings)

        success = [r for r in results if r.get("ok")]
        failed = [r for r in results if not r.get("ok")]

        lines = [
            "📈 Автопокупка выполнена",
            f"Дата: {today_str}",
            f"Успешно: {len(success)}",
            f"Ошибок: {len(failed)}",
            "",
        ]
        for r in success:
            lines.append(f"✅ {r['ticker']} x{r['qty']} | order_id: {r.get('order_id')}")
        for r in failed:
            lines.append(f"❌ {r['ticker']} x{r['qty']} | {r.get('error')}")

        await context.bot.send_message(chat_id=ADMIN_USER_ID, text="\n".join(lines))

    except Exception as e:
        logger.error(f"Критическая ошибка автопокупки: {e}")
        await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"❌ Критическая ошибка автопокупки: {e}")


def _parse_qty(value: str) -> int:
    qty = int(value)
    if qty <= 0:
        raise ValueError
    return qty


def _upsert_position(settings: Dict[str, Any], ticker: str, qty: int) -> None:
    positions = settings.get("positions", [])
    updated = False
    for item in positions:
        if str(item.get("ticker", "")).upper() == ticker:
            item["qty"] = qty
            updated = True
            break
    if not updated:
        positions.append({"ticker": ticker, "qty": qty})
    settings["positions"] = positions


def _remove_position(settings: Dict[str, Any], ticker: str) -> bool:
    positions = settings.get("positions", [])
    original_len = len(positions)
    positions = [p for p in positions if str(p.get("ticker", "")).upper() != ticker]
    settings["positions"] = positions
    return len(positions) != original_len


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

    if not settings.get("positions"):
        await update.message.reply_text("❌ Список автопокупки пуст. Добавьте тикер: /autobuy_add SBER 1")
        return

    settings["enabled"] = True
    settings["daily_time"] = time_str
    settings["timezone"] = DEFAULT_TIMEZONE_NAME
    save_autobuy_settings(settings)

    job_queue = _resolve_job_queue(context)
    if job_queue:
        ensure_autobuy_job(job_queue)

    await update.message.reply_text(
        "✅ Автопокупка включена\n"
        f"Время: {time_str} ({DEFAULT_TIMEZONE_NAME})\n"
        f"Позиций: {len(settings.get('positions', []))}"
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

    await update.message.reply_text("🛑 Автопокупка отключена")


async def autobuy_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return

    settings = load_autobuy_settings()
    status = "🟢 Включена" if settings.get("enabled") else "🔴 Выключена"
    portfolio_str = "н/д"
    cash_str = "н/д"

    if TINVEST_API_TOKEN:
        headers = {
            "Authorization": f"Bearer {TINVEST_API_TOKEN}",
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                account_id = await _get_primary_account_id(session, headers)
                snapshot = await _get_account_snapshot(session, headers, account_id)
                portfolio_str = _format_rub(snapshot.get("portfolio_total"))
                cash_str = _format_rub(snapshot.get("cash_total"))
        except Exception as e:
            logger.warning(f"Не удалось получить snapshot счета в autobuy_status: {e}")

    lines = [
        "📋 Статус автопокупки",
        f"Статус: {status}",
        f"Время: {settings.get('daily_time', DEFAULT_AUTOBUY_TIME)} ({settings.get('timezone', DEFAULT_TIMEZONE_NAME)})",
        f"Последний запуск: {settings.get('last_run_date') or 'не выполнялся'}",
        f"Портфель (оценка): {portfolio_str}",
        f"Денежный остаток (RUB): {cash_str}",
        "",
        "Позиции:",
    ]
    positions = settings.get("positions", [])
    if positions:
        for p in positions:
            lines.append(f"• {p.get('ticker')} x{p.get('qty')}")
    else:
        lines.append("• нет")

    await update.message.reply_text("\n".join(lines))


async def autobuy_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /autobuy_add <TICKER> <QTY>")
        return

    ticker = str(context.args[0]).upper().strip()
    if not ticker.isalnum():
        await update.message.reply_text("❌ Некорректный тикер")
        return

    try:
        qty = _parse_qty(context.args[1])
    except Exception:
        await update.message.reply_text("❌ QTY должно быть целым числом > 0")
        return

    settings = load_autobuy_settings()
    _upsert_position(settings, ticker, qty)
    save_autobuy_settings(settings)

    await update.message.reply_text(f"✅ Добавлено в автопокупку: {ticker} x{qty}")


async def autobuy_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return

    if not context.args:
        await update.message.reply_text("❌ Использование: /autobuy_remove <TICKER>")
        return

    ticker = str(context.args[0]).upper().strip()
    settings = load_autobuy_settings()
    removed = _remove_position(settings, ticker)
    save_autobuy_settings(settings)

    if removed:
        await update.message.reply_text(f"🗑️ Удалено из автопокупки: {ticker}")
    else:
        await update.message.reply_text(f"ℹ️ {ticker} не найден в списке автопокупки")


async def autobuy_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return

    settings = load_autobuy_settings()
    positions = settings.get("positions", [])

    lines = ["🧾 Список автопокупки:"]
    if not positions:
        lines.append("• пусто")
    else:
        for p in positions:
            lines.append(f"• {p.get('ticker')} x{p.get('qty')}")

    await update.message.reply_text("\n".join(lines))


async def autobuy_set_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return

    if not context.args:
        await update.message.reply_text("❌ Использование: /autobuy_set_time <HH:MM>")
        return

    time_str = context.args[0].strip()
    if not _validate_time_format(time_str):
        await update.message.reply_text("❌ Неверный формат времени. Используйте HH:MM")
        return

    settings = load_autobuy_settings()
    settings["daily_time"] = time_str
    save_autobuy_settings(settings)

    job_queue = _resolve_job_queue(context)
    if job_queue and settings.get("enabled"):
        ensure_autobuy_job(job_queue)

    await update.message.reply_text(f"⏰ Время автопокупки обновлено: {time_str} ({DEFAULT_TIMEZONE_NAME})")
