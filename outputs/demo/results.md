# Demo

## Query Q40

##### Tell me the scientists who were students of Planck in 1907.

```json
[
  {
    "target": ["e1"],
    "entities": [
      {"id": "e1", "type": "Scientist"},
      {"id": "e2", "type": "Scientist"}
    ],
    "relationships": [
      {
        "id": "r1",
        "role": "student_of",
        "from": "e1",
        "to": "e2"
      }
    ],
    "constraint": {
      "and_conditions": [
        {
          "left": {"attribute_name": "name", "of": "e2"},
          "operator": "=",
          "right": "Planck"
        },
        {
          "left": {"attribute_name": "year", "of": "r1"},
          "operator": "=",
          "right": 1907
        }
      ]
    }
  }
]
```

## Query Q04

##### Give me the communication routes between the server with ID 'SR45' and any server at the University of Oviedo.

```json
[
  {
    "target": ["p1"],
    "entities": [
      {"id": "e1", "type": "Server"},
      {"id": "e2", "type": "Server"},
      {"id": "e3", "type": "University"}
    ],
    "relationships": [
      {
        "id": "r1",
        "role": "communicates_with",
        "from": "e1",
        "to": "e2"
      },
      {
        "id": "r2",
        "role": "belongs_to",
        "from": "e2",
        "to": "e3"
      }
    ],
    "paths": [
      {
        "id": "p1",
        "start": "e1",
        "end": "e2",
        "roles": ["communicates_with"]
      }
    ],
    "constraint": {
      "and_conditions": [
        {
          "left": {
            "attribute_name": "server_id",
            "of": "e1"
          },
          "operator": "=",
          "right": "SR45"
        },
        {
          "left": {"attribute_name": "name", "of": "e3"},
          "operator": "=",
          "right": "University of Oviedo"
        }
      ]
    }
  }
]
```

