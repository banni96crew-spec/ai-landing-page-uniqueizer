```markdown
---
name: js-six-pattern-class-replace
description: Implements JavaScript class and ID replacement using exactly six regex
patterns defined in JS_REPLACE_PATTERNS, compiled per (original, alias) pair
and applied via re.sub with re.IGNORECASE. Use when editing
backend/worker/module_dom_mutator.py JS mutation logic in Backend / Worker.
---
# js-six-pattern-class-replace

## When to use
Use this skill when working on:
- `backend/worker/module_dom_mutator.py`
- JavaScript class replacement logic
- M3.4 implementation
- GAP-H requirements

Applies only to **AI Landing Page Uniqueizer** worker.

---

## Rationale from PRD

§3.3, GAP-H, M3.4:

- Replace selectors in JS using regex only.
- Define exactly **6 pattern templates** in `JS_REPLACE_PATTERNS`.
- Each template contains `{class_name}` or `{id_name}` placeholder —
  compiled separately for each `(original, alias)` pair.
- Apply `re.sub(..., flags=re.IGNORECASE)` for each compiled pattern.
- Do NOT parse JS AST.
- String concatenation cases are explicitly **out of scope**.
- Only the 6 defined patterns are supported.

---

## Required instruction

Implement `JS_REPLACE_PATTERNS` list with exactly 6 **parametrized pattern
templates** covering:

1. `querySelector` / `querySelectorAll` — dot `.` is hardcoded in pattern body
2. `classList.add/remove/toggle/contains`
3. `getElementsByClassName`
4. `getElementById`
5. jQuery `$()` — dot `.` is hardcoded in pattern body
6. `setAttribute('class', ...)` — exact full-value match only

Each template is formatted with the concrete `class_name` or `id_name` before
compilation. Apply via `re.sub` with `re.IGNORECASE` per each
`(original, alias)` pair.

No AST parsing.
String concatenation patterns: skip entirely.

---

## Non-negotiable rules

1. `JS_REPLACE_PATTERNS` must contain exactly 6 template entries.
2. Each template must target one allowed JS API group.
3. Templates must use `{class_name}` or `{id_name}` placeholder.
4. Must compile each template via `.format(class_name=..., id_name=...)`
   before passing to `re.sub`.
5. Must use backreference `\2` inside each pattern to enforce quote consistency
   (single vs double quotes must match on both sides).
6. Must use `re.sub(..., flags=re.IGNORECASE)`.
7. Must apply replacement for each `(original, alias)` in `selector_map`.
8. Must not introduce additional JS parsing logic.
9. Must not attempt to handle string concatenation.
10. Must not use JS AST tools.
11. Must not replace arbitrary strings globally.
12. Must support both `.class` and `#id` — dot and hash are hardcoded
    in the pattern body, NOT passed inside `{class_name}` / `{id_name}`.

---

# JS_REPLACE_PATTERNS (exactly 6 templates)

```python
JS_REPLACE_PATTERNS = [
    # 1. querySelector('.class') / querySelectorAll('.class')
    # Dot is hardcoded in pattern — class_name passed WITHOUT dot
    r"""(querySelector(?:All)?)\(\s*(['"])\.({class_name})\2\s*\)""",

    # 2. classList.add/remove/toggle/contains('class')
    r"""(classList\.(?:add|remove|toggle|contains))\(\s*(['"])({class_name})\2\s*\)""",

    # 3. getElementsByClassName('class')
    r"""(getElementsByClassName)\(\s*(['"])({class_name})\2\s*\)""",

    # 4. getElementById('id')
    # id_name passed WITHOUT hash
    r"""(getElementById)\(\s*(['"])({id_name})\2\s*\)""",

    # 5. jQuery $('.class')
    # Dot is hardcoded in pattern — class_name passed WITHOUT dot
    r"""(\$\()\s*(['"])\.({class_name})\2\s*(\))""",

    # 6. setAttribute('class', 'class-name')
    # Exact full-value match only.
    # KNOWN LIMITATION (MVP): multi-class strings like
    # setAttribute('class', 'foo bar old-name') are NOT handled.
    r"""(setAttribute\(\s*['"]class['"]\s*,\s*['"])({class_name})(['"])""",
]
```

- Must not add more patterns.
- Must not remove any.

---

# Replacement algorithm

## How parametrization works

`original` in `selector_map` includes CSS prefix:
- `.order-btn` → class selector → strip `.` → `class_name = "order-btn"`
- `#main-section` → id selector → strip `#` → `id_name = "main-section"`

`alias` is always the raw alias string without prefix (e.g. `"x8f9q"`).

## Compiled pattern per selector

For each `(original, alias)` pair, determine selector type and compile
each template:

```python
import re

def replace_js_selectors(js_text: str, selector_map: dict[str, str]) -> str:
    for original, alias in selector_map.items():
        if original.startswith('.'):
            # Class selector — strip dot, pass class_name only
            class_name = re.escape(original[1:])
            alias_name = alias  # alias without dot

            for template in JS_REPLACE_PATTERNS:
                # Skip id-only patterns for class selectors
                if '{id_name}' in template:
                    continue
                pattern = template.format(class_name=class_name)
                js_text = re.sub(
                    pattern,
                    lambda m, a=alias_name: _make_replacement(m, a),
                    js_text,
                    flags=re.IGNORECASE,
                )

        elif original.startswith('#'):
            # ID selector — strip hash, pass id_name only
            id_name = re.escape(original[1:])
            alias_name = alias  # alias without hash

            for template in JS_REPLACE_PATTERNS:
                # Skip class-only patterns for id selectors
                if '{class_name}' in template:
                    continue
                pattern = template.format(id_name=id_name)
                js_text = re.sub(
                    pattern,
                    lambda m, a=alias_name: _make_replacement(m, a),
                    js_text,
                    flags=re.IGNORECASE,
                )

    return js_text
```

---

## Replacement callback `_make_replacement`

The callback receives the match object and the alias string.
It must reconstruct the full matched string substituting only the
selector/id value group, preserving all surrounding syntax.

```python
def _make_replacement(m: re.Match, alias: str) -> str:
    """
    Reconstruct match with alias substituted for the selector value.

    Group layout per pattern:

    Pattern 1 — querySelector/querySelectorAll:
      group(1) = function name, e.g. "querySelector"
      group(2) = quote char, e.g. "'" or '"'
      group(3) = class_name (WITHOUT dot)
      → dot is in the pattern body between group(2) and group(3)
      → output: querySelector('.alias')
      return f"{m.group(1)}({m.group(2)}.{alias}{m.group(2)})"

    Pattern 2 — classList.*:
      group(1) = "classList.add" (or remove/toggle/contains)
      group(2) = quote char
      group(3) = class_name
      return f"{m.group(1)}({m.group(2)}{alias}{m.group(2)})"

    Pattern 3 — getElementsByClassName:
      group(1) = "getElementsByClassName"
      group(2) = quote char
      group(3) = class_name
      return f"{m.group(1)}({m.group(2)}{alias}{m.group(2)})"

    Pattern 4 — getElementById:
      group(1) = "getElementById"
      group(2) = quote char
      group(3) = id_name (WITHOUT hash)
      return f"{m.group(1)}({m.group(2)}{alias}{m.group(2)})"

    Pattern 5 — jQuery $():
      group(1) = "$("
      group(2) = quote char
      group(3) = class_name (WITHOUT dot)
      group(4) = ")"
      → dot is in pattern body between group(2) and group(3)
      → output: $('.alias')
      return f"{m.group(1)}{m.group(2)}.{alias}{m.group(2)}{m.group(4)}"

    Pattern 6 — setAttribute:
      group(1) = setAttribute('class', '   [opening quote included]
      group(2) = class_name
      group(3) = closing quote char
      return f"{m.group(1)}{alias}{m.group(3)}"
    """
    groups = m.lastindex  # total number of captured groups

    # Pattern 1: querySelector / querySelectorAll (3 groups, dot in body)
    if groups == 3 and 'querySelector' in m.group(1):
        return f"{m.group(1)}({m.group(2)}.{alias}{m.group(2)})"

    # Pattern 2: classList.* (3 groups, no dot)
    if groups == 3 and 'classList' in m.group(1):
        return f"{m.group(1)}({m.group(2)}{alias}{m.group(2)})"

    # Pattern 3: getElementsByClassName (3 groups, no dot)
    if groups == 3 and 'getElementsByClassName' in m.group(1):
        return f"{m.group(1)}({m.group(2)}{alias}{m.group(2)})"

    # Pattern 4: getElementById (3 groups, no dot)
    if groups == 3 and 'getElementById' in m.group(1):
        return f"{m.group(1)}({m.group(2)}{alias}{m.group(2)})"

    # Pattern 5: jQuery $() (4 groups, dot in body)
    if groups == 4:
        return f"{m.group(1)}{m.group(2)}.{alias}{m.group(2)}{m.group(4)}"

    # Pattern 6: setAttribute (3 groups, no function name in group 1)
    if groups == 3 and 'setAttribute' in m.group(1):
        return f"{m.group(1)}{alias}{m.group(3)}"

    # Fallback: return original match unchanged
    return m.group(0)
```

> **Note:** A cleaner production approach is to dispatch by pattern index
> rather than inspecting group content. The pattern above is shown for
> clarity; refactor to index-based dispatch if preferred.

---

# Important behavior distinctions

## Class selectors

Original in selector_map: `.order-btn` → `class_name = "order-btn"`

In JS:
```
getElementsByClassName("order-btn")   → pattern 3
classList.add("order-btn")             → pattern 2
querySelector(".order-btn")            → pattern 1 (dot in pattern body)
$(".order-btn")                        → pattern 5 (dot in pattern body)
setAttribute('class', 'order-btn')     → pattern 6 (exact value only)
```

Replacement:
```
getElementsByClassName("x8f9q")
classList.add("x8f9q")
querySelector(".x8f9q")
$(".x8f9q")
setAttribute('class', 'x8f9q')
```

**Key:** For patterns 1 and 5, the dot `.` is part of the regex pattern body,
NOT part of `class_name`. The alias is inserted without dot — the dot
is reconstructed in the replacement callback explicitly.

---

## ID selectors

Original in selector_map: `#main-section` → `id_name = "main-section"`

In JS:
```
getElementById("main-section")      → pattern 4 only
querySelector("#main-section")      → pattern 1 with hash logic
```

> **Note on querySelector with IDs:** Pattern 1 as written targets `.class`
> (dot hardcoded). For `#id` support in querySelector, either:
> (a) add a 7th pattern — which violates the 6-pattern rule, or
> (b) handle querySelector `#id` as a special case inside pattern 1
>     by making the dot/hash optional: `[.#]` — but this must be agreed
>     with PRD. Per PRD §3.3 current wording, getElementById covers
>     the ID use case; querySelector `#id` replacement is implicitly
>     handled via getElementById pattern only.

Replacement:
```
getElementById("x1234")
querySelector("#x1234")   ← only if pattern 1 is extended per note above
```

---

# Explicitly out of scope

Do NOT handle:
```
"btn-" + size
".class-" + varName
"#" + id
```

String concatenation patterns must be skipped entirely.
No attempt to detect them.

---

# Prohibited patterns

- ❌ Adding more than 6 regex pattern templates
- ❌ Using AST parser
- ❌ Replacing via naive `.replace()`
- ❌ Global string replacement without context
- ❌ Handling string concatenation
- ❌ Case-sensitive matching
- ❌ Breaking quotes or parentheses
- ❌ Replacing unrelated strings
- ❌ Passing dot `.` or hash `#` inside `{class_name}` / `{id_name}`
- ❌ Using fixed patterns without `{class_name}` / `{id_name}` placeholders
- ❌ Omitting backreference `\2` (mixing quote styles must not match)

---

# Definition of done

- `JS_REPLACE_PATTERNS` contains exactly 6 parametrized template entries
- Each template uses `{class_name}` or `{id_name}` placeholder
- Each template uses `\2` backreference for quote consistency
- Dot `.` for class and hash `#` for id are hardcoded in pattern body
  where applicable (patterns 1 and 5), NOT inside the placeholder value
- Templates are compiled per `(original, alias)` pair via `.format()`
- `re.sub(..., flags=re.IGNORECASE)` used on compiled pattern
- Replacement callback correctly reconstructs dot/hash for patterns 1 and 5
- No AST parsing
- String concatenation ignored
- JS text remains syntactically valid after all replacements
- Only supported patterns are modified
```

