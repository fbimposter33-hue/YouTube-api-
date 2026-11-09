
import json
import os
import re
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler

import yt_dlp

MAX_URL_LENGTH = 2048
MAX_FORMATS = 50

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtube-nocookie.com",
}


def validate_url(url):
    if not isinstance(url, str) or not url.strip():
        raise ValueError("YouTube URL is required.")

    url = url.strip()

    if len(url) > MAX_URL_LENGTH:
        raise ValueError("URL is too long.")

    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise ValueError("Only HTTPS URLs are allowed.")

    host = (parsed.hostname or "").lower()

    if host not in ALLOWED_HOSTS:
        raise ValueError("Only YouTube URLs are supported.")

    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed.")

    if host == "youtu.be":
        video_id = parsed.path.strip("/")
    else:
        video_id = parse_qs(parsed.query).get("v", [""])[0]

    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
        raise ValueError("Invalid YouTube video URL.")

    return url


def extract_video(url):
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
        "socket_timeout": 20,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise RuntimeError("Could not extract video information.")

    formats = []

    for item in info.get("formats", []):
        if item.get("vcodec") in (None, "none"):
            continue

        height = item.get("height")

        formats.append({
            "format_id": item.get("format_id"),
            "quality": f"{height}p" if height else item.get("format_note"),
            "height": height,
            "width": item.get("width"),
            "ext": item.get("ext"),
            "fps": item.get("fps"),
            "filesize": (
                item.get("filesize")
                or item.get("filesize_approx")
            ),
            "video_codec": item.get("vcodec"),
            "audio_codec": item.get("acodec"),
            "has_audio": item.get("acodec") not in (None, "none"),
        })

    formats.sort(
        key=lambda x: (
            x["height"] or 0,
            x["has_audio"]
        ),
        reverse=True
    )

    return {
        "title": info.get("title"),
        "video_id": info.get("id"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader"),
        "view_count": info.get("view_count"),
        "formats": formats[:MAX_FORMATS],
        "format_count": min(len(formats), MAX_FORMATS),
        "download_supported": False,
        "note": (
            "This Vercel API provides video information and "
            "format metadata, not downloadable media files."
        )
    }


class handler(BaseHTTPRequestHandler):

    def send_json(self, status, data):
        body = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header(
            "Content-Length",
            str(len(body))
        )
        self.send_header(
            "Access-Control-Allow-Origin",
            os.getenv("CORS_ORIGIN", "*")
        )
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header(
            "Access-Control-Allow-Origin",
            os.getenv("CORS_ORIGIN", "*")
        )
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path not in ("/", "/api"):
            self.send_json(404, {
                "success": False,
                "error": "Endpoint not found."
            })
            return

        params = parse_qs(parsed.query)

        if params.get("health") == ["1"]:
            self.send_json(200, {
                "success": True,
                "status": "online",
                "service": "YouTube Downloader API"
            })
            return

        url = params.get("url", [None])[0]

        if not url:
            self.send_json(400, {
                "success": False,
                "error": "Missing required parameter: url"
            })
            return

        try:
            url = validate_url(url)
            result = extract_video(url)

            self.send_json(200, {
                "success": True,
                "data": result
            })

        except ValueError as exc:
            self.send_json(400, {
                "success": False,
                "error": str(exc)
            })

        except Exception as exc:
            print("Extraction error:", type(exc).__name__)

            self.send_json(502, {
                "success": False,
                "error": "Unable to extract YouTube information.",
                "message": "The video may be unavailable or YouTube extraction may have changed."
            })
