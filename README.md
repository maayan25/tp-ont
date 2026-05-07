# tp-ont
The Task-Planning Ontology

### Setup Instructions
Create and activate a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install required packages:
```bash
python3 -m pip install -r requirements.txt
```

#### For KG Construction
sudo apt install libxcb-cursor-dev

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

### Running instructions
#### KG Construction
To create the KG, you can use the [bash script](scripts/kg_construction/create_kg.sh) to run multiple domains at once, or the Python [PDDLKGConstructor.py](scripts/kg_construction/PDDLKGConstructor.py) directly.

#### Ontology Construction
Once you have created the KG, you can use [extract_tbox_from_kg.py](scripts/kg_construction/extract_tbox_from_kg.py) to extract the ontology from the knowledge graph.

#### Adding plans
Sample plan instances can be found in [here](results/planner_outputs). In order to generate more plans and simulations, please follow the steps below.

###### Prerequisites
To create plans and state simulations, you need to install the [FastDownward planner](https://github.com/aibasel/downward/blob/main/BUILD.md) and [VAL](https://github.com/KCL-Planning/VAL).

###### Running instructions
If you would like to generate new plans, or plan simulations, you can use the [RunFDPlanner.py](scripts/kg_construction/RunFDPlanner.py) file to run the planner and state simulator, or the [run_planner.sh](scripts/kg_construction/run_planner.sh) to run multiple domains in a row.
