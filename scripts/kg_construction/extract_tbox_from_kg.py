import os

from rdflib import Graph, RDF, RDFS, OWL, BNode
import argparse

# Predicates from the ontology level
TBOX_PREDICATES = {
    # RDF.type,
    RDFS.subClassOf,
    RDFS.subPropertyOf,
    RDFS.domain,
    RDFS.range,
    # RDFS.label,
    RDFS.comment,
    OWL.inverseOf,
    OWL.equivalentClass,
    OWL.disjointWith,
    OWL.onProperty,
    OWL.someValuesFrom,
    OWL.allValuesFrom,
    OWL.minCardinality,
    OWL.maxCardinality,
    OWL.qualifiedCardinality,
}

# rdf:type objects that indicate a TBox triple
TBOX_TYPES = {
    OWL.Class,
    OWL.ObjectProperty,
    OWL.DatatypeProperty,
    OWL.AnnotationProperty,
    OWL.TransitiveProperty,
    OWL.SymmetricProperty,
    OWL.FunctionalProperty,
    OWL.Restriction,
    OWL.Ontology,
}

def extract_tbox(input_path: str, output_path: str):
    """
    Extract the TBox from a mixed KG+ontology OWL file.
    """
    full_kg = Graph()
    full_kg.parse(input_path, format="xml")

    tbox_graph = Graph()
    for prefix, ns in full_kg.namespaces():
        tbox_graph.bind(prefix, ns)

    for s, p, o in full_kg:
        # Always include blank nodes (OWL restrictions)
        if isinstance(s, BNode):
            tbox_graph.add((s, p, o))
            continue

        # Include rdf:type triples only if the object is a TBox type
        if p == RDF.type:
            if o in TBOX_TYPES:
                tbox_graph.add((s, p, o))
            continue

        # Include all other TBox predicates
        if p in TBOX_PREDICATES:
            tbox_graph.add((s, p, o))

    tbox_graph.serialize(output_path, format="xml")
    
    # For HF dataset
    # tbox_graph.serialize(output_path.replace(".owl", ".json"), format="json-ld", auto_compact=True)
    print(f"Full graph:  {len(full_kg)} triples")
    print(f"TBox extracted: {len(tbox_graph)} triples")
    print(f"ABox filtered:  {len(full_kg) - len(tbox_graph)} triples")
    print(f"TBox classes: {len(list(tbox_graph.subjects(RDF.type, OWL.Class)))}")
    print(f"TBox object properties: {len(list(tbox_graph.subjects(RDF.type, OWL.ObjectProperty)))}")
    print(f"Saved to {output_path}")

def parse_args():
    parser = argparse.ArgumentParser(description="Extract the TBox (ontology/schema) from a mixed KG+ontology OWL file")
    parser.add_argument("--input_kg", type=str, default="tp-kg.owl", help="Name of KG file that contains the ontology")
    parser.add_argument("--output_file", type=str, default="tp-ont.owl", help="Name fo the ontology OWL file")
    return parser.parse_args()

if __name__ == "__main__":
    input_kg_dir = os.path.join(os.getcwd(), os.pardir, os.pardir, "knowledge_graphs")
    output_kg_dir = os.path.join(os.getcwd(), os.pardir, os.pardir, "ontologies", "planning", "ours")

    args = parse_args()
    input_file = os.path.join(input_kg_dir, args.input_kg)
    output_file = os.path.join(output_kg_dir, args.output_file)

    extract_tbox(input_file, output_file)