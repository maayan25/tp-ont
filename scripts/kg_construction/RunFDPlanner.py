# Author: Ma'ayan Armony <maayan.armony@kcl.ac.uk>
# Class to run the FD planner and VAL on a list of PDDL problems and log the results
# Based on my previous work on plan evaluation, which can be found in the repository:
# https://github.com/maayan25/llm-plan-evaluation/blob/main/scripts/plan_recovery/evaluate_plan.py

import os
from argparse import ArgumentParser
import re
from copy import deepcopy
import subprocess

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

def check_plan_validity(domain_file, problem_file, plan_path, val_path) -> None:
    """
    Check if the plan is valid using VAL validator
    """
    plan_validation_path = plan_path.replace(".txt", "_validation.txt")

    cmd = [f"{val_path}/validate", "-v", domain_file, problem_file, plan_path]
    subprocess.run(cmd, timeout=300, stdout=open(plan_validation_path, "w"), stderr=subprocess.DEVNULL)

    # cmd = f"{VAL_PATH}/validate -v {domain_file} {problem_file} {plan_path} 2>&1 | tee {plan_validation_path}"
    # response = os.popen(cmd).read()

    return plan_validation_path

def run_fd_planner(domain_file: str, problem_file: str, planner_dir: str) -> tuple[str, int]:
    """Run the FD planner and return the plan and its length."""
    cmd = [f"{planner_dir}/fast-downward.py", domain_file, problem_file, "--search", "astar(lmcut())",]
    subprocess.run(cmd, timeout=300, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    plan = find_and_read_plan("sas_plan", planner_dir)
    if plan is None:
        print(f"No plan found for instance: {problem_file}")
        return "No plan found within time limit.", 0

    return "\n".join(plan), len(plan)

def run_symk_planner(domain_file: str, problem_file: str, planner_dir: str, top_k: int = 5) -> list[tuple[str, int]]:
    """Run the symk planner and return the top-k plans and their lengths."""
    cmd = [f"{planner_dir}/fast-downward.py", domain_file, problem_file, "--search", f"symk_bd(plan_selection=top_k(num_plans={top_k}))",]
    subprocess.run(cmd, timeout=300, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    plans = []
    for i in range(1, top_k + 1):
        plan = find_and_read_plan(f"sas_plan.{i}", planner_dir)
        if plan is None:
            print(f"No plan {i} found for instance: {problem_file}")
            plans.append(("No plan found within time limit.", 0))
        else:
            plans.append(("\n".join(plan), len(plan)))

    print(f"Found {len(plans)} plans for instance: {problem_file}")
    return plans

def find_and_read_plan(plan_file: str, planner_dir: str) -> list[str] | None:
    """Locate a plan file in cwd or planner_dir, read it, remove it, and return its lines."""
    for path in [plan_file, os.path.join(planner_dir, plan_file)]:
        if os.path.exists(path):
            with open(path) as f:
                lines = [line.rstrip() for line in f][:-1]  # strip trailing cost comment
            os.remove(path)
            return lines
    return None

def resolve_paths(args) -> dict[str, str]:
    project_dir = os.path.join(os.getcwd()) # , os.pardir, os.pardir
    is_IPC = args.is_IPC.lower() in ['true', '1', 't', 'y', 'yes']

    if is_IPC:
        domain_path = "pddl-instances/ipc-{}/domains/{}".format(*args.domain.split("."))
    else:
        domain_path = f"domains/{args.domain}"

    return {
        "domain_file":  os.path.join(project_dir, domain_path, "domain.pddl"),
        "problem_dir":  os.path.join(project_dir, domain_path, "instances"),
        "planners_dir": os.path.join(project_dir, os.pardir, "planners"),
        "output_dir":   os.path.join(project_dir, "results", "planner_outputs", args.domain),
    }

def save_plans(plans: list[tuple[str, int]], output_path_base: str) -> list[str]:
    """Write each plan variant to its own file and return the list of paths."""
    paths = []
    for i, (readable_plan, _) in enumerate(plans, start=1):
        path = output_path_base.replace(".txt", f"_plan{i}.txt")
        with open(path, "w") as f:
            f.write(readable_plan)
        print(f"Saved plan {i} to {path}")
        paths.append(path)
    return paths

def save_state_simulation(states: list, output_path: str) -> None:
    with open(output_path, "w") as f:
        f.write("Initial state:\n")
        f.write(" ".join(states[0]) + "\n")
        for i, state in enumerate(states[1:], start=1):
            f.write(f"State after action {i}:\n")
            f.write(" ".join(state) + "\n")
    print(f"Saved state simulation to {output_path}")

def process_problem(problem_file: str, domain_file: str, planner_dir: str, output_dir: str, top_k: int = 5) -> None:
    problem = os.path.basename(problem_file)
    output_path_base = os.path.join(output_dir, f"{problem}.txt")

    plans = run_symk_planner(domain_file, problem_file, f"{planner_dir}/symk", top_k=top_k)
    plan_paths = save_plans(plans, output_path_base)

    for plan_path, (_, plan_length) in zip(plan_paths, plans):
        VAL_PATH = f"{planner_dir}/VAL"
        plan_validation_path = check_plan_validity(domain_file, problem_file, plan_path, VAL_PATH)
        print(f"Saved plan validation to {plan_validation_path}")

        states = simulate_states(problem_path=problem_file, plan_validation_path=plan_validation_path, plan_size=plan_length)
        # print(f"Simulated states: {states}")

        sim_path = plan_path.replace(".txt", "_state_simulation.txt")
        save_state_simulation(states, sim_path)

def run_pipeline(args, max_instances: int = 10) -> None:
    paths = resolve_paths(args)
    os.makedirs(paths["output_dir"], exist_ok=True)

    for i in range(1, max_instances):
        problem_file = os.path.join(paths["problem_dir"], f"instance-{i}.pddl")
        if not os.path.exists(problem_file):
            print(f"No problem file found at {problem_file}, stopping.")
            break
        process_problem(problem_file, paths["domain_file"], paths["planners_dir"], paths["output_dir"])


def parse_args():
    parser = ArgumentParser(description="Run the FD planner on a list of PDDL problems and log the results")
    # parser.add_argument("--planner_dir", type=str, default=, help="Directory containing the FD planner executable from project directory")
    parser.add_argument("--domain", type=str, default="2000.logistics-strips-typed", help="Name of the PDDL domain directory. If IPC, use the format <ipc-year>.<domain-name> (e.g., '2000.blocks-strips-typed').")
    parser.add_argument("--is_IPC", type=str, default="True", help="Whether the domain is from the IPC (International Planning Competition) dataset, which has a specific directory structure")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run_pipeline(args)