# Author: Ma'ayan Armony <maayan.armony@kcl.ac.uk>
# Class to construct a knowledge graph from a given PDDL domain and problem

import os
import argparse

from ParsePDDL import UnifiedPlanningParser
from utils import add_state_entity, get_mamespaces, bind_namespaces, parse_plan_and_simulation, load_graph
from BaseKG import BasePDDLKG

from rdflib import RDF, RDFS, Graph

namespace_dict = get_mamespaces()
PLAN = namespace_dict["plan"]

class PlanPDDLKG(BasePDDLKG):
    def __init__(self, domain_file, problem_file, plans_file, data=None):
        super().__init__()
        self.parser = UnifiedPlanningParser(domain_file, problem_file)

        self.output_path = data["output_path"] if "output_path" in data else f"{os.getcwd()}/knowledge_graphs/"
        self.domain_name = data["domain_name"] if "domain_name" in data else self.parser.domain_name
        self.problem_name = data["problem_name"] if "problem_name" in data else self.parser.problem_name
        os.makedirs(self.output_path, exist_ok=True)
        self.plans_file = plans_file

        self.input_kg_path = data["input_kg_path"] if "input_kg_path" in data else os.path.join(self.output_path, "tp-kg.owl")
        self.input_kg = load_graph(self.input_kg_path)

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

    def add_plan_to_kg(self, plan_name, plan_steps, plan_states) -> None:
        """
        Add an entity for the plan itself
        :param plan_name: the name of the plan
        :param plan_steps: the list of steps in the plan, as strings (e.g. ["(move robot1 room1 room2)"])
        :param plan_states: the list of states in the plan, as strings (e.g. ["(at robot1 room2)", "(at robot2 room1)"])
        :return: None
        """
        self.record_entity((plan_name, "Plan"), is_class=False)
        problem_name = f"{self.domain_name}_{self.problem_name}"
        self.record_relation((problem_name, "hasPlan", plan_name), is_head_class=False, is_tail_class=False) # e.g. Problem1 hasPlan Plan1

        self.add_plan_terms(plan_name, plan_steps, plan_states)

    def get_init_and_goal_state_entities(self) -> tuple[str, str]:
        """
        Get the initial and goal state entities from the knowledge graph.
        :return: A tuple of (init_uri, goal_uri)
        """
        init_uri = self.kg_data.get_related_entities(self.problem_name, "planning-ontology:hasInitialState")[0]
        goal_uri = self.kg_data.get_related_entities(self.problem_name, "planning-ontology:hasGoalState")[0]
        return init_uri, goal_uri

    # Step entities (grounded actions) and relations
    def add_step_entities(self, plan_name: str, step: str, step_string: str) -> None:
        """Register a step entity and its argument relations for a given plan."""
        self.record_entity((step_string, "Step"), is_class=False)
        self.record_relation((plan_name, "hasStep", step_string))

        parts = step_string.split("_")
        act_name = self.create_dependent_identifiers(parts[0], "domain")
        for i, arg in enumerate(parts[1:]):
            arg = self.create_dependent_identifiers(arg, "problem")
            self.record_relation((step_string, f"{act_name}_hasArg{i}", arg))

    def parse_step_string(self, step: str) -> str:
            """Normalize a step string: '(move robot1 room1 room2)' -> 'move_robot1_room1_room2'"""
            return "_".join(step.replace("(", "").replace(")", "").strip().split())

    def add_step_temporal_relations(self, step_strings: list[str]) -> None:
        """Add happensBefore/happensAfter relations between consecutive steps."""
        for i in range(len(step_strings) - 1):
            self.record_relation((step_strings[i], "happensAfter", step_strings[i + 1]))
            self.record_relation((step_strings[i + 1], "happensBefore", step_strings[i]))

    # State entities and relations
    def add_state_entities(self, plan_name: str, plan_states: list[str], step_strings: list[str]) -> None:
        """Register state entities, link them to the plan and steps, and decompose their propositions."""
        init_uri, goal_uri = self.get_init_and_goal_state_entities()
        state_uris = [init_uri]
        self.record_relation((step_strings[0], "hasPrecondition", init_uri))
        self.record_relation((plan_name, "hasState", init_uri))
        self.record_relation((plan_name, "hasState", goal_uri))

        for i, state in enumerate(plan_states):
            state_uri = add_state_entity(str(state).strip(), "planning-ontology:State", self.kg_data)
            self.record_relation((plan_name, "hasState", state_uri))
            self.record_relation((state_uris[i], "precedes", state_uri))
            state_uris.append(state_uri)

            if i < len(plan_states) - 2:
                self.record_relation((step_strings[i + 1], "hasPrecondition", state_uri))

            for prop in self.parse_state_propositions(state):
                self.add_proposition_relations(prop, state_uri, plan_name)

    def parse_state_propositions(self, state: str) -> list[str]:
            """Split a state string into normalized proposition tokens."""
            parts = state.strip().split(") (")
            parts[0] = parts[0].lstrip("(")
            parts[-1] = parts[-1].rstrip(")")
            return ["_".join(p.split()) for p in parts]

    def add_proposition_relations(self, prop_raw: str, state_uri: str, plan_name: str) -> None:
        """Add a proposition entity and link it to its state, fluent, and arguments."""
        prop = prop_raw.replace(" ", "_").replace("(", "").replace(")", "").replace(",", "_").replace("?", "")
        prop_name = self.create_dependent_identifiers(prop, plan_name)
        self.record_entity((prop_name, "Proposition"), is_class=False)
        self.record_relation((prop_name, "partOf", state_uri))

        fluent = self.create_dependent_identifiers(prop.split("_")[0], "domain")
        self.record_relation((prop_name, "hasFluent", fluent))

        for i, arg in enumerate(prop.split("_")[1:]):
            arg = self.create_dependent_identifiers(arg, "problem")
            self.record_relation((prop_name, f"{fluent}_hasArg{i}", arg))

    def add_plan_terms(self, plan_name: str, plan_steps: list[str], plan_states: list[str]) -> None:
        """
        Add entities and relations for a plan, including steps, states, and propositions.
        :param plan_name: the name of the plan
        :param plan_steps: the list of steps in the plan, as strings (e.g. ["(move robot1 room1 room2)"])
        :param plan_states: the state simulation, each state is a string
        :return: None
        """
        step_strings = [self.parse_step_string(s) for s in plan_steps]

        for step, step_string in zip(plan_steps, step_strings):
            self.add_step_entities(plan_name, step, step_string)

        self.add_step_temporal_relations(step_strings)
        self.add_state_entities(plan_name, plan_states, step_strings)

    def create_relations(self) -> None:
        """
        Call all the methods to create entities and relations from different types of info
        :return: None
        """
        # TODO get k plans and run this all in a loop
        print(f"Plan-level construction for plan {self.domain_name}_{self.problem_name}_plan")
        # print(f"Skipping adding domain-level entities and relations for domain {self.domain_name} to the knowledge graph.")
        
        # Add problem-specific entities and relations
        actions, states = parse_plan_and_simulation(self.domain_name, self.problem_name)

        self.add_plan_to_kg(f"{self.parser.domain_name}_{self.problem_name}_plan", actions, states)

    def create_kg(self) -> None:
        """
        Create Dataframes for entities and relations, convert them to JSON and load to a file
        :return: None
        """
        self.create_relations()
        output_file = os.path.join(self.output_path, "plans_tp-kg.owl")
        self.save_kg_to_owl(output_file)

def main():
    current_dir = os.getcwd()
    current_dir = os.path.abspath(os.path.join(current_dir, os.pardir, os.pardir))

    # Get arguments from command line
    parser = argparse.ArgumentParser(description="Construct a PDDL knowledge graph from domain and problem files.")
    parser.add_argument("--domain", type=str, default="2000.logistics-strips-typed", help="Name of the PDDL domain directory. If IPC, use the format <ipc-year>.<domain-name> (e.g., '2000.blocks-strips-typed').")
    parser.add_argument("--problem", type=str, default="instance-1", help="The instance filename (e.g., 'instance-1').")
    parser.add_argument("--plans_file", type=str, default=None, help="The path to the plans file (optional). If not provided, the default location will be used.")
    parser.add_argument("--is_IPC", default="True", help="Whether the problem is from an IPC benchmark set.")

    args = parser.parse_args()

    is_IPC = args.is_IPC.lower() in ['true', '1', 't', 'y', 'yes']
    if is_IPC:
        domain_path = "pddl-instances/" + "ipc-" + args.domain.split(".")[0] + "/domains/" + args.domain.split(".")[1]
    else:
        domain_path = "domains/" + args.domain
    domain_file = os.path.join(current_dir, domain_path, "domain.pddl")
    problem_file = os.path.join(current_dir, domain_path, "instances", args.problem + ".pddl")

    input_kg_path = os.path.join(current_dir, "knowledge_graphs", "tp-kg.owl")
    if not os.path.exists(input_kg_path):
        raise FileNotFoundError(f"Input knowledge graph not found at {input_kg_path}")

    plans_file = args.plans_file if args.plans_file else os.path.join(current_dir, "plans", args.domain, args.problem + ".plan")
    pddl_kg = PlanPDDLKG(domain_file, problem_file, plans_file=plans_file, data={"output_path": f"{current_dir}/knowledge_graphs/", "domain_name":args.domain, "problem_name":args.problem, "input_kg_path": input_kg_path})
    pddl_kg.create_kg()

if __name__ == "__main__":
    main()
