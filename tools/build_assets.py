import base64
import io
import json
import math
import re
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "src"
OUT = ROOT / "assets" / "manga"

PAPER = "#f2f0eb"
INK = "#111013"
INK_SOFT = "#3a383d"
RED = "#d7141f"
GOLD = "#e8a93a"
TONE = "#bdb9b2"

UNICODES = list(range(0x20, 0x7F)) + list(range(0xA0, 0x100)) + [0x2019, 0x2026]

FONT_FILES = {
    "Anton": "Anton.ttf",
    "Bangers": "Bangers.ttf",
    "Comic": "ComicNeue-Bold.ttf",
    "Mono": "JetBrainsMono-Bold.ttf",
}


class Font:
    def __init__(self, family, path):
        self.family = family
        self.tt = TTFont(path)
        self.upm = self.tt["head"].unitsPerEm
        self.cmap = self.tt.getBestCmap()
        self.hmtx = self.tt["hmtx"]
        self.woff2 = self._subset(path)

    def _subset(self, path):
        options = subset.Options()
        options.flavor = "woff2"
        options.layout_features = ["kern", "liga"]
        font = subset.load_font(str(path), options)
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=UNICODES)
        subsetter.subset(font)
        buffer = io.BytesIO()
        subset.save_font(font, buffer, options)
        return base64.b64encode(buffer.getvalue()).decode()

    def width(self, text, size, spacing=0.0):
        units = sum(self.hmtx[self.cmap.get(ord(ch), ".notdef")][0] for ch in text)
        return units * size / self.upm + spacing * max(len(text) - 1, 0)

    def wrap(self, text, size, max_width, spacing=0.0):
        lines, current = [], ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if current and self.width(candidate, size, spacing) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines


FONTS = {name: Font(name, SRC / "fonts" / file) for name, file in FONT_FILES.items()}


def font_face(*names):
    return "".join(
        f"@font-face{{font-family:'{FONTS[n].family}';src:url(data:font/woff2;base64,{FONTS[n].woff2}) format('woff2')}}"
        for n in names
    )


def image_uri(name):
    data = (SRC / name).read_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def svg(width, height, body, fonts, label):
    style = font_face(*fonts) + (
        ".an{font-family:'Anton',Impact,sans-serif}"
        ".bg{font-family:'Bangers',Impact,sans-serif}"
        ".cm{font-family:'Comic',sans-serif}"
        ".mo{font-family:'Mono',monospace}"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">'
        f"<title>{escape(label)}</title><style>{style}</style>{body}</svg>"
    )


def text(x, y, value, cls, size, fill=INK, anchor="start", spacing=0, extra=""):
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}"{ls} {extra}>{escape(value)}</text>'
    )


def sfx(x, y, value, size, rotate=-7, anchor="end"):
    return (
        f'<g transform="rotate({rotate} {x} {y})">'
        + text(x + 3, y + 3, value, "bg", size, INK, anchor)
        + text(x, y, value, "bg", size, RED, anchor, extra=f'stroke="{INK}" stroke-width="{size / 18:.1f}" paint-order="stroke"')
        + "</g>"
    )


def panel_frame(x, y, w, h, stroke=6):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{INK}" stroke-width="{stroke}"/>'


def panel_image(clip_id, x, y, w, h, href, align="xMidYMid", flip=False):
    transform = f' transform="translate({2 * x + w} 0) scale(-1 1)"' if flip else ""
    return (
        f'<clipPath id="{clip_id}"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath>'
        f'<g clip-path="url(#{clip_id})"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fff"/>'
        f'<image x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="{align} slice" href="{href}"{transform}/></g>'
        + panel_frame(x, y, w, h)
    )


def speedlines(cx, cy, inner, outer, count, color, opacity=1.0):
    lines = []
    for i in range(count):
        angle = 2 * math.pi * i / count + ((i * 13) % 7) / 60
        r1 = inner + (i * 29) % 40
        width = 2.4 if i % 3 == 0 else 1.1
        lines.append(
            f'<line x1="{cx + math.cos(angle) * r1:.1f}" y1="{cy + math.sin(angle) * r1:.1f}" '
            f'x2="{cx + math.cos(angle) * outer:.1f}" y2="{cy + math.sin(angle) * outer:.1f}" stroke-width="{width}"/>'
        )
    return f'<g stroke="{color}" stroke-opacity="{opacity}">' + "".join(lines) + "</g>"


def tone_pattern(pid):
    return (
        f'<pattern id="{pid}" width="8" height="8" patternUnits="userSpaceOnUse">'
        f'<circle cx="4" cy="4" r="1.5" fill="{TONE}"/></pattern>'
    )


def spiky(cx, cy, rx, ry, points, depth):
    coords = []
    for i in range(points * 2):
        angle = 2 * math.pi * i / (points * 2)
        k = 1 if i % 2 else 1 + depth * (0.7 + ((i * 37) % 10) / 25)
        coords.append(f"{cx + math.cos(angle) * rx * k:.1f} {cy + math.sin(angle) * ry * k:.1f}")
    return "M" + " L".join(coords) + "Z"


def bubble(cx, cy, lines, size, tail, max_w):
    comic = FONTS["Comic"]
    line_h = size * 1.18
    widest = max(comic.width(line, size) for line in lines)
    rx = min(max_w, widest) / 2 + size * 1.1
    ry = len(lines) * line_h / 2 + size * 0.95
    tx, ty = tail
    base_dx = rx * 0.22
    tail_path = f'<path d="M{cx - base_dx:.1f} {cy + (ry - 6 if ty > cy else -ry + 6):.1f} L{tx:.1f} {ty:.1f} L{cx + base_dx * 0.3:.1f} {cy + (ry - 6 if ty > cy else -ry + 6):.1f}Z" fill="#fff" stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>'
    body = (
        tail_path
        + f'<ellipse cx="{cx}" cy="{cy}" rx="{rx:.1f}" ry="{ry:.1f}" fill="#fff" stroke="{INK}" stroke-width="4"/>'
        + f'<path d="M{cx - base_dx + 3:.1f} {cy + (ry - 3 if ty > cy else -ry + 3):.1f} L{cx + base_dx * 0.3 - 3:.1f} {cy + (ry - 3 if ty > cy else -ry + 3):.1f}" stroke="#fff" stroke-width="6"/>'
    )
    first = cy - (len(lines) - 1) * line_h / 2 + size * 0.36
    for i, line in enumerate(lines):
        body += text(cx, first + i * line_h, line, "cm", size, INK, "middle")
    return body


W = 1280
EDGE = 8
TOP = 4
GUT = 16
CW = W - 2 * EDGE
STATS_URL = (
    "https://github-readme-stats-two-roan.vercel.app/api"
    "?username=Akayashuu&include_all_commits=true&number_format=long&disable_animations=true"
)
STATS_CACHE = SRC / "stats.json"


def load_stats():
    try:
        request = urllib.request.Request(STATS_URL, headers={"User-Agent": "akayashuu-readme"})
        desc = re.search(r"<desc[^>]*>([^<]+)</desc>", urllib.request.urlopen(request, timeout=30).read().decode())
        fields = {
            "commits": r"Total Commits\s*:\s*([\d,]+)",
            "prs": r"Total PRs\s*:\s*([\d,]+)",
            "issues": r"Total Issues\s*:\s*([\d,]+)",
            "contributed": r"Contributed to \(last year\)\s*:\s*([\d,]+)",
        }
        stats = {key: int(re.search(pattern, desc.group(1)).group(1).replace(",", "")) for key, pattern in fields.items()}
        STATS_CACHE.write_text(json.dumps(stats, indent=2) + "\n")
        return stats
    except Exception as error:
        print(f"live stats unavailable ({error}), using cache")
        return json.loads(STATS_CACHE.read_text())


ICONS = {
    path.stem: re.search(r' d="([^"]+)"', path.read_text()).group(1)
    for path in (SRC / "icons").glob("*.svg")
}


def icon(name, x, y, size, fill=INK):
    return f'<path transform="translate({x:.1f} {y:.1f}) scale({size / 24:.4f})" d="{ICONS[name]}" fill="{fill}"/>'


def box(x, y, w, h, fill="#fff"):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>' + panel_frame(x, y, w, h)


def band(title_a, title_b, label=None, tag=None, y=TOP):
    anton = FONTS["Anton"]
    out = box(EDGE, y, CW, 52, INK)
    out += text(EDGE + 20, y + 38, title_a, "an", 30, PAPER, spacing=1)
    out += text(EDGE + 20 + anton.width(title_a + "  ", 30, 1), y + 38, title_b, "an", 30, RED)
    if label:
        out += text(W - EDGE - 20, y + 32, label, "mo", 13, GOLD, "end", 2.4)
    if tag:
        out += text(W - EDGE - 20, y + 38, tag, "bg", 30, GOLD, "end", 1)
    return out


def build_cover():
    h = 688
    art_w, art_h = 744, 680
    col_x = EDGE + art_w + GUT
    col_w = W - EDGE - col_x
    anton, mono, comic = FONTS["Anton"], FONTS["Mono"], FONTS["Comic"]

    body = panel_image("art", EDGE, TOP, art_w, art_h, image_uri("hero.jpg"), "xMidYMin")
    body += f'<g transform="translate(6 6)"><path d="{spiky(206, 124, 158, 74, 13, 0.3)}" fill="{INK}"/></g>'
    body += f'<path d="{spiky(206, 124, 158, 74, 13, 0.3)}" fill="#fff" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
    body += text(206, 114, "YOU THERE!", "bg", 50, INK, "middle", 1)
    body += text(206, 148, "SCROLL DOWN AND", "bg", 25, INK, "middle", 0.5)
    body += text(206, 174, "BEHOLD MY REPOS!", "bg", 25, RED, "middle", 0.5)

    body += box(col_x, TOP, col_w, 52, INK)
    body += text(col_x + 18, TOP + 33, "VOL.", "mo", 14, PAPER, spacing=3) + text(col_x + 70, TOP + 33, "01", "mo", 14, GOLD, spacing=3)
    body += text(col_x + col_w - 18, TOP + 33, "VSK STUDIO PRESENTS", "mo", 14, PAPER, "end", 3)

    narration = (
        "France, present day. One founder, two partners, no investors. He forges a Discord RPG "
        "played on 15,000 servers, builds analytics that speak eleven frameworks, and runs every "
        "service on machines he hardens himself."
    )
    cap_size = 17.5
    cap_lines = comic.wrap(narration, cap_size, col_w - 36)
    cap_h = 46 + len(cap_lines) * 23 + 12
    cap_y = TOP + art_h - cap_h

    title_y = TOP + 52 + GUT
    body += box(col_x, title_y, col_w, cap_y - GUT - title_y, PAPER)
    body += text(col_x + 20, title_y + 36, "A FULLSTACK CHRONICLE", "mo", 13, RED, spacing=2.6)
    title_size = 100
    for i, (word, color) in enumerate([("AKA", INK), ("YASHUU", INK), ("SHIPS.", RED)]):
        body += text(col_x + 18, title_y + 128 + i * 108, word, "an", title_size, color, spacing=1)
    for i, line in enumerate(["FULLSTACK FOUNDER,", "THREE THOUSAND COMMITS AT ONCE"]):
        body += text(col_x + 20, title_y + 386 + i * 31, line, "an", 25, INK_SOFT, spacing=0.8)

    body += box(col_x, cap_y, col_w, cap_h)
    body += text(col_x + 18, cap_y + 28, "NARRATION", "mo", 12, RED, spacing=2.4)
    for i, line in enumerate(cap_lines):
        body += text(col_x + 18, cap_y + 54 + i * 23, line, "cm", cap_size, INK)

    assert title_y + 417 + 14 < cap_y - GUT, (title_y, cap_y)
    assert anton.width("YASHUU", title_size) < col_w - 32
    return svg(W, h, body, ["Anton", "Bangers", "Comic", "Mono"], "Akayashuu ships: a fullstack chronicle")


def build_strip(commits):
    top = TOP + 52 + GUT
    pw = (CW - 3 * GUT) / 4
    ph = pw * 4 / 3
    h = int(top + ph + TOP)
    comic = FONTS["Comic"]
    body = f'<defs>{tone_pattern("tone")}</defs>'
    body += band("NOBU", "EXPLAINS", "A 4-PANEL INTRODUCTION")
    xs = [EDGE + i * (pw + GUT) for i in range(4)]
    chibi, face = image_uri("chibi.jpg"), image_uri("chibi-face.jpg")

    body += panel_image("k1", xs[0], top, pw, ph, chibi, "xMidYMin")
    body += panel_image("k2", xs[1], top, pw, ph, face)
    body += panel_image("k4", xs[3], top, pw, ph, face, flip=True)

    x3 = xs[2]
    body += f'<clipPath id="k3"><rect x="{x3}" y="{top}" width="{pw}" height="{ph}"/></clipPath>'
    body += f'<g clip-path="url(#k3)"><rect x="{x3}" y="{top}" width="{pw}" height="{ph}" fill="#fff"/>'
    body += f'<rect x="{x3}" y="{top}" width="{pw}" height="{ph}" fill="url(#tone)"/>'
    body += speedlines(x3 + pw / 2, top + ph / 2, 80, 420, 76, INK)
    body += f'<ellipse cx="{x3 + pw / 2}" cy="{top + ph / 2}" rx="104" ry="118" fill="#fff" opacity=".9"/></g>'
    body += panel_frame(x3, top, pw, ph)
    body += sfx(x3 + pw / 2 + 4, top + ph / 2 - 20, "BRRRT!", 62, -8, "middle")
    body += text(x3 + pw / 2, top + ph / 2 + 50, f"{commits:,}", "an", 52, INK, "middle")
    body += text(x3 + pw / 2, top + ph / 2 + 78, "COMMITS FIRED", "cm", 17, INK, "middle")

    lines = [
        (0, ["NOBU IS HERE!"]),
        (1, ["THIS GUY? AKAYASHUU.", "HE RUNS VSK STUDIO", "WITH TWO PARTNERS."]),
        (3, ["AND HE DEPLOYS", "ON FRIDAYS.", "LUCK RANK: E."]),
    ]
    for idx, bubble_lines in lines:
        cx = xs[idx] + pw / 2
        cy = top + ph - 74 - (len(bubble_lines) - 1) * 10
        body += bubble(cx, cy, bubble_lines, 17, (cx - 34, cy - 76 - len(bubble_lines) * 8), pw - 40)
        assert max(comic.width(l, 17) for l in bubble_lines) < pw - 40
    return svg(W, h, body, ["Anton", "Bangers", "Comic", "Mono"], f"Nobu explains: {commits:,} commits fired")


WEAPONS = [("typescript", "TYPESCRIPT"), ("rust", "RUST"), ("go", "GO"), ("svelte", "SVELTE"), ("php", "PHP")]


def build_profile():
    side = 440
    h = side + 2 * TOP
    sx = EDGE + side + GUT
    sw = W - EDGE - sx
    anton, mono = FONTS["Anton"], FONTS["Mono"]
    body = f'<filter id="gray"><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncR type="linear" slope="1.25" intercept="-.1"/><feFuncG type="linear" slope="1.25" intercept="-.1"/><feFuncB type="linear" slope="1.25" intercept="-.1"/></feComponentTransfer></filter>'
    body += f'<clipPath id="face"><rect x="{EDGE}" y="{TOP}" width="{side}" height="{side}"/></clipPath>'
    body += f'<g clip-path="url(#face)"><image x="{EDGE}" y="{TOP}" width="{side}" height="{side}" preserveAspectRatio="xMidYMid slice" href="{image_uri("chibi-face.jpg")}" filter="url(#gray)"/></g>'
    body += panel_frame(EDGE, TOP, side, side)
    body += f'<rect x="{EDGE}" y="{TOP + side - 40}" width="216" height="40" fill="{RED}"/>'
    body += text(EDGE + 16, TOP + side - 14, "CHARACTER FILE", "mo", 15, "#fff", spacing=2.4)

    body += box(sx, TOP, sw, side)
    body += text(sx + 28, TOP + 78, "AKAYASHUU", "an", 68, INK, spacing=1)
    body += text(sx + sw - 28, TOP + 70, "LV. 99", "an", 34, RED, "end", 1)
    value_x = sx + 188
    facts = [("CLASS", "Founder (Archer)"), ("BASE", "France, Arch Linux + Hyprland")]
    for i, (k, v) in enumerate(facts):
        y = TOP + 130 + i * 38
        body += text(sx + 28, y, k, "mo", 15, RED, spacing=2)
        body += text(value_x, y + 1, v, "cm", 22, INK)

    wy = TOP + 206
    body += text(sx + 28, wy, "WEAPONS", "mo", 15, RED, spacing=2)
    cx = value_x
    for slug, name in WEAPONS:
        cw = 22 + 10 + mono.width(name, 13, 1.2) + 22
        body += f'<rect x="{cx:.1f}" y="{wy - 24}" width="{cw:.1f}" height="36" fill="#fff" stroke="{INK}" stroke-width="3"/>'
        body += icon(slug, cx + 11, wy - 17, 22)
        body += text(cx + 43, wy + 0.5, name, "mo", 13, INK, spacing=1.2)
        cx += cw + 10
    assert cx < sx + sw - 20, cx

    body += text(sx + 28, TOP + 254, "NOBLE PH.", "mo", 15, RED, spacing=2)
    body += text(value_x, TOP + 255, "Three Thousand Worlds: ship every project at once", "cm", 22, INK)
    body += f'<line x1="{sx + 28}" y1="{TOP + 280}" x2="{sx + sw - 28}" y2="{TOP + 280}" stroke="{INK}" stroke-width="3" stroke-dasharray="10 6"/>'

    ranks = {"E": 1, "B": 4, "A": 5, "A+": 5, "A++": 6, "EX": 6}
    params = [("STR", "backend", "A"), ("END", "uptime", "A+"), ("AGI", "shipping", "A++"),
              ("MANA", "rust", "B"), ("LUCK", "friday deploys", "E"), ("NP", "projects", "EX")]
    col_gap = 36
    col_w = (sw - 56 - col_gap) / 2
    for i, (k, sub, rank) in enumerate(params):
        cx = sx + 28 + (i // 3) * (col_w + col_gap)
        cy = TOP + 322 + (i % 3) * 44
        color = RED if rank == "EX" else INK
        body += text(cx, cy, k, "mo", 19, INK)
        body += text(cx, cy + 16, sub.upper(), "mo", 10.5, INK_SOFT, spacing=1.2)
        body += text(cx + 160, cy + 6, rank, "an", 30, color, "end")
        seg_w = (col_w - 180) / 6
        for s in range(6):
            fill = color if s < ranks[rank] else "#fff"
            bx = cx + 176 + s * seg_w
            body += f'<rect x="{bx:.1f}" y="{cy - 14}" width="{seg_w - 5:.1f}" height="20" fill="{fill}" stroke="{INK}" stroke-width="2.5" transform="skewX(-18) translate({(cy - 4) * math.tan(math.radians(18)):.1f} 0)"/>'
    assert anton.width("AKAYASHUU", 68, 1) < sw - 200
    return svg(W, h, body, ["Anton", "Comic", "Mono"], "Character file: Akayashuu. Founder (Archer). TypeScript, Rust, Go, Svelte, PHP.")


def build_band_svg(name, title_a, title_b, label=None, tag=None):
    body = band(title_a, title_b, label, tag)
    (OUT / f"{name}.svg").write_text(svg(W, 60, body, ["Anton", "Bangers", "Mono"], f"{title_a} {title_b}"))


CHAPTERS = [
    ("vskstudio", "VSK Studio", "Web studio for SaaS and e-commerce", "BOOM!", "col-vskstudio.jpg"),
    ("takt", "Takt", "Privacy-friendly, self-hosted analytics", "TICK TICK", "col-takt.jpg"),
    ("naht", "Naht", "Conflict-safe FS sync for Roblox Studio", "SNIP!", "col-naht.jpg"),
    ("enderbot", "EnderBot", "A full RPG inside Discord", "CLANG!", "col-ender.jpg"),
    ("herrscher", "Herrscher", "Discord to AI agents, one worktree per session", "ZAP!", None),
    ("ganyu", "Ganyu", "Discord bot: economy, levels, gacha", "PING!", "col-ganyu.jpg"),
    ("neublox", "Neublox", "MCP hub between AI and creation tools", "BZZT!", None),
    ("karamon", "Karamon", "Cobblemon server with its own launcher", "CRACK!", "col-karamon.jpg"),
]


def build_chapter(index, slug, name, desc, sound, image):
    w, h = 320, 308
    px, py, pw, ph = EDGE, TOP, w - 2 * EDGE, h - 2 * TOP
    ih = 196
    comic = FONTS["Comic"]
    body = f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" fill="{PAPER}"/>'
    body += f'<clipPath id="p"><rect x="{px}" y="{py}" width="{pw}" height="{ih}"/></clipPath><g clip-path="url(#p)">'
    if image:
        body += f'<image x="{px}" y="{py}" width="{pw}" height="{ih}" preserveAspectRatio="xMidYMin slice" href="{image_uri(image)}"/></g>'
    else:
        body += f'<rect x="{px}" y="{py}" width="{pw}" height="{ih}" fill="{INK}"/>'
        body += speedlines(px + pw / 2, py + ih / 2, 58, 320, 64, PAPER, 0.35) + "</g>"
        body += text(px + pw / 2, py + ih / 2 + 20, name.upper(), "an", 46, PAPER, "middle", 1)
    body += f'<line x1="{px}" y1="{py + ih}" x2="{px + pw}" y2="{py + ih}" stroke="{INK}" stroke-width="5"/>'
    body += panel_frame(px, py, pw, ph)
    body += f'<rect x="{px}" y="{py}" width="72" height="26" fill="{INK}"/>'
    body += text(px + 10, py + 18, f"CH.{index:02d}", "mo", 12.5, PAPER, spacing=1.6)
    body += sfx(px + pw - 10, py + ih - 12, sound, 38)
    body += text(px + 14, py + ih + 40, name.upper(), "an", 28, INK)
    lines = comic.wrap(desc, 15, pw - 28)
    assert len(lines) <= 2, desc
    for i, line in enumerate(lines):
        body += text(px + 14, py + ih + 64 + i * 18, line, "cm", 15, INK_SOFT)
    (OUT / f"ch-{slug}.svg").write_text(svg(w, h, body, ["Anton", "Bangers", "Comic", "Mono"], f"Chapter {index}: {name}. {desc}"))


SIDE_STORIES = [
    ("naht", "Bidirectional, conflict-safe sync between your filesystem and Roblox Studio.", ["rust"]),
    ("herrscher", "Self-hosted daemon bridging Discord to AI agents, one git worktree per session.", ["go"]),
    ("dctl", "Pure, dependency-free Discord client library.", ["go"]),
    ("takt-*", "Takt SDKs for React, Vue, Svelte, Solid, Angular, Astro, Laravel, Symfony, WordPress and MCP.", ["typescript", "php"]),
    ("enderbot-sdk", "Typed client and CLI for the EnderBot wiki API, zero dependencies.", ["typescript"]),
    ("cryptobar", "Crypto prices for Quickshell, Waybar and the terminal, no API key.", ["rust"]),
    ("promethee-linux", "Promethee, packaged and patched for Linux.", ["javascript"]),
]


def build_side_stories():
    top = TOP + 52 + GUT
    cols, rows = 2, 4
    cw = (CW - GUT) / cols
    ch = 132
    h = int(top + rows * ch + (rows - 1) * GUT + TOP)
    anton, comic = FONTS["Anton"], FONTS["Comic"]
    body = band("SIDE STORIES", "OPEN SOURCE, TAKE THEM", tag="FREE!")
    for i, (name, desc, tags) in enumerate(SIDE_STORIES):
        x = EDGE + (i % cols) * (cw + GUT)
        y = top + (i // cols) * (ch + GUT)
        body += box(x, y, cw, ch, PAPER)
        body += f'<rect x="{x}" y="{y}" width="92" height="{ch}" fill="{INK}"/>'
        body += text(x + 46, y + ch / 2 + 22, f"{i + 1:02d}", "an", 58, RED, "middle")
        body += text(x + 46, y + 30, "EP.", "mo", 12, PAPER, "middle", 2)
        tx = x + 116
        body += text(tx, y + 50, name.upper(), "an", 32, INK, spacing=0.6)
        ix = x + cw - 26
        for tag in reversed(tags):
            ix -= 30
            body += icon(tag, ix, y + 24, 26)
            ix -= 10
        lines = comic.wrap(desc, 18, cw - 116 - 28)
        assert len(lines) <= 2, desc
        for j, line in enumerate(lines):
            body += text(tx, y + 84 + j * 23, line, "cm", 18, INK_SOFT)
        assert anton.width(name.upper(), 32, 0.6) < ix - tx - 10, name
    x = EDGE + cw + GUT
    y = top + 3 * (ch + GUT)
    body += f'<clipPath id="more"><rect x="{x}" y="{y}" width="{cw}" height="{ch}"/></clipPath>'
    body += f'<g clip-path="url(#more)"><rect x="{x}" y="{y}" width="{cw}" height="{ch}" fill="{INK}"/>'
    body += speedlines(x + cw / 2, y + ch / 2, 40, 420, 70, PAPER, 0.25) + "</g>" + panel_frame(x, y, cw, ch)
    body += icon("github", x + 40, y + ch / 2 - 26, 52, PAPER)
    body += text(x + 116, y + 62, "MORE ON GITHUB", "an", 36, PAPER, spacing=1)
    body += text(x + 118, y + 92, "GITHUB.COM/AKAYASHUU", "mo", 14, GOLD, spacing=2)
    (OUT / "side-stories.svg").write_text(svg(W, h, body, ["Anton", "Bangers", "Comic", "Mono"], "Side stories: open source projects"))


def build_record(stats):
    ph = 340
    h = ph + 2 * TOP
    eye_w = 600
    rx = EDGE + eye_w + GUT
    rw = W - EDGE - rx
    anton, mono = FONTS["Anton"], FONTS["Mono"]
    body = f'<defs>{tone_pattern("tone")}</defs>'
    body += panel_image("eye", EDGE, TOP, eye_w, ph, image_uri("eye.jpg"))
    body += box(EDGE + 20, TOP + ph - 70, eye_w - 40, 50)
    body += text(EDGE + eye_w / 2, TOP + ph - 38, "NOBU KEEPS COUNT.", "cm", 21, INK, "middle")

    body += box(rx, TOP, rw, ph)
    body += text(rx + 28, TOP + 60, "BATTLE", "an", 40, INK)
    body += text(rx + 28 + anton.width("BATTLE ", 40), TOP + 60, "RECORD", "an", 40, RED)
    body += text(rx + rw - 28, TOP + 54, "LIVE", "mo", 12, RED, "end", 2.4)
    rows = [
        ("COMMITS, ALL TIME", stats["commits"], RED),
        ("PULL REQUESTS", stats["prs"], INK),
        ("ISSUES", stats["issues"], INK),
        ("REPOS CONTRIBUTED TO, LAST YEAR", stats["contributed"], INK),
    ]
    for i, (label, value, color) in enumerate(rows):
        y = TOP + 124 + i * 54
        value_text = f"{value:,}"
        vw = anton.width(value_text, 36)
        lw = mono.width(label, 13, 1.4)
        body += text(rx + 28, y, label, "mo", 13, INK_SOFT, spacing=1.4)
        body += f'<line x1="{rx + 40 + lw:.1f}" y1="{y}" x2="{rx + rw - 40 - vw:.1f}" y2="{y}" stroke="{TONE}" stroke-width="2.5" stroke-dasharray="2 6" stroke-linecap="round"/>'
        body += text(rx + rw - 28, y + 4, value_text, "an", 36, color, "end")
    label = f"Commits {stats['commits']:,}, PRs {stats['prs']:,}, issues {stats['issues']:,}, repos contributed to {stats['contributed']:,}"
    return svg(W, h, body, ["Anton", "Comic", "Mono"], f"Battle record. {label}")


def build_finale():
    ph = 360
    h = ph + 2 * TOP
    pw = 300
    anton = FONTS["Anton"]
    body = panel_image("chibi", EDGE, TOP, pw, ph, image_uri("chibi.jpg"), "xMidYMin")
    body += bubble(EDGE + pw / 2, TOP + 60, ["SEE YOU NEXT", "CHAPTER!"], 19, (EDGE + pw / 2 + 20, TOP + 140), pw - 60)
    rx = EDGE + pw + GUT
    rw = W - EDGE - rx
    body += box(rx, TOP, rw, ph)
    body += f'<defs>{tone_pattern("tone")}</defs><rect x="{rx + 3}" y="{TOP + 3}" width="{rw - 6}" height="{ph - 6}" fill="url(#tone)" opacity=".55"/>'
    body += text(rx + 40, TOP + 62, "FINAL PAGE", "mo", 14, RED, spacing=3)
    body += text(rx + 36, TOP + 148, "THAT'S ALL FOR", "an", 76, INK)
    body += text(rx + 36, TOP + 234, "VOLUME 01.", "an", 76, RED)
    body += text(rx + 40, TOP + 280, "Every chapter above is live. The next one is being written.", "cm", 20, INK)
    tbc = "TO BE CONTINUED"
    tw = FONTS["Bangers"].width(tbc, 34, 1.5) + 40
    bx, by = rx + rw - tw - 30, TOP + ph - 72
    body += f'<g transform="skewX(-10) translate({(by + 24) * math.tan(math.radians(10)):.1f} 0)"><rect x="{bx}" y="{by}" width="{tw:.1f}" height="48" fill="{INK}"/></g>'
    body += text(bx + tw / 2, by + 36, tbc, "bg", 34, PAPER, "middle", 1.5)
    assert anton.width("THAT'S ALL FOR", 76) < rw - 60
    return svg(W, h, body, ["Anton", "Bangers", "Comic", "Mono"], "That's all for volume 01. To be continued.")


def globe(x, y, size):
    r = size / 2
    cx, cy = x + r, y + r
    return (
        f'<g fill="none" stroke="{INK}" stroke-width="{size / 12:.1f}">'
        f'<circle cx="{cx}" cy="{cy}" r="{r - size / 24:.1f}"/>'
        f'<ellipse cx="{cx}" cy="{cy}" rx="{r * 0.42:.1f}" ry="{r - size / 24:.1f}"/>'
        f'<line x1="{x + size / 24:.1f}" y1="{cy}" x2="{x + size - size / 24:.1f}" y2="{cy}"/>'
        f'<path d="M{cx - r * 0.85:.1f} {cy - r * 0.5:.1f} H{cx + r * 0.85:.1f} M{cx - r * 0.85:.1f} {cy + r * 0.5:.1f} H{cx + r * 0.85:.1f}"/></g>'
    )


def portfolio_mark(x, y, size):
    return (
        f'<rect x="{x + size * 0.06:.1f}" y="{y + size * 0.14:.1f}" width="{size * 0.88:.1f}" height="{size * 0.72:.1f}" fill="none" stroke="{INK}" stroke-width="{size / 12:.1f}"/>'
        f'<rect x="{x + size * 0.06:.1f}" y="{y + size * 0.14:.1f}" width="{size * 0.88:.1f}" height="{size * 0.18:.1f}" fill="{INK}"/>'
        f'<path d="M{x + size * 0.22:.1f} {y + size * 0.72:.1f} L{x + size * 0.42:.1f} {y + size * 0.48:.1f} L{x + size * 0.56:.1f} {y + size * 0.62:.1f} L{x + size * 0.66:.1f} {y + size * 0.52:.1f} L{x + size * 0.8:.1f} {y + size * 0.72:.1f}Z" fill="{RED}"/>'
    )


def linkedin_mark(x, y, size):
    return (
        f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{size * 0.14:.1f}" fill="{INK}"/>'
        + text(x + size / 2, y + size * 0.8, "in", "an", size * 0.78, PAPER, "middle")
    )


CONTACTS = [
    ("vskstudio", "STUDIO", "VSKSTUDIO.FR", lambda x, y, s: globe(x, y, s)),
    ("portfolio", "PORTFOLIO", "SAUVAGEL.XYZ", portfolio_mark),
    ("x", "X", "@AKAYASHUU", lambda x, y, s: icon("x", x, y, s)),
    ("linkedin", "LINKEDIN", "PRO PROFILE", linkedin_mark),
    ("discord", "DISCORD", "AKAYASHUU", lambda x, y, s: icon("discord", x, y, s)),
]


def build_contacts():
    w, h = W / len(CONTACTS), 132
    px, py, pw, ph = EDGE, TOP, w - 2 * EDGE, h - 2 * TOP
    for slug, title, handle, mark in CONTACTS:
        body = box(px, py, pw, ph, PAPER)
        body += f'<rect x="{px}" y="{py}" width="{pw}" height="8" fill="{RED}"/>'
        body += mark(px + pw / 2 - 20, py + 22, 40)
        body += text(px + pw / 2, py + 94, title, "an", 26, INK, "middle", 1.2)
        body += text(px + pw / 2, py + 114, handle, "mo", 11.5, RED, "middle", 1.6)
        (OUT / f"contact-{slug}.svg").write_text(svg(round(w, 2), h, body, ["Anton", "Mono"], f"{title}: {handle}"))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.svg"):
        stale.unlink()
    stats = load_stats()
    (OUT / "cover.svg").write_text(build_cover())
    (OUT / "strip.svg").write_text(build_strip(stats["commits"]))
    (OUT / "profile.svg").write_text(build_profile())
    build_band_svg("band-chapters", "CHAPTER", "LIST", "FLAGSHIP PROJECTS · CLICK A PANEL")
    for i, chapter in enumerate(CHAPTERS, start=1):
        build_chapter(i, *chapter)
    build_side_stories()
    (OUT / "record.svg").write_text(build_record(stats))
    (OUT / "finale.svg").write_text(build_finale())
    build_contacts()
    print("stats:", stats)
    for f in sorted(OUT.iterdir()):
        print(f"{f.name:28} {f.stat().st_size / 1024:8.1f} KiB")


if __name__ == "__main__":
    main()
