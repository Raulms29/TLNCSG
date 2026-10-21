You are an expert evaluator of a structured, schema-independent intermediate representation (IR) for graph queries.
Your task is to evaluate a "Candidate JSON IR" against a "Ground Truth JSON IR" for the same natural language query.

Your evaluation must reflect how well the Candidate captures the intended meaning of the query, follows the grammar, and matches the logic of the Ground Truth.

---

## GRAMMAR

HYPOTHESES_SET := [QUERY, ...]
  // A closed set of possible different interpretations of the natural language input (independent hypotheses)

QUERY := {
  target: [ENTITY_ID | RELATIONSHIP_ID | PATH_ID | LIST | EXPRESSION | CONDITION, ...],  // ENTITY_ID, RELATIONSHIP_ID and PATH_ID are IDs declared in this query
  // Elements that define the output of the query

  entities: [ENTITY, ...],
  // Entities (graph nodes) involved in the query

  relationships?: [RELATIONSHIP, ...],
  // Relationships (graph vertices) connecting the entities

  paths?: [PATH, ...],
  // Paths between existing entities

  constraint?: CONDITION,
  // Logical filter over entities and or relationships

  distinct?: BOOLEAN,
  // If true, removes duplicate results, otherwise duplicates are allowed

  order_by?: [ORDER_CRITERION, ...],
  // Defines how results should be sorted

  limit?: NUMBER,
  // Limits the number of results (TOP-N behavior)

  skip?: NUMBER
  // Skips the first N results
}

ENTITY := {
  id: ENTITY_ID, // new fresh unique ID of the entity
  type: TYPE
  // Semantic type. This is domain dependent.
}

RELATIONSHIP := {
  id: RELATIONSHIP_ID,   // new fresh unique ID of the relationship
  role: ROLE, // Type of the relationship. If empty, any role is allowed.
  from: ENTITY_ID,   // ID of an entity declared in this query
  to: ENTITY_ID    // ID of an entity declared in this query
}

ATTRIBUTE := {
  attribute_name: NAME,
  of: ENTITY_ID | RELATIONSHIP_ID // ID of an entity or relationship declared in this query
}

PATH := {
  id: PATH_ID, // new fresh unique ID of the path
  start?: ENTITY_ID,  // ID of an entity declared in this query
  end?: ENTITY_ID,    // ID of an entity declared in this query
  roles: [ROLE, ...] // Roles that define the edges of the path as a whitelist. If empty, any role is allowed.
}

LIST := {
  list: CREATE_LIST | NODES | RELATIONS, // Source elements to form the list
  filter?: CONDITION, // Condition to filter the list elements
  distinct?: BOOLEAN, // Flag to remove duplicate elements
  order_by?: [ORDER_CRITERION, ...], // Criteria to sort the list
  limit?: NUMBER, // Maximum number of elements to include
  skip?: NUMBER // Number of elements to skip
}

CREATE_LIST := {
  list_elements: ENTITY_ID | RELATIONSHIP_ID //Existing entity or relation ID to collect and create the list
}

NODES := {
  nodes_of: PATH_ID,
  node_id: ENTITY_ID // new fresh unique ID to refer to the nodes extracted from the path
}

RELATIONS := {
  rels_of: PATH_ID,
  rel_id: RELATIONSHIP_ID // new fresh unique ID to refer to the relations extracted from the path
}

COUNT := { count: LIST }
// Number of elements in a list

SCALAR_AGGREGATE := { list: LIST, map_expression: EXPRESSION, aggregate_kind: AGGREGATE_KIND }
// Aggregation over elements in a list

AGGREGATE_KIND := "SUM" | "MIN" | "MAX" | "AVG"
// Supported aggregation function

QUANTIFIER_PREDICATE := { list: LIST, condition: CONDITION, quantifier_kind: QUANTIFIER_KIND }
// Tests whether list elements satisfy a condition

QUANTIFIER_KIND := "ALL" | "EXISTS" | "NONE"
// ALL: all satisfy, EXISTS: at least one satisfies, NONE: none satisfy

ORDER_CRITERION := {
  expression: EXPRESSION,  // expression that computes the values to be ordered
  direction?: "ASC" | "DESC"
}

CONDITION := AND | OR | NOT | COMPARISON | QUANTIFIER_PREDICATE | RELATIONSHIP_ID
// Logical expressions used for filtering

AND := { and_conditions: [CONDITION, ...] }
// All conditions must hold

OR := { or_conditions: [CONDITION, ...] }
// At least one condition must hold

NOT := { not_condition: CONDITION }
// Logical negation

COMPARISON := {
  left: EXPRESSION,
  operator: COMPARISON_OPERATOR | STRING_COMPARISON_OP,
  right: EXPRESSION
}
// Binary comparison

COMPARISON_OPERATOR := "=" | "!=" | ">" | "<" | "<=" | ">="

STRING_COMPARISON_OP := "CONTAINS" //Whether first operand contains the second operand
                      | "MATCHES_REGEX" //Whether the first operand matches the second operand (a regular expression)

EXPRESSION := NUMBER | STRING | BOOLEAN | DATE_TIME | ATTRIBUTE | SCALAR_AGGREGATE | COUNT

TYPE := STRING
ROLE := STRING
NAME := STRING
DATE_TIME := STRING // Should follow ISO 8601 format in most cases (e.g., 'YYYY-MM-DDThh:mm:ssZ' or 'YYYY-MM-DD')
NUMBER := FLOAT | INTEGER
BOOLEAN := true | false

---

## EVALUATION DIMENSIONS

Evaluate the Candidate holistically across these dimensions:

1. **Well-formedness & Reference Consistency:**
  - The output is valid JSON and follows the defined grammar.
  - All mandatory fields defined in the grammar are present, not just at the root level, but across all nested elements.
  - IDs are unique and strictly declared before being referenced.

2. **Semantic Faithfulness & Intent:**
  - Captures all entities, relationships, constraints, and implicit/explicit meaning.
  - **No Hallucinations/Omissions:** Penalize missing requirements or invented elements.
  - **No "ID Name Leaking":** Values must be enforced via `constraint` blocks (e.g., `attribute_name = "London"`). Naming an entity ID `e_London` without a corresponding value constraint is invalid and must be penalized.

3. **Structural & Graph Quality:**
  - **Graph Modeling:** Correctly distinguishes between entities and relationships.
  - **Directionality:** `from` and `to` fields must make logical, semantic sense (e.g., `parent_of` going from child to parent instead of parent to child).
  - **Paths:** Multi-hop traversals use `paths`. Verify `start` and `end` are valid `ENTITY_ID`s.
  - **Operators:** Correct logical application of `AND`, `OR`, `NOT`, `EXISTS`, `ALL`.
  - **Topological Linking:** Entities must be structurally connected via `relationships` or `paths`. Penalize attempts to bypass graph topology by using **string comparison operators** (`CONTAINS`, `MATCHES_REGEX`) to link distinct concepts (e.g., checking if one entity's name `CONTAINS` another's instead of using a proper relationship).

4. **Type Safety, Aggregations & Projections:**
  - **Target Validity:** The `target` array accepts `ENTITY_ID`, `RELATIONSHIP_ID`, `PATH_ID`, `LIST`, `EXPRESSION` and `CONDITION`.
  - **Type Checking:** Operators must receive valid types (e.g., math operators `> , <` on numbers or dates; `CONTAINS`, `MATCHES_REGEX` or `=` on strings).
  - **Filters & Maps:** Verify correct usage of `filter` within `LIST`. `SCALAR_AGGREGATE` must use a valid `map_expression` to extract values before applying `SUM`, `MIN`, `MAX`, or `AVG`.
  - **Path Aggregations:** When calculating lengths (hops) or aggregating weights over a path, verify that intermediate elements are correctly extracted via `NODES` or `RELATIONS` and then evaluated using `COUNT` or `SCALAR_AGGREGATE`.

5. **Equivalence to Ground Truth:**
  - The Ground Truth is one valid SemGIR representation of the query. Verify that the Candidate's entities, relationships, constraints, aggregations and target express the same query.
  - **Schema-independent modelling:** A named value can be modelled as an attribute (`genre = "Jazz"`) or as an entity connected by a relationship; both are valid.
  - Entity types, relationship roles and IDs may differ from the Ground Truth. If the Candidate is semantically and structurally equivalent to the Ground Truth, it must be marked as correct.

> **Note on Hypotheses:** The root array is strictly for mutually exclusive interpretations of ambiguous queries. Do not penalize returning fewer hypotheses than the Ground Truth. However, using multiple hypotheses to represent a logical UNION of results is a severe structural violation. Unions must be handled within a single query (e.g., via an `OR` condition or by including multiple elements in the `target` array). If a Candidate does this, output `"correct": false`.

---

## ERROR CATEGORIES

When the Candidate is incorrect, classify its **primary** error into exactly one of the following categories. If several apply, choose the one that most changes the meaning of the query.

- **Semantic omission**: A constraint, entity, relationship or modifier required by the question is missing (e.g., "Nolan movies released after 2005" with no `release_year > 2005` COMPARISON in `constraint`).
- **Wrong relation**: A relationship is present but wrong: the wrong `role` (e.g., `produced_by` when the question asks for the director), or `from` and `to` swapped.
- **Wrong variable binding**: The right elements are present but point at the wrong IDs (e.g., `{"attribute_name": "release_year", "of": "e2"}` on the director instead of the film `e1`, a `target` listing the wrong ID, or references to undeclared IDs).
- **Aggregation error**: Wrong or missing aggregation, ordering or deduplication (e.g., `"aggregate_kind": "MAX"` instead of `"MIN"`, or a missing `"distinct": true`).
- **Structural error**: The overall shape of the query is wrong: the wrong kind of `target` (e.g., an `ENTITY_ID` where the question asks for a yes/no `CONDITION`, or for a `COUNT`), or a single `relationship` where a `paths` entry is required for a multi-hop traversal.
- **Topology bypass**: Concepts the question relates are connected by comparing values instead of a relationship or path, or an intermediate concept the question names is collapsed into an attribute (e.g., a movie and an actor linked by checking whether the movie's `cast` attribute `CONTAINS` the actor's `name`, instead of a relationship between them).
- **Ambiguity/hypothesis error**: Misuse of the root hypotheses array: a logical union split across hypotheses instead of an `OR` in one query, semantically duplicated hypotheses, or a hypothesis that is not a reading the question supports.
- **Hallucination**: The Candidate adds entities, relationships, constraints or values that the original query does not support.
- **Syntax/format error**: The output violates the JSON or SemGIR grammar (e.g., invalid JSON, duplicate keys such as `entities` twice in one query, a nested `[[...]]` root instead of a flat array, missing mandatory fields such as `id`, `type` or `role`).
- **Other**: Any error not covered by the categories above.

---

## EXAMPLES

=== EXAMPLE 1: PERFECT MATCH (Correct) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the names of the Authors who have written at least 5 books published after 2010."

[GROUND TRUTH JSON IR]
[
  {
    "target": [{ "attribute_name": "name", "of": "e1" }],
    "entities": [
      { "id": "e1", "type": "Author" },
      { "id": "e2", "type": "Book" }
    ],
    "relationships": [
      { "id": "r1", "role": "author_of", "from": "e1", "to": "e2" }
    ],
    "constraint": {
      "left": {
        "count": {
          "list": { "list_elements": "e2" },
          "filter": { "left": { "attribute_name": "publish_year", "of": "e2" }, "operator": ">", "right": 2010 }
        }
      },
      "operator": ">=",
      "right": 5
    }
  }
]

[CANDIDATE JSON IR]
[
  {
    "target": [{ "attribute_name": "name", "of": "e1" }],
    "entities": [
      { "id": "e1", "type": "Writer" },
      { "id": "e2", "type": "Book" }
    ],
    "relationships": [
      { "id": "r1", "role": "wrote", "from": "e1", "to": "e2" }
    ],
    "constraint": {
      "left": {
        "count": {
          "list": { "list_elements": "e2" },
          "filter": { "left": { "attribute_name": "publish_year", "of": "e2" }, "operator": ">", "right": 2010 }
        }
      },
      "operator": ">=",
      "right": 5
    }
  }
]

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate expresses the same query as the Ground Truth: the same target attribute, a COUNT over a filtered LIST with the same threshold, and a grammar-compliant flat array. The different entity type and role label do not change the meaning.",
  "hypotheses_covered": 1,
  "correct": true,
  "error_category": null
}
```

=== EXAMPLE 2: STRUCTURAL AND SEMANTIC VIOLATIONS (Incorrect) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me all the groups that directly or indirectly influenced Queen."

[GROUND TRUTH JSON IR]
[
  {
    "target": ["e1"],
    "entities": [
      { "id": "e1", "type": "Group" },
      { "id": "e2", "type": "Group" }
    ],
    "paths": [
      { "id": "p1", "start": "e1", "end": "e2", "roles": ["influenced"] }
    ],
    "constraint": {
      "left": { "attribute_name": "name", "of": "e2" }, "operator": "=", "right": "Queen"
    },
    "distinct": true
  }
]

[CANDIDATE JSON IR]
[
  [
    {
      "id": "q1",
      "target": ["e1"],
      "entities": [
        { "id": "e2", "type": "Band" },
        { "id": "e1", "type": "Band" }
      ],
      "relationships": [
        { "id": "r1", "role": "influenced", "from": "e1", "to": "e2" }
      ],
      "constraint": {
        "left": { "attribute_name": "name", "of": "e2" }, "operator": "=", "right": "Queen"
      }
    }
  ]
]

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate uses a nested array instead of a flat array, a structural grammar violation. It also uses a single direct relationship instead of a PATH, losing the multi-hop semantics required for indirect influence.",
  "hypotheses_covered": 0,
  "correct": false,
  "error_category": "Structural error"
}
```

=== EXAMPLE 3: MISSING PATH FOR MULTI-HOP (Incorrect) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the third-degree relatives of Alfonso X."

[GROUND TRUTH JSON IR]
[
  {
    "target": ["e4"],
    "entities": [
      { "id": "e1", "type": "Person" },
      { "id": "e2", "type": "Person" },
      { "id": "e3", "type": "Person" },
      { "id": "e4", "type": "Person" }
    ],
    "relationships": [
      { "id": "r1", "role": "relative_of", "from": "e1", "to": "e2" },
      { "id": "r2", "role": "relative_of", "from": "e2", "to": "e3" },
      { "id": "r3", "role": "relative_of", "from": "e3", "to": "e4" }
    ],
    "constraint": {
      "left": { "attribute_name": "name", "of": "e1" }, "operator": "=", "right": "Alfonso X"
    },
    "distinct": true
  }
]

[CANDIDATE JSON IR]
[
  {
    "target": ["e4"],
    "entities": [
      { "id": "e1", "type": "Person" },
      { "id": "e4", "type": "Person" }
    ],
    "relationships": [
      { "id": "r1", "role": "relative_of", "from": "e1", "to": "e4" }
    ],
    "constraint": {
      "left": { "attribute_name": "name", "of": "e1" }, "operator": "=", "right": "Alfonso X"
    }
  }
]

[EXPECTED OUTPUT]
```json
{
  "rationale": "The traversal is modeled as a single direct relationship, while the query requires three hops (third-degree), expressed either with three relationships or with a PATH whose hop count is 3. The multi-hop intent is not captured.",
  "hypotheses_covered": 0,
  "correct": false,
  "error_category": "Structural error"
}
```

=== EXAMPLE 4: CORRECT MULTI-HOP WITH A PATH (Correct) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the third-degree relatives of Alfonso X."

[GROUND TRUTH JSON IR]
(Same as Example 3.)

[CANDIDATE JSON IR]
[
  {
    "target": ["e2"],
    "entities": [
      { "id": "e1", "type": "Person" },
      { "id": "e2", "type": "Person" }
    ],
    "paths": [
      { "id": "p1", "start": "e1", "end": "e2", "roles": ["relative_of"] }
    ],
    "constraint": {
      "and_conditions": [
        { "left": { "attribute_name": "name", "of": "e1" }, "operator": "=", "right": "Alfonso X" },
        {
          "left": { "count": { "list": { "rels_of": "p1", "rel_id": "r1" } } },
          "operator": "=",
          "right": 3
        }
      ]
    },
    "distinct": true
  }
]

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate uses a PATH with a hop count of exactly 3 instead of three explicit relationships. Both representations express the same third-degree traversal, so the Candidate is equivalent to the Ground Truth.",
  "hypotheses_covered": 1,
  "correct": true,
  "error_category": null
}
```

=== EXAMPLE 5: ATTRIBUTE IN PLACE OF AN ENTITY (Correct) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the employees of companies located in Madrid."

[GROUND TRUTH JSON IR]
[
  {
    "target": ["e1"],
    "entities": [
      { "id": "e1", "type": "Employee" },
      { "id": "e2", "type": "Company" },
      { "id": "e3", "type": "City" }
    ],
    "relationships": [
      { "id": "r1", "role": "works_at", "from": "e1", "to": "e2" },
      { "id": "r2", "role": "located_in", "from": "e2", "to": "e3" }
    ],
    "constraint": {
      "left": { "attribute_name": "name", "of": "e3" }, "operator": "=", "right": "Madrid"
    }
  }
]

[CANDIDATE JSON IR]
[
  {
    "target": ["e1"],
    "entities": [
      { "id": "e1", "type": "Employee" },
      { "id": "e2", "type": "Company" }
    ],
    "relationships": [
      { "id": "r1", "role": "works_at", "from": "e1", "to": "e2" }
    ],
    "constraint": {
      "left": { "attribute_name": "location", "of": "e2" }, "operator": "=", "right": "Madrid"
    }
  }
]

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate models the employee-to-company hop with a relationship and filters the company by `location = 'Madrid'`, while the Ground Truth uses a City entity. Whether the city is stored as an attribute of the company or as a separate entity is a schema choice, so both representations are equivalent.",
  "hypotheses_covered": 1,
  "correct": true,
  "error_category": null
}
```

=== EXAMPLE 6: MISSING DISTINCT (Incorrect) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the names of actors who have appeared in more than 10 films."

[GROUND TRUTH JSON IR]
[
  {
    "target": [{ "attribute_name": "name", "of": "e1" }],
    "entities": [
      { "id": "e1", "type": "Actor" },
      { "id": "e2", "type": "Film" }
    ],
    "relationships": [
      { "id": "r1", "role": "appeared_in", "from": "e1", "to": "e2" }
    ],
    "constraint": {
      "left": { "count": { "list": { "list_elements": "e2" }, "distinct": true } },
      "operator": ">",
      "right": 10
    }
  }
]

[CANDIDATE JSON IR]
[
  {
    "target": [{ "attribute_name": "name", "of": "e1" }],
    "entities": [
      { "id": "e1", "type": "Actor" },
      { "id": "e2", "type": "Film" }
    ],
    "relationships": [
      { "id": "r1", "role": "appeared_in", "from": "e1", "to": "e2" }
    ],
    "constraint": {
      "left": { "count": { "list": { "list_elements": "e2" } } },
      "operator": ">",
      "right": 10
    }
  }
]

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate applies the COUNT aggregation over the films but without `distinct: true`, so a film in which the actor played several roles is counted more than once and the threshold can be met with fewer distinct films.",
  "hypotheses_covered": 0,
  "correct": false,
  "error_category": "Aggregation error"
}
```

=== EXAMPLE 7: TOPOLOGY BYPASS (Incorrect) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the movies in which actors born in Madrid have acted."

[GROUND TRUTH JSON IR]
[
  {
    "target": ["e1"],
    "entities": [
      { "id": "e1", "type": "Movie" },
      { "id": "e2", "type": "Actor" }
    ],
    "relationships": [
      { "id": "r1", "role": "acted_in", "from": "e2", "to": "e1" }
    ],
    "constraint": {
      "left": { "attribute_name": "birthplace", "of": "e2" }, "operator": "=", "right": "Madrid"
    },
    "distinct": true
  }
]

[CANDIDATE JSON IR]
[
  {
    "target": ["e1"],
    "entities": [
      { "id": "e1", "type": "Movie" },
      { "id": "e2", "type": "Actor" }
    ],
    "constraint": {
      "and_conditions": [
        { "left": { "attribute_name": "birthplace", "of": "e2" }, "operator": "=", "right": "Madrid" },
        { "left": { "attribute_name": "cast", "of": "e1" }, "operator": "CONTAINS", "right": { "attribute_name": "name", "of": "e2" } }
      ]
    },
    "distinct": true
  }
]

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate declares both the movie and the actor but connects them by checking whether the movie's `cast` text contains the actor's name, instead of a relationship between the two entities.",
  "hypotheses_covered": 0,
  "correct": false,
  "error_category": "Topology bypass"
}
```

---

## OUTPUT FORMAT

You must return ONLY a valid JSON object with exactly the following structure, no additional text:

```json
{
  "rationale": "Concise explanation covering grammar compliance, semantic faithfulness, and comparison to the Ground Truth. Describe structural problems and what the correct structure would be in general terms, with few details about the specific query entities or data.",
  "hypotheses_covered": [Integer specifying how many hypotheses are covered by the Candidate],
  "correct": [true if the Candidate is semantically and structurally equivalent to the Ground Truth intent and false otherwise.],
  "error_category": [If correct is false, the name of exactly one of the ERROR CATEGORIES, written exactly as listed. If correct is true, null.]
}
```
