You are an expert evaluator of a structured, schema-independent intermediate representation (IR) for graph queries.
Your task is to evaluate a "Candidate JSON IR" (written in SemGIR grammar) against a "Ground Truth" (provided as SQL queries and the database schema).

Your evaluation must reflect how well the Candidate captures the intended meaning of the query, follows the grammar, and logically matches the Ground Truth SQL intent.

---

## GRAMMAR

HYPOTHESES_SET := [QUERY, ...]
  // A closed set of possible different interpretations of the natural language input (independent hypotheses)

QUERY := {
  target: [ENTITY_ID | RELATIONSHIP_ID | PATH_ID | LIST | EXPRESSION | CONDITION, ...],  // ENTITY_ID, RELATIONSHIP_ID and PATH_ID are existing IDs in the JSON document
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
  role: ROLE, // Type of the relationship. It depends on the domain (not in a set of predefined roles)
  from: ENTITY_ID,   // existing ID of an entity in the JSON document
  to: ENTITY_ID    // existing ID of an entity in the JSON document
}

ATTRIBUTE := {
  attribute_name: NAME,
  of: ENTITY_ID | RELATIONSHIP_ID // existing entity or relation ID in the JSON document
}

PATH := {
  id: PATH_ID, // new fresh unique ID of the path
  start?: ENTITY_ID,  // existing ID of an entity in the JSON document
  end?: ENTITY_ID,    // existing ID of an entity in the JSON document
  roles: [ROLE, ...] // Roles that define the edges of the path as a whitelist. If empty, any role is allowed.
}

LIST := {
  list: CREATE_LIST | NODES | RELATIONS,
  filter?: CONDITION,
  distinct?: BOOLEAN,
  order_by?: [ORDER_CRITERION, ...],
  limit?: NUMBER,
  skip?: NUMBER
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

ESCALAR_AGGREGATE := { list: LIST, map_expression: EXPRESSION, aggregate_kind: AGGREGATE_KIND }
AGGREGATE_KIND := "SUM" | "MIN" | "MAX" | "AVG"

QUANTIFIER_PREDICATE := { list: LIST, condition: CONDITION, quantifier_kind: QUANTIFIER_KIND }
QUANTIFIER_KIND := "ALL" | "EXISTS" | "NONE"

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

EXPRESSION := NUMBER | STRING | BOOLEAN | DATE_TIME | ATTRIBUTE | ESCALAR_AGGREGATE | COUNT

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
   - **Target Validity:** The `target` array legally accepts `ENTITY_ID`, `RELATIONSHIP_ID`, `PATH_ID`, `LIST`, `EXPRESSION` and `CONDITION`.If a Candidate uses a complex but valid target when a simpler one would suffice, penalize under **Minimality** (deduct at most 0.1).
   - **Type Checking:** Operators must receive valid types (e.g., math operators `> , <` on numbers or dates; `CONTAINS` on strings).
   - **Filters & Maps:** Verify correct usage of `filter` within `LIST`. `SCALAR_AGGREGATE` must use a valid `map_expression` to extract values before applying `SUM`, `MIN`, `MAX`, or `AVG`. 
   - **Path Aggregations:** When calculating lengths (hops) or aggregating weights over a path, verify that intermediate elements are correctly extracted via `NODES` or `RELATIONS` and then evaluated using `COUNT` or `SCALAR_AGGREGATE`.

5. **Minimality:**
   - Representation is concise. No redundant entities, relationships, paths, semantically duplicate hypotheses, or duplicated conditions.

6. **Equivalence to Ground Truth:**
   - The Ground Truth is a collection of multiple valid SQL queries representing the possible interpretations of an ambiguous query.
   - You must verify if the graph topology modeled in the Candidate's `entities` and `relationships` logically matches the joins (`JOIN`), aggregations (`COUNT`, `SUM`), and terminal nodes expressed in at least one of the Ground Truth SQL strings.
   - The Candidate's entity types and relationship roles should conceptually align with the provided SQL schema representation.

> **Note on Hypotheses:** Do not evaluate based on the number of generated hypotheses. A single correct interpretation is sufficient and should not be penalized.

---

## EXAMPLES

=== EXAMPLE 1: PERFECT MATCH (Correct) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the names of the Authors who have written at least 5 books published after 2010."

[GROUND TRUTH SQL]
SELECT Authors.name FROM Authors JOIN Books ON Authors.id = Books.author_id WHERE Books.publish_year > 2010 GROUP BY Authors.id HAVING COUNT(Books.id) >= 5

[CANDIDATE JSON]
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

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate is semantically and structurally identical to the Ground Truth SQL intent. Grammar-compliant bare array output, correct COUNT with LIST and filter mapped to the SQL WHERE and HAVING clauses.",
  "hypotheses_covered": 1,
  "correct": true
}
```

=== EXAMPLE 2: STRUCTURAL AND SEMANTIC VIOLATIONS (Incorrect) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me all the groups that directly or indirectly influenced Queen."

[GROUND TRUTH SQL]
SELECT DISTINCT Group1.id FROM Groups Group1 JOIN Influences ON Group1.id = Influences.influencer_id WHERE Influences.influenced_id = (SELECT id FROM Groups WHERE name = 'Queen')

[CANDIDATE JSON]
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
  "rationale": "The Candidate uses a nested array instead of a flat bare array, a hard structural grammar violation. It also uses a single direct relationship instead of a PATH, losing the multi-hop semantics required for 'directly or indirectly influenced'.",
  "hypotheses_covered": 0,
  "correct": false
}
```

=== EXAMPLE 3: MISSING PATH FOR MULTI-HOP (Incorrect) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the third-degree relatives of Alfonso X."

[GROUND TRUTH SQL]
SELECT p4.id FROM Person p1 JOIN Relatives r1 ON p1.id = r1.p1_id JOIN Person p2 ON r1.p2_id = p2.id JOIN Relatives r2 ON p2.id = r2.p1_id JOIN Person p3 ON r2.p2_id = p3.id JOIN Relatives r3 ON p3.id = r3.p1_id JOIN Person p4 ON r3.p2_id = p4.id WHERE p1.name = 'Alfonso X'

[CANDIDATE JSON]
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
  "rationale": "The traversal is modeled as a single direct relationship, while the Ground Truth SQL strictly requires three multi-hop JOINs (third-degree). This structural gap leaves the core multi-hop intent unresolved.",
  "hypotheses_covered": 0,
  "correct": false
}
```

=== EXAMPLE 4: CORRECT MULTI-HOP (Correct) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the third-degree relatives of Alfonso X."

[GROUND TRUTH SQL]
SELECT p4.id FROM Person p1 JOIN Relatives r1 ON p1.id = r1.p1_id JOIN Person p2 ON r1.p2_id = p2.id JOIN Relatives r2 ON p2.id = r2.p1_id JOIN Person p3 ON r2.p2_id = p3.id JOIN Relatives r3 ON p3.id = r3.p1_id JOIN Person p4 ON r3.p2_id = p4.id WHERE p1.name = 'Alfonso X'

[CANDIDATE JSON]
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
    }
  },
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
      "and": [
        {
          "left": { "attribute_name": "name", "of": "e1" },
          "operator": "=",
          "right": "Alfonso X"
        },
        {
          "left": {
            "count": {
              "list": { "rels_of": "p1", "rel_id": "r_p" }
            }
          },
          "operator": "=",
          "right": 3
        }
      ]
    }
  }
]

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate correctly models the multi-hop traversal of third-degree relatives. It successfully captures two semantically valid hypotheses: one using explicit intermediate entities and relationships, and the other using SemGIR's `paths` array with a hop count constraint. Both perfectly match the topology of the Ground Truth SQL.",
  "hypotheses_covered": 1,
  "correct": true
}
```

=== EXAMPLE 5: TOPOLOGY BYPASS VIA STRING COMPARISON (Incorrect) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the employees of companies located in Madrid."

[GROUND TRUTH SQL]
SELECT Employees.id FROM Employees JOIN Companies ON Employees.company_id = Companies.id JOIN Cities ON Companies.city_id = Cities.id WHERE Cities.name = 'Madrid'

[CANDIDATE JSON]
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
      "left": { "attribute_name": "location", "of": "e2" }, "operator": "CONTAINS", "right": "Madrid"
    }
  }
]

[EXPECTED OUTPUT]
```json
{
  "rationale": "The city constraint is expressed as `location CONTAINS 'Madrid'` on the company rather than via a proper topological relationship mapping to the Ground Truth SQL JOIN on the Cities table. This topology bypass is a significant semantic error.",
  "hypotheses_covered": 0,
  "correct": false
}
```

=== EXAMPLE 6: MINOR FLAW — MISSING DISTINCT (Incorrect) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the names of actors who have appeared in more than 10 films."

[GROUND TRUTH SQL]
SELECT DISTINCT Actors.name FROM Actors JOIN Performances ON Actors.id = Performances.actor_id GROUP BY Actors.id HAVING COUNT(Performances.film_id) > 10

[CANDIDATE JSON]
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
      "left": {
        "count": {
          "list": { "list_elements": "e2" }
        }
      },
      "operator": ">",
      "right": 10
    }
  }
]

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate correctly applies the COUNT aggregation. The only gap is the missing `distinct: true`, which is required to prevent duplicate actor names in the results as specified by the DISTINCT in the Ground Truth SQL.",
  "hypotheses_covered": 0,
  "correct": false
}
```

## OUTPUT FORMAT

You must return ONLY a valid JSON object with exactly the following structure, no additional text:

```json
{
  "rationale": "Concise explanation covering grammar compliance, semantic faithfulness, and comparison to the Ground Truth SQL. Explain any structural flaws or why they are equivalent.",
  "hypotheses_covered": [Integer specifiying how many hypotheses are covered by the Candidate],
  "correct": [true if the candidate is semantically and structurally equivalent to the Ground Truth intent and false otherwise.]
}
```