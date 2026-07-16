"""Markdown parser for the lightweight TASTE.md schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from nanotaste.domains import normalize_domain
from nanotaste.security import MAX_TASTE_FILE_BYTES, MAX_TASTE_RULES, safe_read_text

KNOWN_SECTIONS = {
    "anchors": "anchors",
    "principles": "principles",
    "tradeoffs": "tradeoffs",
    "trade-offs": "tradeoffs",
    "forbidden moves": "forbidden_moves",
    "forbidden_moves": "forbidden_moves",
    "calibration examples": "calibration_examples",
    "calibration_examples": "calibration_examples",
    "update policy": "update_policy",
    "update_policy": "update_policy",
}


@dataclass(frozen=True)
class TasteRules:
    """Rules loaded for one task domain."""

    domain: str
    anchors: tuple[str, ...] = ()
    principles: tuple[str, ...] = ()
    tradeoffs: tuple[str, ...] = ()
    forbidden_moves: tuple[str, ...] = ()
    calibration_examples: tuple[str, ...] = ()
    update_policy: tuple[str, ...] = ()

    def positive_rules(self) -> tuple[str, ...]:
        """Return taste rules that can add positive score evidence."""
        return self.anchors + self.principles + self.tradeoffs + self.calibration_examples


@dataclass
class TasteProfile:
    """Parsed taste profile with frontmatter, sections, and source hash."""

    frontmatter: dict[str, str] = field(default_factory=dict)
    sections: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    source_paths: tuple[Path, ...] = ()
    source_text: str = ""

    @property
    def digest(self) -> str:
        """Return the stable hash used in output records."""
        return sha256(self.source_text.encode("utf-8")).hexdigest()

    @classmethod
    def empty(cls) -> "TasteProfile":
        """Return an empty profile for no-taste baselines."""
        return cls(source_text="")

    @classmethod
    def from_paths(cls, paths: list[Path]) -> "TasteProfile":
        """Load and merge one or more taste markdown files."""
        profile = cls()
        chunks: list[str] = []
        source_paths: list[Path] = []
        for path in paths:
            if not path.exists() and not path.is_symlink():
                continue
            text = safe_read_text(path, limit_bytes=MAX_TASTE_FILE_BYTES, label="taste file")
            parsed = cls.from_text(text)
            profile._merge(parsed)
            chunks.append(text)
            source_paths.append(path.resolve())
        _validate_rule_count(profile.sections)
        profile.source_text = "\n\n--- source split ---\n\n".join(chunks)
        profile.source_paths = tuple(source_paths)
        return profile

    @classmethod
    def from_text(cls, text: str) -> "TasteProfile":
        """Parse a markdown taste file."""
        frontmatter, body = _split_frontmatter(text)
        profile = cls(frontmatter=_parse_frontmatter(frontmatter), source_text=text)
        profile.sections = _parse_body_sections(body)
        _validate_rule_count(profile.sections)
        return profile

    def rules_for(self, domain: str | None) -> TasteRules:
        """Return general rules plus domain-specific rules."""
        canonical = normalize_domain(domain)
        values: dict[str, list[str]] = {name: [] for name in KNOWN_SECTIONS.values()}
        for section, by_domain in self.sections.items():
            values.setdefault(section, [])
            values[section].extend(by_domain.get("general", []))
            if canonical != "general":
                values[section].extend(by_domain.get(canonical, []))
        return TasteRules(
            domain=canonical,
            anchors=tuple(values["anchors"]),
            principles=tuple(values["principles"]),
            tradeoffs=tuple(values["tradeoffs"]),
            forbidden_moves=tuple(values["forbidden_moves"]),
            calibration_examples=tuple(values["calibration_examples"]),
            update_policy=tuple(values["update_policy"]),
        )

    def _merge(self, other: "TasteProfile") -> None:
        self.frontmatter.update(other.frontmatter)
        for section, by_domain in other.sections.items():
            target = self.sections.setdefault(section, {})
            for domain, items in by_domain.items():
                target.setdefault(domain, []).extend(items)


def _split_frontmatter(text: str) -> tuple[str, str]:
    start = _frontmatter_start(text)
    if start is None:
        return "", text
    end = text.find("\n---", start + 4)
    if end == -1:
        return "", text
    frontmatter = text[start + 4 : end]
    if not _looks_like_frontmatter(frontmatter):
        return "", text
    body = text[end + len("\n---") :].lstrip("\n")
    return frontmatter, body


def _frontmatter_start(text: str) -> int | None:
    lines = text.splitlines(keepends=True)
    if not lines:
        return None
    if lines[0].strip() == "---":
        return 0
    if lines[0].startswith("#") and len(lines) > 1 and lines[1].strip() == "---":
        return len(lines[0])
    return None


def _parse_frontmatter(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _looks_like_frontmatter(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key = stripped.split(":", 1)[0].strip()
        if key and key[0].isalpha() and all(char.isalnum() or char in "_-" for char in key):
            return True
    return False


def _parse_body_sections(body: str) -> dict[str, dict[str, list[str]]]:
    sections: dict[str, dict[str, list[str]]] = {}
    current_section = ""
    current_domain = "general"
    pending_quote: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            _flush_quote(sections, current_section, current_domain, pending_quote)
            current_section = KNOWN_SECTIONS.get(stripped[3:].strip().lower(), "")
            current_domain = "general"
        elif stripped.startswith("### "):
            _flush_quote(sections, current_section, current_domain, pending_quote)
            current_domain = normalize_domain(stripped[4:].strip())
        elif stripped.startswith("- ") and current_section:
            _flush_quote(sections, current_section, current_domain, pending_quote)
            _add_item(sections, current_section, current_domain, stripped[2:].strip())
        elif stripped.startswith(">") and current_section:
            pending_quote.append(stripped.lstrip("> "))
        elif not stripped:
            _flush_quote(sections, current_section, current_domain, pending_quote)
    _flush_quote(sections, current_section, current_domain, pending_quote)
    return sections


def _add_item(
    sections: dict[str, dict[str, list[str]]], section: str, domain: str, item: str
) -> None:
    if not item:
        return
    sections.setdefault(section, {}).setdefault(domain, []).append(item)


def _flush_quote(
    sections: dict[str, dict[str, list[str]]],
    section: str,
    domain: str,
    pending: list[str],
) -> None:
    if section and pending:
        _add_item(sections, section, domain, " ".join(pending).strip())
    pending.clear()


def _validate_rule_count(sections: dict[str, dict[str, list[str]]]) -> None:
    count = sum(len(items) for by_domain in sections.values() for items in by_domain.values())
    if count > MAX_TASTE_RULES:
        raise ValueError(f"taste profile has too many rules: {count} > {MAX_TASTE_RULES}")
