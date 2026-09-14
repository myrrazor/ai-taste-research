# Taste-file hierarchy

`TASTE.md` is the index. Category files live beside it under `taste/`.
Scheduled harvest writes overlays under `taste/learned/` and does not
overwrite the seeded category files unless you pass `nanotaste learn --apply`.

Do not copy this tree next to `examples/TASTE.example.md`. Companion
discovery would merge those files into the documented critic example.

```text
TASTE.md
taste/writing.md
taste/code.md
taste/aesthetic.md
taste/product.md
taste/personal.md
taste/brand.md
taste/communication.md
taste/research.md
taste/learned/general.md
```

After `nanotaste setup`, the same tree is written into the workspace from
the packaged seeds in `src/nanotaste/data/taste/`.
