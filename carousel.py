"""
wittywhispers carousel maker + Instagram auto-poster (free, stdlib + Pillow only).

Usage:
    python carousel.py generate      # render the next carousel into posts/carousel_N/
    python carousel.py post          # publish it to Instagram, advance state
    python carousel.py preview       # render ALL carousels into preview/ to skim them locally

Env vars for posting: IG_USER_ID, IG_ACCESS_TOKEN
Optional: IG_API_HOST (default graph.instagram.com), GITHUB_REPOSITORY, GITHUB_REF_NAME
"""
import json, os, random, sys, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
DATA = HERE / "carousels.json"
STATE = HERE / "carousel_state.json"
FONT_DIR = HERE / "fonts"
W, H = 1080, 1350  # 4:5 portrait, best size for carousels
HANDLE = "@wittywhispers4u"
API_HOST = os.environ.get("IG_API_HOST", "graph.instagram.com")
API_VER = "v21.0"

PALETTES = [
    ((255, 94, 98), (255, 153, 102), (255, 255, 255)),
    ((67, 67, 109), (136, 97, 163), (255, 255, 255)),
    ((17, 153, 142), (56, 239, 125), (20, 30, 30)),
    ((255, 175, 189), (255, 195, 160), (60, 20, 40)),
    ((20, 30, 48), (36, 59, 85), (255, 255, 255)),
    ((252, 227, 138), (243, 129, 129), (50, 25, 25)),
    ((106, 17, 203), (37, 117, 252), (255, 255, 255)),
    ((30, 30, 30), (70, 70, 70), (255, 214, 102)),
]

HASHTAGS = {
    "relationships": "#relationshipquotes #lovequotes #relationshipadvice #datingadvice #selflove #healthyrelationships #wittywhispers",
    "motivation": "#motivationalquotes #mindset #selfgrowth #dailymotivation #selfimprovement #growthmindset #wittywhispers",
}


# ---------- rendering helpers ----------
def gradient(c1, c2):
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        row = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        for x in range(W):
            px[x, y] = row
    return img


def fonts_available():
    return sorted(FONT_DIR.glob("*.ttf")) + sorted(FONT_DIR.glob("*.otf")) if FONT_DIR.exists() else []


def load_font(path, size):
    try:
        if path:
            return ImageFont.truetype(str(path), size)
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except Exception:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


def wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_text(draw, text, font_path, max_w, max_h, start=110, minimum=44):
    size = start
    while size >= minimum:
        font = load_font(font_path, size)
        lines = wrap(draw, text, font, max_w)
        line_h = int(size * 1.25)
        if len(lines) * line_h <= max_h:
            return font, lines, line_h
        size -= 4
    font = load_font(font_path, minimum)
    return font, wrap(draw, text, font, max_w), int(minimum * 1.25)


def draw_centered(draw, lines, font, line_h, fill, cy, shadow=True):
    total = len(lines) * line_h
    y = cy - total // 2
    for line in lines:
        w = draw.textlength(line, font=font)
        x = (W - w) / 2
        if shadow:
            draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 70))
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h


def render_slide(kind, text, idx, total, palette, font_path, number=None):
    c1, c2, ink = palette
    img = gradient(c1, c2).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    pad = 110
    max_w = W - pad * 2

    if kind == "hook":
        font, lines, lh = fit_text(d, text, font_path, max_w, 760, start=120)
        draw_centered(d, lines, font, lh, ink, H // 2 - 40)
        hint = load_font(font_path, 40)
        d.text((W - pad - d.textlength("swipe  \u2192", font=hint), H - 190), "swipe  \u2192", font=hint, fill=ink)
    elif kind == "point":
        if number is not None:
            badge = load_font(font_path, 150)
            label = f"{number:02d}"
            d.text((pad, 150), label, font=badge, fill=(*ink, 120) if len(ink) == 3 else ink)
        font, lines, lh = fit_text(d, text, font_path, max_w, 640, start=86)
        draw_centered(d, lines, font, lh, ink, H // 2 + 60)
    else:  # cta
        font, lines, lh = fit_text(d, text, font_path, max_w, 560, start=90)
        draw_centered(d, lines, font, lh, ink, H // 2 - 20)
        small = load_font(font_path, 42)
        sub = "save  \u2022  share  \u2022  follow"
        d.text(((W - d.textlength(sub, font=small)) / 2, H - 260), sub, font=small, fill=ink)

    # footer: handle + progress dots
    foot = load_font(font_path, 34)
    d.text((pad, H - 110), HANDLE, font=foot, fill=ink)
    dot_r, gap = 9, 30
    x0 = W - pad - (total * gap)
    for i in range(total):
        cx = x0 + i * gap + dot_r
        fillc = ink if i == idx else (*ink, 90)
        d.ellipse((cx - dot_r, H - 100 - dot_r + 20, cx + dot_r, H - 100 + dot_r + 20), fill=fillc)

    return Image.alpha_composite(img, overlay).convert("RGB")


def render_carousel(item, out_dir, seed=None):
    rnd = random.Random(seed)
    palette = rnd.choice(PALETTES)
    fonts = fonts_available()
    font_path = rnd.choice(fonts) if fonts else None
    out_dir.mkdir(parents=True, exist_ok=True)

    slides = [("hook", item["hook"], None)]
    for i, p in enumerate(item["points"], 1):
        slides.append(("point", p, i))
    slides.append(("cta", item.get("cta", "Save this for the days you forget it."), None))

    paths = []
    for i, (kind, text, num) in enumerate(slides):
        img = render_slide(kind, text, i, len(slides), palette, font_path, num)
        p = out_dir / f"slide_{i + 1:02d}.jpg"
        img.save(p, "JPEG", quality=92)
        paths.append(p)
    return paths


# ---------- state ----------
def load_items():
    items = json.loads(DATA.read_text(encoding="utf-8"))
    # fixed shuffle so categories alternate but order is stable run to run
    random.Random(2026).shuffle(items)
    return items


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"next": 0}


def save_state(s):
    STATE.write_text(json.dumps(s, indent=2))


# ---------- instagram ----------
def api(method, path, params):
    url = f"https://{API_HOST}/{API_VER}/{path}"
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        token = os.environ.get("IG_ACCESS_TOKEN", "")
        sys.exit(f"Instagram API error {e.code}: {body.replace(token, '***') if token else body}")


def wait_public(url, tries=12):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(10)
    return False


def build_caption(item):
    tags = HASHTAGS.get(item.get("category", ""), "#wittywhispers")
    return f"{item['caption']}\n\n{tags}"


def post_carousel(item, folder_rel, n_slides):
    user = os.environ["IG_USER_ID"]
    token = os.environ["IG_ACCESS_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    base = f"https://raw.githubusercontent.com/{repo}/{branch}/{folder_rel}"

    child_ids = []
    for i in range(1, n_slides + 1):
        url = f"{base}/slide_{i:02d}.jpg"
        if not wait_public(url):
            sys.exit(f"Image not publicly reachable yet: {url}")
        res = api("POST", f"{user}/media", {
            "image_url": url, "is_carousel_item": "true", "access_token": token})
        child_ids.append(res["id"])
        print("child", i, res["id"])

    parent = api("POST", f"{user}/media", {
        "media_type": "CAROUSEL", "children": ",".join(child_ids),
        "caption": build_caption(item), "access_token": token})["id"]

    for _ in range(20):
        st = api("GET", parent, {"fields": "status_code", "access_token": token}).get("status_code")
        print("status:", st)
        if st == "FINISHED":
            break
        if st in ("ERROR", "EXPIRED"):
            sys.exit(f"Container failed with status {st}")
        time.sleep(6)

    pub = api("POST", f"{user}/media_publish", {"creation_id": parent, "access_token": token})
    print("Published:", pub)


# ---------- cli ----------
def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "generate"
    items = load_items()

    if cmd == "preview":
        for i, it in enumerate(items):
            render_carousel(it, HERE / "preview" / f"carousel_{i + 1:03d}", seed=i)
        print(f"Rendered {len(items)} carousels into preview/")
        return

    state = load_state()
    n = state["next"]
    if n >= len(items):
        sys.exit("All carousels used. Add more to carousels.json.")
    item = items[n]
    folder = HERE / "posts" / f"carousel_{n + 1:03d}"

    if cmd == "generate":
        paths = render_carousel(item, folder, seed=n)
        print(f"Generated {len(paths)} slides in {folder}")
    elif cmd == "post":
        slides = len(list(folder.glob("slide_*.jpg")))
        if not slides:
            sys.exit("Run generate first.")
        post_carousel(item, f"posts/carousel_{n + 1:03d}", slides)
        state["next"] = n + 1
        save_state(state)
    else:
        sys.exit("Use: generate | post | preview")


if __name__ == "__main__":
    main()
