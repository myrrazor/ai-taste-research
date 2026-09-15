"""Seeded taste-file hierarchy: one index plus category files."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from nanotaste.domains import normalize_domain
from nanotaste.schema import TasteProfile
from nanotaste.security import MAX_TASTE_FILE_BYTES, atomic_write_text, safe_read_text
from nanotaste.workspace import TasteWorkspace


@dataclass(frozen=True)
class TasteCategory:
    """One area of taste in the workspace hierarchy."""

    id: str
    title: str
    summary: str
    tags: tuple[str, ...]
    path: str


CATEGORIES: tuple[TasteCategory, ...] = (
    TasteCategory("writing", "Writing", "Voice, docs, and launch notes.", ("voice", "prose", "docs"), "taste/writing.md"),
    TasteCategory("code", "Code", "Shape, tests, and reviewability.", ("code", "tests", "cli"), "taste/code.md"),
    TasteCategory("aesthetic", "Aesthetic", "Visual hierarchy and product imagery.", ("visual", "ui", "layout"), "taste/aesthetic.md"),
    TasteCategory("product", "Product", "Narrow loops and visible decisions.", ("product", "scope", "metrics"), "taste/product.md"),
    TasteCategory("personal", "Personal", "Identity, biography, and what you care about.", ("identity", "bio", "values"), "taste/personal.md"),
    TasteCategory("brand", "Brand", "Naming, tone, and how the work presents itself.", ("brand", "naming", "tone"), "taste/brand.md"),
    TasteCategory("communication", "Communication", "How you talk to agents and collaborators.", ("comms", "prompts", "review"), "taste/communication.md"),
    TasteCategory("research", "Research", "Evidence, claims, and experiment hygiene.", ("research", "claims", "evidence"), "taste/research.md"),
)


@dataclass(frozen=True)
class CatalogNode:
    """One file in the taste hierarchy, with parsed tags and rule counts."""

    id: str
    title: str
    kind: str
    path: str
    exists: bool
    tags: tuple[str, ...]
    summary: str
    rule_count: int
    parent: str | None


def category_ids() -> tuple[str, ...]:
    """Return canonical category identifiers."""
    return tuple(item.id for item in CATEGORIES)


def install_hierarchy(workspace: TasteWorkspace, overwrite: bool = False) -> list[Path]:
    """Write the index TASTE.md and seeded category files if they are missing."""
    written: list[Path] = []
    index = workspace.root / "TASTE.md"
    if overwrite or not index.exists():
        atomic_write_text(index, index_markdown(), label="taste index")
        written.append(index)
    workspace.taste_dir.mkdir(parents=True, exist_ok=True)
    workspace.learned_overlays_dir.mkdir(parents=True, exist_ok=True)
    for category in CATEGORIES:
        path = workspace.root / category.path
        if overwrite or not path.exists():
            atomic_write_text(path, packaged_category_markdown(category.id), label="category taste file")
            written.append(path)
    return written


def load_catalog(workspace: TasteWorkspace) -> list[CatalogNode]:
    """Return the index plus every seeded or learned category file."""
    nodes = [_node_for_index(workspace)]
    for category in CATEGORIES:
        path = workspace.root / category.path
        nodes.append(_node_from_path(workspace, path, category.id, category.title, category.summary, category.tags, "category"))
        overlay = workspace.learned_overlays_dir / f"{category.id}.md"
        if overlay.exists():
            nodes.append(
                _node_from_path(
                    workspace,
                    overlay,
                    f"{category.id}-learned",
                    f"{category.title} learned overlay",
                    "Scheduled harvest overlay for this category.",
                    ("learned", *category.tags),
                    "overlay",
                    parent=category.id,
                )
            )
    return nodes


def catalog_payload(workspace: TasteWorkspace) -> dict[str, Any]:
    """JSON view of the taste hierarchy for the studio and reports."""
    nodes = load_catalog(workspace)
    return {
        "schema": "nanotaste/taste-catalog/1.0",
        "index": "TASTE.md",
        "categories": [category.id for category in CATEGORIES],
        "nodes": [
            {
                "id": node.id,
                "title": node.title,
                "kind": node.kind,
                "path": node.path,
                "exists": node.exists,
                "tags": list(node.tags),
                "summary": node.summary,
                "rule_count": node.rule_count,
                "parent": node.parent,
            }
            for node in nodes
        ],
    }


def write_learned_overlay(workspace: TasteWorkspace, domain: str, markdown: str) -> Path:
    """Write a reviewable learned overlay beside the seeded category file."""
    canonical = normalize_domain(domain)
    workspace.learned_overlays_dir.mkdir(parents=True, exist_ok=True)
    path = workspace.learned_overlays_dir / f"{canonical}.md"
    atomic_write_text(path, markdown, label="learned overlay")
    return path


def packaged_category_markdown(category_id: str) -> str:
    """Return packaged seed text for one category."""
    try:
        return (
            resources.files("nanotaste")
            .joinpath(f"data/taste/{category_id}.md")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        return category_markdown(category_id)


def index_markdown() -> str:
    """Return the main taste index with pointers to category files."""
    try:
        return resources.files("nanotaste").joinpath("data/TASTE.starter.md").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        return _fallback_index()


def category_markdown(category_id: str) -> str:
    """Return seed markdown for a category, preferring packaged files."""
    return SEED_BODIES.get(category_id, _generic_category(category_id))


def _node_for_index(workspace: TasteWorkspace) -> CatalogNode:
    path = workspace.root / "TASTE.md"
    return _node_from_path(
        workspace,
        path,
        "index",
        "Main taste index",
        "Pointers to category taste files and general rules.",
        ("index", "general"),
        "index",
    )


def _node_from_path(
    workspace: TasteWorkspace,
    path: Path,
    node_id: str,
    title: str,
    summary: str,
    tags: tuple[str, ...],
    kind: str,
    parent: str | None = None,
) -> CatalogNode:
    rule_count = 0
    extra_tags = tags
    if path.is_file():
        text = safe_read_text(path, limit_bytes=MAX_TASTE_FILE_BYTES, label="taste file")
        profile = TasteProfile.from_text(text)
        rules = profile.rules_for(normalize_domain(node_id if node_id not in {"index", "general"} else "general"))
        rule_count = len(rules.positive_rules()) + len(rules.forbidden_moves)
        raw_tags = profile.frontmatter.get("tags", "")
        parsed = _split_csv(raw_tags)
        if parsed:
            extra_tags = tuple(parsed)
    rel = str(path.relative_to(workspace.root)) if path.is_relative_to(workspace.root) else str(path)
    return CatalogNode(
        id=node_id,
        title=title,
        kind=kind,
        path=rel,
        exists=path.is_file(),
        tags=extra_tags,
        summary=summary,
        rule_count=rule_count,
        parent=parent,
    )


def _split_csv(value: str) -> list[str]:
    cleaned = value.strip().strip("[]")
    if not cleaned:
        return []
    return [item.strip().strip("'\"") for item in cleaned.split(",") if item.strip().strip("'\"")]


def _fallback_index() -> str:
    links = "\n".join(f"- [{item.title}]({item.path}) — {item.summary}" for item in CATEGORIES)
    return f"""# TASTE.md
---
schema: taste/1.1
kind: index
domains: [general, writing, code, product, aesthetic, personal, brand, communication, research]
children: [writing, code, aesthetic, product, personal, brand, communication, research]
---

## Catalog

{links}

## Principles

### general
- Specificity beats polish.

## Update Policy

### general
- Seeded category files stay reviewable.
- Scheduled harvest writes overlays under `taste/learned/`.
"""


def _generic_category(category_id: str) -> str:
    return f"""# {category_id.title()} taste
---
schema: taste/1.1
kind: category
domain: {category_id}
tags: [{category_id}]
parent: TASTE.md
---

## Principles

### {category_id}
- Keep {category_id} decisions concrete and inspectable.

## Update Policy

### {category_id}
- Review learned overlays before merging them into this file.
"""


SEED_BODIES: dict[str, str] = {
    "writing": """# Writing taste
---
schema: taste/1.1
kind: category
domain: writing
tags: [voice, prose, docs]
parent: TASTE.md
---

## Anchors

### writing
- Closer to concrete builder notes than to generic best-practice prose.

## Principles

### writing
- Name the action, the output, and the signal that proves it worked.

## Forbidden Moves

### writing
- "In today's fast-paced world"
- "seamlessly"
- "empower"

## Calibration Examples

### writing
> Good: "Run the harness on three drafts. If it picks your edit, the taste file is doing work."
> Why: concrete action, specific signal, no filler.

> Bad: "This solution empowers teams to seamlessly navigate the AI landscape."
> Why: generic verbs, no visible user, forbidden phrases.
""",
    "code": """# Code taste
---
schema: taste/1.1
kind: category
domain: code
tags: [code, tests, cli]
parent: TASTE.md
---

## Anchors

### code
- Closer to small explicit functions with tests than to clever abstractions.

## Principles

### code
- Return reasons with scores so behavior is easy to test.

## Tradeoffs

### code
- When abstraction and debuggability conflict, choose debuggability.

## Forbidden Moves

### code
- "This function is responsible for"
- "console.log"
""",
    "aesthetic": """# Aesthetic taste
---
schema: taste/1.1
kind: category
domain: aesthetic
tags: [visual, ui, layout]
parent: TASTE.md
---

## Anchors

### aesthetic
- Closer to real product imagery and restrained hierarchy than to generic SaaS decoration.

## Principles

### aesthetic
- Make the primary object obvious in the first viewport.

## Forbidden Moves

### aesthetic
- "gradient"
- "floating card"
- "decorative blob"
""",
    "product": """# Product taste
---
schema: taste/1.1
kind: category
domain: product
tags: [product, scope, metrics]
parent: TASTE.md
---

## Principles

### product
- Start with one loop: compare drafts, pick one, and explain the decision.

## Tradeoffs

### product
- When a broader platform and a narrow experiment conflict, choose the experiment.

## Forbidden Moves

### product
- "all-in-one platform"
""",
    "personal": """# Personal taste
---
schema: taste/1.1
kind: category
domain: personal
tags: [identity, bio, values]
parent: TASTE.md
---

## Anchors

### personal
- Closer to a specific person with visible preferences than to a generic user persona.

## Principles

### personal
- Seed this file with a site, bio, or files that show what you actually like.

## Update Policy

### personal
- Personal seeds stay local. Do not paste secrets or private addresses into the file.
""",
    "brand": """# Brand taste
---
schema: taste/1.1
kind: category
domain: brand
tags: [brand, naming, tone]
parent: TASTE.md
---

## Principles

### brand
- Prefer short, specific names over abstract evocation.

## Forbidden Moves

### brand
- "synergy"
- "next-generation"
""",
    "communication": """# Communication taste
---
schema: taste/1.1
kind: category
domain: communication
tags: [comms, prompts, review]
parent: TASTE.md
---

## Principles

### communication
- Ask for a decision, a draft, or a test; do not ask an agent to "be helpful."

## Forbidden Moves

### communication
- "as an AI language model"
""",
    "research": """# Research taste
---
schema: taste/1.1
kind: category
domain: research
tags: [research, claims, evidence]
parent: TASTE.md
---

## Principles

### research
- Separate workflow mechanics from preference-model claims.

## Forbidden Moves

### research
- "validated preference alignment"
""",
}
