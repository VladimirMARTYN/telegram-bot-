"""Build a complete report without mixing estimates with observed market quotes."""

from io import BytesIO
from html import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from utils import positive_price, finite_number, is_estimated_quote, parse_timestamp, format_price


def quote_status(quote):
    status = 'Estimated' if is_estimated_quote(quote) else (
        'Trading' if quote.get('is_live') is True else 'Last quote'
    )
    as_of = quote.get('as_of')
    stamp = parse_timestamp(as_of)
    if isinstance(as_of, str) and len(as_of) == 10:
        status += '\nas of ' + as_of
    elif stamp:
        status += '\nas of ' + stamp.strftime('%Y-%m-%d %H:%M UTC')
    return status


def build_pdf_report(fx, crypto, stocks, commodities, indices, current_time, stock_tickers):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=40, rightMargin=40,
                            topMargin=44, bottomMargin=42, title='Financial report')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ReportCell', fontName='Helvetica', fontSize=8,
                             leading=11, textColor=colors.HexColor('#263747')))
    styles.add(ParagraphStyle(name='ReportHeader', fontName='Helvetica-Bold', fontSize=8,
                             leading=11, textColor=colors.white))
    styles['Heading2'].textColor = colors.HexColor('#174c67')
    styles['Heading2'].keepWithNext = True
    story = [Paragraph('FINANCIAL REPORT', styles['Title']),
             Paragraph(f'Generated: {escape(current_time)} MSK', styles['Normal']), Spacer(1, 10)]
    if fx.get('conversion_note'):
        story += [Paragraph(
            'RUB conversions use a saved or estimated USD/RUB rate. Current FX data is unavailable; '
            'see the currency source below.', styles['Normal']), Spacer(1, 10)]

    def value(number, prefix=''):
        return prefix + format_price(number) if positive_price(number) else 'N/A'

    def change(number):
        return f'{number:+.2f}%' if finite_number(number) else 'N/A'

    def section(title, headers, rows, widths):
        story.append(Paragraph(title, styles['Heading2']))
        data = [[Paragraph(escape(str(cell)).replace('\n', '<br/>'),
                           styles['ReportHeader' if row_index == 0 else 'ReportCell'])
                 for cell in row] for row_index, row in enumerate([headers] + rows)]
        table = Table(data, colWidths=[doc.width * width for width in widths], repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#174c67')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f0f5f8'), colors.white]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#d4dfe5')),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        story.extend([table, Spacer(1, 9)])

    section('CURRENCY RATES', ['Currency', 'RUB per unit', 'Source'], [
        [symbol, value(fx['rates'].get(symbol)), fx['sources'].get(symbol, 'Unavailable')]
        for symbol in ('USD', 'EUR', 'CNY')
    ], [0.2, 0.3, 0.5])
    usd = fx['usd_to_rub_rate']
    crypto_rows = []
    for coin, name in [('bitcoin', 'Bitcoin'), ('the-open-network', 'TON'), ('solana', 'Solana'), ('tether', 'USDT')]:
        quote = crypto.get(coin) or {}
        currency = quote.get('currency', 'USD')
        price = quote.get('price')
        rub = price * usd if positive_price(price) and positive_price(usd) and currency == 'USD' else None
        crypto_rows.append([name, value(price) + ' ' + currency, value(rub),
                            change(quote.get('change_24h')), quote_status(quote) if positive_price(price) else 'Unavailable'])
    section('CRYPTOCURRENCIES', ['Asset', 'Price', 'RUB', '24h change', 'Status'], crypto_rows, [.17, .23, .23, .14, .23])

    section('RUSSIAN STOCKS AND FUNDS', ['Ticker', 'RUB per share', 'Daily change', 'Status'], [
        [ticker, value((stocks.get(ticker) or {}).get('price')),
         change((stocks.get(ticker) or {}).get('change_pct')),
         quote_status(stocks[ticker]) if positive_price((stocks.get(ticker) or {}).get('price')) else 'Unavailable']
        for ticker in stock_tickers
    ], [.17, .26, .2, .37])

    commodity_rows = []
    for key, label in [('gold', 'Gold / oz'), ('silver', 'Silver / oz'), ('brent', 'Brent / barrel'), ('urals', 'Urals / barrel')]:
        quote = commodities.get(key) or {}
        price = quote.get('price')
        rub = price * usd if positive_price(price) and positive_price(usd) else None
        commodity_rows.append([label, value(price, '$'), value(rub),
                               quote_status(quote) if positive_price(price) else 'Unavailable'])
    section('COMMODITIES', ['Asset', 'USD', 'RUB', 'Status'], commodity_rows, [.23, .2, .22, .35])
    section('STOCK INDICES', ['Index', 'Value', 'Daily change', 'Status'], [
        [label, value((indices.get(key) or {}).get('price')), change((indices.get(key) or {}).get('change_pct')),
         quote_status(indices[key]) if positive_price((indices.get(key) or {}).get('price')) else 'Unavailable']
        for key, label in [('imoex', 'IMOEX'), ('sp500', 'S&P 500')]
    ], [.2, .23, .2, .37])
    story.append(Paragraph(
        'Estimated values are not market quotes. Last-quote timestamps do not indicate an open exchange. '
        'Unavailable values are shown as N/A.', styles['Normal']))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#607889'))
        canvas.setFont('Helvetica', 8)
        canvas.drawString(40, 24, 'Financial Bot')
        canvas.drawRightString(A4[0] - 40, 24, str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer
