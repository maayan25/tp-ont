# Author: Ma'ayan Armony <maayan.armony@kcl.ac.uk>
# Validate the ontology using OOPS! and Hermit reasoner

import os
from owlready2 import get_ontology, sync_reasoner, Nothing

class OntologyValidation:
    def __init__(self, ontology_file):
        self.ontology_file = ontology_file
        self.ontology = self.load_ontology()

    # TODO validate with OOPS!: https://oops.linkeddata.es/

    def load_ontology(self):
        onto = get_ontology(self.ontology_file).load()
        print(f"Loaded ontology from {self.ontology_file}")
        return onto

    def validate_with_hermit(self) -> bool:
        """
        Validate the ontology using HermiT.
        """
        with self.ontology:
            try:
                sync_reasoner(infer_property_values=True)
            except Exception as e:
                print(f"Ontology is inconsistent: {e}")
                return False
            print("Ontology is consistent")

            class_hierarchy = {}
            for cls in self.ontology.classes():
                parents = [p.name for p in cls.is_a if hasattr(p, "name")]
                if parents:
                    class_hierarchy[cls.name] = parents
                    print(f"{cls.name} subClassOf {parents}")
                else:
                    class_hierarchy[cls.name] = []
                    print(f"{cls.name} has no superclasses")

            print(f"Class hierarchy: {class_hierarchy}")
            return True

    def get_ontology_details(self):
        details = {}
        # Unsatisfiable classes (disjointness violations etc.)
        unsat = [cls for cls in self.ontology.classes() if cls.equivalent_to == [Nothing]]
        print(f"Unsatisfiable classes: {len(unsat)} \n")
        details["unsatisfiable_classes"] = [cls.name for cls in unsat]
        for cls in unsat:
            print(f"{cls.name}")

        # Object properties with no domain and/or range declared
        print(f"\nObject properties with no domain or range: \n")
        no_rng_dmn = []
        for prop in self.ontology.object_properties():
            if not prop.domain:
                print(f"{prop.name} has no domain;")
                no_rng_dmn.append((prop.name, "domain"))
            if not prop.range:
                print(f"{prop.name} has no range;")
                no_rng_dmn.append((prop.name, "range"))
        details["properties_missing_domain_or_range"] = no_rng_dmn

        # Inferred subclass hierarchy
        print("\nInferred hierarchy:")
        implicit_hierarchy = {}
        for cls in self.ontology.classes():
            inferred_parents = cls.ancestors() - {cls}
            declared_parents = set(cls.is_a)
            new_inferences = inferred_parents - declared_parents
            if new_inferences:
                implicit_hierarchy[cls.name] = new_inferences
                print(f"Inferred parents for class {cls.name}: {[p.name for p in new_inferences if hasattr(p, 'name')]} \n")
        details["inferred_parents"] = implicit_hierarchy

        return details

    def save_details_for_ontology(self, details, output_file):
        with open(output_file, "w") as f:
            f.write(f"Unsatisfiable classes: {len(details['unsatisfiable_classes'])}\n")
            for cls in details["unsatisfiable_classes"]:
                f.write(f"{cls}\n")
            f.write("\nObject properties with no domain or range:\n")
            for prop, missing in details["properties_missing_domain_or_range"]:
                f.write(f"{prop} missing {missing}\n")
            f.write("\nInferred parents:\n")
            for cls, parents in details["inferred_parents"].items():
                parent_names = [p.name for p in parents if hasattr(p, "name")]
                f.write(f"{cls} inferred parents: {parent_names}\n")


if __name__ == "__main__":
    project_dir = os.path.join(os.getcwd(), os.pardir, os.pardir)
    parent_dir = os.path.join(project_dir, os.pardir)

    ontology_file = os.path.join(project_dir, "ontologies/planning/ours/tp-ont.owl")
    validator = OntologyValidation(ontology_file)
    results_dir = os.path.join(project_dir, "results", "ontology_validation")
    os.makedirs(results_dir, exist_ok=True)

    if validator.validate_with_hermit():
        details = validator.get_ontology_details()
        output_file = os.path.join(results_dir, "defaults_ontology_details.txt")
        validator.save_details_for_ontology(details, output_file)
    else:
        print("Ontology validation failed. See above for details.")
        output_file = os.path.join(results_dir, "defaults_ontology_details.txt")
        with open(output_file, "w") as f:
            f.write("Ontology validation failed. See above for details.\n")