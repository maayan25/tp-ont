# Author: Ma'ayan Armony <maayan.armony@kcl.ac.uk>
# Class to construct a knowledge graph from a given PDDL domain and problem

import os
import argparse

from ParsePDDL import UnifiedPlanningParser
from rdflib import Graph
from utils import bind_namespaces, get_mamespaces, parse_plan_and_states, load_graph, query_kg_for_object, generate_uid
from BaseKG import BasePDDLKG
from PlanAndValidate import run_planner_and_validate

namespace_dict = get_mamespaces()
PLAN = namespace_dict["plan"]

class PlanPDDLKG(BasePDDLKG):
    def __init__(self, domain_file, problem_file, plans_file, data=None):
        super().__init__()
        # Optionally add to an existing (shared) graph, e.g. to accumulate the plans of many problems in one KG
        self.owns_graph = "kg_data" not in data
        if not self.owns_graph:
            self.kg_data = data["kg_data"]
        self.parser = UnifiedPlanningParser(domain_file, problem_file)

        self.output_path = data["output_path"] if "output_path" in data else f"{os.getcwd()}/knowledge_graphs/"
        self.domain_path = data["domain_name"] if "domain_name" in data else self.parser.domain_name
        self.domain_name = self.parser.domain_name
        self.problem_name = data["problem_name"] if "problem_name" in data else self.parser.problem_name
        os.makedirs(self.output_path, exist_ok=True)
        self.plans_file = plans_file
        self.plans_dir = data.get("plans_dir", os.path.join(os.getcwd(), "results", "planner_outputs", self.domain_path))
        self.problem_stem = data.get("problem_stem", self.problem_name)
        self.k = data.get("k", 5)
        self.output_filename = data.get("output_filename", "plans_tp-kg.owl")

        self.input_kg_path = data["input_kg_path"] if "input_kg_path" in data else os.path.join(self.output_path, "tp-kg.owl")
        self.input_kg = load_graph(self.input_kg_path) if os.path.exists(self.input_kg_path) else None
        if self.input_kg is None:
            print(f"Input KG not found at {self.input_kg_path}; initial/goal state entities will not be linked.")

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

    def add_plan_to_kg(self, plan_name, steps, states) -> None:
        """
        Add a plan with its steps, states and propositions to the KG.
        :param plan_name: unique name of the plan (includes the plan index)
        :param steps: list of (action, args) tuples
        :param states: list of len(steps) + 1 states (initial state, then the state after each action),
                       each a frozenset of (fluent, args) atoms
        """
        self.record_entity((plan_name, "Plan"), is_class=False)
        problem_name = f"{self.domain_name}_{self.problem_name}"
        self.record_relation((problem_name, "hasPlan", plan_name), is_head_class=False, is_tail_class=False) # e.g. Problem1 hasPlan Plan1

        print(f"Adding plan {plan_name} with {len(steps)} steps and {len(states)} states.")
        step_ids = self.add_step_entities(plan_name, steps)
        self.add_step_temporal_relations(step_ids)
        self.add_state_entities(plan_name, states, step_ids)

    def get_init_and_goal_state_entities(self):
        """
        Get the initial and goal state entities of the problem from the input knowledge graph.
        :return: (init_uri, goal_uri); each is None if the input KG is missing or does not contain it
        """
        if self.input_kg is None:
            return None, None
        problem_name = f"{self.domain_name}_{self.problem_name}"
        init_uri = query_kg_for_object(self.input_kg, PLAN[problem_name], "planning-ontology:hasInitialState")
        goal_uri = query_kg_for_object(self.input_kg, PLAN[problem_name], "planning-ontology:hasGoalState")
        return init_uri, goal_uri

    # Step entities (grounded actions) and relations
    def add_step_entities(self, plan_name: str, steps: list) -> list[str]:
        """
        Register one step entity per grounded action. Step ids are unique per plan and position, so the same
        grounded action in different plans (or twice in the same plan) is a different entity.
        :return: the list of step ids, in plan order
        """
        step_ids = []
        for i, (action, args) in enumerate(steps, start=1):
            step_id = "_".join([plan_name, f"step{i}", action, *args])
            step_ids.append(step_id)
            self.record_entity((step_id, "Step"), is_class=False)
            self.record_relation((plan_name, "hasStep", step_id))

            act_name = self.create_dependent_identifiers(action, "domain")
            for k, arg in enumerate(args):
                self.record_relation((step_id, f"{act_name}_hasArg{k}", self.create_dependent_identifiers(arg, "problem")))
        return step_ids

    def add_step_temporal_relations(self, step_ids: list[str]) -> None:
        """Add happensBefore/happensAfter relations between consecutive steps (step i happens before step i+1)."""
        for earlier, later in zip(step_ids, step_ids[1:]):
            self.record_relation((earlier, "happensBefore", later))
            self.record_relation((later, "happensAfter", earlier))

    # State entities and relations
    def make_state_id(self, state: frozenset) -> str:
        """A state is identified by its set of atoms, so identical states of different plans are the same entity."""
        canonical = " ".join(sorted(f"({name} {' '.join(args)})" for name, args in state))
        return f"{PLAN}state_{self.domain_name}_{self.problem_name}_{generate_uid(canonical)}"

    def add_state_entities(self, plan_name: str, states: list, step_ids: list[str]) -> None:
        """
        Register state entities, link them to the plan and steps, and decompose them into propositions.
        states[i] is the state before step i + 1 (so it is its precondition); the last state is the final state.
        """
        init_uri, goal_uri = self.get_init_and_goal_state_entities()
        if init_uri is not None:
            self.record_relation((plan_name, "hasState", init_uri))
        if goal_uri is not None:
            self.record_relation((plan_name, "hasState", goal_uri))

        state_ids = [self.make_state_id(state) for state in states]
        for i, (state, state_id) in enumerate(zip(states, state_ids)):
            self.record_entity((state_id, "planning-ontology:State"), is_class=False)
            self.record_relation((plan_name, "hasState", state_id))
            if i > 0:
                self.record_relation((state_ids[i - 1], "precedes", state_id))
            if i < len(step_ids):
                self.record_relation((step_ids[i], "hasPrecondition", state_id))
            for name, args in sorted(state):
                self.add_proposition_relations(name, args, state_id)

    def add_proposition_relations(self, fluent_name: str, args: tuple, state_id: str) -> None:
        """Add a proposition entity (shared by all states/plans of the problem) and link it to its state, fluent and arguments."""
        prop_name = self.create_dependent_identifiers("_".join([fluent_name, *args]), "problem")
        self.record_entity((prop_name, "Proposition"), is_class=False)
        self.record_relation((prop_name, "partOf", state_id))

        fluent = self.create_dependent_identifiers(fluent_name, "domain")
        self.record_relation((prop_name, "hasFluent", fluent))
        for i, arg in enumerate(args):
            self.record_relation((prop_name, f"{fluent}_hasArg{i}", self.create_dependent_identifiers(arg, "problem")))

    def create_relations(self) -> None:
        """Add all k plans of the problem to the KG."""
        for plan_index in range(1, self.k + 1):
            parsed = parse_plan_and_states(self.plans_dir, self.problem_stem, plan_index)
            if parsed is None:
                continue
            steps, states = parsed
            self.add_plan_to_kg(f"{self.parser.domain_name}_{self.problem_name}_plan{plan_index}", steps, states)

    def create_kg(self) -> None:
        """Add the plans and save the KG"""
        self.create_relations()
        if self.owns_graph:  # with a shared graph, the caller saves once at the end
            self.save_kg_to_owl(os.path.join(self.output_path, self.output_filename))

def resolve_domain_name(domain_arg: str) -> str:
    """
    Resolve the domain name from the command line argument to the parser name format.
    :param domain_arg: The domain argument from the command line.
    :return: The resolved domain name.
    """
    domain_names = {
        "2000.blocks-strips-typed": "BlocksDomain",
        "2000.elevator-strips-simple-typed": "ElevatorDomain",
        "2000.logistics-strips-typed": "LogisticsDomain",
        "2002.depots-strips-automatic": "DepotDomain",
        "2002.driverlog-strips-automatic": "DriverlogDomain",
        "2002.rovers-strips-automatic": "RoverDomain",
        "2002.satellite-strips-automatic": "SatelliteDomain"
    }
    return domain_names.get(domain_arg, domain_arg)

def main():
    current_dir = os.getcwd()

    parser = argparse.ArgumentParser(description="Add plans and their simulated states to a PDDL knowledge graph.")
    parser.add_argument("--domain", type=str, default="2000.elevator-strips-simple-typed", help="Name of the PDDL domain directory. If IPC, use the format <ipc-year>.<domain-name> (e.g., '2000.blocks-strips-typed'). Also the folder under results/planner_outputs (e.g. 'igibson').")
    parser.add_argument("--problems", type=str, nargs="+", default=["instance-1"], help="Problem file stems (e.g. 'instance-1', or 'sorting_books_simple' for igibson). The plans are read from <plans_dir>/<problem>.pddl_plan<k>.txt.")
    parser.add_argument("--k", type=int, default=5, help="Number of plans per problem.")
    parser.add_argument("--plans_dir", type=str, default=None, help="Directory with the planner outputs of the domain. Defaults to results/planner_outputs/<domain>.")
    parser.add_argument("--plans_file", type=str, default=None, help="The path to the plans file (optional).")
    parser.add_argument("--domain_file", type=str, default=None, help="Path to the domain PDDL (overrides the standard location, e.g. for non-IPC domains).")
    parser.add_argument("--problem_file", type=str, default=None, help="Path to the problem PDDL (overrides the standard location; only valid with a single problem).")
    parser.add_argument("--input_kg", type=str, default=None, help="Input KG with the problem's initial/goal states. Defaults to knowledge_graphs/tp-kg.owl; optional.")
    parser.add_argument("--run_planner", action="store_true", help="Run the planner and VAL first to (re)generate the plans. By default existing plans are used.")
    parser.add_argument("--is_IPC", default="True", help="Whether the problem is from an IPC benchmark set.")
    parser.add_argument("--aggregate", action="store_true", help="Accumulate the plans of all problems into one KG file (--output_file) instead of one file per problem. An existing --output_file is loaded and extended, so repeated runs (e.g. for other domains) add to it; re-adding the same plans is idempotent.")
    parser.add_argument("--output_file", type=str, default=None, help="With --aggregate: path of the aggregate KG. Defaults to knowledge_graphs/tp-kg_plans.owl.")
    parser.add_argument("--base_kg", type=str, default=None, help="With --aggregate: start a new aggregate from this KG (e.g. knowledge_graphs/tp-kg.owl) instead of an empty graph. Ignored if --output_file already exists.")

    args = parser.parse_args()
    if args.problem_file and len(args.problems) > 1:
        parser.error("--problem_file can only be used with a single problem")

    is_IPC = args.is_IPC.lower() in ['true', '1', 't', 'y', 'yes']
    if is_IPC:
        domain_path = "pddl-instances/" + "ipc-" + args.domain.split(".")[0] + "/domains/" + args.domain.split(".")[1]
    else:
        domain_path = "domains/" + args.domain
    domain_file = args.domain_file or os.path.join(current_dir, domain_path, "domain.pddl")
    input_kg_path = args.input_kg or os.path.join(current_dir, "knowledge_graphs", "tp-kg.owl")

    shared_graph, output_file = None, None
    if args.aggregate:
        output_file = args.output_file or os.path.join(current_dir, "knowledge_graphs", "tp-kg_plans.owl")
        if os.path.exists(output_file):
            print(f"Extending existing aggregate KG {output_file}")
            shared_graph = load_graph(output_file)
        elif args.base_kg:
            print(f"Starting aggregate KG from {args.base_kg}")
            shared_graph = load_graph(args.base_kg)
        else:
            shared_graph = Graph()
            bind_namespaces(shared_graph)

    for problem in args.problems:
        problem_file = args.problem_file or os.path.join(current_dir, domain_path, "instances", problem + ".pddl")
        if args.run_planner:
            run_planner_and_validate(args.domain, is_IPC, problem)

        plans_file = args.plans_file if args.plans_file else os.path.join(current_dir, "plans", args.domain, problem + ".plan")
        data = {"output_path": f"{current_dir}/knowledge_graphs/", "domain_name": args.domain, "problem_name": problem,
                "input_kg_path": input_kg_path, "k": args.k,
                "output_filename": f"plans_{args.domain}_{problem}_tp-kg.owl"}
        if args.plans_dir:
            data["plans_dir"] = args.plans_dir
        if shared_graph is not None:
            data["kg_data"] = shared_graph
        PlanPDDLKG(domain_file, problem_file, plans_file=plans_file, data=data).create_kg()

    if shared_graph is not None:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        shared_graph.serialize(output_file, format="xml")
        print(f"Saved aggregate KG with {len(shared_graph)} triples to {output_file}")

if __name__ == "__main__":
    main()
