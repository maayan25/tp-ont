# Author: Ma'ayan Armony <maayan.armony@kcl.ac.uk>
# Class to run the FD planner and VAL on a list of PDDL problems and log the results
# Based on my previous work on plan evaluation, which can be found in the repository:
# https://github.com/maayan25/llm-plan-evaluation/blob/main/scripts/plan_recovery/evaluate_plan.py

import os
from argparse import ArgumentParser
import re
from copy import deepcopy


def parse_args():
    parser = ArgumentParser(description="Run the FD planner on a list of PDDL problems and log the results")
    # parser.add_argument("--planner_dir", type=str, default=, help="Directory containing the FD planner executable from project directory")
    parser.add_argument("--domain", type=str, default="2000.logistics-strips-typed", help="Name of the PDDL domain directory. If IPC, use the format <ipc-year>.<domain-name> (e.g., '2000.blocks-strips-typed').")
    parser.add_argument("--is_IPC", type=str, default="True", help="Whether the domain is from the IPC (International Planning Competition) dataset, which has a specific directory structure")
    return parser.parse_args()


def get_initial_state(problem_path):
    """
    Get the initial state from the problem file
    :param problem_path:
    :return:
    """
    init = []
    with open(problem_path, "r") as f:
        if not f:
            print("No problem file found")
            return init
        print(f"Reading initial state from problem file: {problem_path}")

        in_init_section = False
        paren_count = 0

        for line in f:
            line = line.strip()

            # Start of :init section
            if "(:init" in line:
                in_init_section = True
                # Count opening parentheses in this line
                paren_count = line.count('(') - line.count(')')
                # Get any predicates on the same line as :init
                if line.endswith("(:init"):
                    continue
                else:
                    init_part = line.split("(:init", 1)[1].strip()
                    if init_part:
                        # This line contains predicate(s) after :init
                        if init_part.startswith('('):
                            init.append(init_part)
            else:
                if in_init_section:
                    # Stop if :goal or :metric (next section)
                    if line.startswith("(:goal") or line.startswith("(:metric"):
                        break

                    # Update parenthesis count
                    paren_count += line.count('(') - line.count(')')

                    # Extract predicates from this line
                    if line and not line == ")":
                        # This line contains predicate(s)
                        if line.startswith('('):
                            init.append(line.replace("))", ")"))  # Remove extra parentheses if they exist

                    # If closed all parentheses done with :init
                    if paren_count <= 0:
                        break

    print(f"Initial state: {init}")
    # Remove dangling parantheses at the end of the last predicate if there is "))" at the end of the last predicate in init list
    cleaned_init = []
    for pred in init:
        if pred.endswith("))"):
            cleaned_init.append(pred[:-1])
        else:
            cleaned_init.append(pred)

    return init

def get_effects(plan_validation_path) -> dict[int, list[str]]:
    """
    Get the effects of the action from the plan validation output file
    :param unique_id: the unique id of the plan
    :return: a dictionary of action index and its effects
    """
    effects = {}
    i = 1
    with open(plan_validation_path, "r") as f:
        if not f:
            print("No plan validation file found")
            return effects
        for line in f:
            if "Checking next happening" in line:
                effects[i] = []
                i += 1
            match = re.match(r"(Deleting|Adding) \((.+)\)", line)
            if match:
                # print(f"Found effect: {line.strip()} for action {i-1} in plan validation output")
                effect_type = match.group(1)  # 'Deleting' or 'Adding'
                effect = [effect_type.lower(), f"({match.group(2)})"]
                effects[i - 1].append(effect)
            elif "Plan failed to execute" in line:
                break

    return effects

def apply_action(effects, state) -> list[str]:
    """
    Parse the output of the plan execution and apply the action to the state
    :param effects: the effects of the current action
    :param state: the current state to apply the action to
    :return: the new state after applying the action
    """
    new_state = state
    if not effects:
        # print("No effects found for state in plan validation")
        return new_state

    for effect in effects:
        if "adding" in effect:
            new_state.append(effect[1])
        elif "deleting" in effect:
            if effect[1] in new_state:
                new_state.remove(effect[1])
            else:
                print(f"Effect {effect[1]} not in current state")

    return new_state

def simulate_states(problem_path, plan_validation_path, plan_size) -> list[list[str]]:
    init = get_initial_state(problem_path)
    states = [deepcopy(init)]
    current_state = deepcopy(init)

    effects = get_effects(plan_validation_path)
    if not effects:
        print("Plan validation has failed, simulation cannot be completed")
        return states

    # Apply all effects of actions up to the last action
    for i in range(1, plan_size + 1):
        # print(f"DEBUG SIM: Applying action {i}, with effects: {effects.get(i)} \n on current state: {current_state}")
        new_state = apply_action(effects.get(i), current_state)
        states.append(deepcopy(new_state))
        current_state = deepcopy(new_state)
        # print(f"DEBUG SIM: New state: {new_state}")

    # print(f"DEBUG SIM: states are {states} for instance {self.instance_id}")
    return deepcopy(states)

def check_plan_validity(domain_file, problem_file, plan_path) -> None:
    """
    Check if the plan is valid using VAL validator
    """
    VAL_PATH = os.path.join(planner_dir, os.pardir, "VAL")
    plan_validation_path = plan_path.replace(".txt", "_validation.txt")

    cmd = f"{VAL_PATH}/validate -v {domain_file} {problem_file} {plan_path} 2>&1 | tee {plan_validation_path}"
    response = os.popen(cmd).read()

    return plan_validation_path


def run_planner(domain_file, problem_file, planner_dir) -> (str, int):
    cmd = f"timeout 60s {planner_dir}/fast-downward.py {domain_file} {problem_file} --search \"astar(lmcut())\" > /dev/null"
    os.system(cmd)
    plan_file = "sas_plan"
    if os.path.exists(plan_file):
        with open(plan_file) as f:
            plan = [line.rstrip() for line in f][:-1]
            readable_plan = '\n'.join(plan)
        os.remove(plan_file)
    elif os.path.exists(os.path.join(planner_dir, plan_file)):
        with open(os.path.join(planner_dir, plan_file)) as f:
            plan = [line.rstrip() for line in f][:-1]
            readable_plan = '\n'.join(plan)
        os.remove(os.path.join(planner_dir, plan_file))
    else:
        print(f"No plan found for instance: {problem_file}")
        readable_plan = "No plan found within time limit."

    plan_length = len(plan) if plan is not None else 0

    return readable_plan, plan_length

if __name__ == "__main__":
    args = parse_args()
    project_dir = os.path.join(os.getcwd(), os.pardir, os.pardir)

    is_IPC = args.is_IPC.lower() in ['true', '1', 't', 'y', 'yes']
    if is_IPC:
        domain_path = "pddl-instances/" + "ipc-" + args.domain.split(".")[0] + "/domains/" + args.domain.split(".")[1]
    else:
        domain_path = "domains/" + args.domain

    domain_name = args.domain
    domain_file = os.path.join(project_dir, domain_path, "domain.pddl")
    problem_dir = os.path.join(project_dir, domain_path, "instances")
    planner_dir = os.path.join(project_dir, os.pardir, "planners", "downward")
    output_dir = os.path.join(project_dir, "results", "planner_outputs", domain_name)
    os.makedirs(output_dir, exist_ok=True)

    max_limit = 10
    # Loop through problem files instance-i.pddl and run the planner and validation on each
    plan_names = []
    for i in range(1, max_limit):
        problem = f"instance-{i}.pddl"
        problem_file = os.path.join(problem_dir, problem)
        output_path = os.path.join(output_dir, f"{problem}_plan.txt")

        readable_plan, plan_length = run_planner(domain_file, problem_file, planner_dir)

        # Save to output file
        with open(output_path, "w") as f:
            f.write(readable_plan)
        print(f"Saved planner output to {output_path}")

        plan_validation_path = check_plan_validity(domain_file, problem_file, output_path)
        print(f"Saved plan validation output to {plan_validation_path}")
        state_simulation_path = output_path.replace(".txt", "_state_simulation.txt")
        states = simulate_states(problem_path=problem_file, plan_validation_path=plan_validation_path, plan_size=plan_length)
        print(f"Simulated states for plan: {states}")
        with open(state_simulation_path, "w") as f:
            f.write("Initial state:\n")
            for predicate in states[0]:
                f.write(f"{predicate} ")
            f.write("\n")
            for i, state in enumerate(states[1:]):
                f.write(f"State after action {i+1}:\n")
                for predicate in state:
                    f.write(f"{predicate} ")
                f.write("\n")
        print(f"Saved state simulation output to {state_simulation_path}")