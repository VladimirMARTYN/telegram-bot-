#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для получения данных из различных источников
Все запросы асинхронные с использованием aiohttp
"""

import logging
import asyncio
import http_compat  # Must precede aiohttp on Python 3.9.
import aiohttp
import json
import ssl
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import pytz

from config import (
    CACHE_TTL_CURRENCIES, CACHE_TTL_CRYPTO, CACHE_TTL_STOCKS,
    CACHE_TTL_COMMODITIES, CACHE_TTL_INDICES, API_TIMEOUT,
    API_RETRY_ATTEMPTS, API_RETRY_DELAY_MIN, API_RETRY_DELAY_MAX,
    URALS_DISCOUNT, EIA_API_KEY, ALPHA_VANTAGE_KEY,
    GOLD_SILVER_RATIO, USO_TO_BRENT_MULTIPLIER, TINVEST_API_TOKEN
)
from utils import (get_cached_data, fetch_with_retry, save_last_known_rate,
                   get_last_known_rate, positive_price, finite_number, parse_timestamp)

logger = logging.getLogger(__name__)

# Используем просто число для таймаута, чтобы избежать проблем с контекстным менеджером
_TIMEOUT = API_TIMEOUT
_TINVEST_REST_BASE = "https://invest-public-api.tbank.ru/rest"
_TINVEST_CA_FILE = Path(__file__).resolve().parent / "certs" / "RussianTrustedRootCA.pem"


def _create_tinvest_ssl_context() -> ssl.SSLContext:
    """Создать TLS-контекст T-Invest с официальным корневым CA Минцифры."""
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(_TINVEST_CA_FILE))
    return context


_TINVEST_SSL_CONTEXT = _create_tinvest_ssl_context()


def _tinvest_money_to_float(value: Optional[Dict[str, Any]]) -> Optional[float]:
    """Конвертация money value {units, nano} в float."""
    if not isinstance(value, dict):
        return None
    units = value.get('units')
    nano = value.get('nano')
    if units is None:
        return None
    try:
        return float(units) + float(nano or 0) / 1_000_000_000
    except (TypeError, ValueError):
        return None


def _tinvest_is_live_status(status: Optional[str]) -> bool:
    """Проверка, что инструмент сейчас торгуется."""
    if not status:
        return False
    return status in {
        "SECURITY_TRADING_STATUS_NORMAL_TRADING",
        "SECURITY_TRADING_STATUS_DEALER_NORMAL_TRADING",
    }


def _moex_timestamp(value):
    """MOEX ISS local timestamps are Moscow time, regardless of server timezone."""
    if not value or len(str(value)) == 10:
        return value
    try:
        stamp = datetime.fromisoformat(str(value))
        if stamp.tzinfo is None:
            stamp = pytz.timezone('Europe/Moscow').localize(stamp)
        return stamp.isoformat()
    except (ValueError, TypeError):
        return None


async def safe_json_response(resp: aiohttp.ClientResponse) -> Any:
    """
    Безопасное получение JSON из ответа с обработкой ошибок Content-Type
    
    Args:
        resp: Объект ответа aiohttp
        
    Returns:
        Распарсенный JSON объект
    """
    try:
        return await resp.json()
    except aiohttp.client_exceptions.ContentTypeError:
        # Если Content-Type неправильный, получаем текст и парсим вручную
        text = await resp.text(encoding='utf-8')
        return json.loads(text)


async def get_cbr_rates(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Получить курсы валют ЦБ РФ"""
    async def _fetch():
        async with session.get(
            "https://www.cbr-xml-daily.ru/daily_json.js",
            timeout=_TIMEOUT
        ) as resp:
            resp.raise_for_status()
            # ЦБ РФ возвращает application/javascript, используем безопасную функцию
            return await safe_json_response(resp)
    
    return await fetch_with_retry(
        _fetch,
        max_attempts=API_RETRY_ATTEMPTS,
        delay_min=API_RETRY_DELAY_MIN,
        delay_max=API_RETRY_DELAY_MAX
    )


async def get_forex_rates(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Получить курсы валют с FOREX"""
    async def _fetch():
        async with session.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=_TIMEOUT
        ) as resp:
            resp.raise_for_status()
            return await safe_json_response(resp)
    
    return await fetch_with_retry(
        _fetch,
        max_attempts=API_RETRY_ATTEMPTS,
        delay_min=API_RETRY_DELAY_MIN,
        delay_max=API_RETRY_DELAY_MAX
    )


async def get_crypto_data(session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
    """Fill missing instruments independently, preserving successful primary quotes."""
    coins = {'bitcoin': 'BTC', 'the-open-network': 'TON', 'solana': 'SOL', 'tether': 'USDT'}
    result = {}
    try:
        async with session.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={'ids': ','.join(coins), 'vs_currencies': 'usd',
                    'include_24hr_change': 'true', 'include_last_updated_at': 'true'},
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status == 200:
                data = await safe_json_response(resp)
                for coin in coins:
                    entry = data.get(coin, {})
                    if not isinstance(entry, dict) or not positive_price(entry.get('usd')):
                        continue
                    change = entry.get('usd_24h_change')
                    result[coin] = {
                        'price': entry['usd'], 'change_24h': change if finite_number(change) else None,
                        'source': 'CoinGecko', 'currency': 'USD',
                        'as_of': entry.get('last_updated_at'), 'is_estimated': False,
                    }
    except Exception as exc:
        logger.warning('CoinGecko unavailable: %s', exc)

    async def coinbase(coin):
        try:
            async with session.get(
                f'https://api.coinbase.com/v2/prices/{coins[coin]}-USD/spot', timeout=_TIMEOUT,
            ) as resp:
                if resp.status == 200:
                    data = await safe_json_response(resp)
                    price = float(data['data']['amount'])
                    if positive_price(price):
                        result[coin] = {'price': price, 'change_24h': None, 'source': 'Coinbase',
                                        'currency': 'USD', 'is_estimated': False}
        except Exception as exc:
            logger.debug('Coinbase %s unavailable: %s', coins[coin], exc)

    await asyncio.gather(*(coinbase(coin) for coin in coins if coin not in result))

    async def binance(coin):
        if coin == 'tether':
            return  # USDTUSDT is not a trading pair.
        try:
            async with session.get(
                'https://api.binance.com/api/v3/ticker/price',
                params={'symbol': coins[coin] + 'USDT'}, timeout=_TIMEOUT,
            ) as resp:
                if resp.status == 200:
                    data = await safe_json_response(resp)
                    price = float(data['price'])
                    if positive_price(price):
                        # Binance prices are in USDT, not necessarily USD.
                        usd_rate = result.get('tether', {}).get('price')
                        converted = positive_price(usd_rate)
                        result[coin] = {'price': price * usd_rate if converted else price,
                                        'change_24h': None, 'source': 'Binance',
                                        'currency': 'USD' if converted else 'USDT',
                                        'is_estimated': not converted}
        except Exception as exc:
            logger.debug('Binance %s unavailable: %s', coins[coin], exc)

    await asyncio.gather(*(binance(coin) for coin in coins if coin not in result))
    return result


async def get_moex_stocks(session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
    """Получить данные акций с Московской биржи"""
    stocks_data = {}
    
    # Список акций для мониторинга
    stocks = {
        'SBER': {'name': 'Сбер', 'emoji': '🟢'},
        'YDEX': {'name': 'Яндекс', 'emoji': '🔴'},
        'VKCO': {'name': 'ВК', 'emoji': '🔵'},
        'T': {'name': 'Т-Технологии', 'emoji': '🟡'},
        'GAZP': {'name': 'Газпром', 'emoji': '💎'},
        'GMKN': {'name': 'Норникель', 'emoji': '⚡'},
        'ROSN': {'name': 'Роснефть', 'emoji': '🛢️'},
        'LKOH': {'name': 'ЛУКОЙЛ', 'emoji': '⛽'},
        'MTSS': {'name': 'МТС', 'emoji': '📱'},
        'PIKK': {'name': 'ПИК', 'emoji': '🏗️'},
        'SMLT': {'name': 'Самолёт', 'emoji': '✈️'},
        'TGLD': {'name': 'TGLD', 'emoji': '🪙'},
        'TOFZ': {'name': 'TOFZ', 'emoji': '📄'},
        'DOMRF': {'name': 'DOMRF', 'emoji': '🏛️'}
    }
    
    # Основной источник: T-Invest REST API
    try:
        if TINVEST_API_TOKEN:
            tinvest_ids = {
                'SBER': 'SBER_TQBR',
                'YDEX': 'YDEX_TQBR',
                'VKCO': 'VKCO_TQBR',
                'T': 'T_TQBR',
                'GAZP': 'GAZP_TQBR',
                'GMKN': 'GMKN_TQBR',
                'ROSN': 'ROSN_TQBR',
                'LKOH': 'LKOH_TQBR',
                'MTSS': 'MTSS_TQBR',
                'PIKK': 'PIKK_TQBR',
                'SMLT': 'SMLT_TQBR',
                'TGLD': 'TGLD_TQBR',
                'TOFZ': 'TOFZ_TQBR',
                'DOMRF': 'DOMRF_TQBR'
            }

            headers = {
                "Authorization": f"Bearer {TINVEST_API_TOKEN}",
                "Content-Type": "application/json"
            }
            payload = {"instrumentId": list(tinvest_ids.values())}

            # Берем цены одним запросом
            async with session.post(
                f"{_TINVEST_REST_BASE}/tinkoff.public.invest.api.contract.v1.MarketDataService/GetLastPrices",
                headers=headers,
                json=payload,
                timeout=_TIMEOUT,
                ssl=_TINVEST_SSL_CONTEXT,
            ) as resp:
                if resp.status == 200:
                    price_data = await safe_json_response(resp)
                else:
                    price_data = {}
                    logger.warning(f"T-Invest GetLastPrices failed ({resp.status})")

            try:
                # И статус торгов вторым запросом
                async with session.post(
                    f"{_TINVEST_REST_BASE}/tinkoff.public.invest.api.contract.v1.MarketDataService/GetTradingStatuses",
                    headers=headers,
                    json=payload,
                    timeout=_TIMEOUT,
                    ssl=_TINVEST_SSL_CONTEXT,
                ) as resp:
                    if resp.status == 200:
                        statuses_data = await safe_json_response(resp)
                    else:
                        statuses_data = {}
                        logger.warning(f"T-Invest GetTradingStatuses failed ({resp.status})")

            except Exception as exc:
                statuses_data = {}
                logger.warning("T-Invest status unavailable; preserving last prices: %s", exc)

            status_by_uid = {}
            for item in statuses_data.get('tradingStatuses', []):
                uid = item.get('instrumentUid')
                if uid:
                    status_by_uid[uid] = item.get('tradingStatus')

            for item in price_data.get('lastPrices', []):
                ticker = item.get('ticker')
                if ticker not in stocks:
                    continue
                price = _tinvest_money_to_float(item.get('price'))
                if not positive_price(price):
                    continue
                uid = item.get('instrumentUid')
                is_live = _tinvest_is_live_status(status_by_uid.get(uid))
                stocks_data[ticker] = {
                    'name': stocks[ticker]['name'],
                    'emoji': stocks[ticker]['emoji'],
                    'shortname': stocks[ticker]['name'],
                    'price': price,
                    'change': None,
                    'change_pct': 0,
                    'volume': None,
                    'open': None,
                    'high': None,
                    'low': None,
                    'is_live': is_live,
                    'source': 'T-Invest', 'as_of': item.get('time'), 'is_estimated': False,
                }

            if all(positive_price(stocks_data.get(ticker, {}).get('price')) for ticker in stocks):
                logger.info("✅ MOEX данные получены через T-Invest API")
                return stocks_data
    except Exception as e:
        logger.error(f"Ошибка получения данных MOEX через T-Invest: {e}")

    try:
        trading_url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
        params = {
            'securities': ','.join(ticker for ticker in stocks if not positive_price(stocks_data.get(ticker, {}).get('price'))),
            'iss.meta': 'off',
            'iss.only': 'securities,marketdata'
        }
        
        async with session.get(
            trading_url,
            params=params,
            timeout=_TIMEOUT
        ) as resp:
            if resp.status == 200:
                data = await safe_json_response(resp)
                
                securities_data = {}
                marketdata = {}
                
                if 'securities' in data and 'data' in data['securities']:
                    securities_cols = data['securities']['columns']
                    for row in data['securities']['data']:
                        row_data = dict(zip(securities_cols, row))
                        secid = row_data.get('SECID')
                        if secid in stocks:
                            securities_data[secid] = {
                                'shortname': row_data.get('SHORTNAME', stocks[secid]['name']),
                                'lotsize': row_data.get('LOTSIZE', 1),
                                'prevprice': row_data.get('PREVPRICE'),
                                'prevdate': row_data.get('PREVDATE')
                            }
                
                if 'marketdata' in data and 'data' in data['marketdata']:
                    marketdata_cols = data['marketdata']['columns']
                    for row in data['marketdata']['data']:
                        row_data = dict(zip(marketdata_cols, row))
                        secid = row_data.get('SECID')
                        if secid in stocks:
                            marketdata[secid] = {
                                'last': row_data.get('LAST'),
                                'change': row_data.get('CHANGE'),
                                'changeprcnt': row_data.get('CHANGEPRCNT'),
                                'volume': row_data.get('VALTODAY'),
                                'open': row_data.get('OPEN'),
                                'high': row_data.get('HIGH'),
                                'low': row_data.get('LOW'),
                                'status': row_data.get('TRADINGSTATUS'),
                                'as_of': row_data.get('SYSTIME')
                            }
                
                # A partial T-Invest response must not suppress the MOEX fallback.
                for ticker in stocks:
                    if positive_price(stocks_data.get(ticker, {}).get('price')):
                        continue
                    security = securities_data.get(ticker, {})
                    market = marketdata.get(ticker, {})
                    last = market.get('last')
                    price = last if positive_price(last) else security.get('prevprice')
                    if not positive_price(price):
                        continue
                    last_trade = positive_price(last)
                    status = market.get('status')
                    stocks_data[ticker] = {
                        'name': stocks[ticker]['name'], 'emoji': stocks[ticker]['emoji'],
                        'shortname': security.get('shortname', stocks[ticker]['name']),
                        'price': price,
                        'change': market.get('change') if last_trade else None,
                        'change_pct': market.get('changeprcnt') if last_trade else None,
                        'volume': market.get('volume'), 'open': market.get('open'),
                        'high': market.get('high'), 'low': market.get('low'),
                        'is_live': (status == 'T') if status is not None and last_trade else None,
                        'as_of': _moex_timestamp(market.get('as_of')) if last_trade else security.get('prevdate'),
                        'note': '' if last_trade else 'Последняя цена закрытия',
                        'source': 'MOEX', 'is_estimated': False,
                    }
    
    except Exception as e:
        logger.error(f"Ошибка получения данных MOEX: {e}")

    return stocks_data


async def get_commodities_data(session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
    """Получить данные по товарам"""
    commodities_data = {}
    
    try:
        # Золото
        logger.debug("Запрашиваю золото с Gold-API.com...")
        try:
            async with session.get(
                "https://api.gold-api.com/price/XAU",
                timeout=_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    gold_data = await safe_json_response(resp)
                    if positive_price(gold_data.get('price')):
                        gold_price = gold_data['price']
                        commodities_data['gold'] = {
                            'name': 'Золото',
                            'price': gold_price,
                            'currency': 'USD', 'is_estimated': False, 'source': 'Gold-API',
                            'as_of': gold_data.get('updatedAt'),
                        }
                        logger.info(f"✅ Золото получено: ${gold_price:.2f}")
                        
                        # Сохраняем цену золота для расчета соотношений
                        save_last_known_rate('GOLD_PRICE', gold_price, timestamp=gold_data.get('updatedAt'))
        except Exception as e:
            logger.error(f"Ошибка запроса золота: {e}")
        
        # Серебро
        logger.debug("Запрашиваю серебро с Gold-API.com...")
        try:
            async with session.get(
                "https://api.gold-api.com/price/XAG",
                timeout=_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    silver_data = await safe_json_response(resp)
                    if positive_price(silver_data.get('price')):
                        silver_price = silver_data['price']
                        commodities_data['silver'] = {
                            'name': 'Серебро',
                            'price': silver_price,
                            'currency': 'USD', 'is_estimated': False, 'source': 'Gold-API',
                            'as_of': silver_data.get('updatedAt'),
                        }
                        logger.info(f"✅ Серебро получено: ${silver_price:.2f}")
                        
                        # Сохраняем цену серебра и соотношение с золотом
                        save_last_known_rate('SILVER_PRICE', silver_price, timestamp=silver_data.get('updatedAt'))
                        if 'gold' in commodities_data:
                            gold_price = commodities_data['gold']['price']
                            ratio = gold_price / silver_price
                            save_last_known_rate('GOLD_SILVER_RATIO', ratio)
                            logger.debug(f"Соотношение золото/серебро: {ratio:.2f}:1")
        except Exception as e:
            logger.error(f"Ошибка запроса серебра: {e}")
        
        # Нефть Brent из EIA API
        logger.debug("Запрашиваю нефть Brent из EIA API...")
        try:
            url = f"https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key={EIA_API_KEY}&facets[product][]=EPCBRENT&data[0]=value&sort[0][column]=period&sort[0][direction]=desc&length=1"
            async with session.get(url, timeout=_TIMEOUT) as resp:
                if resp.status == 200:
                    brent_data = await safe_json_response(resp)
                    if 'response' in brent_data and 'data' in brent_data['response'] and len(brent_data['response']['data']) > 0:
                        brent_price = float(brent_data['response']['data'][0]['value'])
                        if not positive_price(brent_price):
                            raise ValueError('Invalid Brent price')
                        commodities_data['brent'] = {
                            'name': 'Нефть Brent',
                            'price': brent_price,
                            'currency': 'USD', 'is_estimated': False, 'source': 'EIA',
                            'as_of': brent_data['response']['data'][0].get('period'),
                        }
                        logger.info(f"✅ Нефть Brent получена: ${brent_price:.2f}")
                        
                        # Сохраняем цену Brent для расчета соотношений
                        save_last_known_rate('BRENT_PRICE', brent_price, timestamp=commodities_data['brent']['as_of'])
        except Exception as e:
            logger.error(f"Ошибка запроса Brent из EIA: {e}")
        
        # Fallback: Alpha Vantage для нефти через USO ETF
        if 'brent' not in commodities_data:
            logger.debug("EIA не сработал, пробуем Alpha Vantage USO ETF...")
            try:
                url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=USO&apikey={ALPHA_VANTAGE_KEY}"
                async with session.get(url, timeout=_TIMEOUT) as resp:
                    if resp.status == 200:
                        oil_data = await safe_json_response(resp)
                        if 'Global Quote' in oil_data and '05. price' in oil_data['Global Quote']:
                            uso_price = float(oil_data['Global Quote']['05. price'])
                            
                            # Получаем последнее известное соотношение или используем константу
                            last_multiplier = get_last_known_rate('USO_TO_BRENT', max_age_hours=24)
                            
                            if positive_price(last_multiplier):
                                estimated_brent = uso_price * last_multiplier
                                logger.debug(f"Используется последнее известное соотношение USO→Brent: {last_multiplier:.3f}")
                            else:
                                # Используем константу из config (правильное значение ~1.3-1.5)
                                estimated_brent = uso_price * USO_TO_BRENT_MULTIPLIER
                                logger.debug(f"Используется константа соотношения USO→Brent: {USO_TO_BRENT_MULTIPLIER:.3f}")
                            
                            commodities_data['brent'] = {
                                'name': 'Нефть Brent (приблиз.)',
                                'price': estimated_brent,
                                'currency': 'USD',
                                'note': 'Рассчитано от USO ETF', 'is_estimated': True, 'source': 'Alpha Vantage (USO)'
                            }
                            logger.info(f"✅ Нефть Brent (USO fallback): ${estimated_brent:.2f}")
                            
            except Exception as e:
                logger.error(f"Ошибка Alpha Vantage USO: {e}")
        
        # Fallback для серебра
        if 'silver' not in commodities_data and 'gold' in commodities_data:
            logger.debug("Серебро недоступно, рассчитываем от золота...")
            gold_price = commodities_data['gold']['price']
            
            # Пробуем получить последнее известное соотношение (не старше недели)
            last_ratio = get_last_known_rate('GOLD_SILVER_RATIO', max_age_hours=168)
            
            if positive_price(last_ratio):
                silver_fallback = gold_price / last_ratio
                logger.debug(f"Используется последнее известное соотношение золото/серебро: {last_ratio:.2f}:1")
            else:
                # Используем константу из config
                silver_fallback = gold_price / GOLD_SILVER_RATIO if positive_price(GOLD_SILVER_RATIO) else None
                logger.debug(f"Используется константа соотношения золото/серебро: {GOLD_SILVER_RATIO:.2f}:1")
            
            commodities_data['silver'] = {
                'name': 'Серебро (расчетное)',
                'price': silver_fallback,
                'currency': 'USD',
                'note': 'Рассчитано от золота', 'is_estimated': True, 'source': 'Gold ratio'
            }
            logger.info('Серебро: расчёт от золота')
        
        # Рассчитываем Urals от Brent
        if 'brent' in commodities_data:
            logger.debug("Рассчитываем Urals от Brent...")
            brent_price = commodities_data['brent']['price']
            urals_price = brent_price - URALS_DISCOUNT
            commodities_data['urals'] = {
                'name': 'Нефть Urals (расчетная)',
                'price': urals_price,
                'currency': 'USD', 'is_estimated': True, 'source': 'Brent minus discount',
                'note': 'Рассчитано от Brent'
            }
            logger.info(f"✅ Urals рассчитана: ${urals_price:.2f}")
    
    except Exception as e:
        logger.error(f"Общая ошибка получения данных товаров: {e}")
    
    return {key: value for key, value in commodities_data.items() if positive_price(value.get('price'))}


async def get_indices_data(session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
    """Получить данные фондовых индексов"""
    indices_data = {}
    
    try:
        # IMOEX через T-Invest (инструмент индекса по UID)
        if TINVEST_API_TOKEN:
            try:
                headers = {
                    "Authorization": f"Bearer {TINVEST_API_TOKEN}",
                    "Content-Type": "application/json"
                }
                imoex_uid = "4821c9aa-36e8-4743-b37c-861e58581b25"
                payload = {"instrumentId": [imoex_uid]}

                async with session.post(
                    f"{_TINVEST_REST_BASE}/tinkoff.public.invest.api.contract.v1.MarketDataService/GetLastPrices",
                    headers=headers,
                    json=payload,
                    timeout=_TIMEOUT,
                    ssl=_TINVEST_SSL_CONTEXT,
                ) as resp:
                    price_data = await safe_json_response(resp) if resp.status == 200 else {}
                    if resp.status != 200:
                        logger.warning(f"T-Invest IMOEX GetLastPrices failed ({resp.status})")

                async with session.post(
                    f"{_TINVEST_REST_BASE}/tinkoff.public.invest.api.contract.v1.MarketDataService/GetTradingStatuses",
                    headers=headers,
                    json=payload,
                    timeout=_TIMEOUT,
                    ssl=_TINVEST_SSL_CONTEXT,
                ) as resp:
                    status_data = await safe_json_response(resp) if resp.status == 200 else {}
                    if resp.status != 200:
                        logger.warning(f"T-Invest IMOEX GetTradingStatuses failed ({resp.status})")

                price_item = (price_data.get('lastPrices') or [{}])[0]
                status_item = (status_data.get('tradingStatuses') or [{}])[0]
                imoex_price = _tinvest_money_to_float(price_item.get('price'))
                if positive_price(imoex_price):
                    indices_data['imoex'] = {
                        'name': 'IMOEX',
                        'price': imoex_price,
                        'change_pct': 0,
                        'is_live': _tinvest_is_live_status(status_item.get('tradingStatus')),
                        'source': 'T-Invest', 'as_of': price_item.get('time')
                    }
                    logger.info("✅ IMOEX получен из T-Invest API")
            except Exception as e:
                logger.error(f"Ошибка получения IMOEX из T-Invest: {e}")

        # Fallback IMOEX через MOEX ISS (если T-Invest не дал цену)
        if 'imoex' not in indices_data:
            logger.debug("Запрашиваю индексы MOEX (fallback)...")
            try:
                async with session.get(
                    "https://iss.moex.com/iss/engines/stock/markets/index/boards/SNDX/securities.json",
                    params={'iss.meta': 'off', 'iss.only': 'securities,marketdata'},
                    timeout=_TIMEOUT
                ) as resp:
                    if resp.status == 200:
                        data = await safe_json_response(resp)
                        if 'marketdata' in data and 'data' in data['marketdata']:
                            marketdata_cols = data['marketdata']['columns']
                            for row in data['marketdata']['data']:
                                row_data = dict(zip(marketdata_cols, row))
                                if row_data.get('SECID') == 'IMOEX':
                                    last_value = row_data.get('LAST')
                                    price = last_value or row_data.get('CURRENTVALUE') or row_data.get('PREVPRICE')
                                    if positive_price(price):
                                        indices_data['imoex'] = {
                                            'name': 'IMOEX',
                                            'price': price,
                                            'change_pct': row_data.get('CHANGEPRCNT', 0),
                                            'is_live': (row_data['TRADINGSTATUS'] == 'T') if row_data.get('TRADINGSTATUS') is not None else None,
                                            'source': 'MOEX', 'as_of': _moex_timestamp(row_data.get('SYSTIME'))
                                        }
            except Exception as e:
                logger.error(f"Ошибка получения индексов MOEX: {e}")
        
        # S&P 500 через FMP (основной источник) или Alpha Vantage
        logger.debug("Запрашиваю S&P 500...")
        try:
            # Пробуем FMP сначала
            from config import FMP_API_KEY
            if FMP_API_KEY and FMP_API_KEY != 'demo':
                url = f"https://financialmodelingprep.com/api/v3/quote/%5EGSPC?apikey={FMP_API_KEY}"
                async with session.get(url, timeout=_TIMEOUT) as resp:
                    if resp.status == 200:
                        sp500_data = await safe_json_response(resp)
                        if isinstance(sp500_data, list) and len(sp500_data) > 0:
                            sp500_info = sp500_data[0]
                            if positive_price(sp500_info.get('price')):
                                indices_data['sp500'] = {
                                    'name': 'S&P 500',
                                    'price': sp500_info['price'],
                                    'change_pct': sp500_info.get('changesPercentage', 0),
                                    'is_live': None,  # A quote timestamp is not an exchange-session status.
                                    'source': 'FMP', 'as_of': sp500_info.get('timestamp')
                                }
                                logger.info(f"✅ S&P 500 получен из FMP: {sp500_info['price']:.2f}")
                                # Не возвращаем здесь, чтобы можно было вернуть все индексы вместе
        except Exception as e:
            logger.debug(f"Ошибка получения S&P 500 из FMP: {e}")
        
        # Fallback: Alpha Vantage SPY (только если FMP не дал данные)
        if 'sp500' not in indices_data:
            try:
                url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey={ALPHA_VANTAGE_KEY}"
                async with session.get(url, timeout=_TIMEOUT) as resp:
                    if resp.status == 200:
                        sp500_data = await safe_json_response(resp)
                        if 'Global Quote' in sp500_data and '05. price' in sp500_data['Global Quote']:
                            spy_price = float(sp500_data['Global Quote']['05. price'])
                            # Приблизительная конвертация SPY в S&P 500
                            sp500_price = spy_price * 10
                            change_pct = float(sp500_data['Global Quote'].get('10. change percent', '0%').replace('%', ''))
                            
                            # Проверяем, открыт ли рынок (если есть время торговли в данных)
                            trading_status = sp500_data['Global Quote'].get('07. latest trading day', '')
                            is_live = None  # Наличие исторической даты не определяет статус сессии.
                            
                            indices_data['sp500'] = {
                                'name': 'S&P 500',
                                'price': sp500_price,
                                'change_pct': change_pct,
                                'is_live': is_live, 'is_estimated': True,
                                'note': 'Оценка по SPY × 10', 'source': 'Alpha Vantage (SPY)',
                                'as_of': trading_status,
                            }
                            logger.info(f"✅ S&P 500 получен из Alpha Vantage: {sp500_price:.2f}")
            except Exception as e:
                logger.error(f"Ошибка получения S&P 500: {e}")

    except Exception as e:
        logger.error(f"Общая ошибка получения индексов: {e}")
    
    return {key: value for key, value in indices_data.items() if positive_price(value.get("price"))}
