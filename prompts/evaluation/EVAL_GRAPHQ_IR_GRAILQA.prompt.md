You are an expert evaluator of GraphQ IR, a unified intermediate representation for graph query languages.

Your task is to evaluate a "CANDIDATE GRAPHQ_IR" sequence against a "Ground Truth" (provided as a LISP s-expression).

Your evaluation must reflect how well the Candidate captures the intended meaning of the query, correctly forms the lexical components, complies with the linear structural grammar, and logically matches the Ground Truth LISP intent.

---

## GRAMMAR

// The root of a GraphQ IR sequence must be one of the supported query types
S := EntityQuery | AttributeQuery | RelationQuery | QualifierQuery | CountQuery | VerifyQuery | ValueQuery | SelectQuery

// Query type definitions mapping to their expected return structures
EntityQuery := "what is" EntitySet
AttributeQuery := "what is the attribute" Attribute "of" EntitySet
RelationQuery := "what is the relation from" EntitySet "to" EntitySet
QualifierQuery := "what is the qualifier" Qualifier "of" EntitySet Constraint
CountQuery := "how many" EntitySet
VerifyQuery := "whether" EntitySet Constraint
ValueQuery := "what is" Value
SelectQuery := "which one has the" SOP Attribute "among" EntitySet

// EntitySet represents a collection of nodes in the graph
EntitySet := "<ES>" EntitySet LOP EntitySet "</ES>"    // Logical operation between two sets
           | "<ES>" EntitySet "(" EntitySet ")" "</ES>" // Intersection between two sets using parentheses
           | "<ES>" EntitySet Constraint "</ES>"     // A set filtered by a constraint
           | "<ES>" Concept EntitySet? "</ES>"       // A set filtered by a concept (EntitySet is optional)
           | Concept | Entity | "ones" | "entities"  // Terminal nodes (ones/entities = anonymous/blank node)

// Constraints filter an EntitySet by its attributes or relations
Constraint := AttributeConstraint QualifierConstraint? | RelationConstraint QualifierConstraint?

// Specific constraint types
AttributeConstraint := "whose" Attribute COP Value | "that" "have" ("top" "[number]")? SOP Attribute
RelationConstraint := "that" Relation DIR "to" (COP Value?)? EntitySet | "that" Relation DIR "to" ("top" "[number]")? SOP EntitySet
QualifierConstraint := "(" Qualifier COP Value ")"   // Qualifier constraints must be wrapped in parentheses

// Terminal nodes wrapped in explicit XML tags
Concept := "<C>" [name] "</C>"
Entity := "<E>" [name] "</E>"
Relation := "<R>" [name] "</R>"
Attribute := "<A>" [name] "</A>"
Qualifier := "<Q>" [name] "</Q>"

// Values can be aggregates, attributes, literals with a specific type, or logical unions
Value := VTYPE "<V>" Literal "</V>"                  // (VTYPE can be "numeric", "string", "date", "year", "time", "month")
       | Value "or" Value                            // Logical union between values
       | VOP "of" Value                              // Aggregation over a value
       | Attribute "of" EntitySet                    // Extraction of an attribute from a set

// Operators defining logic, aggregation, comparison, superlatives, and direction
LOP := "and" | "or" | "not"                          // Logical operators
VOP := "sum" | "average" | "maximum" | "minimum"     // Value operators (Aggregations)
COP := "is" | "equal to" | "is not" | "not equal to" | "larger than" | "more than" | "smaller than" | "less than" | "at least" | "at most"
SOP := "largest" | "most" | "smallest" | "least"     // Superlative operators
DIR := "forward" | "backward"                        // Edge direction in the graph

---

## EVALUATION DIMENSIONS

Evaluate the Candidate holistically across these dimensions:

1. **Well-formedness & Grammar Compliance:**
  - The output must be a valid GraphQ IR linear sequence starting with a root query type.
  - **Terminal Node Tags:** Terminal nodes (`Concept`, `Entity`, `Relation`, `Attribute`, `Qualifier`) MUST be wrapped in their respective XML tags (e.g. `<C> movie </C>`). For `Value`, if it includes a `VTYPE`, it will precede the tag (e.g. `year <V> 2004 </V>`).
  - **Constrained EntitySets:** When an `EntitySet` has a `Constraint`, the parent node must be wrapped with `<ES>` and `</ES>`.

2. **Semantic Faithfulness & Intent:**
  - Captures all entities, relationships, constraints, and implicit/explicit meaning of the natural language query.
  - **No Hallucinations/Omissions:** Penalize missing requirements or invented concepts.
  - **Query Type Correctness:** Verify the root query type perfectly aligns with the query intent (e.g., `CountQuery` for counts, `VerifyQuery` for booleans, `EntityQuery` for extraction).

3. **Structural & Graph Quality:**
  - **Topology:** Correct nesting of `EntitySet`s inside `Constraint` blocks to reflect the traversal.
  - **Directionality:** `forward` and `backward` directions on relations must make logical, semantic sense relative to the onnected nodes.
  - **Operators:** Correct logical application of `AND`, `OR`, `NOT`, and comparative operators (`larger than`, `smallest`, etc.).

4. **Equivalence to Ground Truth:**
  - The Ground Truth is a LISP s-expression representing a knowledge graph traversal.
  - You must verify if the graph topology modeled in the Candidate's AST logically matches the joins (`JOIN`), aggregations (`COUNT`, `ARGMAX`), and terminal nodes expressed in the LISP string.
  - The Candidate's entity types and relationship roles should conceptually align with the LISP representation.

---

## EXAMPLES

=== EXAMPLE 1: PERFECT MATCH (Correct) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the movies directed by Eastwood."

[GROUND TRUTH LISP]
(AND film.film (JOIN (R film.director.film) m.eastwood))

[CANDIDATE GRAPHQ_IR]
what is <ES> <C> movie </C> that <R> director </R> forward to <E> Eastwood </E> </ES>

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate correctly structures the relational constraint and matches the entity. The semantic graph traversal perfectly mirrors the Ground Truth LISP's JOIN and constraints.",
  "correct": true
}
```

=== EXAMPLE 2: DIRECTIONALITY MISMATCH (Incorrect) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Give me the movies directed by Eastwood."

[GROUND TRUTH LISP]
(AND film.film (JOIN (R film.director.film) m.eastwood))

[CANDIDATE GRAPHQ_IR]
what is <ES> <C> movie </C> that <R> director </R> backward to <E> Eastwood </E> </ES>

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate uses a 'backward' direction on the relation from the movie to Eastwood, but the semantic relationship logically requires a 'forward' traversal to match the Ground Truth LISP. The structural directionality is flawed.",
  "correct": false
}
```

=== EXAMPLE 3: INCORRECT QUERY TYPE (Incorrect) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Tell me whether the actors of Matrix are taller than 160 cm."

[GROUND TRUTH LISP]
(AND film.actor (JOIN (R film.performance.actor) (JOIN film.performance.film m.matrix)) (> height 160))

[CANDIDATE GRAPHQ_IR]
what is <ES> <C> actor </C> that <R> actor </R> backward to <E> Matrix </E> </ES>

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Ground Truth LISP is a boolean evaluation, but the Candidate hallucinates an EntityQuery (extraction) instead of using a VerifyQuery. It also completely misses the height > 160 constraint.",
  "correct": false
}
```

=== EXAMPLE 4: MISSING CONSTRAINT (Incorrect) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Tell me whether the actors of Matrix are taller than 160 cm."

[GROUND TRUTH LISP]
(AND film.actor (JOIN (R film.performance.actor) (JOIN film.performance.film m.matrix)) (> height 160))

[CANDIDATE GRAPHQ_IR]
whether <ES> <C> actor </C> that <R> actor </R> backward to <E> Matrix </E> </ES>

[EXPECTED OUTPUT]
```json
{
  "rationale": "While the Candidate correctly identifies the VerifyQuery and the relation to Matrix, it fails to include the AttributeConstraint for height > 160 cm that is clearly present in the Ground Truth LISP.",
  "correct": false
}
```

=== EXAMPLE 5: COMPLEX NESTED QUERY (Perfect Match) ===

[ORIGINAL NATURAL LANGUAGE QUERY]
"Which has less elevation above sea level, Rome that is the filming location of To Rome with Love or Lisbon which is the twinned administrative body of Santo Domingo?"

[GROUND TRUTH LISP]
(ARGMIN (OR (AND location.location (JOIN (R film.location.film) m.to_rome_with_love) m.rome) (AND location.location (JOIN (R location.twinned_administrative_body.location) m.santo_domingo) m.lisbon)) location.location.elevation)

[CANDIDATE GRAPHQ_IR]
which one has the smallest <A> elevation above sea level </A> among <ES> <ES> <E> Rome </E> (<ES> ones that <R> filming location </R> backward to <E> To Rome with Love </E> </ES>) </ES> or <ES> <E> Lisbon </E> (<ES> ones that <R> twinned administrative body </R> backward to <E> Santo Domingo </E> </ES>) </ES> </ES>

[EXPECTED OUTPUT]
```json
{
  "rationale": "The Candidate correctly captures the complex union (OR) of two intersection (parenthetical) EntitySets. The superlative 'less' is correctly translated to 'smallest', matching the ARGMIN in the Ground Truth LISP, and the nested constraints accurately mirror the graph topology.",
  "correct": true
}
```

## OUTPUT FORMAT

You must return ONLY a valid JSON object with exactly the following structure, no additional text:

```json
{
  "rationale": "Concise explanation covering grammar compliance, semantic faithfulness, and comparison to the Ground Truth LISP. Explain any structural flaws or why they are equivalent.",
  "correct": [true if the candidate is semantically and structurally equivalent to the Ground Truth intent and false otherwise.]
}
```
