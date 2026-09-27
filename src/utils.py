"""
src/utils.py — shared text utility helpers.
"""
import re


def clean_text(text: str) -> str:
    """
    Collapse runs of spaces/tabs into a single space.
    Collapse runs of blank lines into at most two newlines.
    Preserves structural newlines needed for section detection.
    """
    if not text:
        return ""
    # Tabs and multiple spaces → single space (but NOT newlines)
    text = re.sub(r"[ \t]+", " ", text)
    # Three or more consecutive newlines → two newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def estimate_tokens(text: str) -> int:
    """
    Rough token-count estimate: ~4 characters per token for English text.
    Used only for informational logging; not used for hard limits.
    """
    if not text:
        return 0
    return len(text) // 4


def split_top_level_delimiters(text: str) -> list[str]:
    """
    Splits text on delimiters (\n, ;, •, or commas) ONLY when they are
    at the top level (outside parentheses, brackets, or quotes).
    Preserves parenthetical lists, explanatory clauses, and enumerations intact.
    """
    if not text:
        return []
    parts = []
    current = []
    depth_paren = 0
    depth_bracket = 0
    in_quote = False
    for char in text:
        if char in ('"', "'"):
            in_quote = not in_quote
            current.append(char)
        elif char == '(' and not in_quote:
            depth_paren += 1
            current.append(char)
        elif char == ')' and not in_quote:
            depth_paren = max(0, depth_paren - 1)
            current.append(char)
        elif char == '[' and not in_quote:
            depth_bracket += 1
            current.append(char)
        elif char == ']' and not in_quote:
            depth_bracket = max(0, depth_bracket - 1)
            current.append(char)
        elif (char in '\n;•' or (char == ',' and depth_paren == 0 and depth_bracket == 0 and not in_quote)):
            part = ''.join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(char)
    last_part = ''.join(current).strip()
    if last_part:
        parts.append(last_part)
    return parts


def deduplicate_sentences(text: str) -> str:
    """
    Deduplicates sentences in a paragraph while preserving complete source meaning.
    If a sentence is an exact or substring duplicate of another longer sentence,
    keeps the longer, more informative sentence.
    Preserves all distinct sentences in original order.
    """
    if not text:
        return text
    raw_sents = [s.strip() for s in re.split(r'(?<=[.!?;])\s+|\n+', text) if s.strip()]
    if not raw_sents:
        return text

    normalized_sents = []
    for s in raw_sents:
        s_clean = s.strip(' ;,')
        if not s_clean:
            continue
        if not s_clean.endswith(('.', '!', '?')):
            s_clean += '.'
        normalized_sents.append(s_clean)

    kept_sents = []
    for i, s_i in enumerate(normalized_sents):
        s_i_core = re.sub(r'[^a-z0-9]+', ' ', s_i.rstrip('.!?').lower()).strip()
        s_i_no_paren = re.sub(r'[^a-z0-9]+', ' ', re.sub(r'\(.*?\)', '', s_i.rstrip('.!?').lower())).strip()
        is_redundant = False
        for j, s_j in enumerate(normalized_sents):
            if i == j:
                continue
            s_j_core = re.sub(r'[^a-z0-9]+', ' ', s_j.rstrip('.!?').lower()).strip()
            s_j_no_paren = re.sub(r'[^a-z0-9]+', ' ', re.sub(r'\(.*?\)', '', s_j.rstrip('.!?').lower())).strip()

            if s_i_core == s_j_core:
                if i > j:
                    is_redundant = True
                    break
            elif s_i_no_paren and s_j_no_paren and s_i_no_paren == s_j_no_paren:
                if len(s_j) > len(s_i) or (len(s_j) == len(s_i) and i > j):
                    is_redundant = True
                    break
            elif len(s_i_core) >= 12 and s_i_core in s_j_core:
                if len(s_j_core) > len(s_i_core):
                    is_redundant = True
                    break
        if not is_redundant:
            kept_sents.append(s_i)

    return ' '.join(kept_sents)


def deduplicate_list_preserve_longest(items: list[str]) -> list[str]:
    """
    Deduplicate a list of documentation requirements conservatively while preserving distinct items.
    1. Does NOT split on commas inside parentheses, explanatory clauses, or enumerations.
    2. Identifies and removes redundant composite items whose individual sub-requirements
       are already present as distinct items in the list.
    3. Never collapses distinct numbered items (e.g. Addendum No. 1 vs Addendum No. 2).
    4. If string A is a substring or core duplicate of string B, keeps the longer,
       more informative variant B.
    """
    if not items:
        return []

    # 1. Normalize whitespace and clean
    cleaned = []
    seen_exact = set()
    for item in items:
        if not item:
            continue
        val = re.sub(r'\s+', ' ', str(item)).strip(' ;,')
        if val and val.lower() not in seen_exact:
            seen_exact.add(val.lower())
            cleaned.append(val)

    if not cleaned:
        return []

    # Helper: get numeric tokens
    def get_numbers(s: str) -> list[str]:
        return re.findall(r'\b\d+\b', s)

    # Helper: get core topic string
    def get_core(s: str) -> str:
        s_low = s.lower()
        s_clean = re.sub(r'[\(\)]', '', s_low)
        s_core = re.sub(r'^(?:a|an|the|copy of|all)\s+', '', s_clean).strip(' ,.-:;')
        # Normalize passive connective verb phrases while preserving qualifiers
        s_core = re.sub(r'\b(?:to be|must be|shall be)\s+(?:presented|submitted|provided|attached|included)\b', '', s_core)
        s_core = re.sub(r'\b(?:may include|including|such as)\b', '', s_core)
        s_core = re.sub(r'\s+', ' ', s_core).strip(' ,.-:;')
        return s_core

    # 2. Identify composite items (items that contain 2 or more OTHER distinct non-overlapping separate items)
    composite_indices = set()
    for i, item_i in enumerate(cleaned):
        core_i = get_core(item_i)
        contained_sub_items = []
        for j, item_j in enumerate(cleaned):
            if i == j:
                continue
            core_j = get_core(item_j)
            if len(core_j) >= 8 and (core_j in core_i or item_j.lower() in item_i.lower()):
                contained_sub_items.append((j, core_j))

        # Check how many mutually distinct (not substrings of each other) sub-items exist
        distinct_contained = []
        for j, core_j in contained_sub_items:
            is_sub_of_another = any(core_j in other_core and core_j != other_core for other_j, other_core in contained_sub_items)
            if not is_sub_of_another:
                distinct_contained.append(j)

        if len(distinct_contained) >= 2:
            composite_indices.add(i)

    # 3. Deduplicate items
    filtered = [item for idx, item in enumerate(cleaned) if idx not in composite_indices]

    result = []
    for i, item_i in enumerate(filtered):
        is_sub = False
        lower_i = item_i.lower()
        nums_i = get_numbers(lower_i)
        core_i = get_core(item_i)

        for j, item_j in enumerate(filtered):
            if i == j:
                continue
            lower_j = item_j.lower()
            nums_j = get_numbers(lower_j)
            core_j = get_core(item_j)

            # Never deduplicate items that have distinct numbers/identifiers
            if nums_i and nums_j and set(nums_i) != set(nums_j):
                continue

            # Check if item_i is a substring of item_j
            if lower_i in lower_j:
                if len(item_j) > len(item_i):
                    is_sub = True
                    break
            # Check core topic match
            elif len(core_i) >= 10 and len(core_j) >= 10:
                topic_i = re.sub(r'\(.*?\)', '', lower_i).strip(' ,.-:;')
                topic_j = re.sub(r'\(.*?\)', '', lower_j).strip(' ,.-:;')
                if (core_i == core_j or (core_i in core_j and len(core_i) >= 12) or
                    (len(topic_i) >= 10 and topic_i in topic_j)):
                    if len(item_j) > len(item_i) or (len(item_j) == len(item_i) and j < i):
                        is_sub = True
                        break

        if not is_sub:
            result.append(item_i)

    return result

