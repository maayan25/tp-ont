Make sure to have the required prefixes defined in your SPARQL endpoint:
```
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX planning-ontology: <https://purl.org/planning-ontology/ontology/planning#>
PREFIX tp-ont: <https://w3id.org/tp-ont/ontology#>
```

See examples folder for queries with instantiated variables that can be directly run on the KG using Protégé's SPARQL 
query interface, or using Apache Jena Fuseki (you'll have to materialise the graph first, which can be done with the 
function in [run_queries.py](../run_queries.py), and run the server (`./fuseki-server --file=/path/to/project/knowledge_graphs/tp-kg_materialised.owl /kg`).

Below are the general templates for the competency questions (CQs) we have defined for our ontology:

**CQ 1 - What object types are of type O? **
```
SELECT ?obj WHERE {
  ?type rdfs:subClassOf* tp-ont:O .
}
```

**CQ 2 - What actions exist in domain D?**
```
SELECT ?action WHERE {
  ?domain rdf:type planning-ontology:PlanningDomain ;
     rdfs:label "D"@en;
     planning-ontology:hasAction ?action.
}
```

**CQ 3 - What domains have an action A?**
```
SELECT ?domain WHERE {
  ?domain rdf:type planning-ontology:PlanningDomain ;
     planning-ontology:hasAction ?action .
  ?action rdfs:label "A"@en .
}
```

**CQ 4 - What domains have objects of type T or its subtypes?**
```
SELECT DISTINCT ?domain WHERE {
  ?domain rdf:type planning-ontology:PlanningDomain ;
        tp-ont:hasType ?type .
  ?type rdfs:subClassOf* tp-ont:T .
}
```

**CQ 5 - How many arguments does predicate P take in domain D?**
```
SELECT (COUNT(?arg) AS ?numArgs) WHERE {
  ?domain rdf:type planning-ontology:PlanningDomain ;
     rdfs:label "D"@en;
     planning-ontology:hasPredicate ?predicate .
  ?predicate tp-ont:hasFluent ?fluent;
     ?property ?arg.
  ?property rdfs:subPropertyOf tp-ont:hasArgument .
  ?fluent rdfs:label "P"@en.
  
  # For the materialised graph, exclude non direct subproperties of hasArgument=
  FILTER (?property != tp-ont:hasArgument)
  FILTER NOT EXISTS {
    ?property rdfs:subPropertyOf ?middle .
    ?middle rdfs:subPropertyOf tp-ont:hasArgument .
    FILTER (?middle != tp-ont:hasArgument)
    FILTER (?middle != ?property)
  }
}
```

**CQ 6 - What predicates have more than N arguments?**
```
SELECT DISTINCT ?fluent WHERE {
  ?predicate rdf:type tp-ont:Predicate ;
            tp-ont:hasFluent ?fluent ;
            ?property ?arg .
  ?property rdfs:subPropertyOf tp-ont:hasArgN .
}
GROUP BY ?fluent
```

**CQ 7 - What are the preconditions of action A across domains?**
```
SELECT ?precon WHERE {
  ?action rdf:type tp-ont:Action ;
     rdfs:label "A"@en ;
     planning-ontology:hasPrecondition ?precon .
}
```

**CQ 8 - What subtype of type T is most common across domains?**

```
SELECT ?type (COUNT(?domain) AS ?frequency) WHERE {
  ?domain rdf:type planning-ontology:PlanningDomain ;
     tp-ont:hasType ?type .
  ?type rdfs:subClassOf+ tp-ont:T .
}
GROUP BY ?type
ORDER BY DESC(?frequency)
LIMIT 1
```

**CQ 9 - Which action was taken right before action A in plan P?**
```
SELECT ?prevstep WHERE {
  ?plan rdf:type tp-ont:Plan ;
        rdfs:label "P"@en ;
        tp-ont:hasStep ?step .
    ?step rdf:type tp-ont:Step ;
          rdfs:label "A"@en .
    ?prevstep rdf:type tp-ont:Step ;
        tp-ont:happensBefore ?step .
            
}
```

**CQ 10 - In problem P, which objects are in location L at the initial state?**
```
SELECT DISTINCT ?obj WHERE {
  ?problem rdf:type planning-ontology:PlanningProblem ;
           rdfs:label "P"@en ;
           planning-ontology:hasInitialState ?state .
  ?proposition tp-ont:partOf ?state.
  ?proposition tp-ont:hasFluent ?fluent ;
             tp-ont:hasArg0 ?obj ; 
             tp-ont:hasArg1 ?loc .
  ?fluent rdfs:label "at"@en .
  ?loc rdfs:label "L"@en .}
```

**CQ 11 - Does predicate P take the same type of object as the Nth argument in D1 and D2?**
```
SELECT ?type1 ?type2 (?type1 = ?type2 AS ?same) WHERE {
  {
    SELECT DISTINCT ?type1 WHERE {
        ?domain1 rdf:type planning-ontology:PlanningDomain ;
               rdfs:label "D1"@en ;
               planning-ontology:hasPredicate ?predicate1 .
        ?predicate1 tp-ont:hasFluent ?fluent1 ;
                            ?property1 ?type1 .
        ?fluent1 rdfs:label "P"@en .
        ?property1 rdfs:subPropertyOf tp-ont:hasArgN .
    }
  }
  {
    SELECT DISTINCT ?type2 WHERE {
        ?domain2 rdf:type planning-ontology:PlanningDomain ;
               rdfs:label "D2"@en ;
               planning-ontology:hasPredicate ?predicate2 .
        ?predicate2 tp-ont:hasFluent ?fluent2 ;
                            ?property2 ?type2 .
        ?fluent2 rdfs:label "P"@en .
        ?property2 rdfs:subPropertyOf tp-ont:hasArgN .
    }
  }
}
```

**CQ 12 - Does domain D have multiple object types of type T?**
```
SELECT ?result WHERE {
  {
    SELECT (COUNT(DISTINCT ?type) AS ?count) WHERE {
      ?domain rdf:type planning-ontology:PlanningDomain ;
              rdfs:label "D"@en ;
              tp-ont:hasType ?type .
      ?type rdfs:subClassOf* tp-ont:T .
    }
  }
  BIND(?count > 1 AS ?result)
}
```

**CQ 13 - Do multiple domains have object types of type T?**
```
SELECT ?result WHERE {
    {
        SELECT (COUNT(DISTINCT ?domain) AS ?numDomains) WHERE {
          ?domain rdf:type planning-ontology:PlanningDomain ;
             tp-ont:hasType ?type .
          ?type rdfs:subClassOf* tp-ont:T .
        }
    }
    BIND(?numDomains > 1 AS ?result)
}
```

**CQ 14 - What object type can be the first argument of predicate P in D?**
```
SELECT DISTINCT ?type WHERE {
    ?domain rdf:type planning-ontology:PlanningDomain ;
        rdfs:label "D"@en;
        planning-ontology:hasPredicate ?predicate .
    ?predicate tp-ont:hasFluent ?fluent ;
                ?property ?type .
    ?fluent rdfs:label "P"@en .
    ?property rdfs:subPropertyOf tp-ont:hasArg0 .
}
```

**CQ 15 - What are the 3 most common fluents across domains?**
```
SELECT ?fluentLabel (COUNT(DISTINCT ?domain) AS ?domainCount) WHERE {
  ?domain rdf:type planning-ontology:PlanningDomain ;
          planning-ontology:hasPredicate ?predicate .
  ?predicate tp-ont:hasFluent ?fluent .
  ?fluent rdfs:label ?fluentLabel .
}
GROUP BY ?fluentLabel
ORDER BY DESC(?domainCount)
LIMIT 3
```

**CQ 16 - Which objects are in location L at any point in plan P?**
```
SELECT DISTINCT ?obj WHERE {
  ?plan rdf:type tp-ont:Plan ;
        rdfs:label "P" ;
        tp-ont:hasState ?state .
  ?prop tp-ont:partOf ?state ;
        tp-ont:hasArg0 ?obj ;
        tp-ont:hasArg1 ?loc .
  ?loc rdf:type tp-ont:Place ;
         rdfs:label "L"@en .
  ?fluent rdfs:label ?fluentLabel .
  FILTER (REGEX(STR(?fluentLabel), "^(at|in|on)", "i"))
}
```

**CQ 17 - Are there common action patterns in plan solutions for domain D?**
```
SELECT ?pattern (COUNT(DISTINCT ?plan) AS ?frequency) WHERE {
?domain rdf:type planning-ontology:PlanningDomain ;
        planning-ontology:hasProblem ?problem ;
        rdfs:label "D"@en .
?problem rdf:type planning-ontology:PlanningProblem ;
    tp-ont:hasPlan ?plan .
?plan rdf:type tp-ont:Plan ;
    tp-ont:hasStep ?step1 ;
    tp-ont:hasStep ?step2 ;
    tp-ont:hasStep ?step3 .
      ?step1 tp-ont:happensBefore ?step2 ;
             rdfs:label ?action1 .
      ?step2 tp-ont:happensBefore ?step3 ;
             rdfs:label ?action2 .
      ?step3 rdfs:label ?action3 .
      BIND(CONCAT(?action1, "+", ?action2, "+", ?action3) AS ?pattern)
    }
    GROUP BY ?pattern
    ORDER BY DESC(?frequency)
    LIMIT 10
```

**CQ 18 - Which domain has typically longer plans, D1 or D2?**
```
SELECT ?domain (AVG(?planLength) AS ?avgLength) WHERE {
  ?domain rdf:type planning-ontology:PlanningDomain ;
          rdfs:label ?domainLabel .
  FILTER (?domainLabel IN ("D1", "D2"))
  ?domain planning-ontology:hasProblem ?problem .
  ?problem tp-ont:hasPlan ?plan .
  {
    SELECT ?plan (COUNT(?step) AS ?planLength) WHERE {
      ?plan tp-ont:hasStep ?step .
    }
    GROUP BY ?plan
  }
}
GROUP BY ?domain
ORDER BY DESC(?avgLength)
```