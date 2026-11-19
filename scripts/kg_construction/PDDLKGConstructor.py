# Author: Ma'ayan Armony <maayan.armony@kcl.ac.uk>
# Class to construct a knowledge graph from a given PDDL domain and problem

import os
import argparse

from ParsePDDL import UnifiedPlanningParser
from utils import add_state_entity, get_mamespaces, bind_namespaces, get_initial_state_from_problem
from BaseKG import BasePDDLKG
from StaticOntology import StaticOntology

from rdflib import RDFS, Graph

namespace_dict = get_mamespaces()
PLAN = namespace_dict["plan"]

# TODO 1. continue difference between typed and untyped objects in PDDL (elevator domain)
# TODO 3. handle numerics: 2004.satellite-complex-strips, 2008.transport-sequential-optimal-strips, 2008.woodworking-sequential-optimal-strips, 2011.barman-sequential-multi-core
# TODO 4. handle temporal

class DomainPDDLKG(BasePDDLKG):
    def __init__(self, domain_file, problem_file, problem_specific=True, domain_specific=True, data=None):
        super().__init__()
        self.parser = UnifiedPlanningParser(domain_file, problem_file)
        self.domain_file = domain_file
        self.problem_file = problem_file

        self.output_path = data["output_path"] if "output_path" in data else f"{os.getcwd()}/knowledge_graphs/"
        self.domain_name = data["domain_name"] if "domain_name" in data else self.parser.domain_name
        # Only the last path segment: for igibson the file stem already ends with the complexity (e.g. cleaning_out_drawers_simple)
        self.problem_name = data["problem_name"].split("/")[-1] if "problem_name" in data else self.parser.problem_name

        print(f"DEBUG: problem name is {self.problem_name}, domain name is {self.domain_name}")
            
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
        # print(f"DEBUG SECOND: Adding problem entities with initial state \n {ser_init} \n and goal state \n {ser_goal}")
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
        # TODO add correct init here
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
        # TODO make this not have to run the whole plan and simulation parsing 
        # actions, states = parse_plan_and_simulation(self.domain_name, self.problem_name)
        # initial_state = states[0]
        print(f"IMPORTANT: adding initial state from problem {self.problem_name} in path {self.problem_file} to the knowledge graph.")
        initial_state = get_initial_state_from_problem(self.problem_file)
        print(f"DEBUG: initial state from problem {self.problem_name} is {initial_state}")

        self.add_problem_entities(initial_state)
        self.add_objects()

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

def resolve_base_dir(base_dir: str | None = None) -> str:
    """Return TP-ONT's project root, either explicitly provided or inferred from cwd."""
    if base_dir:
        return os.path.abspath(base_dir)
    return os.path.abspath(os.path.join(os.getcwd(), os.pardir, os.pardir))

def resolve_domain_path(domain: str, is_IPC: bool) -> str:
    """Return the relative path to the domain directory."""
    if is_IPC:
        year, domain_name = domain.split(".", 1)
        return os.path.join("pddl-instances", f"ipc-{year}", "domains", domain_name)
    return os.path.join("domains", domain)

def build_static_ontology(output_path: str) -> StaticOntology:
    """Load and initialise the shared static ontology."""
    defaults_kg = os.path.join(output_path, "defaults.owl")
    static_onto = StaticOntology(defaults_kg)
    static_onto.create_kg()
    return static_onto

def build_problem_kg(base_dir: str, domain: str, domain_path: str, problem: str, 
                     problem_specific: bool, domain_specific: bool, output_path: str, problem_path = None, domain_file: str | None = None) -> DomainPDDLKG:
    """Construct and return the KG for a single problem instance."""
    domain_file = domain_file or os.path.join(base_dir, domain_path, "domain.pddl")
    problem_file = os.path.join(base_dir, domain_path, "instances", f"{problem}.pddl") if problem_path is None else os.path.join(problem_path, f"{problem}.pddl")

    pddl_kg = DomainPDDLKG(domain_file, problem_file, problem_specific=problem_specific, domain_specific=domain_specific,
        data={
            "output_path": output_path,
            "domain_name": domain,
            "problem_name": problem,
        },
    )
    
    pddl_kg.create_kg()
    return pddl_kg

def create_kg(domain: str = "2000.logistics-strips-typed", problems: list[str] | None = None, problem_specific: bool = False, 
        domain_specific: bool = False, is_IPC: bool = True, base_dir: str | None = None, problem_path: str | None = None, domain_file: str | None = None) -> list[DomainPDDLKG]:
    """
    Build knowledge graphs for one domain and one or more problem instances.

    :param domain: Domain identifier in IPC format (e.g., '2000.blocks-strips-typed').
    :param problems: List of problem instance names. Defaults to ['instance-1'].
    :param problem_specific: If True, build a problem-specific KG (implies domain_specific=True).
    :param domain_specific: If True, build/load a domain-level KG. If both flags are False, augment the general KG instead.
    :param is_IPC: Whether the domain comes from an IPC benchmark set.
    :param base_dir: TP-ONT project root directory. Inferred from cwd if not provided.
    :param domain_file: Path to the domain PDDL, overriding the standard location (for non-IPC domains, where the domain is just the name, e.g. igibson).

    :return: List of constructed DomainPDDLKG objects, one for each problem instance.
    """
    problems = ["instance-1"] if problems is None else problems

    base_dir = resolve_base_dir(base_dir)
    domain_path = resolve_domain_path(domain, is_IPC)

    if problem_specific:
        problem_specific, domain_specific = True, True
    else:
        problem_specific, domain_specific = False, domain_specific

    output_path = os.path.join(base_dir, "knowledge_graphs")
    os.makedirs(output_path, exist_ok=True)

    build_static_ontology(output_path)

    results = []
    for problem in problems:
        _log_kg_mode(domain, problem, problem_specific, domain_specific)
        kg = build_problem_kg(base_dir, domain, domain_path, problem, problem_specific, domain_specific, output_path, problem_path, domain_file)
        results.append(kg)

    return results

def _log_kg_mode(domain: str, problem: str, problem_specific: bool, domain_specific: bool) -> None:
    """Print a summary of the KG mode being used."""
    if problem_specific:
        print(f"[{problem}] Creating problem-specific KG for domain '{domain}'.")
    elif domain_specific:
        print(f"[{problem}] Creating/loading domain-level KG for domain '{domain}'.")
    else:
        print(f"[{problem}] Augmenting general KG with domain info for domain '{domain}'.")


def parse_args() -> argparse.Namespace:
    """Parse and return command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Construct a PDDL knowledge graph from domain and problem files."
    )
    parser.add_argument("--base_dir", type=str, default=None, help="TP-ONT project root directory. Defaults to two levels above cwd.")
    parser.add_argument("--domain", type=str, default="2000.logistics-strips-typed", help="IPC format: '<year>.<domain-name>' (e.g. '2000.blocks-strips-typed').")
    parser.add_argument("--problems", type=str, nargs="+", default=["instance-1"], help="One or more instance names to run in sequence.")
    parser.add_argument("--problem_specific", action="store_true", help="Create a problem-specific KG.")
    parser.add_argument("--domain_specific", action="store_true", help="Create a domain-level KG (ignored if --problem_specific is set).")
    parser.add_argument("--is_IPC", default="True", help="Whether the domain is from an IPC benchmark set.")
    parser.add_argument("--problem_path", type=str, default=None, help="Path to the problem file if not in the standard IPC directory structure.")
    parser.add_argument("--domain_file", type=str, default=None, help="Path to the domain PDDL if not in the standard directory structure (the --domain value is then only the domain name, e.g. 'igibson').")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    is_IPC = args.is_IPC.lower() in ["true", "1", "t", "y", "yes"]
    create_kg(domain=args.domain, problems=args.problems, problem_specific=args.problem_specific, 
        domain_specific=args.domain_specific, is_IPC=is_IPC, base_dir=args.base_dir, problem_path=args.problem_path, domain_file=args.domain_file)