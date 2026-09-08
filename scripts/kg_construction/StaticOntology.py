# Author: Ma'ayan Armony <maayan.armony@kcl.ac.uk>
# Class to construct the static ontology knowledge graph for TP-ONT on top of the base knowledge graph

from utils import add_part_of_speech, bind_namespaces
from BaseKG import BasePDDLKG

from rdflib import OWL, Graph

class StaticOntology(BasePDDLKG):
    def __init__(self, kg_data="defaults.owl"):
        super().__init__()
        self.kg_data_path = kg_data
        self.kg_data = Graph()
        bind_namespaces(self.kg_data)
        self.kg_data.parse(self.kg_data_path, format="xml")

        self.create_kg()

    def add_classes_and_properties(self) -> None:
        """
        Add classes and properties for the static ontology
        :return: None
        """
        self.record_entity(("Proposition", OWL.Thing), is_class=True)
        self.record_entity(("Fluent", OWL.Thing), is_class=True)
        self.record_entity(("NegatedFluent", "Fluent"), is_class=True)

        self.record_property("hasArgument", domain="Predicate", range="Object")  # range is anything
        self.record_property("partOf", domain="Proposition", range="State")  # e.g. at_robot1_room2 partOf state_hash
        self.record_property("hasFluent", domain="Proposition", range="Fluent")
        self.record_property("hasType", domain="planning-ontology:PlanningDomain", range="Object")
        self.record_property("isNegationOf", domain="Predicate", range="Predicate")

    def add_equivalence_to_planning_ontology(self) -> None:
        """
        Add equivalence relations to link to planning-ontology
        :return: None
        """
        self.record_constraint(("Action", OWL.equivalentClass, "planning-ontology:DomainAction", "owl"))
        self.record_constraint(("Parameter", OWL.equivalentClass, "planning-ontology:ActionParameter", "owl"))
        self.record_constraint(("Object", OWL.equivalentClass, "planning-ontology:ProblemObject", "owl"))
        self.record_constraint(("Precondition", OWL.equivalentClass, "planning-ontology:ActionPrecondition", "owl"))
        self.record_constraint(("Effect", OWL.equivalentClass, "planning-ontology:ActionEffect", "owl"))
        self.record_constraint(("Predicate", OWL.equivalentClass, "planning-ontology:ProblemPredicate", "owl"))


    def add_plan_entities_and_relations(self) -> None:
        """
        Add entities and relations for plans, steps, and ordering constraints
        :return: None
        """
        self.record_entity(("Plan", OWL.Thing), is_class=True)
        # self.record_property("hasPlan", domain="PDDLDomain", range="Plan") # Extended from AI-Planning-Ontology

        self.record_entity(("Step", OWL.Thing), is_class=True) # TODO can extend from knowrob or somewhere?
        self.record_property("hasStep", domain="Plan", range="Step")
        self.record_property("happensBefore", domain="Step", range="Step")
        self.record_property("happensAfter", domain="Step", range="Step")
        self.record_constraint(("happensBefore", OWL.inverseOf, "happensAfter", "plan"))

        self.record_entity(("State", OWL.Thing), is_class=True)
        self.record_property("hasState", domain="Plan", range="State")
        self.record_property("precedes", domain="State", range="State")

    def add_temporal_and_numeric_entities_and_relations(self) -> None:
        """
        Add entities and relations for temporal and numeric information
        :return: None
        """
        self.record_entity(("TemporalConstraint", OWL.Thing), is_class=True)
        self.record_property("hasTemporalConstraint", domain="Plan", range="TemporalConstraint")
        self.record_entity(("Duration", OWL.Thing), is_class=True)
        self.record_property("hasDuration", domain="Action", range="Duration")

        self.record_entity(("NumericFluent", OWL.Thing), is_class=True)
        self.record_property("hasNumericFluent", domain="Plan", range="NumericFluent")
        self.record_property("hasNumericValue", domain="NumericFluent", range="xsd:float")


    def create_disjoint_constraints(self) -> None:
        """
        Create disjoint constraints for all classes in the knowledge graph data
        :return: None
        """
        disjoint_classes = ["Action", "Predicate", "State", "planning-ontology:PlanningDomain", "planning-ontology:PlanningProblem", "Object", "Relation"]

        # classes = set(self.kg_data.subjects(RDF.type, OWL.Class))
        for i, type1 in enumerate(disjoint_classes):
            for type2 in disjoint_classes[i+1:]:
                self.record_constraint((type1, OWL.disjointWith, type2, "owl"))

    def create_subclass_relations(self) -> None:
        """
        Create subclass relations for all default types in the knowledge graph
        :return: None
        """
        hierarchy = {
            "Precondition": "Predicate",
            "Effect": "Predicate",
            # Extended from AI-Planning-Ontology
            # "InitialState": "State",
            # "GoalState": "State",
        }
        for subclass, superclass in hierarchy.items():
            self.record_subclass(subclass, superclass)

        add_part_of_speech(["Action"], ["Object", "Parameter"], self.kg_data)

    # def create_subproperty_relations(self) -> None:
    #     """
    #     Create subproperty relations for all default properties in the knowledge graph
    #     :return: None
    #     """
    #     hierarchy = {
    #         "planning-ontology:hasPrecondition": "planning-ontology:hasPredicate",
    #         "planning-ontology:hasEffect": "planning-ontology:hasPredicate",
    #     }
    #     for subprop, superprop in hierarchy.items():
    #         self.record_constraint((subprop, RDFS.subPropertyOf, superprop, "rdfs"))


    def create_kg(self) -> None:
        """
        Create Dataframes for entities and relations, convert them to JSON and load to a file
        :return: None
        """
        self.create_subclass_relations()
        self.create_disjoint_constraints()

        # Only in ontology currently
        self.add_plan_entities_and_relations()
        self.add_temporal_and_numeric_entities_and_relations()

        self.add_classes_and_properties()
        self.add_equivalence_to_planning_ontology()

        # output_file = os.path.join(os.getcwd(), "knowledge_graphs", "static_ontology.owl")
        output_file = self.kg_data_path.replace("defaults.owl", "static_ontology.owl")
        self.save_kg_to_owl(output_file)
