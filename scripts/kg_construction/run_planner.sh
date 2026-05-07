#!/bin/bash

# To run from current directory
PYTHON_SCRIPT="RunFDPlanner.py"

IPC_DOMAINS=(
    "2000.blocks-strips-typed" # ALL (about 400 triples, 60 entities, 5 classes)
    "2000.elevator-strips-simple-typed" # ALL (about 400 triples, 60 entities, 4 classes)
#    "2000.freecell-strips-typed" # parsing issue with UP
    "2000.logistics-strips-typed" # only in REG and FULL (about 830 triples, 130 entities, 11 classes)
    "2002.depots-strips-automatic" # ALL (about 800 triples, 120 entities, 9 classes)
    "2002.driverlog-strips-automatic" # only in REG and FULL (about 1000 triples, 160 entities, 4 classes)
    "2002.rovers-strips-automatic" # only in REG and FULL (about 1600 triples, 140 entities, 12 classes)
    "2002.satellite-strips-automatic" # ALL (about 700 triples, 110 entities, 7 classes)
#    "2002.zenotravel-strips-automatic" # parsing issue with UP, maybe solvable with a hack
#    "2004.airport-nontemporal-strips" # TODO fix has multiple domains
#    "2004.pipesworld-tankage-nontemporal-strips" # only in FULL (about 4000 triples, 600 entities, 13 classes)
#    "2004.promela-dining-philosophers-strips" # TODO fix has multiple domains
)

OTHER_DOMAINS=(
#    "counters" # parsing issue with UP
#    "office-robot" # check temporal
#    "rapid" # only in FULL (about 1700 triples, 170 entities, 12 classes)
)

DOMAINS_W_ISSUES=()

TOTAL=$(( ${#IPC_DOMAINS[@]} + ${#OTHER_DOMAINS[@]}))
COUNT=0

for domain in "${IPC_DOMAINS[@]}"; do
        COUNT=$(( COUNT + 1 ))
        echo "------------------------------------------------------------"
        echo "Run $COUNT / $TOTAL"
        echo "  --domain $domain"
        echo "  --is_IPC True"
        echo "------------------------------------------------------------"

        python "$PYTHON_SCRIPT" \
            --domain "$domain" \
            --is_IPC "True"

        if [ $? -ne 0 ]; then
            echo "WARNING: Run $COUNT failed — skipping to next combination"
            DOMAINS_W_ISSUES+="$domain"
        fi
done

echo "Completed $COUNT / $TOTAL combinations"

for domain in "${OTHER_DOMAINS[@]}"; do
        COUNT=$(( COUNT + 1 ))
        echo "------------------------------------------------------------"
        echo "Run $COUNT / $TOTAL"
        echo "  --domain $domain"
        echo "  --is_IPC False"
        echo "------------------------------------------------------------"

        python "$PYTHON_SCRIPT" \
            --domain "$domain" \
            --is_IPC "False"

        if [ $? -ne 0 ]; then
            echo "WARNING: Run $COUNT failed — skipping to next combination"
            DOMAINS_W_ISSUES+="$domain"
        fi
done

echo "Completed $COUNT / $TOTAL combinations"
echo "Domains with issues: $DOMAINS_W_ISSUES"