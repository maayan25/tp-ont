import csv
import os
import xml.etree.ElementTree as ET
import datetime
from pathlib import Path

def extract_matchings_to_csv(results_dir: str, output_csv: str):
    """
    Extract all matchings from XML files into a single CSV for inspection.
    """
    results_dir = Path(results_dir)
    rows = []

    print(f"Extracting matchings from {results_dir}")
    for xml_file in results_dir.rglob("*.xml"):
        # Check that it's not in the analysis folder to avoid processing already extracted CSVs
        if "analysis" in xml_file.parts:
            continue
        print(f"Processing {xml_file}")
        parts = xml_file.relative_to(results_dir).parts
        if len(parts) != 6:
            # print(f"Warning: {xml_file} has {len(parts)} parts, skipping..")
            # check if it's the llm folder, which has a different structure
            # if len(parts) == 4 and parts[2] == "llm":
            #     print(f"LLM file needs restructuring, skipping for now: {xml_file}")
            # else:
            #     print(f"Warning: {xml_file} has unexpected structure with {len(parts)} parts, skipping..")
            continue
        src_onto, tgt_onto, alignment_method, aligner, encoder, _ = parts

        if alignment_method == "llm":
            print(f"Parsing LLM file: {xml_file}")

        tree = ET.parse(xml_file)
        root = tree.getroot()

        AL = "http://knowledgeweb.semanticweb.org/heterogeneity/alignment"

        for cell in root.iter(f"{{{AL}}}Cell"):
            entity1 = cell.find(f"{{{AL}}}entity1")
            entity2 = cell.find(f"{{{AL}}}entity2")
            relation = cell.find(f"{{{AL}}}relation")
            measure = cell.find(f"{{{AL}}}measure")
            if alignment_method == "llm":
                print(f"Found matching {entity1} {entity2} {relation} {measure}")

            if None in (entity1, entity2, relation, measure):
                if alignment_method == "llm":
                    if None in (entity1, entity2, relation):
                        continue
                    else:
                        print(f"Warning: missing measure for matching {entity1} {entity2} {relation} in file {xml_file}, setting to 0.5")
                        measure = ET.Element("measure")
                        measure.text = "1.0" # KGE also sets to 1.0

                else:
                    continue

            RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
            rows.append({
                "src_onto":         src_onto,
                "tgt_onto":         tgt_onto,
                "alignment_method": alignment_method,
                "aligner":          aligner,
                "encoder":          encoder,
                "entity1":          entity1.get(f"{{{RDF}}}resource", ""),
                "entity1_short":    entity1.get(f"{{{RDF}}}resource", "").split("#")[-1],
                "entity2":          entity2.get(f"{{{RDF}}}resource", ""),
                "entity2_short":    entity2.get(f"{{{RDF}}}resource", "").split("#")[-1],
                "relation":         relation.text.strip() if relation.text else "=",
                "measure":          float(measure.text.strip()) if measure.text else 0.0,
            })
        # i = i + 1

    if not rows:
        print("No matchings found.")
        return

    rows.sort(key=lambda x: (-x["measure"]))

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Extracted {len(rows)} matchings from {len(list(results_dir.rglob('matchings.xml')))} files \n"
          f"Saved to {output_csv}")

if __name__ == "__main__":
    results_dir = os.path.join(os.getcwd(), os.pardir, os.pardir, "results", "ontology_alignment")
    output_dir = os.path.join(results_dir, "analysis")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.datetime.now()
    timestamp = timestamp.strftime("%Y%m%d_%H%M%S")
    extract_matchings_to_csv(
        results_dir=results_dir,
        output_csv=f"{output_dir}/matchings_inspection_{timestamp}.csv"
    )