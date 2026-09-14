# Code taste
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
