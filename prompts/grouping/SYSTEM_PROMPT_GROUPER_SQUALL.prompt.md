You are an expert evaluator of a Controlled Natural Language (CNL) that maps directly to SPARQL for querying knowledge bases.
Your task is to determine if two LLM outputs (Output A and Output B) represent the EXACT SAME syntactic and semantic intent for a given natural language query.

You will be provided with:
1. The original natural language query.
2. Output A and Output B.

---

## GRAMMAR

// A SQUALL output is a question. Any phrase can be coordinated or negated with 'and' (join), 'or' (union), 'not' (negation), 'maybe' (optional part) and brackets

SQUALL_SENTENCE := S '?'                                   // open question when S has which/what/who/how many
                 | 'Whether' S '?'                         // Yes/No question (ASK)
                 | INVERTED_S '?'                          // Yes/No question (ASK)
                 | 'To which' NG1 (S | INVERTED_S) '?'
                 | ('For' NP ',')* QUERY_IMP NP '.'        // returns the noun phrases. After 'For … ,' QUERY_IMP is lowercase
INVERTED_S := ('Does' | 'Do' | 'Did') NP (VP_DO | 'have' VP_HAVE)
            | ('Is' | 'Are' | 'Was' | 'Were') (NP VP_BE | 'there' NP)
            | ('Has' | 'Have' | 'Had') NP VP_HAVE
QUERY_IMP := 'Give me' | 'Return' | 'List' | 'Describe'   // 'Describe' returns all the facts about the resources (DESCRIBE)

// Statements
S := NP VP                                       // the subject NP does VP
   | 'for' NP ',' S                              // NP applies to the whole sentence S
   | 'there' AUX_BE NP                           // something matching NP exists
   | S 'where' S                                 // both hold

// Noun phrases
NP := TERM | DET NG1 | NP2 'of' NP               // NP2 'of' NP: the value of a relation for NP
    | 'what' | 'who' | 'whom'                    // the unknown being asked for
    | EXPR
    | ('more' | 'less') NG1 'than' NG1 | 'as many' NG1 'as' NG1   // compares two counts
    | '[' LIST ']' | '_'                         // an ordered list; '_' is any one element
NP2 := DET NG2 | ('more' | 'less') NG2 'than' (NG2 | NP) | 'as many' NG2 'as' (NG2 | NP) | EXPR
NPQ := 'the' NG1 | 'the' NG2 'of' NP | TERM      // what an aggregation applies to
TERM := ENTITY | LITERAL | LABEL | PATTERN | 'that' S | '[' ']'

// Determiners and noun groups
DET := 'a' | 'an' | 'some' | 'no' | 'every' | 'all' | 'the' | 'which' | 'how many'   // 'every'/'all': for all; 'no': none;
                                                 // 'which': asked for (SELECT); 'how many': asked count (COUNT)
     | NUMBER | ('more than' | 'less than' | 'at least' | 'at most' | 'exactly') NUMBER   // condition on the count
     | 'between' NUMBER 'and' NUMBER
     | 'the' ORDINAL? ('most' | 'least')         // largest or smallest count
NG1 := ADJ_SUPER? CLASS APP? REL?                // a class with optional name and conditions
     | 'number' APP? REL? 'of' (NG1 | NG2 'of' NPQ) DIMS?   // COUNT
     | AGGREG APP? (NG1 | NG2 'of' NPQ) DIMS?    // SUM / AVG / MIN / MAX / SAMPLE / GROUP_CONCAT
NG2 := ADJ_SUPER? RELATION APP?                  // a relation, read from the subject to the value
APP := LABEL | ENTITY                            // names the noun group with a label, or fixes it to one resource
DIMS := 'per' (NG2 | NPQ) ('and' 'per' (NG2 | NPQ))*   // one aggregated value per group (GROUP BY)

// Relative clauses
REL := ('that' | 'which' | 'who') VP
     | ('that' | 'which' | 'whom') S_GAP         // S_GAP: S without the noun phrase the pronoun stands for
     | NP2 'of which' VP                         // condition on a relation value
     | 'whose' NG2 VP                            // condition on a relation value
     | COMPARATOR NP | 'between' NP 'and' NP     // comparison with a value (FILTER)
     | ('with' | 'without') VP_HAVE              // has / has not
     | 'such that' S                             // any extra condition

// Verb phrases
VP := VP_DO | AUX_DO NEG? VP_DO | AUX_BE NEG? VP_BE | AUX_HAVE NEG? VP_HAVE
AUX_DO := 'does' | 'do' | 'did'
AUX_BE := 'is' | 'are' | 'was' | 'were'
AUX_HAVE := 'has' | 'have' | 'had'
NEG := 'not' | "n't"                              // the fact does not hold (NOT EXISTS)
VP_DO := RELATION NP                             // the relation from the subject to NP
       | ('starts' | 'start' | 'ends' | 'end') 'with' NP | ('contains' | 'contain' | 'matches' | 'match') NP   // string filters
       | ('belongs' | 'belong' | 'belonged') 'to' NP      // class membership
       | ('relates' | 'relate' | 'related') NP 'to' NP    // the property linking two resources
       | ('shares' | 'share' | 'shared') (DET NG2 'with' NP | 'with' NP DET NG2)   // has the same relation value as NP
       | ('=' | '!=' | '<' | '>' | '<=' | '>=') NP      // symbolic comparison
VP_BE := 'there' | REL | NPC                     // is equal to, is an instance of, or meets a condition
NPC := TERM | ('a' | 'an' | 'the') NG1 | ('a' | 'an' | 'the') NG2 'of' NP | 'the' ADJ_SUPER
VP_HAVE := RELATION NP                            // relation value
         | NP2 REL?                               // relation value with a condition on it
         | 'the same' RELATION 'as' NP

// Comparisons and expressions
COMPARATOR := ('greater' | 'higher' | 'later' | 'lesser' | 'lower' | 'earlier') ('than' | 'or equal to')
            | 'equal to' | 'same as' | 'other than' | 'different from'
EXPR := EXPR ('+' | '-' | '*' | '/') EXPR | '-' EXPR | '(' EXPR ')' | 'now' | TERM | NP | NP2 | NPC   // arithmetic on values
      | FUNC '(' EXPR (',' EXPR)* ')'             // SPARQL function call
LIST := LIST_ELEM (',' LIST_ELEM)* ('|' NP)?      // '|' NP: the rest of the list
LIST_ELEM := NP | '_' | '...'                     // '...': any number of elements

// Names: a label between angle brackets, as it would be said; spaces and any characters but < > { } | ^ ` are allowed
ENTITY := '<' TEXT '>'                                  // e.g., <France>, <John Smith>
CLASS := '<' TEXT '>' SUFFIX? | 'thing'                 // 'thing' is any resource, e.g., <person>, <author>-s, <video game>
RELATION := '<' TEXT '>' CLOSURE? SUFFIX?               // e.g., <author>, <birth date>, <know>-s, <cite>+
                                                  // used as a noun (has <author> X, the <author>-s of X) or as a verb (<know>-s X)

// Terminal types
FUNC := 'concat' | 'substr' | 'strlen' | 'ucase' | 'year' | 'abs' | 'round'   // SPARQL functions
SUFFIX := '-s' | '-es'                             // optional plural or 3rd-person mark
CLOSURE := '+' | '*' | '?'                         // one or more / zero or more / zero or one step
LABEL := CAPITAL_LETTER DIGIT* | '?' NAME               // a variable, to refer to the same resource again, e.g., X, Y2, ?foo
PATTERN := "'" WORD+ "'"                           // the resource whose label contains these words, e.g., 'Prince Harry'
LITERAL := NUMBER | STRING | DATE | 'true' | 'false'    // e.g., 2013, "Hello", "Hello"@en, 2010-01-01
ADJ_SUPER := (NUMBER | ORDINAL ('to' ORDINAL)?)? ('highest' | 'greatest' | 'latest' | 'lowest' | 'least' | 'earliest')   // ordering and limit (ORDER BY + LIMIT / OFFSET), e.g., 2nd latest
ORDINAL := NUMBER ('st' | 'nd' | 'rd' | 'th') | 'first' | 'second' | 'third'
AGGREG := 'total' | 'average' | 'minimum' | 'maximum' | 'sample' | 'concatenated'

---

## INSTRUCTIONS

Compare the two outputs (Output A and Output B) and determine if they represent the same syntactic and semantic intent for the given natural language query.

Please follow these evaluation rules:
* **Semantic Equivalence:** If both outputs translate the query into logically and semantically identical structures, they are equivalent.
* **Commutativity:** The order of logical constraints or symmetric operations does not matter as long as the semantics remain identical.
* **Whitespace & Formatting:** Ignore superficial spacing, newlines, or tabs.
* **Aliases & Variable Names:** Table or column aliases (e.g., `?X` vs `?Y`) are equivalent if they resolve to the exact same logic and structure.
* **Strictness:** If the outputs represent different structural interpretations, use different predicates, or yield different logical meanings, they are NOT equivalent.

## OUTPUT FORMAT

You must return ONLY a valid JSON object with exactly the following structure, no additional text:

```json
{
  "reasoning": "Concise explanation covering syntactic and semantic comparison between the two outputs. It must explain in a few words any differences identified and how they structurally diverge.",
  "equivalent": true/false
}
```