import os

from rdflib import Graph, RDF, RDFS, OWL, BNode, Namespace, URIRef
import argparse
from lxml import etree

DCTERMS = Namespace("http://purl.org/dc/terms/")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
VANN = Namespace("http://purl.org/vocab/vann/")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")

# Predicates that ONLY ever appear on TBox entities (safe to keep regardless of subject)
TBOX_ONLY_PREDICATES = {
    RDFS.subClassOf,
    RDFS.subPropertyOf,
    RDFS.domain,
    RDFS.range,
    OWL.inverseOf,
    OWL.equivalentClass,
    OWL.disjointWith,
    OWL.onProperty,
    OWL.someValuesFrom,
    OWL.allValuesFrom,
    OWL.minCardinality,
    OWL.maxCardinality,
    OWL.qualifiedCardinality,
    OWL.imports,
    OWL.versionIRI,
    OWL.versionInfo,
}

# Predicates that may be used on both TBox and ABox entities, only kept if the subject is a TBox entity
SHARED_ANNOTATION_PREDICATES = {
    RDFS.comment,
    RDFS.label,
    DCTERMS.title,
    DCTERMS.description,
    DCTERMS.license,
    DCTERMS.creator,
    DCTERMS.contributor,
    DCTERMS.issued,
    DCTERMS.modified,
    DCTERMS.identifier,
    DCTERMS.conformsTo,
    DCTERMS.format,
    DCTERMS.bibliographicCitation,
    VANN.preferredNamespacePrefix,
    VANN.preferredNamespaceUri,
    DCAT.keyword,
    FOAF.homepage,
}

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
    full_kg = Graph()
    full_kg.parse(input_path, format="xml")

    # Find every subject that's a TBox entity (class, property, or the ontology itself)
    tbox_entities = {
        s for s, p, o in full_kg.triples((None, RDF.type, None)) if o in TBOX_TYPES
    }

    tbox_graph = Graph()
    for prefix, ns in full_kg.namespaces():
        tbox_graph.bind(prefix, ns)
    tbox_graph.bind("dcterms", DCTERMS)
    tbox_graph.bind("dcat", DCAT)
    tbox_graph.bind("vann", VANN)
    tbox_graph.bind("foaf", FOAF)

    # Filter triples
    for s, p, o in full_kg:
        if isinstance(s, BNode):
            tbox_graph.add((s, p, o))
            continue

        # Include rdf:type triples only if they are a TBox type
        if p == RDF.type:
            if o in TBOX_TYPES:
                tbox_graph.add((s, p, o))
            continue

        # Include all other TBox predicates
        if p in TBOX_ONLY_PREDICATES:
            tbox_graph.add((s, p, o))
            continue

        if p in SHARED_ANNOTATION_PREDICATES and s in tbox_entities:
            tbox_graph.add((s, p, o))
            continue

    ensure_ontology_header(tbox_graph, "https://w3id.org/tp-ont/ontology")
    tbox_graph.serialize(output_path, format="pretty-xml")
    move_ontology_desc_to_top(output_path)
    print(f"Full graph:  {len(full_kg)} triples")
    print(f"TBox extracted: {len(tbox_graph)} triples")
    print(f"ABox filtered:  {len(full_kg) - len(tbox_graph)} triples")
    print(f"TBox classes: {len(list(tbox_graph.subjects(RDF.type, OWL.Class)))}")
    print(f"TBox object properties: {len(list(tbox_graph.subjects(RDF.type, OWL.ObjectProperty)))}")
    print(f"Saved to {output_path}")

# def ensure_ontology_header(g: Graph, ontology_uri: str):
#     """Make sure the ontology node serializes as <owl:Ontology>, not <rdf:Description>."""
#     ont = URIRef(ontology_uri)
#
#     # Bind owl explicitly — don't rely on it being inherited
#     g.bind("owl", OWL, override=True)
#
#     # Ensure there is exactly ONE rdf:type triple for the ontology subject
#     existing_types = list(g.objects(ont, RDF.type))
#     for t in existing_types:
#         if t != OWL.Ontology:
#             g.remove((ont, RDF.type, t))
#     if (ont, RDF.type, OWL.Ontology) not in g:
#         g.add((ont, RDF.type, OWL.Ontology))

def ensure_ontology_header(g: Graph, ontology_uri: str):
    """Bind namespaces and ensure the ontology header is present in the graph."""
    ont = URIRef(ontology_uri)

    for prefix, ns in get_namespaces():
        g.bind(prefix, ns)

    # g.bind("owl", OWL, override=True)

    # Ensure there is exactly ONE rdf:type triple for the ontology subject
    existing_types = list(g.objects(ont, RDF.type))
    for t in existing_types:
        if t != OWL.Ontology:
            g.remove((ont, RDF.type, t))
    if (ont, RDF.type, OWL.Ontology) not in g:
        g.add((ont, RDF.type, OWL.Ontology))

def move_ontology_desc_to_top(file_path: str):
    """Move the owl:Ontology element to the top of the RDF/XML file."""
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(file_path, parser)
    root = tree.getroot()

    OWL_NS = {'owl': 'http://www.w3.org/2002/07/owl#'}
    ontology_elem = root.find('owl:Ontology', OWL_NS)

    if ontology_elem is not None:
        root.remove(ontology_elem)
        root.insert(0, ontology_elem)
        tree.write(file_path, pretty_print=True, xml_declaration=True, encoding='UTF-8')

def get_namespaces():
    """Return a list of (prefix, namespace) tuples for ontology namespaces used in the static ontology."""
    return [
        ("owl", OWL),
        ("rdfs", RDFS),
        ("rdf", RDF),
        ("dcterms", DCTERMS),
        ("dcat", DCAT),
        ("vann", VANN),
        ("foaf", FOAF),
    ]

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