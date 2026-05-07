#!/bin/bash

PYTHON_SCRIPT="run_ontoaligner.py"

SOURCE_ONTOS=(
    "ontologies/planning/ours/pddl-kg-ontology.owl"
#    "ontologies/planning/AI-Planning-Ontology/plan-ontology-rdf.owl"
#    "ontologies/robotics/knowrob/knowrob.owl"
)

TARGET_ONTOS=(
    "ontologies/general_knowledge/conceptnet-assertions-5.7.0.csv/conceptnet_tbox.owl"
    "ontologies/general_knowledge/dbpedia/dbpedia_tbox.owl"
    "ontologies/general_knowledge/DOLCE/DOLCEbasic.owl.rdf"
    "ontologies/general_knowledge/opencyc-latest/owl-export-unversioned.owl"
    "ontologies/general_knowledge/schema.org/schemaorg.owl"
    "ontologies/robotics/knowrob/knowrob.owl"
    "ontologies/robotics/ocra/ocra.owl"
    "ontologies/robotics/SOMA/SOMA.owl.rdf"
)

CONFIGS=(
#    "fuzzy"
    "llm"
    "kge"
    "rag"
    "propmatch"
)

TOTAL=$(( ${#SOURCE_ONTOS[@]} * ${#TARGET_ONTOS[@]} * ${#CONFIGS[@]} ))
COUNT=0

for pddl_onto in "${SOURCE_ONTOS[@]}"; do
    for knowledge_onto in "${TARGET_ONTOS[@]}"; do
        for config in "${CONFIGS[@]}"; do
            COUNT=$(( COUNT + 1 ))
            echo "------------------------------------------------------------"
            echo "Run $COUNT / $TOTAL"
            echo "  --pddl_onto      $pddl_onto"
            echo "  --knowledge_onto $knowledge_onto"
            echo "  --config         $config"
            echo "------------------------------------------------------------"

            python "$PYTHON_SCRIPT" \
                --pddl_onto      "$pddl_onto" \
                --knowledge_onto "$knowledge_onto" \
                --config         "$config"

            if [ $? -ne 0 ]; then
                echo "WARNING: Run $COUNT failed — skipping to next combination"
            fi
        done
    done
done

echo "Completed $COUNT / $TOTAL combinations"
