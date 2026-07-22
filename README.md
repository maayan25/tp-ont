# TP-ONT: A Task-Planning Ontology

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-blue.svg)](https://creativecommons.org/licenses/by/4.0/)
[![DOI](https://zenodo.org/badge/1228188718.svg)](https://doi.org/10.5281/zenodo.21495382)
[![HuggingFace Dataset](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Dataset-yellow)](https://huggingface.co/datasets/ma25/tp-ont)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)


**TP-ONT** is an ontology designed for task planning and knowledge representation. This repository provides:
1. The current ontology definition
2. Tools for Knowledge Graph (KG) and ontology construction from PDDL 
3. Scripts to align the ontology with general knowledge ontologies
4. Scripts to run a planner on PDDL files to generate plans to be added to the KG.

## Overview

* [📖 Quick Start & Ontology Files](#quick-start--ontology-files)
* [🛠️ Installation & Setup](#installation--setup)
* [🚀 Running the Pipeline](#running-the-pipeline)
* [🧭 Plan Generation & Simulation](#plan-generation--simulation)
* [📄 License](#license)

[//]: # (* [Citing TP-ONT]&#40;#citing-tp-ont&#41;)

## Quick Start & Ontology Files

If you just want to view or query the ontology:
* **Ontology File:** Find the TBox / ontology definitions in [`tp-ont.owl`](./tp-ont.owl) or [`ontologies/`](./ontologies/) for both the dynamic and static ontologies.
* **KG File:** Find the raw ABox / knowledge graph definitions in [`knowledge_graphs`](./knowledge_graphs/) for the raw and materialised knowledge graphs.
* **Sample SPARQL Queries:** the [`examples`](./sparql/examples/) folder contains sample SPARQL queries to explore the ontology and knowledge graph. They can be run with the [`run_queries.py`](./sparql/run_queries.py) script and a Jena Fuseki server.
* **Compatibility:** Compatible with Protégé, `rdflib`, or any standard OWL/RDF reasoner.

## Installation & Setup
> The framework was tested on Ubuntu 24.04 using Python 3.12.3.

Create and activate a virtual environment and install the required packages:
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

#### For KG Construction
```bash
sudo apt update && sudo apt install libxcb-cursor-dev
```

#### For OntoAligner
Download nltk required data:
```bash
python3 -m pip install nltk
```

In Python:
```python
import nltk
nltk.download('averaged_perceptron_tagger_eng')
```

## Running the Pipeline
### KG Construction
1. Single domain KG construction: You can run the [PDDLKGConstructor.py](scripts/kg_construction/PDDLKGConstructor.py) script to create a knowledge graph for a single domain. The script takes the path to the PDDL domain and problem files as input, and outputs the corresponding knowledge graph in RDF format.
```bash
cd scripts/kg_construction
python3 PDDLKGConstructor.py --domain <path_to_domain_file> --problem <path_to_problem_file>
```
2. Batch KG construction: You can use [create_kg.sh](scripts/kg_construction/create_kg.sh) to run multiple domains at once. The script takes a list of PDDL domain names as input, and outputs the corresponding knowledge graphs in RDF format. It uses the instance-1 problem file as the default problem file for each domain as the input, which can be changed in the script if needed. The output knowledge graphs are saved in the `knowledge_graphs` directory.
```bash
cd scripts/kg_construction
./create_kg.sh
```

### Ontology Construction
Once you have created the KG, you can extraact the ontology schema (TBox) with [extract_tbox_from_kg.py](scripts/kg_construction/extract_tbox_from_kg.py):
```bash
cd scripts/kg_construction
python3 extract_tbox_from_kg.py
```

### Plan Generation & Simulation
> Sample plan instances can be found in [results/planner_outputs](results/planner_outputs).

##### Prerequisites
To generate new plans and state simulations, make sure you have installed the following:
- [FastDownward planner](https://github.com/aibasel/downward/blob/main/BUILD.md) 
- [VAL](https://github.com/KCL-Planning/VAL)

##### Running instructions
1. Run the planner on a **single problem file**: You can run the [RunFDPlanner.py](scripts/kg_construction/RunFDPlanner.py) script to generate a plan for a single problem file. The script takes the path to the PDDL domain and problem files as input, and outputs the corresponding plan in text format.
2. Run the planner on **multiple problem files**: You can use [run_planner.sh](scripts/kg_construction/run_planner.sh) to run the planner on multiple problem files at once.
Both scripts will output the generated plans and a corresponding state simulation of the plan execution. The files are saved in the `results/planner_outputs` directory.


## License
This project is licensed under the [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).

[//]: # (## Citing TP-ONT)
[//]: # (If you use TP-ONT in your research, please cite the following paper:)
