# SemGIR element coverage of Text2Cypher
How many queries of each pipeline selection use each SemGIR grammar element, and which elements GrailQA does not cover.

## Setup

- **Text2Cypher selection:** `Text2CypherDataset("datasets/text2cypher_2025v1/test.parquet").sample(200, seed=42)`, the call the pipeline makes. It is stable across repeated calls.
- **All Text2Cypher test queries:** the 4,297 eligible queries the selection is sampled from.
- **GrailQA selection:** `GrailQADataset("datasets/GrailQA_v1.0/grailqa_v1.0_dev.json").sample(200, seed=42)`. It is identical to `datasets/selected/selected_queries_grailqa_n200_seed42.csv`.
- **All GrailQA dev templates:** the 1,764 templates, one paraphrase each, the selection is sampled from.
- **Counting:** a query counts when its gold query most naturally maps to the element, so a model may encode it differently. A query can use several elements, so columns do not add up to 200.
- **Mapping choices:** `STARTS WITH` and `ENDS WITH` are not regex in Cypher, but they count as `MATCHES_REGEX` because SemGIR has no other way to express them. A bounded path such as `[*2]` counts as `PATH` plus a `COUNT` of its `RELATIONS` compared with a number, as in the prompt's 3-hop example. A named path counts as `PATH` even without a variable-length relationship. `IS NOT NULL` counts as `!=` with an empty value and `IS NULL` as `=` with an empty value; a not-exists condition is also valid.
- **Checking:** Text2Cypher elements are tagged with regexes on the Cypher, with string literals removed. They were compared with the parse trees of `antlr4-cypher`, which parsed 3,973 of the 4,297 queries and 184 of the 200 selected; a sample of each remaining disagreement was read and the regex was right in those. The 16 selected queries it could not parse were read by hand. The parser does not accept `=~`, `UNION`, `exists(pattern)` or `count{}`, and its `BOOLEAN` check did not work, so across all test queries those rest on the regexes alone. `LIST.order_by` and `LIST.limit` were counted by reading the selection.

## Full table per dataset

Every grammar element, in grammar order, including those a dataset never uses.

### GrailQA

| Section | SemGIR element | Selection (of 200) | All dev templates (of 1,764) | Share of all |
|---|---|---|---|---|
| Hypotheses | One hypothesis | 200 | 1,764 | 100.0% |
|  | Several hypotheses | 0 | 0 | 0.0% |
| Query | `ENTITY` | 200 | 1,764 | 100.0% |
|  | `relationships` | 168 | 1,447 | 82.0% |
|  | `PATH` | 0 | 0 | 0.0% |
|  | `constraint` | 186 | 1,640 | 93.0% |
|  | Query `distinct` | 0 | 0 | 0.0% |
|  | `order_by` | 17* | 147* | 8.3% |
|  | `limit` | 17* | 147* | 8.3% |
|  | Query `skip` | 0 | 0 | 0.0% |
| Target | Target `ENTITY_ID` | 190 | 1,677 | 95.1% |
|  | Target `RELATIONSHIP_ID` | 0 | 0 | 0.0% |
|  | Target `PATH_ID` | 0 | 0 | 0.0% |
|  | Target `LIST` | 0 | 0 | 0.0% |
|  | Target `ATTRIBUTE` | 0 | 0 | 0.0% |
|  | Target relationship attribute | 0 | 0 | 0.0% |
|  | Target `COUNT` | 10 | 87 | 4.9% |
|  | Target `SCALAR_AGGREGATE` | 0 | 0 | 0.0% |
|  | Target `CONDITION` | 0 | 0 | 0.0% |
|  | Several targets | 0 | 0 | 0.0% |
| Relationship and attribute | Relationship with a role | 168 | 1,447 | 82.0% |
|  | Relationship with any role | 0 | 0 | 0.0% |
|  | `ATTRIBUTE` (anywhere) | 200 | 1,764 | 100.0% |
|  | Relationship attribute | 0 | 0 | 0.0% |
| Path | `PATH` with a role list | 0 | 0 | 0.0% |
|  | `PATH` with an empty role list | 0 | 0 | 0.0% |
| List | `LIST` (any kind) | 27* | 234* | 13.3% |
|  | `CREATE_LIST` | 27* | 234* | 13.3% |
|  | `NODES` | 0 | 0 | 0.0% |
|  | `RELATIONS` | 0 | 0 | 0.0% |
|  | `LIST.filter` (optional) | 13* | 110* | 6.2% |
|  | `LIST.distinct` | 0 | 0 | 0.0% |
|  | `LIST.order_by` | 0 | 0 | 0.0% |
|  | `LIST.limit` | 0 | 0 | 0.0% |
|  | `LIST.skip` | 0 | 0 | 0.0% |
| Aggregation | `COUNT` | 10 | 87 | 4.9% |
|  | `SCALAR_AGGREGATE` | 17* | 147* | 8.3% |
|  | `SUM` | 0 | 0 | 0.0% |
|  | `MIN` | 8* | 67* | 3.8% |
|  | `MAX` | 9* | 80* | 4.5% |
|  | `AVG` | 0 | 0 | 0.0% |
| Quantifier | `QUANTIFIER_PREDICATE` (optional) | 0 | 0 | 0.0% |
|  | `QUANTIFIER ALL` | 0 | 0 | 0.0% |
|  | `QUANTIFIER EXISTS` (optional) | 0 | 0 | 0.0% |
|  | `QUANTIFIER NONE` (explicit) | 0 | 0 | 0.0% |
| Order direction | `ASC` | 8* | 67* | 3.8% |
|  | `DESC` | 9* | 80* | 4.5% |
| Condition | `AND` | 18 | 118 | 6.7% |
|  | `OR` | 0 | 0 | 0.0% |
|  | `NOT` | 0 | 0 | 0.0% |
|  | `COMPARISON` | 186 | 1,640 | 93.0% |
|  | `RELATIONSHIP_ID` as a condition | 0 | 0 | 0.0% |
| Operator | `=` | 178 | 1,573 | 89.2% |
|  | `!=` | 0 | 0 | 0.0% |
|  | `>` | 3 | 14 | 0.8% |
|  | `<` | 3 | 18 | 1.0% |
|  | `<=` | 4 | 30 | 1.7% |
|  | `>=` | 4 | 25 | 1.4% |
|  | `CONTAINS` | 0 | 0 | 0.0% |
|  | `MATCHES_REGEX` | 0 | 0 | 0.0% |
| Value | `STRING` value | 163 | 1,416 | 80.3% |
|  | `NUMBER` value | 25 | 199 | 11.3% |
|  | `BOOLEAN` value | 0 | 0 | 0.0% |
|  | `DATE_TIME` | 4 | 43 | 2.4% |

\* Maximum, because the encoding is the model's choice. GrailQA's superlatives can use `order_by` + `limit` or `MAX`/`MIN`, and all of them are top-1. A count's condition can sit in `LIST.filter` or `constraint`. The 10 counts are certain for `LIST` and `CREATE_LIST`. With `MAX`/`MIN`, the 14 selected superlatives without another filter would also use `constraint`, `COMPARISON` and `=`.

### Text2Cypher

| Section | SemGIR element | Selection (of 200) | All test queries (of 4,297) | Share of all |
|---|---|---|---|---|
| Hypotheses | One hypothesis | 200 | 4,297 | 100.0% |
|  | Several hypotheses | 0 | 0 | 0.0% |
| Query | `ENTITY` | 200 | 4,297 | 100.0% |
|  | `relationships` | 118 | 2,391 | 55.6% |
|  | `PATH` | 20 | 341 | 7.9% |
|  | `constraint` | 160 | 3,336 | 77.6% |
|  | Query `distinct` | 26 | 403 | 9.4% |
|  | `order_by` | 48 | 1,170 | 27.2% |
|  | `limit` | 65 | 1,301 | 30.3% |
|  | Query `skip` | 1 | 15 | 0.3% |
| Target | Target `ENTITY_ID` | 41 | 775 | 18.0% |
|  | Target `RELATIONSHIP_ID` | 3 | 53 | 1.2% |
|  | Target `PATH_ID` | 3 | 49 | 1.1% |
|  | Target `LIST` | 8 | 97 | 2.3% |
|  | Target `ATTRIBUTE` | 114 | 2,524 | 58.7% |
|  | Target relationship attribute | 1 | 36 | 0.8% |
|  | Target `COUNT` | 28 | 817 | 19.0% |
|  | Target `SCALAR_AGGREGATE` | 9 | 302 | 7.0% |
|  | Target `CONDITION` | 3 | 51 | 1.2% |
|  | Several targets | 59 | 1,598 | 37.2% |
| Relationship and attribute | Relationship with a role | 94 | 1,929 | 44.9% |
|  | Relationship with any role | 28 | 509 | 11.8% |
|  | `ATTRIBUTE` (anywhere) | 192 | 4,173 | 97.1% |
|  | Relationship attribute | 17 | 338 | 7.9% |
| Path | `PATH` with a role list | 0 | 6 | 0.1% |
|  | `PATH` with an empty role list | 20 | 335 | 7.8% |
| List | `LIST` (any kind) | 62 | 1,462 | 34.0% |
|  | `CREATE_LIST` | 52 | 1,318 | 30.7% |
|  | `NODES` | 5 | 68 | 1.6% |
|  | `RELATIONS` | 7 | 97 | 2.3% |
|  | `LIST.filter` (optional) | 23 | 724 | 16.8% |
|  | `LIST.distinct` | 9 | 199 | 4.6% |
|  | `LIST.order_by` | 2 | not counted | not counted |
|  | `LIST.limit` | 2 | not counted | not counted |
|  | `LIST.skip` | 0 | 0 | 0.0% |
| Aggregation | `COUNT` | 48 | 1,074 | 25.0% |
|  | `SCALAR_AGGREGATE` | 10 | 340 | 7.9% |
|  | `SUM` | 3 | 55 | 1.3% |
|  | `MIN` | 0 | 37 | 0.9% |
|  | `MAX` | 2 | 47 | 1.1% |
|  | `AVG` | 5 | 233 | 5.4% |
| Quantifier | `QUANTIFIER_PREDICATE` (optional) | 7 | 96 | 2.2% |
|  | `QUANTIFIER ALL` | 0 | 1 | 0.0% |
|  | `QUANTIFIER EXISTS` (optional) | 7 | 95 | 2.2% |
|  | `QUANTIFIER NONE` (explicit) | 0 | 0 | 0.0% |
| Order direction | `ASC` | 12 | 289 | 6.7% |
|  | `DESC` | 36 | 888 | 20.7% |
| Condition | `AND` | 55 | 1,028 | 23.9% |
|  | `OR` | 2 | 108 | 2.5% |
|  | `NOT` | 6 | 94 | 2.2% |
|  | `COMPARISON` | 158 | 3,285 | 76.4% |
|  | `RELATIONSHIP_ID` as a condition | 10 | 125 | 2.9% |
| Operator | `=` | 110 | 2,261 | 52.6% |
|  | `!=` | 9 | 287 | 6.7% |
|  | `>` | 16 | 465 | 10.8% |
|  | `<` | 10 | 215 | 5.0% |
|  | `<=` | 4 | 47 | 1.1% |
|  | `>=` | 8 | 107 | 2.5% |
|  | `CONTAINS` | 9 | 180 | 4.2% |
|  | `MATCHES_REGEX` (2 from `=~`, 9 from `STARTS WITH`, 0 from `ENDS WITH`) | 11 | 189 | 4.4% |
| Value | `STRING` value | 118 | 2,527 | 58.8% |
|  | `NUMBER` value | 45 | 936 | 21.8% |
|  | `BOOLEAN` value | 1 | 31 | 0.7% |
|  | `DATE_TIME` | 6 | 143 | 3.3% |

Cypher constructs without a direct element, which is not a complete list. `functions/cypher_functions.md` has the full list of functions, and `OPTIONAL MATCH` is not counted.

| Construct | Selection (of 200) | All test queries (of 4,297) | Share of all |
|---|---|---|---|
| Target `properties()`, `labels()`, `type()` or `keys()` | 23 | 386 | 9.0% |
| `ANY(key IN keys(n))` | 6 | 84 | 2.0% |
| `size()` or `length()` of a property | 1 | 26 | 0.6% |
| Several role types or labels, such as `[:A\|B]` | 1 | 8 | 0.2% |
| `UNION` | 4 | 93 | 2.2% |

## Comparison

### In Text2Cypher, missing from GrailQA

| SemGIR element | Text2Cypher selection (of 200) | All test queries (of 4,297) |
|---|---|---|
| Target `ATTRIBUTE` | 114 | 58.7% |
| Several targets | 59 | 37.2% |
| Relationship with any role | 28 | 11.8% |
| Query `distinct` | 26 | 9.4% |
| `PATH` | 20 | 7.9% |
| `PATH` with an empty role list | 20 | 7.8% |
| Relationship attribute | 17 | 7.9% |
| `MATCHES_REGEX` (2 from `=~`, 9 from `STARTS WITH`, 0 from `ENDS WITH`) | 11 | 4.4% |
| `RELATIONSHIP_ID` as a condition | 10 | 2.9% |
| Target `SCALAR_AGGREGATE` | 9 | 7.0% |
| `LIST.distinct` | 9 | 4.6% |
| `!=` | 9 | 6.7% |
| `CONTAINS` | 9 | 4.2% |
| Target `LIST` | 8 | 2.3% |
| `RELATIONS` | 7 | 2.3% |
| `QUANTIFIER_PREDICATE` (optional) | 7 | 2.2% |
| `QUANTIFIER EXISTS` (optional) | 7 | 2.2% |
| `NOT` | 6 | 2.2% |
| `NODES` | 5 | 1.6% |
| `AVG` | 5 | 5.4% |
| Target `RELATIONSHIP_ID` | 3 | 1.2% |
| Target `PATH_ID` | 3 | 1.1% |
| Target `CONDITION` | 3 | 1.2% |
| `SUM` | 3 | 1.3% |
| `LIST.order_by` | 2 | not counted |
| `LIST.limit` | 2 | not counted |
| `OR` | 2 | 2.5% |
| Query `skip` | 1 | 0.3% |
| Target relationship attribute | 1 | 0.8% |
| `BOOLEAN` value | 1 | 0.7% |

### In neither selection

| SemGIR element | Text2Cypher selection | GrailQA selection | All test queries |
|---|---|---|---|
| Several hypotheses | 0 | 0 | 0 queries |
| `PATH` with a role list | 0 | 0 | 6 queries |
| `LIST.skip` | 0 | 0 | 0 queries |
| `QUANTIFIER ALL` | 0 | 0 | 1 query |
| `QUANTIFIER NONE` (explicit) | 0 | 0 | 0 queries |

### In GrailQA only

| SemGIR element | Text2Cypher selection | GrailQA selection | All test queries |
|---|---|---|---|
| `MIN` | 0 | 8* | 37 (0.9%) |

### In both

| SemGIR element | Text2Cypher selection (of 200) | All test queries (of 4,297) | GrailQA selection (of 200) |
|---|---|---|---|
| One hypothesis | 200 | 100.0% | 200 |
| `ENTITY` | 200 | 100.0% | 200 |
| `ATTRIBUTE` (anywhere) | 192 | 97.1% | 200 |
| `constraint` | 160 | 77.6% | 186 |
| `COMPARISON` | 158 | 76.4% | 186 |
| `relationships` | 118 | 55.6% | 168 |
| `STRING` value | 118 | 58.8% | 163 |
| `=` | 110 | 52.6% | 178 |
| Relationship with a role | 94 | 44.9% | 168 |
| `limit` | 65 | 30.3% | 17* |
| `LIST` (any kind) | 62 | 34.0% | 27* |
| `AND` | 55 | 23.9% | 18 |
| `CREATE_LIST` | 52 | 30.7% | 27* |
| `order_by` | 48 | 27.2% | 17* |
| `COUNT` | 48 | 25.0% | 10 |
| `NUMBER` value | 45 | 21.8% | 25 |
| Target `ENTITY_ID` | 41 | 18.0% | 190 |
| `DESC` | 36 | 20.7% | 9* |
| Target `COUNT` | 28 | 19.0% | 10 |
| `LIST.filter` (optional) | 23 | 16.8% | 13* |
| `>` | 16 | 10.8% | 3 |
| `ASC` | 12 | 6.7% | 8* |
| `SCALAR_AGGREGATE` | 10 | 7.9% | 17* |
| `<` | 10 | 5.0% | 3 |
| `>=` | 8 | 2.5% | 4 |
| `DATE_TIME` | 6 | 3.3% | 4 |
| `<=` | 4 | 1.1% | 4 |
| `MAX` | 2 | 1.1% | 9* |

\* Maximum, see the GrailQA table.

## Findings

- **Text2Cypher adds 28 distinct elements GrailQA lacks**, 20 of them in fewer than 10 selected queries. The table has 30 rows because `PATH` and `QUANTIFIER_PREDICATE` also appear as totals over their variants.
- **`ALL`, explicit `NONE`, `LIST.skip` and `PATH` role lists are dataset gaps.** The whole test set has at most 6 queries of each, so another seed would not cover them.
- **`MIN` is a sampling miss.** The test set has 37 queries with it.
- **Only 2 selected queries contain a real regex.** The other 9 `MATCHES_REGEX` queries use `STARTS WITH`, so the model has to write the regex itself.
- **5 of the 7 `RELATIONS` queries are bounded paths.** A model could also encode them as explicit relationships, which would leave 2.
- **`QUANTIFIER EXISTS` is optional.** Its 7 queries also fit `RELATIONSHIP_ID` as a condition (4) or a target `CONDITION` (3).
- **`LIST.filter` and `NONE` are never required.** 23 selected queries have a condition ahead of an aggregate that could use `LIST.filter` or stay in `constraint`, and 5 negated queries could use `NONE` instead of `NOT`.
- **Paths come from one source.** All 20 `PATH`, 5 `NODES`, 7 `RELATIONS`, 3 target `PATH_ID` and 3 target `CONDITION` queries are `neo4jLabs_functional_cypher`, as are `OR` (2) and query `skip` (1). The 20 `PATH` queries follow about 8 templates and none has a role list.
- **The selection's source mix:** 68 of the 200 queries are `neo4jLabs_functional_cypher`.

## Files

- `results/text2cypher_elements.csv`: every element for Text2Cypher, with counts and shares for the selection and all test queries.
- `results/grailqa_elements.csv`: every element for GrailQA, with counts and shares for the selection and all dev templates.
- `results/summary.csv`: per element, the comparison group and the counts side by side.
- `results/queries.csv`: the 200 selected Text2Cypher queries with source, question, Cypher and tagged elements.
- `functions/cypher_functions.md`: the Cypher functions and constructs without a direct element, with counts, the SemGIR workaround and the selected queries using each.
- `functions/properties_queries.md`: the autoresearch pool queries that ask for all properties of a node, with their outputs and verdicts.
- `count_elements.py`: generates everything in `results/` and `functions/cypher_functions.md`. Run it from the repository root.
