# Author: Ma'ayan Armony <maayan.armony@kcl.ac.uk>
# Class to construct a knowledge graph from a given PDDL domain and problem

import os
import argparse

from ParsePDDL import UnifiedPlanningParser
from utils import add_entity_to_kg, add_relation_to_kg, add_constraint_to_kg, add_state_entity, \
    get_mamespaces, add_subclass_to_kg, add_part_of_speech, \
    add_object_property_to_kg, bind_namespaces, parse_plan_and_simulation  # add_predicate_instance

from rdflib import RDF, RDFS, OWL, Graph, URIRef

namespace_dict = get_mamespaces()
PLAN = namespace_dict["plan"]
# PLANR = namespace_dict["planr"]

# TODO 1. continue difference between typed and untyped objects in PDDL (elevator domain)
# TODO 2. check initial_state relations (maybe change has_predicate to the state itself rather than the initial_state entity)
# TODO 3. handle numerics: 2004.satellite-complex-strips, 2008.transport-sequential-optimal-strips, 2008.woodworking-sequential-optimal-strips, 2011.barman-sequential-multi-core
# TODO 4. handle temporal

def _add_domain_name_to_entity(entity_name, domain_name):
    """Helper function to add domain name as a prefix to an entity name if not already present"""
    if not entity_name.startswith(f"{domain_name}/"):
        return f"{domain_name}/{entity_name}"
    return entity_name

def _add_domain_name_to_entities(entities, domain_name):
    """Helper function to add domain name as a prefix to a list of entity names if not already present"""
    return [_add_domain_name_to_entity(e, domain_name) for e in entities]

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
        self.kg_data.serialize(output_file, format=format)

class DomainPDDLKG(BasePDDLKG):
    def __init__(self, domain_file, problem_file, problem_specific=True, domain_specific=True, data=None):
        super().__init__()
        self.parser = UnifiedPlanningParser(domain_file, problem_file)

        self.output_path = data["output_path"] if "output_path" in data else f"{os.getcwd()}/knowledge_graphs/"
        self.domain_name = data["domain_name"] if "domain_name" in data else self.parser.domain_name
        self.problem_name = data["problem_name"] if "problem_name" in data else self.parser.problem_name
        os.makedirs(self.output_path, exist_ok=True)

        self.problem_specific = problem_specific
        self.domain_specific = domain_specific

        self.init_uri = self.goal_uri = None

        self.domain_kg = find_kg_for_domain(self.domain_name, self.output_path)
        # self.general_kg = os.path.join(os.getcwd(), "knowledge_graphs", "tp-kg.owl")
        self.general_kg = os.path.join(self.output_path, "tp-kg.owl")
        if not self.domain_specific:
            self.kg_data = Graph()
            bind_namespaces(self.kg_data)
            if os.path.exists(self.general_kg):
                print(f"Found existing general TP-KG at {self.general_kg}."
                      f"\n It will be loaded and augmented with information from domain {self.domain_name} and problem {self.problem_name}.")
                self.kg_data.parse(self.general_kg, format="xml")
            else:
                print(f"General TP-KG not found at {self.general_kg}, parsing static_ontology.owl instead.")
                # defaults_kg = os.path.join(os.getcwd(), "knowledge_graphs", "static_ontology.owl")
                defaults_kg = os.path.join(self.output_path, "static_ontology.owl")
                self.kg_data.parse(defaults_kg, format="xml")

                # kg_uri = URIRef(f"http://tp-ont.org/kg")
                # self.record_instance_of(kg_uri, "KnowledgeGraph")
        elif not self.problem_specific and self.domain_kg:
            print(f"Found existing knowledge graph for domain {self.domain_name} at {self.domain_kg}. It will be loaded into the graph.")
            self.kg_data = Graph()
            bind_namespaces(self.kg_data)
            self.kg_data.parse(self.domain_kg, format="xml")
        else:
            print(f"No existing knowledge graph found for domain {self.domain_name}, or problem-specific KG requested. "
                  f"\n A new KG will be created with information from the domain and problem files.")
            # defaults_kg = os.path.join(os.getcwd(), "knowledge_graphs", "static_ontology.owl")
            defaults_kg = os.path.join(self.output_path, "static_ontology.owl")
            self.kg_data = Graph()
            bind_namespaces(self.kg_data)
            self.kg_data.parse(defaults_kg, format="xml")

            # kg_uri = URIRef(f"http://tp-ont.org/kg/{self.domain_name}")
            # self.record_instance_of(kg_uri, "KnowledgeGraph")

    def create_dependent_identifiers(self, ent_name, dependency_type):
        """
        Create any identifiers that depend on the domain/problem.
        :return:
        """
        dependency_prefixes = {
            "domain": f"{self.parser.domain_name}",
            "problem": f"{self.parser.domain_name}/{self.problem_name}",
        }
        # Check name is not already prefixed with domain name
        if not "/" in ent_name:
            # If not in list, use as is
            prefix = dependency_prefixes.get(dependency_type, dependency_type)
            ent_name = f"{prefix}/{ent_name}"
        return ent_name

    # Objects
    def add_types(self) -> None:
        """
        Add entities for types of entities
        :return: None
        """
        # Add type entities according to parser
        # self.record_entity(("ObjectType", OWL.Class, "ObjectType"), is_class=True)

        for type in self.parser.types:
            type_name = type.name.capitalize()
            self.record_entity((type_name, "Object"), is_class=True)
            if type.father is not None:
                father_type = type.father.name.capitalize()
                self.record_subclass(type_name, father_type)
            else:
                self.record_subclass(type_name, "Object")

            self.record_relation((self.parser.domain_name, "hasType", type_name), is_head_class=False, is_tail_class=True)
        # Add init and goal state are subclasses of state
        # self.record_relation(("InitialState", RDFS.subClassOf, "State", "rdfs"), subclass_of=True)
        # self.record_relation(("GoalState", RDFS.subClassOf, "State", "rdfs"), subclass_of=True)

    def add_objects(self) -> None:
        """
        Add entities for objects in the problem file
        :return: None
        """
        parsed_entities = self.get_entity_names()
        for obj_type, objs in self.parser.objects.items():
            for obj in objs:
                if obj not in parsed_entities:
                    problem_obj = self.create_dependent_identifiers(obj, "problem")
                    self.record_entity((problem_obj, obj_type.capitalize()), is_class=False) # instance of its type
                    parsed_entities.append(obj)

    def add_actions(self) -> None:
        """
        Create action entities, and relations for preconditions and effects
        """
        domain_name = self.parser.domain_name
        for act_name in self.parser.action_names:
            # Create an entity for each action with its name
            print(f"Adding action {act_name} as an entity")
            domain_action = self.create_dependent_identifiers(act_name, "domain")
            self.record_entity((domain_action, "Action"), is_class=False)
            # General relations for the action
            # self.record_relation((act_name, RDF.type, OWL.Class, "rdf"))
            self.record_relation((domain_action, "admissible", domain_name), is_head_class=False)
            self.record_relation((domain_name, "planning-ontology:hasAction", domain_action), is_tail_class=False)
        for action in self.parser.actions:
            # TODO check that no relations are missing
            self.add_action_params(action)
            self.add_preconditions(action)
            self.add_effects(action)

    def add_action_params(self, action) -> None:
        """
        Get all parameters in an action and parse them (remove '?')
        :param action: an Operator object representing an action from the domain
        :return: a list of variable names for this action
        """
        act_name = action.name
        params = action.parameters
        parsed_params = self.get_entity_names()
        for param in params:
            if param.name not in parsed_params:
                # param_name = param.name
                param_name = self.create_dependent_identifiers(param.name, "domain")
                param_type = param.type.name.capitalize() if param.type is not None else "Object"
                self.record_entity((param_name, param_type), is_class=False) # e.g. x in bw
                domain_action = self.create_dependent_identifiers(act_name, "domain")
                self.record_relation((domain_action, "planning-ontology:hasParameter", param_name), is_head_class=False)
                # self.record_instance_of(param_name, param_type) # e.g. x is an instance of Location, should already happen in record entity
                self.record_instance_of(param_name, "Parameter")
                parsed_params.append(param_name)

    def add_preconditions(self, action) -> None:
        """
        Add preconditions of an action to the knowledge graph
        :param action: the action object containing preconditions
        """
        precons = self.parser.parse_predicates(list(action.preconditions))
        self.add_precons_effects(precons, action_name=action.name, pred_type="Precondition")

    def add_effects(self, action) -> None:
        """
        Add effects of an action to the knowledge graph
        :param action: the action object containing effects
        """
        effects = self.parser.parse_predicates(list(action.effects))
        self.add_precons_effects(effects, action_name=action.name, pred_type="Effect")

    def add_domain_predicates(self) -> None:
        """
        Takes a set of predicates from the domain definition file and adds them to the KG as n-ary relations
        (reification), with arguments as object properties.
        :return: None
        """
        fluents: dict = self.parser.fluents

        for pred_name, arg_types in fluents.items():
            # Normalise pred name to remove special chars, e.g. (at ?x) -> at_x
            pred_name = pred_name.replace(" ", "_").replace("(", "").replace(")", "").replace(",", "_").replace("?", "")
            domain_pred_name = self.create_dependent_identifiers(pred_name, "domain")
            # All predicates are classes under Predicate
            full_predicate = f"{domain_pred_name}_{"_".join(arg_types)}" if arg_types else domain_pred_name
            self.record_instance_of(full_predicate, "Predicate")
            self.record_relation((self.parser.domain_name, "planning-ontology:hasPredicate", full_predicate))
            self.record_relation((full_predicate, "hasFluent", domain_pred_name))

            for i, arg_type in enumerate(arg_types):
                slot_prop = f"{domain_pred_name}_hasArg{i}"  # e.g. Logistics/at_hasArg0, BLOCKS/on_hasArg0, Logistics/on_hasArg1
                self.record_property(f"hasArg{i}", domain="Predicate", range="Object")
                self.record_property(slot_prop, domain="Predicate", range=arg_type.capitalize())
                self.record_constraint((slot_prop, RDFS.subPropertyOf, f"hasArg{i}", "rdfs"))
                self.record_constraint((f"hasArg{i}", RDFS.subPropertyOf, "hasArgument", "rdfs"))
                self.record_relation((full_predicate, slot_prop, arg_type.capitalize())) # e.g. Logistics/at_location has Logistics/at_hasArg0 Location

    def add_precons_effects(self, lst, action_name="", pred_type="predicate") -> None:
        """
        Takes a set of predicates from the domain definition file and adds them to the KG
        :param lst: the list of predicates (list of dictionaries with keys "name", "args")
        :param action_name: the name of the action these predicates are associated with
        :param pred_type: precond, effect, or predicate
        """
        action_name = self.create_dependent_identifiers(action_name, "domain")
        for pred in lst:
            r = pred["name"]
            args = pred["args"]

            is_negated = "not_" in r
            base_fluent = r.replace("not_", "")
            fluent = f"not_{base_fluent}" if is_negated else base_fluent

            predicate = f"{fluent}_{"_".join(args)}" if args else fluent
            self.add_predicate_data(predicate, fluent, args, pred_type, action_name)

            if is_negated:
                self.add_negative_predicate_data(predicate, fluent, pred_type, action_name)

    def add_grounded_predicates(self, lst, state_uri) -> None:
        """
        Takes a state and adds the grounded predicates to the KG as instances
        of their corresponding fluent classes, linked to the given state.
        :param lst: list of dicts with keys "name", "args"
        :param state_uri: the hashed URI of the state entity these predicates belong to
        """
        for pred in lst:
            fluent = pred["name"]
            args = pred["args"]
            if "apt2" in args:
                print(f"DEBUG: Adding predicate {pred} with fluen {fluent} and args {args} to state {state_uri}")

            predicate = f"{fluent}_{'_'.join(args)}" if args else fluent
            # self.add_predicate_data(predicate, fluent, args, state_type, state_type)
            self.record_entity((predicate, "Proposition"), is_class=False) # e.g. at_robot1_room2 is a proposition
            self.record_relation((predicate, "partOf", state_uri)) # e.g. at_robot1_room2 is part of state_hash
            self.record_relation((predicate, "hasFluent", fluent)) # e.g. at_robot1_room2 hasFluent at
            for i, arg in enumerate(args):
                domain_fluent = self.create_dependent_identifiers(fluent, "domain")
                slot_prop = f"{domain_fluent}_hasArg{i}"
                arg = self.create_dependent_identifiers(arg, "problem")
                self.record_relation((predicate, slot_prop, arg)) # e.g. at_robot1_room2 Domain1/at_hasArg0 robot1, hasArg1 room2 # Required because holds domain and range
                # self.record_relation((predicate, f"hasArg{i}", arg))

            # print(f"DEBUG: Adding grounded predicate {predicate} as part of state {state_uri}")


    def add_predicate_data(self, predicate, fluent, args: list, pred_type, action_name) -> None:
        """
        Takes a state and adds the grounded predicates to the KG
        :param predicate: the instance name (e.g. at_robot1_room2)
        :param fluent: the fluent class name (e.g. at)
        :param args: ordered list of argument values (e.g. ["robot1", "room2"])
        :param pred_type: precond, effect, or predicate
        :param action_name: the action this predicate belongs to
        """
        domain_action_name = self.create_dependent_identifiers(action_name, "domain")
        # domain_predicate = self.create_dependent_identifiers(predicate, "domain") # ok if it has relations to many fluents, as long as they are domain-dependent?
        # domain_fluent = self.create_dependent_identifiers(fluent, "domain")

        # Declare predicate instance as member of its fluent class
        self.record_entity((fluent, "Fluent"), is_class=False) # e.g. at is a Fluent
        self.record_entity((predicate, pred_type), is_class=False)
        self.record_relation((predicate, "hasFluent", fluent)) # e.g. not_on_robot1_table hasFluent not_on

        # self.record_subclass(fluent, pred_type) # TODO double check this should be removed
        self.record_relation((domain_action_name, f"planning-ontology:has{pred_type.capitalize()}", predicate)) # e.g. Domain1/move has precondition at_robot1_room2

        for i, arg_val in enumerate(args):
            if arg_val is not None:
                arg = self.create_dependent_identifiers(arg_val, "domain")
                self.record_entity((arg, self.get_entity_type(arg_val)), is_class=False) # e.g. robot1 is an instance of Robot, room2 is an instance of Location
                self.record_relation((predicate, f"hasArg{i}", arg)) # e.g. at hasArg0 robot1, hasArg1 room2 # TODO repetitive, but not sure there is a more effective place to record this

    def add_negative_predicate_data(self, predicate, fluent, pred_type, action_name) -> None:
        """
        If the predicate is negated, add relations to the negation
        :param predicate: the full predicate string, e.g. not_on_robot1_table
        :param fluent: the relation name, e.g. not_on
        :param pred_type: the type of the predicate, e.g. precondition, effect, or predicate
        :param action_name: the name of the action this predicate is associated with
        :return: None
        """
        # TODO check if anything missing
        pos_fluent = fluent.replace("not_", "")
        pos_predicate = predicate.replace("not_", "")

        self.record_instance_of(fluent, pred_type)  # e.g. not_on is an instance of Precondition, Effect
        self.record_instance_of(fluent, "NegatedFluent")
        self.record_entity((pos_predicate, pred_type), is_class=False) # In case it's not positive yet?
        # self.record_constraint((fluent, OWL.disjointWith, pos_fluent)) # e.g. not_on is disjoint with on
        self.record_relation((fluent, "isNegationOf", pos_fluent)) # e.g. not_on_robot1_table isNegationOf on_robot1_table
        self.record_relation((predicate, "isNegationOf", pos_predicate)) # e.g. not_on_robot1_table isNegationOf on_robot1_table

        # print(f"DEBUG: r is {r}, pos_r is {pos_r}, predicate is {predicate}, neg_predicate is {neg_predicate}")
        #     self.record_relation((fluent, OWL.complementOf, pos_fluent), is_head_class=True, is_tail_class=True)
        #     self.record_instance_of(neg_predicate, fluent)

    def add_plan_to_kg(self, plan_name, plan_steps, plan_states) -> None:
        """
        Add an entity for the plan itself
        :param plan_name: the name of the plan
        :param plan_steps: the list of steps in the plan, as strings (e.g. ["(move robot1 room1 room2)"])
        :param plan_states: the list of states in the plan, as strings (e.g. ["(at robot1 room2)", "(at robot2 room1)"])
        :return: None
        """
        self.record_entity((plan_name, "Plan"), is_class=False)
        problem_name = f"{self.parser.domain_name}_{self.problem_name}"
        self.record_relation((problem_name, "hasPlan", plan_name), is_head_class=False, is_tail_class=False) # e.g. Problem1 hasPlan Plan1

        self.add_plan_terms(plan_name, plan_steps, plan_states)

    def add_plan_terms(self, plan_name, plan_steps, plan_states) -> None:
        """
        Add entities and relations for a plan, including actions and their parameters, preconditions, and effects
        :param plan_name: the name of the plan
        :param plan_steps: the list of steps in the plan, as strings (e.g. ["(move robot1 room1 room2)"])
        :param plan_states: the list of states in the plan, as strings (e.g. ["(at robot1 room2)", "(at robot2 room1)"])
        :return: None
        """
        print(f"Adding plan: {plan_name} \n with steps: {plan_steps} \n and states: {plan_states}")
        step_strings = []
        # Decompose steps
        for step in plan_steps:
            step: str = step.replace("(", "").replace(")", "").strip()
            step = "_".join(step.split())
            # print(f"Adding step {step} as an entity for plan {plan_name}")
            step_strings.append(step)
            self.record_entity((step, "Step"), is_class=False) # e.g. move_robot1_room1_room2 is a Step
            self.record_relation((plan_name, "hasStep", step)) # e.g. Plan1 hasStep move_robot1_room1_room2

            # Decompose the step into action name and parameters, e.g. (move robot1 room1 room2) -> action name: move, parameters: robot1, room1, room2
            act_name = step.split()[0]
            act_name = self.create_dependent_identifiers(act_name, "domain")

            args = step.split()[1:]
            for i, arg in enumerate(args):
                arg = self.create_dependent_identifiers(arg, "problem")
                slot_prop = f"{act_name}_hasArg{i}"
                self.record_relation((step, slot_prop, arg)) # e.g. move_robot1_room1_room2 Domain1/move_hasArg0 Domain1/robot1

        # Temporal relations between steps
        for i in range(len(plan_steps)-1):
            self.record_relation((step_strings[i], "happensAfter", step_strings[i+1]))
            self.record_relation((step_strings[i+1], "happensBefore", step_strings[i]))

        # Decompose states and link to steps
        state_uris = [self.init_uri]
        self.record_relation((step_strings[0], "hasPrecondition", self.init_uri))
        self.record_relation((plan_name, "hasState", self.init_uri))
        self.record_relation((plan_name, "hasState", self.goal_uri))

        for i, state in enumerate(plan_states):
            state: str = str(state).strip()
            state_uri = add_state_entity(state, "planning-ontology:State", self.kg_data)
            # print(f"Adding state entity: {state} with URI {state_uri}")
            self.record_relation((plan_name, "hasState", state_uri))
            state_uris.append(state_uri)
            self.record_relation((state_uris[i], "precedes", state_uri))

            # Relate to step if not the last state (which is the goal state)
            if i < len(plan_states)-2:
                # print(f"Adding relation between step at index {i+1} and state at index {i} with URI {state_uri}")
                print(f"Number of states: {len(plan_states)}, number of steps: {len(plan_steps)}")
                self.record_relation((step_strings[i+1], "hasPrecondition", state_uri))

            # Decompose the state into its propositions and link to the state entity
            # Add each as an element of a list, e,g, "(at driver2 s2) (at truck1 s0) (at truck2 s0)" -> ["at_driver2_s2", "at_truck1_s0", "at_truck2_s0"]
            state_list = state.strip().split(") (")
            state_list[0] = state_list[0].lstrip("(")
            state_list[-1] = state_list[-1].rstrip(")")
            state_lst = ["_".join(s.split()) for s in state_list]

            num = 0
            for prop in state_lst:
                prop = prop.replace(" ", "_").replace("(", "").replace(")", "").replace(",", "_").replace("?", "")
                prop_name = self.create_dependent_identifiers(prop, plan_name)
                self.record_entity((prop_name, "Proposition"), is_class=False)
                self.record_relation((prop_name, "partOf", state_uri))

                fluent = prop.split("_")[0]
                fluent = self.create_dependent_identifiers(fluent, "domain")
                self.record_relation((prop_name, "hasFluent", fluent)) # e.g. at_robot1_room2 hasFluent at
                for i, arg in enumerate(prop.split("_")[1:]):
                    arg = self.create_dependent_identifiers(arg, "problem")
                    slot_prop = f"{fluent}_hasArg{i}"
                    print(f"Adding relation for state proposition {prop_name} \n "
                          f"with fluent {fluent} and argument {arg} using slot property {slot_prop}"
                          f"for state number {num} in plan {plan_name}")
                    self.record_relation((prop_name, slot_prop, arg))
                num += 1

    # General
    def add_problem_entities(self, initial_state) -> None:
        """
        Add entities that are not directly parsed, e.g. domain and problem, and their relations
        :return: None
        """
        # Create entities for problem
        problem_name = f"{self.parser.domain_name}_{self.problem_name}"
        domain_name = self.parser.domain_name

        self.record_entity((problem_name, "planning-ontology:PlanningProblem"), is_class=False)

        ser_init, ser_goal = str(initial_state), str(self.parser.goal)
        print(f"DEBUG SECOND: Adding problem entities with initial state \n {ser_init} \n and goal state \n {ser_goal}")
        self.init_uri = add_state_entity(ser_init, "planning-ontology:InitialState", self.kg_data)
        self.goal_uri = add_state_entity(ser_goal, "planning-ontology:GoalState", self.kg_data)
        print(f"Adding initial state entity: {ser_init} with URI {self.init_uri}")
        print(f"Adding goal state entity: {ser_goal} with URI {self.goal_uri}")

        # Relations between problem and initial/goal states
        self.record_relation((self.init_uri, "initialStateOf", problem_name))
        self.record_relation((problem_name, "planning-ontology:hasInitialState", self.init_uri))
        self.record_relation((self.goal_uri, "goalStateOf", problem_name))
        self.record_relation((problem_name, "planning-ontology:hasGoalState", self.goal_uri))

        # Add the grounded predicates in initial and goal states
        # print(f"Adding initial state predicates with state URI {self.init_uri}: {initial_state}")
        # self.add_grounded_predicates(initial_state, self.init_uri)
        print(f"Adding goal state predicates with state URI {self.goal_uri}: {self.parser.goal_state}")
        self.add_grounded_predicates(self.parser.goal_state, self.goal_uri)

        # Domain -> Problem relation
        self.record_relation((domain_name, "planning-ontology:hasProblem", problem_name))

    def add_domain_entities(self) -> None:
        """
        Add entities that are not directly parsed, e.g. domain and problem, and their relations
        :return: None
        """
        # Create entities for domain
        domain_name = self.parser.domain_name
        self.record_entity((domain_name, "planning-ontology:PlanningDomain"), is_class=False)

    def create_relations(self) -> None:
        """
        Call all the methods to create entities and relations from different types of info
        :return: None
        """
        # If no existing domain KG, or if problem-specific, or if adding to general KG, add all domain-level entities and relations
        if not self.problem_specific and self.domain_specific and self.domain_kg:
            print(f"Skipping adding domain-level entities and relations for domain {self.domain_name} to the knowledge graph, as an existing domain KG was found and problem-specific KG not requested.")
        else:
            print(f"Adding domain-level entities and relations for domain {self.domain_name} to the knowledge graph.")
            self.add_domain_entities()
            self.add_domain_predicates()
            self.add_types()
            self.add_actions() # Add action names, preconditions, and effects

        # Add problem-specific entities and relations
        actions, states = parse_plan_and_simulation(self.domain_name, self.problem_name)
        initial_state = states[0]
        print(f"IMPORTANT: adding initial state from plan and simulation parsing: \n {initial_state}")
        self.add_problem_entities(initial_state)
        self.add_objects()

        self.add_plan_to_kg(f"{self.parser.domain_name}_{self.problem_name}_plan", actions, states)


    def create_kg(self) -> None:
        """
        Create Dataframes for entities and relations, convert them to JSON and load to a file
        :return: None
        """
        self.create_relations()

        if self.problem_specific:
            output_filename = f"{self.domain_name}_{self.problem_name}_knowledge_graph.owl"
            output_file = os.path.join(self.output_path, output_filename)
            print(f"Saving problem-specific knowledge graph for domain {self.domain_name} and problem {self.problem_name} to {output_file}")
        else:
            if self.domain_specific:
                output_file = self.domain_kg if self.domain_kg else os.path.join(self.output_path, f"{self.domain_name}_knowledge_graph.owl")
                print(f"Saving domain-level knowledge graph for domain {self.domain_name} to {output_file}")
            else:
                output_file = self.general_kg if self.general_kg else os.path.join(self.output_path, "tp-kg.owl")
                print(f"Saving augmented general knowledge graph with information from domain {self.domain_name} and problem {self.problem_name} to {output_file}")

        self.save_kg_to_owl(output_file)

def find_kg_for_domain(domain_name: str, kg_path: str) -> str:
    """
    Check if a knowledge graph file exists for a given domain, and return its path if it does
    :param domain_name: the name of the domain
    :param kg_path: the path to the knowledge graphs directory
    :return: the path to the knowledge graph file, or None if not found
    """
    kg_file = os.path.join(kg_path, f"{domain_name}_knowledge_graph.owl")
    if os.path.exists(kg_file):
        return kg_file
    return ""

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

def main():
    current_dir = os.getcwd()
    current_dir = os.path.abspath(os.path.join(current_dir, os.pardir, os.pardir))

    # Get arguments from command line
    parser = argparse.ArgumentParser(description="Construct a PDDL knowledge graph from domain and problem files.")
    parser.add_argument("--domain", type=str, default="2000.logistics-strips-typed", help="Name of the PDDL domain directory. If IPC, use the format <ipc-year>.<domain-name> (e.g., '2000.blocks-strips-typed').")
    parser.add_argument("--problem", type=str, default="instance-1", help="The instance filename (e.g., 'instance-1').")
    parser.add_argument("--problem_specific", action='store_true', help="Whether to create a problem-specific knowledge graph (True) or use/load a domain-level knowledge graph (False).")
    parser.add_argument("--domain_specific", action='store_true', help="Whether to create a domain-specific knowledge graph (True) or augment a general KG with domain/problem info (False). If False, will create a problem-specific KG that extends the general KG.")
    parser.add_argument("--is_IPC", default="True", help="Whether the problem is from an IPC benchmark set.")
    args = parser.parse_args()

    # DID NOT PARSE
    # sokoban-temporal_instance-1.pddl
    # 2014.hiking-sequential-optimal

    is_IPC = args.is_IPC.lower() in ['true', '1', 't', 'y', 'yes']
    if is_IPC:
        domain_path = "pddl-instances/" + "ipc-" + args.domain.split(".")[0] + "/domains/" + args.domain.split(".")[1]
    else:
        domain_path = "domains/" + args.domain
    domain_file = os.path.join(current_dir, domain_path, "domain.pddl")
    problem_file = os.path.join(current_dir, domain_path, "instances", args.problem + ".pddl")

    if args.problem_specific:
        print(f"Creating problem-specific knowledge graph for domain {args.domain} and problem {args.problem}.")
        problem_specific = True
        domain_specific = True
    else:
        if args.domain_specific:
            print(f"Creating/loading domain-level knowledge graph for domain {args.domain}.")
            problem_specific = False
            domain_specific = True
        else:
            print(f"Augmenting the general knowledge graph with domain information for domain {args.domain}.")
            problem_specific = False
            domain_specific = False

    defaults_kg = os.path.join(current_dir, "knowledge_graphs", "defaults.owl")
    static_onto = StaticOntology(defaults_kg)
    static_onto.create_kg()

    pddl_kg = DomainPDDLKG(domain_file, problem_file, problem_specific=problem_specific, domain_specific=domain_specific, data={"output_path": f"{current_dir}/knowledge_graphs/", "domain_name":args.domain, "problem_name":args.problem, })
    pddl_kg.create_kg()

if __name__ == "__main__":
    main()
