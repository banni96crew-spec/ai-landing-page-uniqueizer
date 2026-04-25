import re
from typing import Final


JS_REPLACE_PATTERNS: Final[list[str]] = [
    # querySelector('.class') / querySelectorAll('.class')
    r"""(querySelector(?:All)?)\(\s*(['"])\.({class_name})\2\s*\)""",
    # classList.add/remove/toggle/contains('class')
    r"""(classList\.(?:add|remove|toggle|contains))\(\s*(['"])({class_name})\2\s*\)""",
    # getElementsByClassName('class')
    r"""(getElementsByClassName)\(\s*(['"])({class_name})\2\s*\)""",
    # getElementById('id')
    r"""(getElementById)\(\s*(['"])({id_name})\2\s*\)""",
    # jQuery $('.class')
    r"""(\$\()\s*(['"])\.({class_name})\2\s*(\))""",
    # setAttribute('class', 'class-name') exact full-value match only.
    r"""(setAttribute\(\s*['"]class['"]\s*,\s*['"])({class_name})(['"])""",
]

_CLASS_VALUE_GROUP_BY_PATTERN_INDEX: Final[dict[int, int]] = {
    0: 3,
    1: 3,
    2: 3,
    4: 3,
    5: 2,
}
_ID_VALUE_GROUP_BY_PATTERN_INDEX: Final[dict[int, int]] = {3: 3}


def mutate_js_string(
    js_content: str,
    class_map: dict[str, str],
    id_map: dict[str, str],
) -> str:
    """
    Replace supported selector literals in JavaScript using GAP-H regex templates.

    class_map and id_map use bare names only, for example {"btn": "x1234"}.
    Unsupported patterns, including string concatenation, are intentionally left
    unchanged by only replacing captured literals inside the six PRD contexts.

    Implementation note: one merged alternation per pattern (6 passes for classes,
    1 for ids) avoids O(len(class_map) * 6 * len(file)) full-string rescans.
    """
    mutated = js_content

    if class_map:
        alias_by_lower = {k.lower(): v for k, v in class_map.items()}
        names_sorted = sorted(class_map.keys(), key=len, reverse=True)
        class_alt = "|".join(re.escape(n) for n in names_sorted)

        for pattern_index in _CLASS_VALUE_GROUP_BY_PATTERN_INDEX:
            group_index = _CLASS_VALUE_GROUP_BY_PATTERN_INDEX[pattern_index]
            pattern = JS_REPLACE_PATTERNS[pattern_index].format(
                class_name=f"(?:{class_alt})"
            )

            def _class_repl(
                match: re.Match[str],
                *,
                gi: int = group_index,
                lookup: dict[str, str] = alias_by_lower,
            ) -> str:
                raw = match.group(gi)
                replacement = lookup[raw.lower()]
                return _replace_group(match, gi, replacement)

            mutated = re.sub(pattern, _class_repl, mutated, flags=re.IGNORECASE)

    if id_map:
        alias_by_lower_id = {k.lower(): v for k, v in id_map.items()}
        ids_sorted = sorted(id_map.keys(), key=len, reverse=True)
        id_alt = "|".join(re.escape(n) for n in ids_sorted)

        for pattern_index, group_index in _ID_VALUE_GROUP_BY_PATTERN_INDEX.items():
            pattern = JS_REPLACE_PATTERNS[pattern_index].format(id_name=f"(?:{id_alt})")

            def _id_repl(
                match: re.Match[str],
                *,
                gi: int = group_index,
                lookup: dict[str, str] = alias_by_lower_id,
            ) -> str:
                raw = match.group(gi)
                replacement = lookup[raw.lower()]
                return _replace_group(match, gi, replacement)

            mutated = re.sub(pattern, _id_repl, mutated, flags=re.IGNORECASE)

    return mutated


def _replace_group(match: re.Match[str], group_index: int, replacement: str) -> str:
    group_start = match.start(group_index) - match.start(0)
    group_end = match.end(group_index) - match.start(0)
    matched_text = match.group(0)
    return f"{matched_text[:group_start]}{replacement}{matched_text[group_end:]}"
