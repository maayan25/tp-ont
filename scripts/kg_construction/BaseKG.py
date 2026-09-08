# Author: Ma'ayan Armony <maayan.armony@kcl.ac.uk>
# Class to construct the base knowledge graph for TP-ONT

from utils import add_entity_to_kg, add_relation_to_kg, add_constraint_to_kg, \
    get_mamespaces, add_subclass_to_kg, \
    add_object_property_to_kg, bind_namespaces

from rdflib import RDF, RDFS, OWL, Graph, URIRef

namespace_dict = get_mamespaces()
PLAN = namespace_dict["plan"]

class BasePDDLKG:
    def __init__(self):
        self.kg_data = Graph()
        bind_namespaces(self.kg_data)

    def record_entity(self, entity: tuple, is_class=False):
        """
        Record an entity in the knowledge graph data
        :param entity: a tuple (name, type, id)
        :param is_class: whether the entity is a class (owl:Class) or an instance (owl:NamedIndividual)
        :return: None
        """
        add_entity_to_kg(entity[0], entity[1], self.kg_data, is_class)

    def record_subclass(self, child, parent):
        """
        Record a subclass relation in the knowledge graph data
        :param child: the name of the child class
        :param parent: the name of the parent class
        :return: None
        """
        add_subclass_to_kg(child, parent, self.kg_data)

    def record_instance_of(self, entity, type):
        """
        Record an instance_of relation in the knowledge graph data
        :param entity: the name of the entity
        :param type: the name of the class the entity is an instance of
        """
        self.record_relation((entity, RDF.type, type), is_tail_class=True)


    def record_relation(self, relation: tuple, is_head_class=False, is_tail_class=False, hashing=False):
        """
        Record a relation in the knowledge graph data
        :param relation: a tuple (head, relation, tail, type, head_ent_type, tail_ent_type)
        :return: None
        """
        add_relation_to_kg(relation[0], relation[1], relation[2], self.kg_data,
                           classes=(is_head_class, is_tail_class), hashing=hashing)

    def record_property(self, property_name, domain="owl:Thing", range="owl:Thing"):
        """
        Record an object property in the knowledge graph data
        :param property_name: the name of the property
        :param domain: the domain of the property
        :param range: the range of the property
        :return: None
        """
        add_object_property_to_kg(property_name, domain, range, self.kg_data)

    def record_constraint(self, constraint: tuple):
        """
        Record a constraint in the knowledge graph data
        :param constraint: a tuple (head, relation, tail)
        :return: None
        """
        add_constraint_to_kg(constraint[0], constraint[1], constraint[2], self.kg_data)

    def get_entity_names(self) -> list:
        """
        Get a list of all entity names in the knowledge graph
        :return: a list of entity names
        """
        return list(self.kg_data.subjects(RDF.type, OWL.NamedIndividual))

    def get_entity_type(self, entity_name: str) -> str:
        """
        Get the type of entity by its name
        :param entity_name: the name of the entity
        :return: the type of the entity, or None if not found
        """
        # Find the entity in the rdflib graph
        for s, p, o in self.kg_data.triples((None, RDFS.label, None)):
            if str(o) == entity_name:
                # Get the type of the entity (not NamedIndividual)
                for t in self.kg_data.objects(s, RDF.type):
                    if t != OWL.NamedIndividual:
                        return str(t)
        return ""

    def log_graph_stats(self):
        """Log basic graph statistics for debugging"""
        entities = set(self.kg_data.subjects(RDF.type, OWL.NamedIndividual))
        classes = set(self.kg_data.subjects(RDF.type, OWL.Class))
        relations = set(self.kg_data.triples((None, None, None)))

        print(f"Entities: {len(entities)}")
        print(f"Classes: {len(classes)}")
        print(f"Total triples: {len(relations)}")

    def save_kg_to_owl(self, output_file, format="xml") -> None:
        """
        Create Dataframes for entities and relations, convert them to JSON and load to a file
        :param output_file: the path to the output JSON file
        :param format: the format of the output file
        :return: None
        """
        # self.create_type_relations()

        self.log_graph_stats()

        bad_uri = URIRef("https://w3id.org/tp-ont/ontology#")

        for s, p, o in self.kg_data:
            if s == bad_uri or p == bad_uri or o == bad_uri:
                print(f"DEBUG: Found bad URI in triple: {s}, {p}, {o}")
        self.kg_data.serialize(output_file, format=format)

