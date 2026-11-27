"""Videos de snakemagic.com para el comando snakemagic!.

Lee la página en vivo (la lista está en el <script> de index.html) y la guarda
en caché una hora, así los videos nuevos que se agreguen al sitio salen solos.
"""
import random
import re
import time

import requests

# "Enforce HTTPS" is on in GitHub Pages (Nov 2026)
SITE_URL = "https://snakemagic.com/"
# Respaldo por si el dominio no responde: el mismo index.html en GitHub
FALLBACK_URL = "https://raw.githubusercontent.com/snakemagic/snakemagic.github.io/main/index.html"
CACHE_SECONDS = 3600

YT = "https://www.youtube.com/watch?v="
VM = "https://vimeo.com/"

_cache = {"at": 0.0, "videos": []}

# const all=`id|título|duración ...` (videos de YouTube)
_ALL_RE = re.compile(r"const all=`(.*?)`", re.S)
_ALL_LINE_RE = re.compile(r"^([\w-]{11})\|(.+)\|(\d+:\d\d)\s*$")
# ['Título','Descripción','img','yt|vm','id','1:23'] (destacados)
_FEAT_RE = re.compile(
    r"\[(['\"])(.+?)\1,\s*(['\"]).*?\3,\s*'[^']*',\s*'(yt|vm)',\s*'([^']+)',\s*'(\d+:\d\d)'\]")


def parse_videos(html):
    videos, seen = [], set()
    for m in _FEAT_RE.finditer(html):
        title, src, vid, dur = m.group(2), m.group(4), m.group(5), m.group(6)
        if vid not in seen:
            seen.add(vid)
            videos.append({"title": title, "url": (VM if src == "vm" else YT) + vid, "dur": dur})
    block = _ALL_RE.search(html)
    if block:
        for line in block.group(1).splitlines():
            m = _ALL_LINE_RE.match(line.strip())
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                videos.append({"title": m.group(2), "url": YT + m.group(1), "dur": m.group(3)})
    return videos


def _download():
    for url in (SITE_URL, FALLBACK_URL):
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "treebot"})
            r.raise_for_status()
            videos = parse_videos(r.text)
            if videos:
                return videos
        except requests.exceptions.RequestException:
            continue
    return []


def get_videos():
    if not _cache["videos"] or time.time() - _cache["at"] > CACHE_SECONDS:
        videos = _download()
        if videos:
            _cache.update(at=time.time(), videos=videos)
    return _cache["videos"]


def random_video():
    """Devuelve el texto para GroupMe, o None si no se pudo leer el sitio."""
    videos = get_videos()
    if not videos:
        return None
    v = random.choice(videos)
    return f"🐍🧙 Snake Magic presents: {v['title']} ({v['dur']})\n{v['url']}\nMore at {SITE_URL}"
