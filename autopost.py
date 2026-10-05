"""
autopost.py - generate the next quote image and publish it to Instagram.

Modes:
    python autopost.py generate            # make posts/NNN.jpg for the next quote
    python autopost.py post                # publish that image to Instagram
    python autopost.py post --dry-run      # show what would be posted

Needs quote_maker.py and quotes.json in the same folder.

Environment variables (set as GitHub Actions secrets):
    IG_USER_ID        Instagram account ID (numeric)
    IG_ACCESS_TOKEN   long-lived access token
Optional:
    IG_API_HOST       default graph.instagram.com (Instagram Login).
                      Use graph.facebook.com if your token came from Facebook Login.
    IG_API_VERSION    default v25.0
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import quote_maker as qm

QUOTES = Path("quotes.json")
STATE = Path("state.json")
POSTS = Path("posts")

API_HOST = os.getenv("IG_API_HOST", "graph.instagram.com")
API_VER = os.getenv("IG_API_VERSION", "v25.0")

HASHTAGS = {
    "motivation": "#motivation #mindset #selfgrowth #dailyquotes #positivevibes #keepgoing",
    "relationship": "#relationshipquotes #lovequotes #relationshipgoals #healthyrelationships #couplegoals #loveadvice",
}
COMMON_TAGS = "#quotes #wittywhispers"


def current():
    """Return (quote, index) for the next post. Order is shuffled but stable."""
    quotes = json.loads(QUOTES.read_text(encoding="utf-8"))
    n = json.loads(STATE.read_text())["next"] if STATE.exists() else 0
    if n >= len(quotes):
        sys.exit("No quotes left - add more to quotes.json (or reset state.json).")
    order = list(range(len(quotes)))
    random.Random(7).shuffle(order)
    return quotes[order[n]], n


def generate():
    q, n = current()
    POSTS.mkdir(exist_ok=True)
    rnd = random.Random(n)
    fonts = qm.find_fonts() or [None]
    img = qm.make_image(q["text"], "feed", rnd.choice(fonts), rnd.choice(qm.PALETTES))
    # Instagram's API accepts JPEG only for images
    path = POSTS / f"{n:03d}.jpg"
    img.convert("RGB").save(path, "JPEG", quality=95)
    print(f"generated {path}: {q['text']}")


def image_url(n):
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.getenv("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/posts/{n:03d}.jpg"


def build_caption(q):
    tags = HASHTAGS.get(q.get("category"), "")
    return f"{q['text']}\n\n.\n.\n{tags} {COMMON_TAGS}".strip()


def api(path, params, method="POST"):
    params = {**params, "access_token": os.environ["IG_ACCESS_TOKEN"]}
    url = f"https://{API_HOST}/{API_VER}/{path}"
    body = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Instagram API error {e.code}: {e.read().decode()}")


def wait_for_url(url, tries=12):
    """raw.githubusercontent.com can lag a few seconds after a push."""
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                if r.status == 200:
                    return
        except urllib.error.URLError:
            pass
        time.sleep(10)
    sys.exit(f"Image not reachable yet: {url}")


def post(dry_run=False):
    q, n = current()
    url = image_url(n) if "GITHUB_REPOSITORY" in os.environ else f"(local) posts/{n:03d}.jpg"
    caption = build_caption(q)
    if dry_run:
        print("IMAGE:", url)
        print("CAPTION:\n" + caption)
        return

    wait_for_url(url)
    ig_id = os.environ["IG_USER_ID"]
    container = api(f"{ig_id}/media", {"image_url": url, "caption": caption})["id"]

    for _ in range(12):
        status = api(container, {"fields": "status_code"}, "GET").get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            sys.exit(f"Container failed with status {status}")
        time.sleep(5)

    result = api(f"{ig_id}/media_publish", {"creation_id": container})
    print("published:", result)
    STATE.write_text(json.dumps({"next": n + 1}))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "generate":
        generate()
    elif mode == "post":
        post(dry_run="--dry-run" in sys.argv)
    else:
        sys.exit(__doc__)
