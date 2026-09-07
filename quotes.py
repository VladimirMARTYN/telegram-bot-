"""Currency normalization shared by Telegram summaries and PDF reports."""

from config import FALLBACK_USD_RUB_RATE
from utils import positive_price, format_price, get_last_known_rate, save_last_known_rate


def resolve_currency_rates(cbr_data, forex_data):
    cbr = cbr_data if isinstance(cbr_data, dict) else {}
    forex = forex_data if isinstance(forex_data, dict) else {}
    valute = cbr.get('Valute') or {}
    forex_rates = forex.get('rates') or {}
    if not isinstance(valute, dict):
        valute = {}
    if not isinstance(forex_rates, dict):
        forex_rates = {}
    rub = forex_rates.get('RUB')
    result = {'rates': {}, 'strings': {}, 'sources': {}, 'conversion_note': ''}
    for symbol in ('USD', 'EUR', 'CNY'):
        entry = valute.get(symbol) or {}
        if not isinstance(entry, dict):
            entry = {}
        raw = entry.get('Value')
        nominal = entry.get('Nominal', 1)
        official = raw / nominal if positive_price(raw) and positive_price(nominal) else None
        cross = 1 if symbol == 'USD' else forex_rates.get(symbol)
        market = rub / cross if positive_price(rub) and positive_price(cross) else None
        rate = official if positive_price(official) else market
        result['rates'][symbol] = rate
        result['sources'][symbol] = 'CBR' if positive_price(official) else 'FOREX'
        if not positive_price(rate):
            result['strings'][symbol] = 'Н/Д'
            result['sources'][symbol] = 'Unavailable'
            continue
        text = f'{format_price(rate)} ₽'
        if official is None:
            text += ' (FOREX)'
        elif market is not None:
            diff = market - official
            text += f' (FOREX: {format_price(market)} ₽, разница: {diff:+.2f} ₽, {diff / official * 100:+.2f}%)'
        result['strings'][symbol] = text
        if symbol == 'USD':
            timestamp = (cbr.get('Timestamp') or cbr.get('Date')) if official else (
                forex.get('time_last_updated') or forex.get('date')
            )
            save_last_known_rate('USD_RUB', rate, timestamp=timestamp, source=result['sources'][symbol])

    usd = result['rates']['USD']
    if not positive_price(usd):
        previous = get_last_known_rate('USD_RUB', max_age_hours=24)
        if positive_price(previous):
            usd = previous
            kind = 'сохранённый курс, до 24 ч'
            result['sources']['USD'] = 'Saved, up to 24h'
        elif positive_price(FALLBACK_USD_RUB_RATE):
            usd = FALLBACK_USD_RUB_RATE
            kind = 'условный резервный курс'
            result['sources']['USD'] = 'Estimated fallback'
        else:
            usd = 0
            kind = ''
        if usd:
            result['strings']['USD'] = f'{format_price(usd)} ₽ ({kind})'
            result['conversion_note'] = f'Пересчёт в рубли: {kind} USD/RUB = {format_price(usd)}; актуальный курс недоступен.'
        result['rates']['USD'] = usd or None
        # Never write a cached or configured value back with a new timestamp.
    result['usd_to_rub_rate'] = usd or 0
    dates = []
    for label, value in (('ЦБ', cbr.get('Date')), ('FOREX', forex.get('date'))):
        if value:
            dates.append(f'{label}: {str(value)[:10]}')
    result['source_dates'] = '; '.join(dates)
    return result
