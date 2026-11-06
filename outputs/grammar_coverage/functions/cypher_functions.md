# Cypher functions without a direct SemGIR element
How often Text2Cypher gold queries use a Cypher function or construct that SemGIR cannot express directly, using the selection and test set of `grammar_coverage.md`. A query can appear in several rows.

- **63 of the 200 selected queries** use at least one row, and 29 use a row with no form.
- **Classification:** read from the grammar, and not tested with the judge.
- **Left out:** `count()`, `sum()`, `avg()`, `min()`, `max()`, `collect()`, `nodes()` and `relationships()`, which have direct elements.

## No form in the grammar

| Cypher | All test queries (of 4,297) | Share of all | Selection (of 200) | SemGIR | Selected queries |
|---|---|---|---|---|---|
| `properties()` | 197 | 4.6% | 15 | `ATTRIBUTE` needs a specific name. Provisionally, returning the node counts | `T2C_11140`, `T2C_12888`, `T2C_12897`, `T2C_18029`, `T2C_12328`, `T2C_13581`, `T2C_10712`, `T2C_12608`, `T2C_18218`, `T2C_9240`, `T2C_10634`, `T2C_13905`, `T2C_10671`, `T2C_12427`, `T2C_10680` |
| `keys()`, usually with `n[key]` | 115 | 2.7% | 7 | `ATTRIBUTE` needs a specific name | `T2C_17290`, `T2C_9381`, `T2C_17198`, `T2C_9426`, `T2C_17052`, `T2C_12528`, `T2C_9447` |
| Arithmetic and durations: `+`, `-`, `*`, `/`, `abs()`, `sqrt()`, `ceil()`, `duration.*` | 41 | 1.0% | 3 | `EXPRESSION` has no arithmetic | `T2C_32196`, `T2C_41989`, `T2C_30847` |
| String and list manipulation: `split()`, `substring()`, `right()`, `range()`, `reduce()`, `coalesce()`, `apoc.*`, `UNWIND`, `[x IN list]` | 30 | 0.7% | 0 | No such operation | None |
| `date()` or `datetime()` without a value: converting an attribute, or the current date | 33 | 0.8% | 3 | `DATE_TIME` is only a fixed value | `T2C_3284`, `T2C_15855`, `T2C_34169` |
| `size()` or `length()` of a property | 26 | 0.6% | 1 | `COUNT` needs a `LIST` of entities or relationships | `T2C_41946` |

## Possible by convention

| Cypher | All test queries (of 4,297) | Share of all | Selection (of 200) | SemGIR | Selected queries |
|---|---|---|---|---|---|
| `type(r)` | 172 | 4.0% | 7 | `role` as an attribute: `{ "attribute_name": "role", "of": "r1" }` | `T2C_11510`, `T2C_13048`, `T2C_11549`, `T2C_13581`, `T2C_11894`, `T2C_13905`, `T2C_11803` |
| `labels(n)` | 90 | 2.1% | 4 | `type` as an attribute: `{ "attribute_name": "type", "of": "e1" }` | `T2C_18112`, `T2C_3839`, `T2C_16454`, `T2C_16424` |

## Possible with a workaround

| Cypher | All test queries (of 4,297) | Share of all | Selection (of 200) | SemGIR | Selected queries |
|---|---|---|---|---|---|
| `IS NULL`, `IS NOT NULL` | 172 | 4.0% | 4 | `=` or `!=` with an empty value, or not-exists | `T2C_7888`, `T2C_25247`, `T2C_44954`, `T2C_35475` |
| `STARTS WITH`, `ENDS WITH` | 149 | 3.5% | 9 | `MATCHES_REGEX` | `T2C_7888`, `T2C_10299`, `T2C_34727`, `T2C_9713`, `T2C_19343`, `T2C_15177`, `T2C_24522`, `T2C_34853`, `T2C_14718` |
| `shortestPath()` | 49 | 1.1% | 3 | `PATH` ordered by the `COUNT` of its `RELATIONS`, with `limit` 1 | `T2C_6479`, `T2C_6555`, `T2C_6541` |
| `size(list)` | 55 | 1.3% | 2 | `COUNT` | `T2C_44980`, `T2C_11803` |
| `length(path)` | 22 | 0.5% | 2 | `COUNT` over `rels_of` | `T2C_13299`, `T2C_13171` |
| `date()` or `datetime()` with a value | 80 | 1.9% | 5 | A `DATE_TIME` string | `T2C_25425`, `T2C_44464`, `T2C_29361`, `T2C_39875`, `T2C_7660` |
| `toFloat()`, `toInteger()`, `toLower()` | 42 | 1.0% | 2 | Usually unnecessary, or a case-insensitive `MATCHES_REGEX` | `T2C_32114`, `T2C_30847` |
| `id()` | 5 | 0.1% | 1 | `{ "attribute_name": "id", ... }` | `T2C_27912` |
