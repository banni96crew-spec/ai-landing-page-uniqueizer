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
    """
    mutated = js_content

    for class_name, alias in class_map.items():
        escaped_class_name = re.escape(class_name)
        for pattern_index, group_index in _CLASS_VALUE_GROUP_BY_PATTERN_INDEX.items():
            pattern = JS_REPLACE_PATTERNS[pattern_index].format(
                class_name=escaped_class_name
            )
            mutated = re.sub(
                pattern,
                lambda match, replacement=alias, index=group_index: _replace_group(
                    match,
                    index,
                    replacement,
                ),
                mutated,
                flags=re.IGNORECASE,
            )

    for id_name, alias in id_map.items():
        escaped_id_name = re.escape(id_name)
        for pattern_index, group_index in _ID_VALUE_GROUP_BY_PATTERN_INDEX.items():
            pattern = JS_REPLACE_PATTERNS[pattern_index].format(
                id_name=escaped_id_name
            )
            mutated = re.sub(
                pattern,
                lambda match, replacement=alias, index=group_index: _replace_group(
                    match,
                    index,
                    replacement,
                ),
                mutated,
                flags=re.IGNORECASE,
            )

    return mutated


def _replace_group(match: re.Match[str], group_index: int, replacement: str) -> str:
    group_start = match.start(group_index) - match.start(0)
    group_end = match.end(group_index) - match.start(0)
    matched_text = match.group(0)
    return f"{matched_text[:group_start]}{replacement}{matched_text[group_end:]}"
