# Author: Ma'ayan Armony <maayan.armony@kcl.ac.uk>
# Classes to parse PDDL into python variables
import argparse
import os
import re

# import pddlpy
from unified_planning.io import PDDLReader
import unified_planning
from unified_planning.model import Problem, FNode, Fluent


class ParsePLan:
    """
    Class to parse a PDDL plan in the form of <time: double> <action_name: str> <action_args: list(str)>
    :param plan_filename: the path to the plan file from the root of the project
    # TODO add handling for plans in other structures
    """
    def __init__(self, plan_filename):
        self.plan_filename = plan_filename
        self.plan = []
        print("Created plan parser")

    def parse(self):
        lines = read_file(self.plan_filename)
        print("Number of actions in plan:", len(lines))
        action_pattern = re.compile(r'(\d+\.*\d*):\s*\(([\w-]+)([^)]*)\)')  # a double number for time
        step = 1
        for line in lines:
            match = action_pattern.match(line)
            if match:
                time = match.group(1)
                action = match.group(2)
                arguments = match.group(3).strip().split() if match.group(3).strip() else []

                # if step_num != step:
                #     print(f"step num not matching iteration; step={step} and step_num={step_num}")
                self.plan.append({
                    'step': step,
                    'time': time,
                    'action': action,
                    'arguments': arguments
                })
                step += 1
        return self.plan

class ParseDomainProblemPDDLPY:
    """
    Class to parse a PDDL domain and problem to python variables using the `pddlpy` Python library
    :param domain_file: the path to the domain file from the root of the project
    :param problem_file: the path to the problem file from the root of the project
    """

    def __init__(self, domain_file, problem_file):
        self.domain_file = domain_file
        self.problem_file = problem_file

        self.domain_name = parse_domain_name(self.domain_file)
        self.problem_name = parse_problem_name(self.problem_file)

        # DomainProblem object for the PDDL files
        self.pddl = pddlpy.DomainProblem(self.domain_file, self.problem_file)

        # Domain entities (see documentation for details):
        # https://github.com/hfoffani/pddl-lib/blob/main/pddlpy/pddl.py
        self.actions = self.pddl.domain.operators.items()
        self.action_names = self.pddl.operators()
        self.grounded_actions = self.set_grounded_actions()  # not currently in use

        self.types = ["domain", "problem", "action", "state", "object"]  # TODO fix? tried: self.types = self.pddl.domain.types()

        # Problem entities
        self.initial_state = self.pddl.initialstate() # set of tuples of strings
        self.goal_state = self.pddl.goals() # set of tuples of strings

        # Domain + Problem entities
        self.objects = self.pddl.worldobjects() # dictionary of {object_name: object_type}

        print("Created PDDLPY parser")
        print("Initial state:", self.initial_state)
        print("Goal state:", self.goal_state)
        print("Actions:", self.actions)

    # Actions
    def set_grounded_actions(self):
        """
        Return the grounded version of actions
        :return: grounded actions for every action name
        """
        grounded_actions = []
        for act_name in self.action_names:
            self.pddl.ground_operator(act_name)
            grounded_actions.append(act_name)
        return grounded_actions

    def get_grounded_action(self, act_name):
        return self.pddl.ground_operator(act_name)


def read_file(filename):
    with open(filename, 'r') as file:
        return file.readlines()

def parse_domain_name(domain_file) -> str:
    """
    Parses and returns the domain name from a PDDL domain file.
    :return: name of domain
    """
    with open(domain_file, 'r') as file:
        content = file.read()
    match = re.search(r'\(domain\s+([^\s\)]+)\)', content, re.IGNORECASE)
    if match:
        domain_name = match.group(1)
        # Strip leading/trailing non-alphanumeric characters (except hyphens within the name)
        domain_name = re.sub(r'^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$', '', domain_name)
        return f"{domain_name.capitalize()}Domain"
    return "UnnamedDomain"

def parse_problem_name(problem_file):
    """
    Parses and returns the problem name from a PDDL problem file.
    :return: name of problem
    """
    with open(problem_file, 'r') as file:
        content = file.read()
    match = re.search(r'\(problem\s+([^\s\)]+)\)', content, re.IGNORECASE)
    if match:
        return match.group(1)
    return "unnamed_problem"

class UnifiedPlanningParser:
    def __init__(self, domain_file, problem_file):
        unified_planning.environment.error_used_name = False
        self.reader = PDDLReader()
        self.pddl: Problem = self.reader.parse_problem(domain_file, problem_file)
        # print(f"PDDL: {self.pddl}")
        # print("=" * 20)
        self.domain_name = parse_domain_name(domain_file)
        self.problem_name = self.pddl.name
        # print(f"Domain name: {self.domain_name}, Problem name: {self.problem_name}")

        self.actions = list(self.pddl.actions) # List of actions; action has: name, parameters, preconditions, unconditional_effects, conditional_effects, environment (Environment object)
        # self.organise_predicates()
        # print("*" * 20)
        # print(f"Parsed Preconditions: \n {self.new_preconditions} \n and Parsed Effects: \n {self.new_effects}")
        # print("*" * 20)
        self.durative_actions = self.pddl.durative_actions  # TODO not currently in use, is it useful?
        # print(f"Actions {self.actions}")
        self.action_names = self.get_action_names()  # List of action names
        # print(f"Action names: {self.action_names}")

        self.types = list(self.pddl.user_types) # List of user types in the domain
        self.types_hierarchy = list(self.pddl.user_types_hierarchy)  # Dictionary of {type_name: list of parent types} # TODO not currently in use, types have father attribute
        self.fluents = self.arrange_fluents(self.pddl.fluents) # Make a list of dicts with fluent name and arg types
        # print(f"Types in domain:", self.types)
        # print(f"Fluents before arranging:", self.pddl.fluents)
        # print(f"Fluents in domain:", self.fluents)

        # Problem entities
        self.init = list(self.pddl.initial_values) # set of tuples of strings
        self.goal = list(self.pddl.goals)

        self.initial_state = self.parse_predicates(self.init)
        self.goal_state = self.parse_predicates(self.goal)
        # print("*" * 20)
        # print(f"Initial state raw: {self.init}")
        # print(f"Goal state raw: {self.goal}")
        # print("\n")
        # print(f"Parsed initial state: {self.initial_state}")
        # print(f"Parsed goal state: {self.goal_state}")
        # print("*" * 20)

        # Domain + Problem entities
        self.objects = self.get_objects_by_type()  # Dictionary of {type: object instances}
        # print(f"Objects in domain:", self.objects)

        print("Created Unified Planning parser")

    def get_action_names(self):
        """
        Get the names of the actions in the PDDL problem.
        :return: list of action names
        """
        action_names = []
        for action in self.actions:
            action_names.append(action.name)
        return action_names

    def get_objects_by_type(self) -> dict[str, list]:
        """
        Get the objects in the PDDL problem organised by type.
        :return: dictionary of {type: list of object instances}
        """
        objects = {}
        for obj in self.pddl.all_objects:
            obj_type = obj.type.name
            objects[obj_type] = [] if obj_type not in objects else objects[obj_type]
            objects[obj_type].append(obj.name)
        return objects

    def arrange_fluents(self, fluents: list[Fluent]) -> dict[str, list]:
        """
        Arrange the fluents as a list of predicate where each pred has a dict of arg index and arg type from the
        list of types in the domain.
        :return: list of fluents with their argument types
        """
        arranged_fluents = {}
        for fluent in fluents:
            # Each fluent has a signature with args of type Parameter
            arg_types = []
            for arg in fluent.signature:
                # arg_name = arg.name
                arg_type = arg.type.name if not isinstance(arg.type, str) else arg.type
                arg_types.append(arg_type)

            arranged_fluents[fluent.name] = arg_types

        return arranged_fluents

    def organise_predicates(self):
        """
        Organise the predicates in the PDDL problem into a dictionary of lists.
        :return: dictionary of predicates, where keys are predicate names and values are lists of arguments
        """
        self.new_preconditions = []
        self.new_effects = []
        for action in self.actions:
            if action.preconditions:
                # print(f"Action {action.name} has preconditions: {action.preconditions}")
                self.new_preconditions.append((action.name, self.parse_predicates(list(action.preconditions))))
            else:
                print(f"Action {action.name} has no preconditions")
            if action.effects:
                # print(f"Action {action.name} has conditional effects: {action.effects}")
                self.new_effects.append((action.name, self.parse_predicates(list(action.effects))))
            else:
                print(f"Action {action.name} has no effects")


    def parse_predicates(self, predicates) -> list:
        """
        Parse the predicates into the format: {"name": predicate_name, "args": [arg1, arg2, ...]} to
        be used in the knowledge graph.

        Preconditions are list with 1 FNode where args are the (FNode) predicates
        Effects are list of Effects each with a fluent which is the predicate
        Initial state is a list of FNode predicates
        Goal state is a list with 1 FNode:
         - if 1 goal then it is the predicate
         - if multiple goals - args are the (FNode) predicates

        :param predicates: list of predicates from the PDDL problem
        :return: list of dictionaries with predicate names and arguments
        """
        parsed_predicates = []

        # In preconditions and goal state (with multiple goals), predicates are inside an FNode
        if isinstance(predicates, list) and isinstance(predicates[0], FNode):
            if len(predicates[0].args[0].args) > 0: # False if only 1 goal in goal state
                predicates: tuple = predicates[0].args
        for pred in predicates:
            value = None
            # If the predicate is not an FNode, it is an Effect
            if not isinstance(pred, FNode):
                value = pred.value if hasattr(pred, "value") else None
                pred = pred.fluent if hasattr(pred, "fluent") else pred
                if not isinstance(pred, FNode):
                    print(f"Predicate {pred.name} is not a FNode it is a {type(pred)}")
                    continue
            pred_content: set = pred.get_contained_names()
            pred_args = [str(arg) for arg in pred.args]  # List of argument names as strings
            pred_name = list(pred_content.difference(pred_args)).pop()
            pred_name = f"not_{pred_name}" if str(value) == "false" else pred_name
            assert pred_name, "Predicate name not found in predicate content"
            new_pred = {"name": pred_name, "args": pred_args}
            parsed_predicates.append(new_pred)
        return parsed_predicates


def main():
    args = parse_args()

    # # Parse a PDDL plan
    # plan_parser = ParsePLan('plans/examples/example_plan.txt')
    # plan = plan_parser.parse()
    # print(plan)

    # Unified planning parses - counters domain
    # pddlpy parser - example domain, pddl-lib domain-01
    # Neither parses - office-robot with named waypoints
    # Both parse - pddl-lib domain-02 and domain-03

    if args.is_IPC:
        domain_path = "pddl-instances/" + "ipc-" + args.domain.split(".")[0] + "/domains/" + args.domain.split(".")[1]
    else:
        domain_path = "domains/" + args.domain
    root_dir = os.path.join(os.getcwd(), os.pardir, os.pardir)
    domain_file = os.path.join(root_dir, domain_path, "domain.pddl")
    problem_file = os.path.join(root_dir, domain_path, "instances", args.problem + ".pddl")

    # Parse Problem and Domain with Unified Planning
    unified_parser = UnifiedPlanningParser(domain_file, problem_file)
    # Issues:
    # 2000.logistics-strips-untyped -> SyntaxError: UPExpressionDefinitionError('In FluentExp, fluent: in has arity 1 but 2 parameters were passed.') \n Error from line: 26, col 30 to line: 26, col 46

    # Parse Problem and Domain with PDDLPY
    # pddlpy_parser = ParseDomainProblemPDDLPY(domain_file, problem_file)

def parse_args():
    parser = argparse.ArgumentParser(description="Parse PDDL files into Python variables.")
    parser.add_argument("--domain", type=str, default="2000.elevator-strips-simple-typed", help="Name of the PDDL domain directory. If IPC, use the format <ipc-year>.<domain-name> (e.g., '2000.blocks-strips-typed').")
    parser.add_argument("--problem", type=str, default="instance-1", help="The instance filename (e.g., 'instance-1').")
    parser.add_argument("--is_IPC", action='store_true', default=True, help="Whether the problem is from an IPC benchmark set.")
    return parser.parse_args()

if __name__ == '__main__':
    main()