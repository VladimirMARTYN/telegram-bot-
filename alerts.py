"""Price observations and a durable outbox, independent of summary history."""

from datetime import datetime, timezone
from uuid import uuid4

from utils import positive_price, finite_number, is_estimated_quote, escape_html, parse_timestamp


def new_alert_state(history=None):
    return {
        'version': 1,
        'prices': {asset: {'price': price, 'observed_at': None}
                   for asset, price in (history or {}).items() if positive_price(price)},
        'pending': {},
    }


def observe_prices(state, quotes, subscribers, default_threshold=2.0, now=None):
    now = now or datetime.now(timezone.utc)
    previous = state.setdefault('prices', {})
    pending = state.setdefault('pending', {})
    for user_id in list(pending):
        if user_id not in subscribers or not subscribers[user_id].get('subscribed'):
            del pending[user_id]
    for asset, quote in quotes.items():
        price = quote.get('price')
        if not positive_price(price) or is_estimated_quote(quote) or quote.get('is_stale'):
            continue
        old = previous.get(asset, {})
        old = old if isinstance(old, dict) else {}
        old_price = old.get('price')
        if not positive_price(old_price):
            old_price = None
        if old.get('currency') and old['currency'] != quote.get('currency'):
            old_price = None
        observed = parse_timestamp(old.get('observed_at'))
        seconds = (now - observed).total_seconds() if observed else None
        period = f'за {seconds / 60:.0f} мин между проверками' if seconds is not None and seconds >= 60 else 'с прошлого наблюдения'
        for user_id, prefs in subscribers.items():
            if not prefs.get('subscribed'):
                continue
            messages = []
            threshold = prefs.get('threshold', default_threshold)
            if not positive_price(threshold):
                threshold = default_threshold
            if old_price is not None:
                change = (price / old_price - 1) * 100
                if finite_number(change) and abs(change) >= threshold:
                    icon = '📈' if change > 0 else '📉'
                    messages.append(f'{icon} <b>{escape_html(asset)}</b>: {change:+.2f}% {period} '
                                    f'({old_price:.2f} → {price:.2f})')
            alert = (prefs.get('alerts') or {}).get(asset)
            if positive_price(alert) and price >= alert and (old_price is None or old_price < alert):
                messages.append(f'🚨 <b>АЛЕРТ:</b> {escape_html(asset)} достиг {price:.2f} (порог: {alert})')
            for text in messages:
                pending.setdefault(user_id, []).append({
                    'id': uuid4().hex[:12], 'text': text, 'asset': asset,
                    'created_at': now.isoformat(),
                })
        previous[asset] = {'price': price, 'observed_at': now.isoformat(),
                           'as_of': quote.get('as_of'), 'currency': quote.get('currency'),
                           'source': quote.get('source')}
    return state
