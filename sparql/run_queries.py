import json
import os

from SPARQLWrapper import SPARQLWrapper, JSON
import owlrl
from rdflib import Graph

sparql = SPARQLWrapper("http://localhost:3030/kg/sparql")
sparql.setReturnFormat(JSON)

def materialise_kg(kg_path):
    g = Graph()
    g.parse(kg_path)
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
    materialised_path = kg_path.replace(".owl", "_materialised.owl")
    g.serialize(materialised_path, format="xml")

def run_query(query):
    # print(f"Running query:\n{query}")
    sparql.setQuery(query)
    results = sparql.query().convert()
    return results

def get_query_from_file(file_path):
    with open(file_path, "r") as f:
        query = f.read()
    return query

def get_example_queries():
    query_dir = f"{os.getcwd()}/examples"
    queries = {}
    for file_name in os.listdir(query_dir):
        if file_name.endswith(".sparql"):
            query_name = file_name[:-7]  # Remove .sparql
            query_path = os.path.join(query_dir, file_name)
            queries[query_name] = get_query_from_file(query_path)
    return queries

def save_results_to_file(results, file_path):
    with open(file_path, "w") as f:
        json.dump(results, f, indent=4)
    print(f"Saved results to {file_path}")

def main():
    queries = get_example_queries()
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)

    results_dict = {}
    for name, query in queries.items():
        print(f"Running query '{name}'...")
        results = run_query(query)
        # for r in results["results"]["bindings"]:
        #     print(r["action"]["value"])
        print(f"Found {len(results['results']['bindings'])} results")
        result_items = results["results"]["bindings"]
        results_dict[name] = {}
        for i, item in enumerate(result_items):
            results_dict[name][i] = item
            # print(item)

    save_results_to_file(results_dict, os.path.join(results_dir, "results.json"))

def test_query():
    sparql = SPARQLWrapper("http://localhost:3030/kg/sparql")
    sparql.setReturnFormat(JSON)

    sparql.setQuery("""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX planning-ontology: <https://purl.org/ai4s/ontology/planning#>
    PREFIX tp-ont: <https://w3id.org/tp-ont/ontology#>
    """)
    results = sparql.query().convert()
    for r in results["results"]["bindings"]:
        print(r)


if __name__ == "__main__":
    # main()
    root_dir = os.path.join(os.getcwd(), os.pardir)
    # materialise_kg(f"{root_dir}/knowledge_graphs/tp-kg.owl")
    test_query()
