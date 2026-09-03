from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

@dataclass(frozen=True)
class WebObservation:
    url: str
    title: str
    status_code: int
    latency_ms: float
    content_sha256: str

def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    if p.scheme not in {"http", "https"} or not p.hostname:
        raise ValueError("invalid URL")
    return f"{p.scheme.lower()}://{p.hostname.lower()}{p.path or '/'}"

def content_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()

def extract_links(html: str, base_url: str = "") -> list[str]:
    links = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    return [urljoin(base_url, x) for x in links if x.startswith(("http://", "https://", "/"))][:200]

def detect_rage_clicks(click_times_ms: list[int], threshold_ms: int = 2000) -> bool:
    return len(click_times_ms) >= 3 and click_times_ms[-1] - click_times_ms[-3] <= threshold_ms

def detect_exit_intent(mouse_y: int, viewport_height: int, threshold: int = 16) -> bool:
    return viewport_height - mouse_y <= threshold

def p99(latencies: list[float]) -> float:
    if not latencies:
        return 0.0
    xs = sorted(latencies)
    return xs[min(len(xs)-1, int(round(.99 * (len(xs)-1))))]
