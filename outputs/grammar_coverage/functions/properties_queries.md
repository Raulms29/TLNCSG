# Queries asking for properties

Autoresearch pool queries that ask for the properties of a node without naming them. The SemGIR grammar has no form for "all properties": `ATTRIBUTE` needs a specific `attribute_name`.

**Current decision (provisional):** returning the nodes counts as listing their properties.

Verdicts come from `autoresearch/verdict_cache.json`. "Cached verdicts" counts every distinct output judged for the query, across all iterations.

## Scores

| Reading | v0 | v48 | v48 val | v48 train |
|---|---|---|---|---|
| Returning the nodes counts | 149/200 | 162/200 | 42/49 | 120/151 |
| SemGIR can't express this, so these queries fail | 144/200 | 156/200 | 39/49 | 117/151 |

## All properties of connected nodes

### `T2C_10881` (val)

- **Question:** Find the nodes connected to Keyword where key_id is c95a6da6fb331984f198feec0b0bb1a5 and list their properties!
- **Ground truth:** `MATCH (a:Keyword{key_id:'c95a6da6fb331984f198feec0b0bb1a5'})-[r]->(n) RETURN properties(n), r`
- **v48 output:** see below
- **Verdicts:** v0 pass, v48 pass
- **Cached verdicts:** 3 pass, 1 fail
- **Open:** one failing entry has the same structure as a passing entry and differs only in ID names (`e0`/`e1` vs `e1`/`e2`).

```json
[
  {
    "target": [
      {
        "list": { "list_elements": "e2" }
      }
    ],
    "entities": [
      { "id": "e1", "type": "Keyword" },
      { "id": "e2", "type": "Node" }
    ],
    "relationships": [
      { "id": "r1", "role": "connected_to", "from": "e1", "to": "e2" }
    ],
    "constraint": {
      "left": { "attribute_name": "key_id", "of": "e1" },
      "operator": "=",
      "right": "c95a6da6fb331984f198feec0b0bb1a5"
    }
  }
]
```

### `T2C_11083` (train)

- **Question:** What are the properties of nodes connected to Journal for which journal_id is e7b0a9b48142710ab6e87f136f6b7606, and what are their relationships to Journal?
- **Ground truth:** `MATCH (c:Journal)<-[r]-(n) WHERE c.journal_id = 'e7b0a9b48142710ab6e87f136f6b7606' RETURN properties(n) AS props, r`
- **v48 output:** see below
- **Verdicts:** v0 pass, v48 pass
- **Cached verdicts:** 4 pass, 3 fail
- **Open:** two outputs that differ only in `target` order have opposite verdicts. The failing one cites relationship direction, while the passing one accepts it.

```json
[
  {
    "target": [
      "e1",
      "e2",
      "r1"
    ],
    "entities": [
      { "id": "e1", "type": "Journal" },
      { "id": "e2", "type": "Node" }
    ],
    "relationships": [
      { "id": "r1", "role": "", "from": "e1", "to": "e2" }
    ],
    "constraint": {
      "left": { "attribute_name": "journal_id", "of": "e1" },
      "operator": "=",
      "right": "e7b0a9b48142710ab6e87f136f6b7606"
    }
  }
]
```

### `T2C_11339` (train)

- **Question:** What are the properties of nodes connected to Article for which comments is 44 pages, and what are their relationships to Article?
- **Ground truth:** `MATCH (c:Article)<-[r]-(n) WHERE c.comments = '44 pages' RETURN properties(n) AS props, r`
- **v48 output:** see below
- **Verdicts:** v0 fail, v48 fail
- **Cached verdicts:** 0 pass, 4 fail
- **Note:** v48 fails because it filters on the number 44 instead of the string '44 pages', not because of the properties.

```json
[
  {
    "target": [
      "e2",
      "r1"
    ],
    "entities": [
      { "id": "e1", "type": "Article" },
      { "id": "e2", "type": "Node" }
    ],
    "relationships": [
      { "id": "r1", "role": "", "from": "e1", "to": "e2" }
    ],
    "constraint": {
      "left": { "attribute_name": "comments", "of": "e1" },
      "operator": "=",
      "right": 44
    }
  }
]
```

### `T2C_13599` (val)

- **Question:** What are the properties of nodes connected to Article where article_id is 1056, by two different types of relationships?
- **Ground truth:** `MATCH (e:Article{article_id:'1056'})-[r1]->(n)-[r2]->(m) WHERE TYPE(r1) <> TYPE(r2) RETURN properties(n) AS props1, properties(m) AS props2`
- **v48 output:** see below
- **Verdicts:** v0 fail, v48 pass
- **Cached verdicts:** 2 pass, 11 fail

```json
[
  {
    "target": [
      "e1",
      "r1",
      "r2"
    ],
    "entities": [
      { "id": "e0", "type": "Article" },
      { "id": "e1", "type": "Node" }
    ],
    "relationships": [
      { "id": "r1", "role": "", "from": "e0", "to": "e1" },
      { "id": "r2", "role": "", "from": "e0", "to": "e1" }
    ],
    "constraint": {
      "and_conditions": [
        {
          "left": { "attribute_name": "article_id", "of": "e0" },
          "operator": "=",
          "right": 1056
        },
        {
          "left": { "attribute_name": "role", "of": "r1" },
          "operator": "!=",
          "right": { "attribute_name": "role", "of": "r2" }
        }
      ]
    }
  }
]
```

### `T2C_13615` (val)

- **Question:** What are the properties of nodes connected to Topic where cluster is 6, by two different types of relationships?
- **Ground truth:** `MATCH (e:Topic{cluster:'6'})-[r1]->(n)-[r2]->(m) WHERE TYPE(r1) <> TYPE(r2) RETURN properties(n) AS props1, properties(m) AS props2`
- **v48 output:** see below
- **Verdicts:** v0 pass, v48 pass
- **Cached verdicts:** 2 pass, 2 fail

```json
[
  {
    "target": [
      {
        "list": {
          "list_elements": "e2"
        }
      }
    ],
    "entities": [
      { "id": "e1", "type": "Topic" },
      { "id": "e2", "type": "Node" }
    ],
    "relationships": [
      { "id": "r1", "role": "", "from": "e1", "to": "e2" },
      { "id": "r2", "role": "", "from": "e1", "to": "e2" }
    ],
    "constraint": {
      "and_conditions": [
        {
          "left": { "attribute_name": "cluster", "of": "e1" },
          "operator": "=",
          "right": 6
        },
        {
          "left": { "attribute_name": "role", "of": "r1" },
          "operator": "!=",
          "right": { "attribute_name": "role", "of": "r2" }
        }
      ]
    },
    "distinct": true
  }
]
```

## Properties of the nodes on a path

### `Q72` (train, hand-written)

- **Question:** Identify the longest path originating from the Topic whose description is 'signal processing in optics', and list the properties of the nodes on the path.
- **Ground truth target:** `[{"list":{"nodes_of":"p1","node_id":"e2"}}]`
- **v48 output:** see below
- **Verdicts:** v0 pass, v48 pass
- **Cached verdicts:** 1 pass, 1 fail
- **Note:** this ground truth returns the nodes for "list the properties". It would have to change, or the query be dropped, if these queries are treated as inexpressible.

```json
[
  {
    "target": [
      "p1",
      {
        "list": {
          "nodes_of": "p1",
          "node_id": "e2"
        }
      }
    ],
    "entities": [
      { "id": "e1", "type": "Topic" },
      { "id": "e2", "type": "Node" }
    ],
    "paths": [
      { "id": "p1", "start": "e1", "roles": [] }
    ],
    "constraint": {
      "left": { "attribute_name": "description", "of": "e1" },
      "operator": "=",
      "right": "signal processing in optics"
    },
    "order_by": [
      {
        "expression": {
          "count": {
            "list": { "rels_of": "p1", "rel_id": "r1" }
          }
        },
        "direction": "DESC"
      }
    ],
    "limit": 1
  }
]
```

### `T2C_13814` (train)

- **Question:** Identify the longest path originating from Topic for which cluster is 6, and list the properties of the nodes on the path!
- **Ground truth:** `MATCH p=(a:Topic{cluster:'6'})-[*]->(n) RETURN p, nodes(p) ORDER BY LENGTH(p) DESC LIMIT 1`
- **v48 output:** see below
- **Verdicts:** v0 pass, v48 pass
- **Cached verdicts:** 2 pass, 0 fail
- **Note:** the Cypher also returns the nodes, not `properties(n)`.

```json
[
  {
    "target": [
      "p1",
      {
        "list": {
          "nodes_of": "p1",
          "node_id": "e2"
        }
      }
    ],
    "entities": [
      { "id": "e1", "type": "Topic" },
      { "id": "e2", "type": "Node" }
    ],
    "paths": [
      { "id": "p1", "start": "e1", "roles": [] }
    ],
    "constraint": {
      "left": { "attribute_name": "cluster", "of": "e1" },
      "operator": "=",
      "right": 6
    },
    "order_by": [
      {
        "expression": {
          "count": {
            "list": { "rels_of": "p1", "rel_id": "r1" }
          }
        },
        "direction": "DESC"
      }
    ],
    "limit": 1
  }
]
```

## Any shared property

### `T2C_16936` (val)

- **Question:** Are there any nodes that are connected with Keyword where name is super-exponential growth and share a common property with Keyword, for which key_id equals 72e4f3fc2930bd3a0a7730a664d069d6?
- **Ground truth:** `MATCH (a:Keyword{name:'super-exponential growth'})-[r]->(n), (d:Keyword{key_id:'72e4f3fc2930bd3a0a7730a664d069d6'}) WHERE ANY(key in keys(n) WHERE n[key] = d[key]) RETURN n`
- **v48 output:** see below
- **Verdicts:** v0 fail, v48 fail
- **Cached verdicts:** 0 pass, 11 fail
- **Note:** this compares any property rather than returning them, so the current decision doesn't make it pass.

```json
[
  {
    "target": [
      {
        "source": {
          "list": { "list_elements": "e1" }
        },
        "condition": {
          "and_conditions": [
            "r1",
            {
              "left": { "attribute_name": "name", "of": "e1" },
              "operator": "=",
              "right": { "attribute_name": "name", "of": "e2" }
            }
          ]
        },
        "quantifier_kind": "EXISTS"
      }
    ],
    "entities": [
      { "id": "e1", "type": "Node" },
      { "id": "e2", "type": "Keyword" }
    ],
    "relationships": [
      { "id": "r1", "role": "connected_with", "from": "e1", "to": "e2" }
    ],
    "constraint": {
      "and_conditions": [
        {
          "left": { "attribute_name": "name", "of": "e2" },
          "operator": "=",
          "right": "super-exponential growth"
        },
        {
          "left": { "attribute_name": "key_id", "of": "e2" },
          "operator": "=",
          "right": "72e4f3fc2930bd3a0a7730a664d069d6"
        }
      ]
    }
  }
]
```

## Not included

`T2C_1336` ("What are the details and opening hours of the museums?") is left out because "details" maps to a named attribute, `Museum_Details`.
