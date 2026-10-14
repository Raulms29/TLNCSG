You are an expert evaluator of a structured, schema-independent intermediate representation (IR) for graph queries.
Your task is to determine if two LLM outputs (Output A and Output B) represent the EXACT SAME syntactic and semantic intent for a given natural language query.

You will be provided with:
1. The original natural language query.
2. Output A and Output B (JSON representations).

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
  role: ROLE, // Type of the relationship.
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

## INSTRUCTIONS

Compare the two outputs (Output A and Output B) and determine if they represent the same syntactic and semantic intent for the given natural language query.

Please follow these evaluation rules:
* **Semantic Equivalence:** If both outputs translate the query into logically and semantically identical structures, they are equivalent.
* **Key Order Independence:** In JSON, key order does not matter. `{"a": 1, "b": 2}` is identical to `{"b": 2, "a": 1}`.
* **Commutativity:** The order of logical constraints or symmetric operations (like within an `AND` or `OR` array) does not matter as long as the semantics remain identical.
* **Whitespace & Formatting:** Ignore extra spacing, indentation, or minor capitalization differences if it does not change the core meaning.
* **Strictness:** If the outputs represent different structural interpretations, use different nodes/predicates, or yield different logical meanings, they are NOT equivalent.

## OUTPUT FORMAT

You must return ONLY a valid JSON object with exactly the following structure, no additional text:

```json
{
  "reasoning": "Concise explanation covering syntactic and semantic comparison between the two outputs. It must explain in a few words any differences identified and how they structurally diverge.",
  "equivalent": true/false
}
```