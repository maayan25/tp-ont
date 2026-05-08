# Helper functions for KG construction

# Utility functions for manipulating knowledge graph data

import hashlib
import os

from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL, XSD, BNode
import re
from urllib.parse import unquote

PREFIXES = {
    "tp-ont": "https://w3id.org/tp-ont/ontology#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "planning-ontology": "https://purl.org/ai4s/ontology/planning#",
}

DEFAULT_PREFIX = "tp-ont"

PLAN = Namespace("https://w3id.org/tp-ont/entities#")
ONTO = Namespace(PREFIXES[DEFAULT_PREFIX])
# PLANR = Namespace(PREFIXES[DEFAULT_PREFIX])

def get_mamespaces() -> dict:
    return {
        "plan": PLAN,
        # "onto": ONTO,
        # "planr": PLANR,
    }

def bind_namespaces(g: Graph):
    for prefix, uri in PREFIXES.items():
        g.bind(prefix, Namespace(uri))

    for prefix, ns in get_mamespaces().items():
        g.bind(prefix, ns)

def resolve_term(term: str, default_prefix=DEFAULT_PREFIX) -> URIRef:
    """
    Resolves a prefixed term or bare name to a full URI for the ontology and relations.
    :param term: the term to resolve, which can be a full URI, a prefixed name, or a bare name
    :param default_prefix: the default prefix to use for bare names (default is "tp-ont")
    """
    if term.startswith("http://") or term.startswith("https://"):
        return URIRef(term)

    if ":" in term:
        prefix, local = term.split(":", 1)
        if prefix in PREFIXES:
            local = cleanup_term(local)
            return URIRef(PREFIXES[prefix] + local)
        raise ValueError(f"Unknown prefix '{prefix}' in term '{term}'")

    # no prefix, use default
    term = cleanup_term(term)
    return URIRef(PREFIXES[default_prefix] + term)

def generate_uid(ent_name: str) -> str:
    raw = ent_name.encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:8]

def make_entity_uri(ent_name: str) -> URIRef:
    """Generate a URI for an entity"""
    if ent_name.startswith("http://") or ent_name.startswith("https://"):
        return URIRef(ent_name)
    else:
        ent_name = cleanup_term(ent_name)
        uri = PLAN[ent_name] if not ent_name.startswith("http") else URIRef(ent_name)
        return uri

def make_hashed_entity_uri(ent_name: str) -> URIRef:
    """Generate a consistent URI for an entity"""
    is_uri = ent_name.startswith("http://")
    if is_uri:
        return URIRef(ent_name)
    else:
        ent_name = cleanup_term(ent_name)
        uid = generate_uid(ent_name)
        return PLAN[f"{ent_name}_{uid}"]

# # For state predicates
# def make_predicate_uri(predicate_name: str) -> URIRef:
#     """URI for the predicate type itself e.g. 'on', 'at', 'in-city'"""
#     predicate_name = cleanup_term(predicate_name)
#     return PLAN[predicate_name]

def make_state_uri(expression: str) -> URIRef:
    """Hash the full expression to a safe URI fragment"""
    if expression.startswith("http://"):
        return URIRef(expression)
    else:
        expression = cleanup_term(expression)
        uid = hashlib.sha1(expression.encode("utf-8")).hexdigest()[:4]
        return PLAN[f"state_{uid}"]

def add_state_entity(expression: str, state_type: str, g: Graph) -> URIRef:
    """Add a state predicate entity with its full expression preserved as label"""
    uri = make_state_uri(expression)
    expression_label = _get_label_name(expression)
    if (uri, RDF.type, None) not in g:
        g.add((uri, RDF.type, resolve_term(state_type)))
        # print(f"Adding state entity: {expression} as {uri}")
        g.add((uri, RDF.type, OWL.NamedIndividual))
        # g.add((uri, RDFS.label, Literal(expression_label, lang="en")))
    return uri

def add_entity_to_kg(ent_name: str, ent_type: str, g: Graph, is_class=False) -> Graph:
    """
    Add an entity to the knowledge graph as an OWL individual.
    :param ent_name: the name of the entity
    :param ent_type: the type of the entity
    :param g: the rdflib Graph to add the entity to
    :param is_class: if True, the entity is added as an OWL class instead of an individual
    """
    type_uri = resolve_term(ent_type)
    g.add((type_uri, RDF.type, OWL.Class))

    label_name = _get_label_name(ent_name)
    if is_class:
        class_uri = resolve_term(ent_name)
        g.add((class_uri, RDF.type, OWL.Class))
        g.add((class_uri, RDFS.subClassOf, type_uri))
        g.add((class_uri, RDFS.label, Literal(label_name, lang="en")))
        return g
    else:
        entity_uri = make_entity_uri(ent_name)

        if (entity_uri, RDF.type, None) in g:
            return g

        g.add((entity_uri, RDF.type, OWL.NamedIndividual))
        g.add((entity_uri, RDF.type, type_uri))
        g.add((entity_uri, RDFS.label, Literal(label_name, lang="en")))

        return g

def add_relation_to_kg(head: str, rel: str, tail: str, g: Graph, classes=(False, False), hashing=False) -> Graph:
    """
    Add a relation to the knowledge graph.
    :param head: the subject entity name
    :param rel: the relation name
    :param tail: the object entity name
    :param g: the rdflib Graph
    :param classes: a tuple indicating whether the head and tail are classes (True) or instances (False)
    :param domain_dependent: a tuple indicating whether the head and tail are domain-dependent (True) or not (False), which affects how their labels are generated
    :param hashing: whether to generate hashed URIs for head and tail
    """
    # if "hasIniti" in rel or "hasGoal" in rel:
    #     print(f"Adding relation with head '{head}', relation '{rel}', tail '{tail}'")
    rel_uri = resolve_term(rel) # default_prefix="rel"

    head_label = _get_label_name(head)
    tail_label = _get_label_name(tail)
    relation_label = _get_label_name(rel)

    is_head_class, is_tail_class = classes
    if is_head_class:
        head_uri = resolve_term(head)
        g.add((head_uri, RDF.type, OWL.Class))
        g.add((head_uri, RDFS.label, Literal(head_label, lang="en")))
    else:
        if hashing:
            head_uri = make_hashed_entity_uri(head)
        else:
            head_uri = make_entity_uri(head)
        g.add((head_uri, RDF.type, OWL.NamedIndividual))
        g.add((head_uri, RDFS.label, Literal(head_label, lang="en")))

    if is_tail_class:
        # tail_uri = ONTO[tail] if not tail.startswith("http") else URIRef(tail)
        tail_uri = resolve_term(tail)
        g.add((tail_uri, RDF.type, OWL.Class))
        g.add((tail_uri, RDFS.label, Literal(tail_label, lang="en")))
    else:
        if hashing:
            tail_uri = make_hashed_entity_uri(tail)
        else:
            tail_uri = make_entity_uri(tail)
        g.add((tail_uri, RDF.type, OWL.NamedIndividual))
        g.add((tail_uri, RDFS.label, Literal(tail_label, lang="en")))

    g.add((rel_uri, RDF.type, OWL.ObjectProperty))
    g.add((rel_uri, RDFS.label, Literal(relation_label, lang="en")))
    g.add((head_uri, rel_uri, tail_uri))

    return g

def _get_label_name(ent_name: str) -> str:
    # Check if there is a forward slash, and take the part after the last slash as the label
    # Take the part after the last forward slash as the label
    if "/" in ent_name:
        local_name = ent_name.rsplit("/", 1)[-1]
        return local_name
    else:
        return ent_name

def _is_datatype(range_str: str) -> bool:
    return range_str.startswith("xsd:") or range_str.startswith(str(XSD))

def add_object_property_to_kg(prop_name: str, domain: str, range: str, g: Graph) -> Graph:
    """
    Add an object property to the knowledge graph with specified domain and range.
    :param prop_name: the name of the property
    :param domain: the domain class name
    :param range: the range class name
    :param g: the rdflib Graph
    """
    prop_uri = resolve_term(prop_name) # default_prefix="rel"
    domain_uri = resolve_term(domain)
    range_uri = resolve_term(range)

    prop_type = OWL.DatatypeProperty if _is_datatype(range) else OWL.ObjectProperty

    prop_label = _get_label_name(prop_name)
    g.add((prop_uri, RDF.type, prop_type))
    g.add((prop_uri, RDFS.label, Literal(prop_label, lang="en")))

    if domain:
        g.add((domain_uri, RDF.type, OWL.Class))
        g.add((prop_uri, RDFS.domain, domain_uri))
    if range:
        if prop_type == OWL.ObjectProperty:
            g.add((range_uri, RDF.type, OWL.Class))
        g.add((prop_uri, RDFS.range, range_uri))

    return g


def add_subclass_to_kg(child: str, parent: str, g: Graph) -> Graph:
    """
    Add a subClassOf relation between two classes.
    :param child: the subclass name
    :param parent: the parent class name
    :param g: the rdflib Graph
    """
    add_class_relation(child, RDFS.subClassOf, parent, g)


def add_class_relation(head: str, rel: str, tail: str, g: Graph) -> Graph:
    """Add class-level relations: disjointWith, equivalentClass, subClassOf..."""
    head_uri = resolve_term(head)
    tail_uri = resolve_term(tail)
    g.add((head_uri, RDF.type, OWL.Class))
    g.add((tail_uri, RDF.type, OWL.Class))
    g.add((head_uri, rel, tail_uri))
    return g

def add_property_constraint(prop: str, rel: str, tail: str, g: Graph) -> Graph:
    """Add property-level constraints or relations"""
    prop_uri = resolve_term(prop) # default_prefix="rel"
    tail_uri = resolve_term(tail) # default_prefix="rel"
    g.add((prop_uri, RDF.type, OWL.ObjectProperty))
    g.add((prop_uri, rel, tail_uri))
    return g


def add_restriction(prop: str, rel: str, tail: str, g: Graph) -> Graph:
    """OWL restrictions on a property: cardinality, someValuesFrom, allValuesFrom."""
    prop_uri = resolve_term(prop) # default_prefix="rel"
    g.add((prop_uri, RDF.type, OWL.ObjectProperty))

    restriction = BNode()
    g.add((restriction, RDF.type, OWL.Restriction))
    g.add((restriction, OWL.onProperty, prop_uri))

    domain = g.value(prop_uri, RDFS.domain) or None
    if domain:
        g.add((domain, RDFS.subClassOf, restriction))

    if rel in (OWL.minCardinality, OWL.maxCardinality):
        g.add((restriction, rel, Literal(int(tail), datatype=XSD.nonNegativeInteger)))
    elif rel in (OWL.someValuesFrom, OWL.allValuesFrom):
        g.add((restriction, rel, resolve_term(tail)))
    else:
        raise ValueError(f"Unknown restriction type: {rel}")

    return g

def add_constraint_to_kg(head: str, rel, tail: str, g: Graph) -> Graph:
    class_constraints = {OWL.disjointWith, OWL.equivalentClass}
    property_constraints = {OWL.propertyDisjointWith, OWL.inverseOf, RDFS.subPropertyOf}
    restrictions = {OWL.minCardinality, OWL.maxCardinality, OWL.someValuesFrom, OWL.allValuesFrom}

    if rel in class_constraints:
        return add_class_relation(head, rel, tail, g)
    elif rel in property_constraints:
        return add_property_constraint(head, rel, tail, g)
    elif rel in restrictions:
        return add_restriction(head, rel, tail, g)
    else:
        raise ValueError(f"Unknown constraint type: {rel}")

def make_problem_state_uri(problem_name: str, state_type: str) -> URIRef:
    """URI for the InitialState/GoalState instance belonging to a specific problem"""
    return PLAN[f"{problem_name}_{state_type}"]

def add_part_of_speech(verbal_concepts: list[str], nominal_concepts: list[str], g: Graph):
    LEXINFO = Namespace("https://www.lexinfo.net/ontology/3.0/lexinfo#")
    g.bind("lexinfo", LEXINFO)


    verbal_concepts = [resolve_term(concept) for concept in verbal_concepts]
    nominal_concepts = [resolve_term(concept) for concept in nominal_concepts]

    g.add((ONTO.VerbalConcept,  RDF.type, OWL.Class))
    g.add((ONTO.NominalConcept, RDF.type, OWL.Class))

    for concept in verbal_concepts:
        g.add((concept, RDFS.subClassOf,      ONTO.VerbalConcept))
        g.add((concept, LEXINFO.partOfSpeech, LEXINFO.verb))

    for concept in nominal_concepts:
        g.add((concept, RDFS.subClassOf,      ONTO.NominalConcept))
        g.add((concept, LEXINFO.partOfSpeech, LEXINFO.noun))

def cleanup_term(term: str) -> str:
    """Check that there are no illegal characters in the term before using it as a URI fragment, and replace them with underscores if there are."""
    term = unquote(term)
    return re.sub(r'[^\w\-]', '_', term)

def parse_plan_and_simulation(domain_name, problem_name) -> (list[str], list[str]):
    """
    Parse the plan and the simulation of its execution to extract the actions and states
    :param domain_name: the name of the domain file
    :param problem_name: the name of the problem file
    """
    project_dir = os.path.join(os.getcwd(), os.pardir, os.pardir)
    output_dir = os.path.join(project_dir, "results", "planner_outputs", domain_name)
    output_path = os.path.join(output_dir, f"{problem_name}.pddl_plan.txt")
    state_simulation_path = output_path.replace(".txt", "_state_simulation.txt")
    if not os.path.exists(state_simulation_path):
        print(f"State simulation file not found at {state_simulation_path}, cannot parse states.")
        return [], []
    print(
        f"Parsing plan from {output_path} and state simulation from {state_simulation_path} for domain '{domain_name}' and problem '{problem_name}'")

    with open(output_path, "r") as f:
        actions = f.readlines()

    states = []
    with open(state_simulation_path, "r") as f:
        state_lines = f.readlines()
        for line in state_lines:
            if line.startswith("State after action"):
                continue
            elif line.startswith("Initial state"):
                continue
            else:
                # print(f"State line: {line.strip()}, type: {type(line)}")
                state_str = line.strip()
                if state_str:
                    state_str = state_str.replace("))", ")")
                    states.append(state_str)

    return actions, states