import base64
import io
import json
import os
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
STATIC = os.environ.get("STATIC") == "1"

PAPER = "#ecebe6"
INK = "#0b0b0c"
GREY = "#5e5d58"
LINE = "#d4d2ca"
COBALT = "#2c3bff"
ORANGE = "#d9480f"
GREEN = "#2b8a3e"
EASE = "cubic-bezier(.2,.8,.2,1)"

MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

KEYFRAMES = (
    "@keyframes cc-rise{from{opacity:0;transform:translateY(14px)}}"
    "@keyframes cc-fade{from{opacity:0}}"
    "@keyframes cc-draw{from{stroke-dashoffset:1}}"
    "@keyframes cc-grow-x{from{transform:scaleX(0)}}"
    "@keyframes cc-grow-y{from{transform:scaleY(0)}}"
    "@keyframes cc-blink{from,to{opacity:1}}"
    "@keyframes cc-show{from{opacity:0}to{opacity:1}}"
    "@keyframes cc-pulse{0%,100%{opacity:1}50%{opacity:.2}}"
    "@keyframes cc-nudge{0%,80%,100%{transform:translate(0,0)}88%{transform:translate(4px,-4px)}}"
)


class Font:
    def __init__(self, filename):
        self.path = ROOT / "fonts" / filename
        font = TTFont(self.path)
        self.cmap = font.getBestCmap()
        self.advances = font["hmtx"].metrics
        self.upm = font["head"].unitsPerEm

    def width(self, text, size, tracking=0):
        units = sum(self.advances[self.cmap.get(ord(char), ".notdef")][0] for char in text)
        return units * size / self.upm + tracking * len(text)

    def has(self, char):
        return ord(char) in self.cmap


FONTS = {
    "serif": Font("InstrumentSerif-Regular.ttf"),
    "sans": Font("Inter-Regular.ttf"),
    "sans-medium": Font("Inter-Medium.ttf"),
    "mono": Font("IBMPlexMono-Regular.ttf"),
    "mono-medium": Font("IBMPlexMono-Medium.ttf"),
}


def font_face(key, chars):
    options = subset.Options()
    options.layout_features = ["kern", "liga", "calt"]
    options.hinting = False
    options.desubroutinize = True
    options.drop_tables += ["meta"]
    font = TTFont(FONTS[key].path)
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes={ord(char) for char in chars} | {0x20})
    subsetter.subset(font)
    font.flavor = "woff2"
    buffer = io.BytesIO()
    font.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"@font-face{{font-family:'cc-{key}';src:url(data:font/woff2;base64,{encoded}) format('woff2')}}"


def anim(name, duration, delay, timing=EASE, mode="backwards", iterations=""):
    return f"animation:{name} {duration}s {timing} {delay:.2f}s {iterations} {mode}".replace("  ", " ")


def nombre(value, font):
    separator = next((sep for sep in (" ", " ") if FONTS[font].has(sep)), " ")
    return f"{value:,}".replace(",", separator)


def wrap(text, font, size, max_width):
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and FONTS[font].width(candidate, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return lines + [current]


class Card:
    def __init__(self, width, height, title):
        self.width = width
        self.height = height
        self.title = title
        self.body = []
        self.css = []
        self.chars = {key: set() for key in FONTS}

    def text(self, content, x, y, font, size, fill, anchor="start", tracking=0, style="", register_only=False):
        self.chars[font].update(content)
        attrs = f'x="{x:.1f}" y="{y:.1f}" font-family="cc-{font}" font-size="{size}" fill="{fill}"'
        if anchor != "start":
            attrs += f' text-anchor="{anchor}"'
        if tracking:
            attrs += f' letter-spacing="{tracking}"'
        if style:
            attrs += f' style="{style}"'
        markup = f"<text {attrs}>{escape(content)}</text>"
        if not register_only:
            self.body.append(markup)
        return markup

    def add(self, markup):
        self.body.append(markup)

    def counter(self, value, x, y, font, size, fill, start, duration, anchor="start", steps=18):
        frame = duration / steps
        for step in range(steps):
            shown = round(value * (1 - (1 - step / steps) ** 3))
            blink = anim("cc-blink", round(frame, 3), start + step * frame, "linear", "none")
            self.text(nombre(shown, font), x, y, font, size, fill, anchor, style=f"opacity:0;{blink}")
        self.text(nombre(value, font), x, y, font, size, fill, anchor, style=anim("cc-show", 0.01, start + duration, "linear"))

    def render(self):
        faces = "".join(font_face(key, chars) for key, chars in self.chars.items() if chars)
        motion = "*{animation:none!important}" if STATIC else "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        title = escape(self.title, {'"': "&quot;"})
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}" role="img" aria-label="{title}">'
            f"<title>{title}</title><style>{faces}{KEYFRAMES}{''.join(self.css)}{motion}</style>"
            + "".join(self.body)
            + "</svg>\n"
        )


def paper(card):
    card.add(
        f'<rect x=".75" y=".75" width="{card.width - 1.5}" height="{card.height - 1.5}" rx="16" '
        f'fill="{PAPER}" stroke="{LINE}" stroke-width="1.5"/>'
    )


def rule(card, x1, x2, y, delay):
    card.add(
        f'<path d="M{x1} {y}H{x2}" stroke="{LINE}" stroke-width="1.5" fill="none" pathLength="1" '
        f'stroke-dasharray="1" style="{anim("cc-draw", 0.9, delay)}"/>'
    )


def hero(today):
    tagline = "Je construis des logiciels qui font gagner du temps aux dirigeants de PME."
    card = Card(1200, 290, f"Clément Creuzenet. {tagline}")
    paper(card)

    name, size, x, baseline = "Clément Creuzenet", 120, 60, 146
    name_width = FONTS["serif"].width(name, size)
    clip_text = card.text(name, x, baseline, "serif", size, INK, register_only=True)
    card.add(
        f'<defs><clipPath id="nom">{clip_text}</clipPath>'
        f'<linearGradient id="reflet"><stop offset="0" stop-color="{COBALT}" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="{COBALT}" stop-opacity=".9"/>'
        f'<stop offset="1" stop-color="{COBALT}" stop-opacity="0"/></linearGradient></defs>'
    )
    card.text(name, x, baseline, "serif", size, INK, style=anim("cc-rise", 0.9, 0.1))
    travel = name_width + 320
    card.css.append(f"@keyframes cc-shine{{0%{{transform:translateX(0)}}35%,100%{{transform:translateX({travel:.0f}px)}}}}")
    card.add(
        f'<g clip-path="url(#nom)"><rect x="{x - 260}" y="20" width="220" height="160" fill="url(#reflet)" '
        f'style="{anim("cc-shine", 9, 1.6, "ease-in-out", "backwards", "infinite")}"/></g>'
    )
    card.add(
        f'<path d="M{x} 172H{x + name_width:.1f}" stroke="{COBALT}" stroke-width="3" fill="none" '
        f'pathLength="1" stroke-dasharray="1" style="{anim("cc-draw", 1.1, 0.55)}"/>'
    )

    tagline_size = 28
    assert FONTS["sans"].width(tagline, tagline_size) < card.width - 2 * x, "accroche trop longue"
    card.text(tagline, x, 220, "sans", tagline_size, "#2b2a27", style=anim("cc-fade", 0.8, 0.75))

    stack = "TYPESCRIPT · NEXT.JS · SUPABASE · VERCEL"
    updated = f"MIS À JOUR LE {today.day} {MOIS[today.month - 1].upper()} {today.year}"
    card.text(stack, x, 262, "mono", 16, GREY, tracking=1.2, style=anim("cc-fade", 0.8, 1.0))
    card.text(updated, card.width - x, 262, "mono", 16, GREY, "end", tracking=1.2, style=anim("cc-fade", 0.8, 1.1))
    return card


def tile(index, kicker, title, accent, footer, delay, body=None, items=None, pill=None):
    width, height, pad = 400, 380, 32
    card = Card(width, height, f"{title}. {body or ', '.join(name for name, _ in items)}")
    paper(card)
    card.add(
        f'<defs><clipPath id="bord"><rect width="{width}" height="{height}" rx="16"/></clipPath></defs>'
        f'<g clip-path="url(#bord)"><rect width="{width}" height="7" fill="{accent}" '
        f'style="transform-box:fill-box;transform-origin:0 0;{anim("cc-grow-x", 0.9, delay)}"/></g>'
    )
    card.text(f"0{index} · {kicker}", pad, 62, "mono-medium", 16, accent, tracking=1.6, style=anim("cc-fade", 0.6, delay + 0.1))

    if pill:
        pill_x = width - pad
        card.text(pill, pill_x, 62, "mono", 15, GREY, "end", tracking=1.2, style=anim("cc-fade", 0.6, delay + 0.15))
        dot_x = pill_x - FONTS["mono"].width(pill, 15, 1.2) - 12
        card.add(
            f'<g style="{anim("cc-fade", 0.6, delay + 0.15)}"><circle cx="{dot_x:.1f}" cy="56.5" r="5" fill="{accent}" '
            f'style="{anim("cc-pulse", 2.2, delay + 0.8, "ease-in-out", "both", "infinite")}"/></g>'
        )

    card.text(title, pad, 136, "serif", 62, INK, style=anim("cc-rise", 0.8, delay + 0.2))

    y = bottom = 184
    if body:
        for line in wrap(body, "sans", 20, width - 2 * pad):
            card.text(line, pad, y, "sans", 20, GREY, style=anim("cc-fade", 0.7, delay + 0.35))
            bottom, y = y, y + 28
    for step, (name, description) in enumerate(items or []):
        item_delay = delay + 0.35 + 0.15 * step
        card.text(name, pad, y, "mono-medium", 19, INK, style=anim("cc-fade", 0.6, item_delay))
        y += 26
        for line in wrap(description, "sans", 17, width - 2 * pad):
            card.text(line, pad, y, "sans", 17, GREY, style=anim("cc-fade", 0.6, item_delay + 0.05))
            bottom, y = y, y + 23
        y += 16
    assert bottom <= 300, f"tuile {title} : le texte déborde sur le pied ({bottom})"

    rule(card, pad, width - pad, 318, delay + 0.4)
    card.text(footer, pad, 354, "mono", 17, accent, style=anim("cc-fade", 0.6, delay + 0.55))
    card.add(
        f'<g style="{anim("cc-nudge", 3, delay + 1.6, "ease-in-out", "both", "infinite")}">'
        + card.text("↗", width - pad, 354, "mono", 20, accent, "end", style=anim("cc-fade", 0.6, delay + 0.55), register_only=True)
        + "</g>"
    )
    return card


def load_days():
    data = json.loads((ROOT / "data" / "contributions.json").read_text())
    weeks = [[(date.fromisoformat(day), count) for day, count in week] for week in data["weeks"]]
    return data["total"], weeks


def activity(total, weeks, today):
    card = Card(1200, 390, f"Activité GitHub : {total} contributions sur un an")
    paper(card)
    left, chart_right, base, top = 60, 800, 304, 118
    card.text("ACTIVITÉ · 12 DERNIERS MOIS", left, 66, "mono-medium", 16, GREY, tracking=1.6, style=anim("cc-fade", 0.6, 1.8))

    days = [day for week in weeks for day in week]
    per_month = {}
    for day, count in days:
        per_month[(day.year, day.month)] = per_month.get((day.year, day.month), 0) + count
    months = []
    year, month = today.year, today.month
    for _ in range(12):
        months.append((year, month))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    months.reverse()
    counts = [per_month.get(key, 0) for key in months]
    peak = max(counts) or 1

    slot = (chart_right - left) / 12
    bar_width = 38
    card.add(f'<path d="M{left} {base + 0.75}H{chart_right}" stroke="{LINE}" stroke-width="1.5" style="{anim("cc-fade", 0.6, 1.8)}"/>')
    for step, ((year, month), count) in enumerate(zip(months, counts)):
        x = left + step * slot + (slot - bar_width) / 2
        height = max(3, (base - top) * count / peak)
        fill = COBALT if count == peak and count > 0 else INK
        card.add(
            f'<rect x="{x:.1f}" y="{base - height:.1f}" width="{bar_width}" height="{height:.1f}" rx="3" fill="{fill}" '
            f'style="transform-box:fill-box;transform-origin:50% 100%;{anim("cc-grow-y", 0.8, 1.9 + 0.06 * step)}"/>'
        )
        centre = x + bar_width / 2
        card.text(nombre(count, "mono"), centre, base - height - 10, "mono", 15, GREY, "middle", style=anim("cc-fade", 0.5, 2.4 + 0.06 * step))
        card.text(MOIS[month - 1], centre, base + 30, "mono", 15, GREY, "middle", style=anim("cc-fade", 0.5, 1.9 + 0.06 * step))

    card.add(f'<path d="M840 104V{base + 30}" stroke="{LINE}" stroke-width="1.5" style="{anim("cc-fade", 0.6, 1.9)}"/>')
    stats_left, stats_right = 880, 1140
    card.counter(total, stats_left, 176, "serif", 96, INK, start=2.0, duration=1.3)
    card.text("contributions sur un an", stats_left, 210, "sans", 19, GREY, style=anim("cc-fade", 0.6, 2.1))
    rule(card, stats_left, stats_right, 240, 2.2)

    active_days = sum(1 for _, count in days if count > 0)
    best_week = max((sum(count for _, count in week) for week in weeks), default=0)
    streak = longest = 0
    for _, count in days:
        streak = streak + 1 if count > 0 else 0
        longest = max(longest, streak)
    rows = [("Jours actifs", active_days, ""), ("Meilleure semaine", best_week, ""), ("Plus longue série", longest, " j")]
    for step, (label, value, unit) in enumerate(rows):
        y = 280 + 36 * step
        card.text(label, stats_left, y, "sans", 18, GREY, style=anim("cc-fade", 0.6, 2.3 + 0.1 * step))
        if unit:
            card.text(unit.strip(), stats_right, y, "mono-medium", 19, INK, "end", style=anim("cc-fade", 0.6, 2.3 + 0.1 * step))
            value_x = stats_right - FONTS["mono-medium"].width(unit, 19)
        else:
            value_x = stats_right
        card.counter(value, value_x, y, "mono-medium", 19, INK, start=2.3 + 0.1 * step, duration=1.0, anchor="end", steps=12)
    return card


def main():
    today = datetime.now(ZoneInfo("Europe/Paris")).date()
    total, weeks = load_days()
    cards = {
        "hero": hero(today),
        "nextlink": tile(
            1, "PRODUIT", "NextLink", ORANGE, "nextlink.space", 1.1,
            body="Le bras droit numérique du dirigeant. Chaque lundi, les chiffres de sa semaine.",
            pill="EN PILOTE",
        ),
        "lacuzon": tile(
            2, "STUDIO", "Lacuzon", COBALT, "lacuzon.fr", 1.25,
            body="Sites internet et logiciels sur mesure pour artisans, PME et cabinets.",
        ),
        "open-source": tile(
            3, "DÉPÔTS PUBLICS", "Open source", GREEN, "github.com/clemcube", 1.4,
            items=[
                ("kbis-empire", "Jeu de gestion sur les vraies règles fiscales françaises."),
                ("seatbelt-lite", "Garde-fous pour Claude Code."),
            ],
        ),
        "activity": activity(total, weeks, today),
    }
    (ROOT / "cards").mkdir(exist_ok=True)
    for name, card in cards.items():
        svg = card.render()
        (ROOT / "cards" / f"{name}.svg").write_text(svg)
        print(f"cards/{name}.svg  {len(svg) / 1024:.0f} Ko")


if __name__ == "__main__":
    main()
