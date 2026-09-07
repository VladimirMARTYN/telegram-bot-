"""Split long Telegram HTML while retaining balanced formatting tags."""

from html import escape, unescape
from html.parser import HTMLParser


def split_html(text, limit=3800):
    class Splitter(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.tags = []
            self.parts = []
            self.buffer = ''
            self.size = 0

        def flush(self):
            if self.size:
                self.parts.append(self.buffer + ''.join(f'</{tag}>' for tag, _ in reversed(self.tags)))
            self.buffer = ''.join(raw for _, raw in self.tags)
            self.size = 0

        def handle_starttag(self, tag, attrs):
            raw = self.get_starttag_text()
            self.tags.append((tag, raw))
            self.buffer += raw

        def handle_endtag(self, tag):
            self.buffer += f'</{tag}>'
            if self.tags and self.tags[-1][0] == tag:
                self.tags.pop()

        def handle_data(self, data):
            # Conservative UTF-16 budget also covers emoji/supplementary characters.
            for character in data:
                size = len(character.encode('utf-16-le')) // 2
                if self.size + size > limit:
                    self.flush()
                self.buffer += escape(character, quote=False)
                self.size += size

    parser = Splitter()
    parser.feed(text)
    parser.close()
    parser.flush()
    return parser.parts
