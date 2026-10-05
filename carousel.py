"""
wittywhispers carousel maker + Instagram auto-poster (free, stdlib + Pillow only).

Usage:
    python carousel.py generate      # render the next carousel into posts/carousel_N/
    python carousel.py post          # publish it to Instagram, advance state
    python carousel.py queries 5     # show each slide text next to the photo keyword it will search
    python carousel.py testphotos    # check your Pixabay/Unsplash/Pexels keys (start here if photos fail)
    python carousel.py preview 5     # render the first 5 carousels into preview/ (omit the number for all)

Env vars for posting: IG_USER_ID, IG_ACCESS_TOKEN
Optional: PEXELS_API_KEY, PIXABAY_API_KEY, UNSPLASH_ACCESS_KEY (free photo backgrounds), PHOTO_SOURCE, IG_API_HOST (default graph.instagram.com), GITHUB_REPOSITORY, GITHUB_REF_NAME
"""
import io, json, os, random, re, sys, time, urllib.request, urllib.parse, urllib.error
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
    "facts": "#didyouknow #factsdaily #amazingfacts #interestingfacts #knowledge #learnsomethingnew #wittywhispers",
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


# ---------- photo backgrounds (Unsplash and/or Pexels, both free) ----------
UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json,image/*;q=0.9,*/*;q=0.8",
}
USED = set()  # photo URLs already used in the current carousel (so no slide repeats a photo)
CREDITS = []  # photo credits for the current carousel (shown in caption)


def _get_json(url, headers):
    with urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **headers}), timeout=30) as r:
        return json.loads(r.read())


def _download(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return Image.open(io.BytesIO(r.read())).convert("RGB")


def _unsplash(query, rnd, count):
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not key:
        return []
    auth = {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"}
    results = []
    for page in dict.fromkeys([rnd.randint(1, 2), 1]):
        params = urllib.parse.urlencode({"query": query, "orientation": "portrait",
                                         "per_page": 20, "page": page, "content_filter": "high"})
        results = _get_json("https://api.unsplash.com/search/photos?" + params, auth).get("results", [])
        if results:
            break
    rnd.shuffle(results)
    out = []
    for ph in results:
        if len(out) >= count:
            break
        try:
            url = ph["urls"]["regular"]  # ~1080px wide
            if url in USED:
                continue
            img = _download(url)
            USED.add(url)
            try:  # Unsplash API guideline: register the download
                _get_json(ph["links"]["download_location"], auth)
            except Exception:
                pass
            out.append(img)
            CREDITS.append(f'{ph["user"]["name"]} (Unsplash)')
        except Exception as e:
            print("Unsplash photo failed:", e)
    return out


def _pixabay(query, rnd, count):
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    hits = []
    for page in dict.fromkeys([rnd.randint(1, 2), 1]):
        params = urllib.parse.urlencode({"key": key, "q": query, "image_type": "photo",
                                         "orientation": "vertical", "per_page": 20, "page": page,
                                         "safesearch": "true", "min_width": 800})
        hits = _get_json("https://pixabay.com/api/?" + params, {}).get("hits", [])
        if hits:
            break
    rnd.shuffle(hits)
    out = []
    for ph in hits:
        if len(out) >= count:
            break
        try:
            if ph["largeImageURL"] in USED:
                continue
            USED.add(ph["largeImageURL"])
            req = urllib.request.Request(ph["largeImageURL"], headers={**UA, "Referer": "https://pixabay.com/"})
            with urllib.request.urlopen(req, timeout=30) as r:
                out.append(Image.open(io.BytesIO(r.read())).convert("RGB"))
            CREDITS.append(f'{ph.get("user", "Pixabay")} (Pixabay)')
        except Exception as e:
            print("Pixabay photo failed:", e)
    return out


def _pexels(query, rnd, count):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    params = urllib.parse.urlencode({"query": query, "orientation": "portrait",
                                     "per_page": 20, "page": rnd.randint(1, 2)})
    photos = _get_json("https://api.pexels.com/v1/search?" + params, {"Authorization": key}).get("photos", [])
    rnd.shuffle(photos)
    out = []
    for ph in photos:
        if len(out) >= count:
            break
        try:
            if ph["src"]["large2x"] in USED:
                continue
            USED.add(ph["src"]["large2x"])
            out.append(_download(ph["src"]["large2x"]))
        except Exception as e:
            print("Pexels photo failed:", e)
    return out


def fetch_photos(query, seed, count=3):
    """Return up to `count` PIL images, or [] so the caller falls back to gradients.

    PHOTO_SOURCE=pixabay | unsplash | pexels | auto (default: tries every source that has a key, Pixabay first).
    """
    if not query:
        return []
    pref = os.environ.get("PHOTO_SOURCE", "auto").lower()
    order = {"unsplash": [_unsplash], "pexels": [_pexels], "pixabay": [_pixabay]}.get(
        pref, [_pixabay, _unsplash, _pexels])
    for provider in order:
        try:
            got = provider(query, random.Random(seed), count)
            if got:
                return got
        except Exception as e:
            print(f"{provider.__name__.strip('_')} failed, trying next source:", e)
    return []


def photo_background(img):
    """Cover-crop to W x H, then darken so white text stays readable."""
    scale = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
    left, top = (img.width - W) // 2, (img.height - H) // 2
    img = img.crop((left, top, left + W, top + H)).convert("RGBA")
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = shade.load()
    for y in range(H):
        a = int(110 + 80 * (abs(y - H / 2) / (H / 2)))  # darker at top and bottom edges
        for x in range(W):
            px[x, y] = (0, 0, 0, a)
    return Image.alpha_composite(img, shade)


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


def render_slide(kind, text, idx, total, palette, font_path, number=None, bg=None):
    c1, c2, ink = palette
    if bg is not None:
        img = photo_background(bg)
        ink = (255, 255, 255)
    else:
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


def cover_crop(img, w, h):
    scale = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
    left, top = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))


def render_fact_slide(text, idx, total, number, photo, font_path, palette):
    """Photo on top, fact in a dark panel below."""
    PH, pad = 680, 90
    c1, c2, _ = palette
    accent = (255, 214, 102)
    img = Image.new("RGBA", (W, H), (18, 22, 34, 255))
    if photo is not None:
        img.paste(cover_crop(photo, W, PH).convert("RGBA"), (0, 0))
    else:
        img.paste(gradient(c1, c2).crop((0, 0, W, PH)).convert("RGBA"), (0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((0, PH, W, PH + 8), fill=accent)
    d.text((pad, PH + 50), f"FACT {number:02d}", font=load_font(font_path, 40), fill=accent)
    font, lines, lh = fit_text(d, text, font_path, W - pad * 2, 400, start=70, minimum=40)
    y = PH + 125
    for line in lines:
        d.text((pad, y), line, font=font, fill=(255, 255, 255))
        y += lh
    d.text((pad, H - 100), HANDLE, font=load_font(font_path, 34), fill=(190, 195, 210))
    dot_r, gap = 9, 30
    x0 = W - pad - total * gap
    for i in range(total):
        cx = x0 + i * gap + dot_r
        col = (255, 255, 255) if i == idx else (110, 116, 135)
        d.ellipse((cx - dot_r, H - 80 - dot_r, cx + dot_r, H - 80 + dot_r), fill=col)
    return img.convert("RGB")


def render_carousel(item, out_dir, seed=None):
    rnd = random.Random(seed)
    palette = rnd.choice(PALETTES)
    fonts = fonts_available()
    font_path = rnd.choice(fonts) if fonts else None
    out_dir.mkdir(parents=True, exist_ok=True)

    CREDITS.clear()
    USED.clear()
    is_facts = item.get("category") == "facts"
    slides = [("hook", item["hook"], None, None)]
    for i, pt in enumerate(item["points"], 1):
        text, q = (pt["text"], pt.get("image")) if isinstance(pt, dict) else (pt, None)
        slides.append(("fact" if is_facts else "point", text, i, q))
    slides.append(("cta", item.get("cta", "Save this for the days you forget it."), None, None))

    # hook + closing slide use the carousel's overall topic; every other slide uses its OWN keyword
    cover = []
    for attempt in range(2):
        cover += fetch_photos(item.get("image"), (seed or 0) + attempt * 7, 2 - len(cover))
        if len(cover) >= 2:
            break
    if not cover:
        print("No photos found (set PIXABAY_API_KEY, UNSPLASH_ACCESS_KEY or PEXELS_API_KEY); using gradients.")

    def slide_photo(query, k):
        """Photo for this slide's own text: full keyword, then its first two words, then the carousel topic."""
        tries = [query, " ".join(query.split()[:2]) if query else None, item.get("image")]
        for n, qy in enumerate(dict.fromkeys(t for t in tries if t)):
            got = fetch_photos(qy, (seed or 0) * 100 + k + n * 50, 1)
            if got:
                return got[0]
        return None

    paths = []
    for i, (kind, text, num, q) in enumerate(slides):
        if kind == "hook":
            bg = cover[0] if len(cover) > 0 else None
        elif kind == "cta":
            bg = cover[1] if len(cover) > 1 else None  # gradient beats a repeated photo
        else:
            bg = slide_photo(q or item.get("image"), i)
        if kind == "fact":
            img = render_fact_slide(text, i, len(slides), num, bg, font_path, palette)
        else:
            img = render_slide(kind, text, i, len(slides), palette, font_path, num, bg)
        p = out_dir / f"slide_{i + 1:02d}.jpg"
        img.save(p, "JPEG", quality=92)
        paths.append(p)
    names = list(dict.fromkeys(CREDITS))
    (out_dir / "credits.json").write_text(json.dumps(names))
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


def build_caption(item, credits=None):
    tags = HASHTAGS.get(item.get("category", ""), "#wittywhispers")
    cap = item["caption"]
    if credits:
        cap += "\n\n\U0001F4F7 Photos: " + ", ".join(credits[:8])
    return f"{cap}\n\n{tags}"


def post_carousel(item, folder_rel, n_slides):
    user = os.environ["IG_USER_ID"]
    token = os.environ["IG_ACCESS_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    base = f"https://raw.githubusercontent.com/{repo}/{branch}/{folder_rel}"

    cred_file = HERE / folder_rel / "credits.json"
    credits = json.loads(cred_file.read_text()) if cred_file.exists() else []

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
        "caption": build_caption(item, credits), "access_token": token})["id"]

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


def test_photos():
    """python carousel.py testphotos  ->  checks each photo API key and saves a sample image."""
    tests = [
        ("Unsplash", "UNSPLASH_ACCESS_KEY",
         "https://api.unsplash.com/search/photos?query=sunrise&per_page=1",
         lambda k: {"Authorization": f"Client-ID {k}", "Accept-Version": "v1"},
         lambda j: (j["results"][0]["urls"]["small"], j["results"][0]["user"]["name"])),
        ("Pixabay", "PIXABAY_API_KEY",
         "https://pixabay.com/api/?key={key}&q=sunrise&image_type=photo&per_page=3",
         lambda k: {},
         lambda j: (j["hits"][0]["webformatURL"], j["hits"][0]["user"])),
        ("Pexels", "PEXELS_API_KEY",
         "https://api.pexels.com/v1/search?query=sunrise&per_page=1",
         lambda k: {"Authorization": k},
         lambda j: (j["photos"][0]["src"]["medium"], j["photos"][0]["photographer"])),
    ]
    for name, env, url, hdr, pick in tests:
        print(f"\n--- {name} ---")
        key = os.environ.get(env)
        if not key:
            print(f"{env} is NOT set in this terminal window. (Skipping)")
            continue
        if key != key.strip() or key[0] in "\"'":
            print("WARNING: the key has spaces or quote marks around it. Remove them.")
            key = key.strip().strip("\"'")
        shown = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "(too short)"
        print(f"Key found ({len(key)} characters), starts/ends with: {shown}")
        odd = [f"U+{ord(ch):04X}" for ch in key if not (ch.isascii() and (ch.isalnum() or ch in "-_"))]
        if odd:
            print("PROBLEM: the key contains hidden or unusual characters:", ", ".join(odd))
            print("Fix: type or copy the key again. Dashes copied from some pages become a different symbol.")
        if env == "PIXABAY_API_KEY" and not re.fullmatch(r"\d+-[0-9a-f]+", key):
            print("WARNING: Pixabay keys look like 12345678-abcdef0123... (digits, one dash, then letters/numbers).")
        print("Compare those first/last 4 characters with the key on pixabay.com/api/docs. Searching...")
        try:
            data = _get_json(url.replace("{key}", urllib.parse.quote(key)), hdr(key))
            img_url, who = pick(data)
            img = _download(img_url)
            out = HERE / f"test_{name.lower()}.jpg"
            img.save(out)
            print(f"OK. Photo by {who}, saved as {out.name} ({img.width}x{img.height}).")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:200].replace(key, "***")
            print(f"FAILED: HTTP {e.code}. {body}")
            if e.code == 429:
                print("Fix: too many requests. Wait a few minutes and retry.")
            elif e.code == 403 and name == "Pixabay":
                print("Fix: Pixabay blocked the request (403). Wait a few minutes, check your internet/VPN, and try again.")
            elif e.code == 400 and name == "Pixabay":
                print("Fix: Pixabay says the request is invalid. Check the API key on pixabay.com/api/docs (it is shown on that page when logged in).")
            elif e.code == 401:
                print("Fix: the key is wrong. For Unsplash use the ACCESS KEY (not the Secret Key). Copy it again.")
            elif e.code == 403:
                print("Fix: rate limit hit (Unsplash demo = 50 requests/hour) or key not allowed. Wait an hour and retry.")
            else:
                print("Fix: check your internet connection or try again later.")
        except (KeyError, IndexError):
            print("Key works but the search returned no photos. Try again.")
        except Exception as e:
            print("FAILED:", type(e).__name__, e)
    print("\nDone. If at least one source says OK, carousel.py can use photos.")


def show_queries(limit=None):
    """python carousel.py queries [N]: list every slide's text next to its photo keyword (fetches nothing)."""
    items = load_items()
    for n, it in enumerate(items[:limit] if limit else items, 1):
        print(f"\n#{n} [{it['category']}] {it['hook']}   (hook/closing photo: {it.get('image')})")
        for pt in it["points"]:
            t, q = (pt["text"], pt.get("image")) if isinstance(pt, dict) else (pt, None)
            print(f"   {t[:62]:<62} -> {q}")


# ---------- cli ----------
def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "generate"
    if cmd == "testphotos":
        return test_photos()
    if cmd == "queries":
        return show_queries(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    items = load_items()

    if cmd == "preview":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else len(items)
        for i, it in enumerate(items[:limit]):
            render_carousel(it, HERE / "preview" / f"carousel_{i + 1:03d}", seed=i)
            print(f"  done {i + 1}/{min(limit, len(items))}: {it['hook']}")
            time.sleep(2)  # be gentle with the photo APIs
        print(f"Rendered {min(limit, len(items))} carousels into preview/")
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
        sys.exit("Use: generate | post | preview | queries | testphotos")


if __name__ == "__main__":
    main()
