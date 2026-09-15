"""Domain normalization for NanoTaste."""

from __future__ import annotations

from nanotaste.security import validate_domain_id

DOMAIN_ALIASES = {
    "aesthetic": "aesthetic",
    "bio": "personal",
    "brand": "brand",
    "branding": "brand",
    "comms": "communication",
    "communication": "communication",
    "copy": "writing",
    "design": "aesthetic",
    "general": "general",
    "html": "aesthetic",
    "layout": "aesthetic",
    "name": "product",
    "naming": "product",
    "identity": "personal",
    "personal": "personal",
    "product": "product",
    "research": "research",
    "prose": "writing",
    "python": "code",
    "typescript": "code",
    "ui": "aesthetic",
    "ux": "aesthetic",
    "visual": "aesthetic",
    "web": "aesthetic",
    "writing": "writing",
    "code": "code",
}


def normalize_domain(domain: str | None) -> str:
    """Return NanoTaste's canonical domain name for user input."""
    if not domain:
        return "general"
    key = domain.strip().lower().replace("_", "-")
    canonical = DOMAIN_ALIASES.get(key, key)
    return validate_domain_id(canonical)
