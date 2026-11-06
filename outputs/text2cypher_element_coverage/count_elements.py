"""Counts the SemGIR grammar elements in the Text2Cypher and GrailQA pipeline selections.

Usage (from the repository root): python outputs/text2cypher_element_coverage/count_elements.py
"""

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

from pipeline.datasets.grailqa import GrailQADataset
from pipeline.datasets.text2cypher import Text2CypherDataset

OUTPUT_DIR = Path(__file__).resolve().parent
TEXT2CYPHER_PATH = ROOT / "datasets/text2cypher_2025v1/test.parquet"
GRAILQA_PATH = ROOT / "datasets/GrailQA_v1.0/grailqa_v1.0_dev.json"
N_QUERIES = 200
SEED = 42

# Found by reading the selection: no regex separates these from a plain ORDER BY ... LIMIT
LIST_ORDER_LIMIT_IDS = {"T2C_39712", "T2C_30836"}

CYPHER_CONSTRUCT = "cypher_construct"
SECTIONS = {
    "Hypotheses": ["One hypothesis", "Several hypotheses"],
    "Query": [
        "ENTITY",
        "relationships",
        "PATH",
        "constraint",
        "Query distinct",
        "order_by",
        "limit",
        "Query skip",
    ],
    "Target": [
        "Target ENTITY_ID",
        "Target RELATIONSHIP_ID",
        "Target PATH_ID",
        "Target LIST",
        "Target ATTRIBUTE",
        "Target relationship attribute",
        "Target COUNT",
        "Target SCALAR_AGGREGATE",
        "Target CONDITION",
        "Several targets",
    ],
    "Relationship and attribute": [
        "Relationship with a role",
        "Relationship with any role",
        "ATTRIBUTE (anywhere)",
        "Relationship attribute",
    ],
    "Path": [
        "PATH with a role list",
        "PATH with an empty role list",
    ],
    "List": [
        "LIST (any kind)",
        "CREATE_LIST",
        "NODES",
        "RELATIONS",
        "LIST.filter",
        "LIST.distinct",
        "LIST.order_by",
        "LIST.limit",
        "LIST.skip",
    ],
    "Aggregation": ["COUNT", "SCALAR_AGGREGATE", "SUM", "MIN", "MAX", "AVG"],
    "Quantifier": [
        "QUANTIFIER_PREDICATE",
        "QUANTIFIER ALL",
        "QUANTIFIER EXISTS",
        "QUANTIFIER NONE",
    ],
    "Order direction": ["ASC", "DESC"],
    "Condition": ["AND", "OR", "NOT", "COMPARISON", "RELATIONSHIP_ID as a condition"],
    "Operator": ["=", "!=", ">", "<", "<=", ">=", "CONTAINS", "MATCHES_REGEX"],
    "Value": ["STRING value", "NUMBER value", "BOOLEAN value", "DATE_TIME"],
}
ELEMENTS = [element for elements in SECTIONS.values() for element in elements]
NOT_COUNTED_IN_ALL = {"LIST.order_by", "LIST.limit"}
CONSTRUCTS = [
    "Target properties(), labels(), type() or keys()",
    "ANY(key IN keys(n))",
    "size() or length() of a property",
    "Several role types or labels",
    "UNION",
]
GRAILQA_UPPER_BOUND = {
    "limit",
    "order_by",
    "DESC",
    "ASC",
    "MAX",
    "MIN",
    "LIST (any kind)",
    "CREATE_LIST",
    "SCALAR_AGGREGATE",
    "LIST.filter",
}
NOTES = {
    "MATCHES_REGEX": "Direct =~ plus STARTS WITH or ENDS WITH",
    "!=": "Also IS NOT NULL, written as != with an empty value",
    "=": "Also IS NULL, written as = with an empty value",
    "QUANTIFIER EXISTS": "Optional: RELATIONSHIP_ID as a condition or a target CONDITION also work",
    "QUANTIFIER NONE": "Explicit none() only; negated patterns can use NOT",
    "LIST.skip": "List slices with a non-zero start",
    "LIST.filter": "Optional: a condition ahead of the aggregate, which can also stay in constraint",
    "LIST.order_by": "Selection found by reading; all test queries not counted",
    "LIST.limit": "Selection found by reading; all test queries not counted",
    "Several hypotheses": "Both datasets give one gold query per question",
}

PATTERNS = {
    "limit": r"\bLIMIT\b",
    "order_by": r"\bORDER\s+BY\b",
    "Query distinct": r"\b(RETURN|WITH)\s+DISTINCT\b",
    "LIST.distinct": r"\b(count|collect|sum|avg|min|max)\s*\(\s*DISTINCT\b",
    "Query skip": r"\bSKIP\b",
    "SUM": r"\bsum\s*\(",
    "AVG": r"\bavg\s*\(",
    "MIN": r"\bmin\s*\(",
    "MAX": r"\bmax\s*\(",
    "OR": r"(?<![\[.:])\bOR\b(?!\s*[:.])",
    "NOT": r"(?<!IS )\bNOT\b",
    "!=": r"<>",
    "PATH": r"-\s*\[[^\]]*\*[^\]]*\]",
    "PATH with a role list": r"-\s*\[\s*\w*\s*:[^\]]*\*[^\]]*\]",
    "PATH with an empty role list": r"-\s*\[\s*\w*\s*\*[^\]]*\]",
    "Relationship with a role": r"-\s*\[\s*\w*\s*:[^\]*]*\]\s*-",
    "NODES": r"\bnodes\s*\(",
    "RELATIONS": r"\brelationships\s*\(|\blength\s*\(\s*(?!\w+\.\w+\s*\))",
    "Relationship with any role": r"-\s*\[\s*\w*\s*(\{[^}]*\})?\s*\]\s*-|-->|<--|\)--\(",
    "COUNT": r"\bcount\s*[({]|\bsize\s*\(\s*(?!keys\b|\w+\.\w+\s*\))|\blength\s*\(\s*(?!\w+\.\w+\s*\))",
    "CREATE_LIST": r"\b(collect|count|sum|avg|min|max)\s*[({]|\bsize\s*\(\s*(?!keys\b|nodes\b|relationships\b|\w+\.\w+\s*\))",
    "CONTAINS": r"(?<![:|.])\bCONTAINS\b",
    "QUANTIFIER EXISTS": r"(?<!NOT )\bexists\s*[({]|\bany\s*\(\s*\w+\s+IN\s+(?!keys\b)",
    "QUANTIFIER ALL": r"\ball\s*\(",
    "QUANTIFIER NONE": r"\bnone\s*\(",
    "LIST.skip": r"[\])]\s*\[\s*[1-9]\d*\s*\.\.",
    "DATE_TIME": r"\b(date|datetime|localdatetime)\s*\(\s*(''|\{)",
    "BOOLEAN value": r"(?:[=:]|<>)\s*(true|false)\b",
    "ANY(key IN keys(n))": r"\bany\s*\(\s*\w+\s+IN\s+keys\b",
    "size() or length() of a property": r"\b(size|length)\s*\(\s*\w+\.\w+\s*\)",
    "Several role types or labels": r"-\s*\[[^\]]*:\s*\w+\s*\||\(\s*\w*\s*:\s*\w+\s*\|",
    "STARTS WITH or ENDS WITH": r"\b(STARTS|ENDS)\s+WITH\b",
    "=~": r"=~",
    "IS NULL or IS NOT NULL": r"\bIS\s+(NOT\s+)?NULL\b",
    "UNION": r"\bUNION\b",
}
COMPARISONS = {
    "=": r"(?<![<>=!~])=(?![~=])\s*(?!\(|shortestPath|allShortestPaths)",
    ">": r"(?<![-<=])>(?![=-])\s*[\w'(-]",
    ">=": r">=",
    "<": r"(?<![<])<(?![-=>])\s*[\w'(-]",
    "<=": r"<=",
}
INLINE_VALUE = r"(?<!\()[{,]\s*\w+\s*:\s*(?:''|-?\d|true|false)"
FUNCTION_MAP = r"\b\w+\s*\(\s*\{[^}]*\}"
UNION_SPLIT = r"\bUNION\b(?:\s+ALL\b)?"
WHERE_CLAUSE = r"\bWHERE\b(.*?)(?=\bRETURN\b|(?<!STARTS )(?<!ENDS )\bWITH\b|\bMATCH\b|\bORDER\b|\bUNION\b|$)"
COUNTED_PATTERN = r"\b(?:count\s*\{[^}]*\}|size\s*\((?:[^()]|\([^()]*\))*\))"
PATTERN_PREDICATE = r"\)\s*<?-\s*[\[-]"
IN_LITERAL_LIST = r"\bIN\s*\[\s*(?:''|-?\d)[^\]]*,"
EXACT_HOPS = r"-\s*\[[^\]]*\*\s*\d+\s*(?:\{[^}]*\}\s*)?\]"
MIN_HOPS = r"-\s*\[[^\]]*\*\s*\d+\s*\.\."
MAX_HOPS = r"-\s*\[[^\]]*\*\s*\d*\s*\.\.\s*\d+"
NAMED_PATH = r"(?:\bMATCH\b|,)\s*\w+\s*=\s*(?:(?:all)?shortestPath\s*\(\s*)?\(.*?(?=\bRETURN\b|\bWITH\b|\bWHERE\b|\bMATCH\b|$)"
ISO_DATE = r"['\"]\d{4}-\d{2}(?:-\d{2}(?:T[\d:.Z+-]*)?)?['\"]"
RELATIONSHIP_VARIABLE = r"-\s*\[\s*([A-Za-z_]\w*)\s*[:\]\*{]"
RELATIONSHIP_BRACKETS = r"<?-\s*\[[^\]]*\]\s*-?>?"
ARITHMETIC = (
    r"(?<![\w.])(?:abs|sqrt|ceil|floor|round|log|exp|sign)\s*\(|\bduration\s*[.(]"
    r"|[\w)\]']\s*[+*/%]\s*[\w(\['-]|[\w)]\s*-\s*[\w(]"
)
NO_FORM = "No form"
CONVENTION = "Convention"
WORKAROUND = "Workaround"
FUNCTIONS = [
    (NO_FORM, "`properties()`", r"\bproperties\s*\(", "`ATTRIBUTE` needs a specific name. Provisionally, returning the node counts"),
    (NO_FORM, "`keys()`, usually with `n[key]`", r"\bkeys\s*\(", "`ATTRIBUTE` needs a specific name"),
    (NO_FORM, "Arithmetic and durations: `+`, `-`, `*`, `/`, `abs()`, `sqrt()`, `ceil()`, `duration.*`", ARITHMETIC, "`EXPRESSION` has no arithmetic"),
    (NO_FORM, "String and list manipulation: `split()`, `substring()`, `right()`, `range()`, `reduce()`, `coalesce()`, `apoc.*`, `UNWIND`, `[x IN list]`", r"\b(?:split|substring|left|right|replace|trim|ltrim|rtrim|reverse|head|last|tail|range|reduce|coalesce)\s*\(|\bapoc\.|\bUNWIND\b|\[\s*\w+\s+IN\b", "No such operation"),
    (NO_FORM, "`date()` or `datetime()` without a value: converting an attribute, or the current date", r"\b(?:date|datetime)\s*\(\s*(?!''|\{)", "`DATE_TIME` is only a fixed value"),
    (NO_FORM, "`size()` or `length()` of a property", PATTERNS["size() or length() of a property"], "`COUNT` needs a `LIST` of entities or relationships"),
    (CONVENTION, "`type(r)`", r"\btype\s*\(", "`role` as an attribute: `{ \"attribute_name\": \"role\", \"of\": \"r1\" }`"),
    (CONVENTION, "`labels(n)`", r"\blabels\s*\(", "`type` as an attribute: `{ \"attribute_name\": \"type\", \"of\": \"e1\" }`"),
    (WORKAROUND, "`IS NULL`, `IS NOT NULL`", r"\bIS\s+(?:NOT\s+)?NULL\b", "`=` or `!=` with an empty value, or not-exists"),
    (WORKAROUND, "`STARTS WITH`, `ENDS WITH`", r"\b(?:STARTS|ENDS)\s+WITH\b", "`MATCHES_REGEX`"),
    (WORKAROUND, "`shortestPath()`", r"\b(?:all)?shortestPath\s*\(", "`PATH` ordered by the `COUNT` of its `RELATIONS`, with `limit` 1"),
    (WORKAROUND, "`size(list)`", r"\bsize\s*\(\s*(?!keys\b|\w+\.\w+\s*\))", "`COUNT`"),
    (WORKAROUND, "`length(path)`", r"\blength\s*\(\s*(?!\w+\.\w+\s*\))", "`COUNT` over `rels_of`"),
    (WORKAROUND, "`date()` or `datetime()` with a value", r"\b(?:date|datetime)\s*\(\s*(?:''|\{)", "A `DATE_TIME` string"),
    (WORKAROUND, "`toFloat()`, `toInteger()`, `toLower()`", r"\b(?:toFloat|toInteger|toLower|toUpper|toString|toBoolean)\s*\(", "Usually unnecessary, or a case-insensitive `MATCHES_REGEX`"),
    (WORKAROUND, "`id()`", r"(?<![\w.])id\s*\(", "`{ \"attribute_name\": \"id\", ... }`"),
]
AGGREGATE = r"\b(collect|count|sum|avg|min|max)\s*[({]"
OPERATORS = {"=", "!=", ">", "<", "<=", ">=", "CONTAINS", "MATCHES_REGEX"}
SCALAR_AGGREGATES = {"SUM", "MIN", "MAX", "AVG"}
QUANTIFIERS = {"QUANTIFIER ALL", "QUANTIFIER EXISTS", "QUANTIFIER NONE"}
SUPERLATIVE_LIST = {"LIST (any kind)", "CREATE_LIST", "SCALAR_AGGREGATE"}


def normalized(cypher: str) -> str:
    """The query on one line, with every string literal replaced by ''."""
    literal = r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*\""""
    return " ".join(re.sub(literal, "''", cypher).split())


def top_level_items(text: str) -> list[str]:
    """The comma-separated parts of a clause, ignoring commas inside brackets."""
    items = []
    depth, current = 0, ""
    for char in text:
        depth += (char in "([{") - (char in ")]}")
        if char == "," and depth == 0:
            items.append(current)
            current = ""
        else:
            current += char
    return items + [current]


def return_items(cypher: str) -> list[str]:
    """The comma-separated items of every RETURN clause, without DISTINCT."""
    clause = r"\bRETURN\b(.*?)(?=\bORDER\s+BY\b|\bSKIP\b|\bLIMIT\b|\bUNION\b|$)"
    items = [
        item for part in re.findall(clause, cypher, re.I) for item in top_level_items(part)
    ]
    return [re.sub(r"^\s*DISTINCT\s+", "", item.strip(), flags=re.I) for item in items]


def target_elements(cypher: str) -> set[str]:
    """The kinds of target of a query, following aliases such as count(x) AS c."""
    projections = re.sub(r"\b(WITH|RETURN)\s+(DISTINCT\s+)?", ",", cypher, flags=re.I)
    aliases = {
        alias: expression.strip()
        for expression, alias in re.findall(r"([^,]+?)\s+AS\s+(\w+)", projections, re.I)
    }
    relationships = set(re.findall(RELATIONSHIP_VARIABLE, cypher))
    paths = set(
        re.findall(
            r"\b(\w+)\s*=\s*(?:shortestPath\s*\(|allShortestPaths\s*\(|\()",
            cypher,
            re.I,
        )
    )
    branches = re.split(UNION_SPLIT, cypher, flags=re.I)
    several = any(len(return_items(branch)) > 1 for branch in branches)
    found = {"Several targets"} if several else set()
    for item in return_items(cypher):
        expression = re.sub(r"\s+AS\s+\w+$", "", item, flags=re.I).strip()
        kind = target_kind(aliases.get(expression, expression), relationships, paths)
        if kind:
            found.add(kind)
    return found


def target_kind(
    expression: str, relationships: set[str], paths: set[str]
) -> str | None:
    if re.match(r"exists\s*[({]", expression, re.I):
        return "Target CONDITION"
    if re.match(r"(collect|nodes|relationships)\s*\(", expression, re.I):
        return "Target LIST"
    if re.search(r"\b(sum|avg|min|max)\s*\(", expression, re.I):
        return "Target SCALAR_AGGREGATE"
    if re.search(r"\bcount\s*[({]|\bsize\s*\(\s*(?!keys\b|\w+\.\w+\s*\))", expression, re.I):
        return "Target COUNT"
    if re.match(r"(size\s*\(\s*)?(properties|keys|labels|type)\s*\(", expression, re.I):
        return "Target properties(), labels(), type() or keys()"
    if re.fullmatch(r"\w+", expression):
        if expression in relationships:
            return "Target RELATIONSHIP_ID"
        return "Target PATH_ID" if expression in paths else "Target ENTITY_ID"
    owner = re.match(r"(\w+)\.", expression)
    if not owner:
        return None
    return (
        "Target relationship attribute"
        if owner.group(1) in relationships
        else "Target ATTRIBUTE"
    )


def hop_elements(cypher: str) -> set[str]:
    """A bounded path is a COUNT of its RELATIONS compared with a number, as in the prompt's 3-hop example."""
    found = set()
    if re.search(EXACT_HOPS, cypher):
        found.add("=")
    if re.search(MIN_HOPS, cypher):
        found.add(">=")
    if re.search(MAX_HOPS, cypher):
        found.add("<=")
    return found


def inline_values(cypher: str) -> int:
    return len(re.findall(INLINE_VALUE, re.sub(FUNCTION_MAP, "", cypher), re.I))


def has_conjunction(branch: str) -> bool:
    clauses = re.findall(WHERE_CLAUSE, branch, re.I)
    keyword = re.search(r"(?<![\[.:])\bAND\b(?!\s*[:.])", " ".join(clauses), re.I)
    conditions = inline_values(branch) + len(clauses) + len(hop_elements(branch))
    return bool(keyword) or conditions >= 2


def condition_elements(cypher: str) -> set[str]:
    clauses = re.findall(WHERE_CLAUSE, cypher, re.I)
    where = " ".join(clauses)
    inline = inline_values(cypher)
    hops = hop_elements(cypher)

    found = {
        name for name, pattern in COMPARISONS.items() if re.search(pattern, where, re.I)
    }
    found |= hops
    if hops:
        found |= {"constraint", "COUNT", "RELATIONS", "NUMBER value"}
    if inline:
        found.add("=")
    if re.search(IN_LITERAL_LIST, where, re.I):
        found |= {"OR", "="}
    if inline or clauses:
        found.add("constraint")
    if any(has_conjunction(branch) for branch in re.split(UNION_SPLIT, cypher, flags=re.I)):
        found.add("AND")
    outside_counts = re.sub(COUNTED_PATTERN, "", where, flags=re.I)
    if re.search(PATTERN_PREDICATE, outside_counts) or re.search(
        r"\bWHERE\b.*?\bexists\s*[({]", cypher, re.I
    ):
        found.add("RELATIONSHIP_ID as a condition")
    return found


def path_elements(cypher: str) -> set[str]:
    """A named path is a PATH even when it has no variable-length relationship."""
    found = set()
    for segment in re.findall(NAMED_PATH, cypher, re.I):
        found.add("PATH")
        has_role = re.search(r"-\s*\[\s*\w*\s*:", segment)
        found.add("PATH with a role list" if has_role else "PATH with an empty role list")
    return found


def relationship_attribute(cypher: str) -> bool:
    variables = set(re.findall(RELATIONSHIP_VARIABLE, cypher))
    if re.search(r"-\s*\[\s*\w*\s*:?\s*\w*\s*\{", cypher):
        return True
    return any(
        re.search(rf"(?<![\w.]){re.escape(name)}\.\w", cypher) for name in variables
    )


def order_directions(cypher: str) -> set[str]:
    clauses = re.findall(
        r"\bORDER\s+BY\b(.*?)(?=\bLIMIT\b|\bSKIP\b|\bRETURN\b|\bWITH\b|$)", cypher, re.I
    )
    return {
        "DESC" if re.search(r"\bDESC(ENDING)?\s*$", criterion, re.I) else "ASC"
        for clause in clauses
        for criterion in top_level_items(clause)
    }


def filter_before_aggregate(cypher: str) -> bool:
    aggregate = re.search(AGGREGATE, cypher, re.I)
    if not aggregate:
        return False
    before = cypher[: aggregate.start()]
    return bool(re.search(r"\bWHERE\s+\S", before, re.I) or inline_values(before))


def shared_elements(found: set[str]) -> set[str]:
    """The umbrella elements that follow from the specific ones of a query, in either dataset."""
    shared = {"One hypothesis"}
    if found & OPERATORS:
        shared.add("COMPARISON")
    if found & SCALAR_AGGREGATES:
        shared.add("SCALAR_AGGREGATE")
    if found & QUANTIFIERS:
        shared.add("QUANTIFIER_PREDICATE")
    return shared


def text2cypher_elements(query_id: str, raw_cypher: str) -> set[str]:
    """The grammar elements and Cypher constructs of one gold query."""
    cypher = normalized(raw_cypher)
    found = (
        {"ENTITY"}
        | target_elements(cypher)
        | condition_elements(cypher)
        | order_directions(cypher)
        | path_elements(cypher)
    )
    found |= {
        name for name, pattern in PATTERNS.items() if re.search(pattern, cypher, re.I)
    }

    if re.search(
        r"\)\s*<?-\s*\[\s*\w*\s*(:[^\]*]*)?(\{[^}]*\})?\s*\]\s*-?>?\s*\(|\)\s*(?:<--|--?>|--)\s*\(",
        cypher,
    ):
        found.add("relationships")
    if re.search(ISO_DATE, raw_cypher):
        found.add("DATE_TIME")
    if found & {"=~", "STARTS WITH or ENDS WITH"}:
        found.add("MATCHES_REGEX")
    if found & {"COUNT", "SUM", "AVG", "MIN", "MAX", "NODES", "RELATIONS"} or re.search(
        r"\bcollect\s*\(", cypher, re.I
    ):
        found.add("LIST (any kind)")
    if re.search(r"\.\w+\b", cypher) or inline_values(cypher):
        found.add("ATTRIBUTE (anywhere)")
    if "''" in cypher:
        found.add("STRING value")
    without_brackets = re.sub(
        r"\[[^\]{}]*\]|\bLIMIT\s+\d+|\bSKIP\s+\d+", "", cypher, flags=re.I
    )
    if re.search(r"(?<![\w.])\d+(\.\d+)?(?![\w.])", without_brackets):
        found.add("NUMBER value")
    if relationship_attribute(cypher):
        found.add("Relationship attribute")
    if filter_before_aggregate(cypher):
        found.add("LIST.filter")
    if re.search(r"\bIS\s+NOT\s+NULL\b", cypher, re.I):
        found |= {"!=", "STRING value"}
    if re.search(r"\bIS\s+NULL\b", cypher, re.I):
        found |= {"=", "STRING value"}
    if query_id in LIST_ORDER_LIMIT_IDS:
        found |= {"LIST.order_by", "LIST.limit"}
    return found | shared_elements(found)


def grailqa_elements(entry: dict) -> set[str]:
    """The grammar elements of one gold s-expression. Superlatives count towards both of their encodings."""
    nodes = {node["nid"]: node for node in entry["graph_query"]["nodes"]}
    function = entry["function"]
    expression = entry["s_expression"]
    entities = sum(node["node_type"] == "entity" for node in nodes.values())
    literals = [
        node
        for node in nodes.values()
        if node["node_type"] == "literal"
        and node["function"] not in ("argmax", "argmin")
    ]

    found = {"ENTITY", "ATTRIBUTE (anywhere)"}
    found.add("Target COUNT" if function == "count" else "Target ENTITY_ID")
    if function == "count":
        found |= {"COUNT", "LIST (any kind)", "CREATE_LIST"}
    if function in (">", ">=", "<", "<="):
        found.add(function)
    if function == "argmax":
        found |= {"order_by", "limit", "DESC", "MAX"} | SUPERLATIVE_LIST
    if function == "argmin":
        found |= {"order_by", "limit", "ASC", "MIN"} | SUPERLATIVE_LIST
    if any(
        nodes[edge["start"]]["node_type"] != "literal"
        and nodes[edge["end"]]["node_type"] != "literal"
        for edge in entry["graph_query"]["edges"]
    ):
        found |= {"relationships", "Relationship with a role"}
    if entities or literals:
        found.add("constraint")
        if function in ("count", "argmax", "argmin"):
            found.add("LIST.filter")
    if entities + len(literals) >= 2:
        found.add("AND")
    if entities or any(node["function"] == "none" for node in literals):
        found.add("=")
    if entities:
        found.add("STRING value")
    if re.search(r"XMLSchema#(integer|float|double)", expression):
        found.add("NUMBER value")
    if re.search(r"XMLSchema#(date|gYear)", expression):
        found.add("DATE_TIME")
    return found | shared_elements(found)


def group_of(element: str, selection: int, grailqa: int) -> str:
    if element in CONSTRUCTS:
        return CYPHER_CONSTRUCT
    if selection and grailqa:
        return "both"
    if selection:
        return "text2cypher_only"
    return "grailqa_only" if grailqa else "neither"


def write_csv(name: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(OUTPUT_DIR / name, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def section_of(element: str) -> str:
    return next(name for name, elements in SECTIONS.items() if element in elements)


def share(count: int, total: int) -> str:
    return f"{100 * count / total:.1f}"


def dataset_rows(
    elements: list[str],
    selection: Counter,
    population: Counter,
    population_size: int,
    notes: dict[str, str],
    not_counted: set[str],
) -> list[dict]:
    """One row per element for the table of a single dataset, including the elements it never uses."""
    rows = []
    for element in elements:
        counted = element not in not_counted
        rows.append(
            {
                "section": CYPHER_CONSTRUCT if element in CONSTRUCTS else section_of(element),
                "element": element,
                "selection": selection[element],
                "selection_pct": share(selection[element], N_QUERIES),
                "all": population[element] if counted else "",
                "all_pct": share(population[element], population_size) if counted else "",
                "note": notes.get(element, ""),
            }
        )
    return rows


def uses_function(cypher: str, pattern: str) -> bool:
    return bool(re.search(pattern, re.sub(RELATIONSHIP_BRACKETS, "", cypher), re.I))


def write_functions_table(population: list, selection: list) -> None:
    """The Cypher functions and constructs SemGIR cannot express directly, with the selected queries using each."""
    all_text = [normalized(q.metadata["cypher"]) for q in population]
    selected = [(q.id, normalized(q.metadata["cypher"])) for q in selection]
    no_form = sum(
        any(uses_function(text, row[2]) for row in FUNCTIONS if row[0] == NO_FORM)
        for _, text in selected
    )
    any_row = sum(any(uses_function(text, row[2]) for row in FUNCTIONS) for _, text in selected)
    lines = [
        "# Cypher functions without a direct SemGIR element",
        "How often Text2Cypher gold queries use a Cypher function or construct that SemGIR cannot express directly, using the selection and test set of the README. A query can appear in several rows.",
        "",
        f"- **{any_row} of the 200 selected queries** use at least one row, and {no_form} use a row with no form.",
        "- **Classification:** read from the grammar, and not tested with the judge.",
        "- **Left out:** `count()`, `sum()`, `avg()`, `min()`, `max()`, `collect()`, `nodes()` and `relationships()`, which have direct elements.",
        "",
    ]
    titles = {
        NO_FORM: "No form in the grammar",
        CONVENTION: "Possible by convention",
        WORKAROUND: "Possible with a workaround",
    }
    for status, title in titles.items():
        lines += [
            f"## {title}",
            "",
            f"| Cypher | All test queries (of {len(population):,}) | Share of all | Selection (of {N_QUERIES}) | SemGIR | Selected queries |",
            "|---|---|---|---|---|---|",
        ]
        for row_status, name, pattern, semgir in FUNCTIONS:
            if row_status != status:
                continue
            total = sum(uses_function(text, pattern) for text in all_text)
            ids = [query_id for query_id, text in selected if uses_function(text, pattern)]
            listed = ", ".join(f"`{query_id}`" for query_id in ids) or "None"
            lines.append(
                f"| {name} | {total:,} | {share(total, len(population))}% | {len(ids)} | {semgir} | {listed} |"
            )
        lines.append("")
    (OUTPUT_DIR / "cypher_functions.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> None:
    dataset = Text2CypherDataset(TEXT2CYPHER_PATH)
    population = dataset.load(seed=SEED)
    selection = dataset.sample(N_QUERIES, seed=SEED)
    tags = {q.id: text2cypher_elements(q.id, q.metadata["cypher"]) for q in population}
    selection_counts = Counter(tag for q in selection for tag in tags[q.id])
    population_counts = Counter(tag for tagged in tags.values() for tag in tagged)

    raw_grailqa = {
        str(e["qid"]): e for e in json.loads(GRAILQA_PATH.read_text(encoding="utf-8"))
    }
    grailqa = GrailQADataset(GRAILQA_PATH)
    grailqa_population = grailqa.load(seed=SEED)
    grailqa_selection = grailqa.sample(N_QUERIES, seed=SEED)
    grailqa_tags = {q.id: grailqa_elements(raw_grailqa[q.id]) for q in grailqa_population}
    grailqa_counts = Counter(tag for q in grailqa_selection for tag in grailqa_tags[q.id])
    grailqa_all_counts = Counter(tag for tagged in grailqa_tags.values() for tag in tagged)

    upper_bound_note = "Maximum: superlatives can use order_by + limit or MAX/MIN, and counts can filter in constraint"
    grailqa_notes = {element: upper_bound_note for element in GRAILQA_UPPER_BOUND}
    grailqa_notes["Several hypotheses"] = NOTES["Several hypotheses"]

    summary = []
    for element in ELEMENTS + CONSTRUCTS:
        counted = element not in NOT_COUNTED_IN_ALL
        total = population_counts[element]
        note = NOTES.get(element, "")
        if element in GRAILQA_UPPER_BOUND and grailqa_counts[element]:
            note = f"GrailQA: {upper_bound_note}"
        summary.append(
            {
                "element": element,
                "group": group_of(
                    element, selection_counts[element], grailqa_counts[element]
                ),
                "text2cypher_selection": selection_counts[element],
                "text2cypher_all": total if counted else "",
                "text2cypher_all_pct": share(total, len(population)) if counted else "",
                "grailqa_selection": grailqa_counts[element],
                "note": note,
            }
        )
    write_csv(
        "summary.csv",
        [
            "element",
            "group",
            "text2cypher_selection",
            "text2cypher_all",
            "text2cypher_all_pct",
            "grailqa_selection",
            "note",
        ],
        summary,
    )
    dataset_columns = ["section", "element", "selection", "selection_pct", "all", "all_pct", "note"]
    write_csv(
        "text2cypher_elements.csv",
        dataset_columns,
        dataset_rows(ELEMENTS + CONSTRUCTS, selection_counts, population_counts, len(population), NOTES, NOT_COUNTED_IN_ALL),
    )
    write_csv(
        "grailqa_elements.csv",
        dataset_columns,
        dataset_rows(ELEMENTS, grailqa_counts, grailqa_all_counts, len(grailqa_population), grailqa_notes, set()),
    )
    write_csv(
        "queries.csv",
        ["id", "data_source", "question", "cypher", "elements"],
        [
            {
                "id": q.id,
                "data_source": q.metadata["data_source"],
                "question": q.text,
                "cypher": q.metadata["cypher"],
                "elements": "; ".join(sorted(tags[q.id])),
            }
            for q in selection
        ],
    )

    write_functions_table(population, selection)

    print(
        f"Text2Cypher: {len(selection)} of {len(population)}, "
        f"GrailQA: {len(grailqa_selection)} of {len(grailqa_population)}"
    )
    for row in summary:
        print(
            f"{row['group']:18}{row['element']:50}{row['text2cypher_selection']:>5}"
            f"{row['text2cypher_all_pct']:>7}{row['grailqa_selection']:>5}"
            f"{grailqa_all_counts[row['element']]:>6}"
        )


if __name__ == "__main__":
    main()
