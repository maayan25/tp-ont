import argparse
import os
from pathlib import Path

import pandas as pd
from itertools import combinations
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.patches as mpatches
from rdflib import Graph, OWL, RDF

from dataclasses import dataclass, field
from scipy.stats import fisher_exact

@dataclass
class MethodConfig:
    """
    Central config for method metadata.
    Pass this to all analysis functions to ensure consistent treatment.
    """
    all_methods:        list[str]
    no_confidence:      list[str]  # methods that never produce a confidence score

    @property
    def confidence_methods(self) -> list[str]:
        return [m for m in self.all_methods if m not in self.no_confidence]

def _fdr_correction_bh(p_values: np.ndarray) -> np.ndarray:
    """
    Benjamini-Hochberg FDR correction.
    Returns corrected p-values (same order as input).
    """
    n    = len(p_values)
    order     = np.argsort(p_values)
    ranked_ps = p_values[order]

    # BH adjusted p-values
    adjusted = np.minimum(1.0, ranked_ps * n / (np.arange(1, n + 1)))

    # Enforce monotonicity (cumulative minimum from the right)
    for i in range(n - 2, -1, -1):
        adjusted[i] = min(adjusted[i], adjusted[i + 1])

    # Return in original order
    result        = np.empty(n)
    result[order] = adjusted
    return result

def get_ontology_paths() -> dict[str, str]:
    """
    Return a dict mapping ontology short names to their file paths.
    """
    return {
        "conceptnet": "ontologies/general_knowledge/conceptnet-assertions-5.7.0.csv/conceptnet_tbox.owl",
        "dbpedia": "ontologies/general_knowledge/dbpedia/dbpedia_tbox.owl",
        "DOLCEbasic": "ontologies/general_knowledge/DOLCE/DOLCEbasic.owl.rdf",
        # "opencyc": "ontologies/general_knowledge/opencyc-latest/owl-export-unversioned.owl",
        "schemaorg": "ontologies/general_knowledge/schema.org/schemaorg.owl",
        "knowrob": "ontologies/robotics/knowrob/knowrob.owl",
        "ocra": "ontologies/robotics/ocra/ocra.owl",
        "SOMA": "ontologies/robotics/SOMA/SOMA.owl.rdf",
        "pddl-kg-ontology": "ontologies/planning/ours/pddl-kg-ontology.owl",
        "plan-ontology-rdf": "ontologies/planning/AI-Planning-Ontology/plan-ontology-rdf.owl",
        "tp-ont": "ontologies/planning/ours/tp-ont.owl",
    }

class AlignmentStats:
        """
        Class to compute various statistics and agreement metrics from the ontology alignment matchings CSV.
        """
        def __init__(self, csv_path: str):
            self.method_config = MethodConfig(
                all_methods=["rag", "llm", "kge", "propmatch"],
                no_confidence=["rag", "llm"],
            )
            self.csv_path = csv_path
            self.df = pd.read_csv(csv_path)
            # Remove if src_onto is the same as tgt_onto (self-alignment)
            self.df = self.df[self.df["src_onto"] != self.df["tgt_onto"]]

            self.df["method"] = self.df["alignment_method"] + "/" + self.df["aligner"] + "/" + self.df["encoder"]
            self.df["pair"] = self.df["entity1_short"] + " → " + self.df["entity2_short"]

            self.robotics_ontos = ["knowrob", "ocra", "SOMA"]
            self.general_ontos = ["conceptnet", "dbpedia", "DOLCEbasic", "opencyc", "schemaorg"]
            self.ontology_paths = get_ontology_paths()

        def per_method_stats(self) -> pd.DataFrame:
            """Per-method summary statistics for ontology alignment results, grouped by source and target ontology pairs."""
            
            df = self.df.copy()
            method_config: MethodConfig = self.method_config

            stats = (
                df.groupby(["src_onto", "tgt_onto", "method"])
                .agg(
                    total=("measure", "count"),
                    # mean_conf only meaningful for confidence methods — NaN otherwise
                    mean_conf=("measure", lambda x: (
                        x.mean() if x.name in method_config.confidence_methods else float("nan")
                    )),
                    high_conf=("measure", lambda x: (
                        (x > 0.8).sum() if x.name in method_config.confidence_methods else 0
                    )),
                    med_conf=("measure", lambda x: (
                        ((x > 0.5) & (x <= 0.8)).sum() if x.name in method_config.confidence_methods else 0
                    )),
                    low_conf=("measure", lambda x: (
                        (x <= 0.5).sum() if x.name in method_config.confidence_methods else 0
                    )),
                    unique_src=("entity1_short", "nunique"),
                    unique_tgt=("entity2_short", "nunique"),
                )
                .reset_index()
                .sort_values(["src_onto", "tgt_onto", "mean_conf"], ascending=[True, True, False])
            )

            # Tag which methods have confidence scores for downstream use
            stats["has_confidence"] = stats["method"].isin(method_config.confidence_methods)
            return stats


        def compute_consensus(self, min_votes: int = 2, conf_threshold: float = 0.0):
            """
            Compute cross-method agreement from the matchings CSV.
            Groups by (src_onto, tgt_onto, entity1_short, entity2_short) and
            counts how many distinct methods agreed on each pair.
            """
            df = self.df.copy()

            # Group by ontology pair + entity pair
            group_cols = ["src_onto", "tgt_onto", "entity1_short", "entity2_short", "entity1", "entity2"]

            consensus = (
                df.groupby(group_cols)
                .agg(
                    votes        = ("method",  "nunique"),   # how many distinct methods agreed
                    mean_conf    = ("measure", "mean"),
                    max_conf     = ("measure", "max"),
                    min_conf     = ("measure", "min"),
                    methods      = ("method",  lambda x: " | ".join(sorted(x.unique()))),
                )
                .reset_index()
                .query("votes >= @min_votes and mean_conf >= @conf_threshold")
                .sort_values(["votes", "mean_conf"], ascending=[False, False])
            )

            return consensus


        def get_ontology_sizes(self, ontology_paths: dict[str, str]) -> dict[str, dict]:
            """
            Get class and property counts from ontology files.
            :param ontology_paths: dict mapping short name to file path
            :return: dict mapping short name to {"classes": int, "properties": int}
            """
            sizes = {}
            for name, path in ontology_paths.items():
                path = os.path.join(os.getcwd(), os.pardir, os.pardir, path)
                g = Graph()
                g.parse(path)
                classes = len(list(g.subjects(RDF.type, OWL.Class)))
                obj_props = len(list(g.subjects(RDF.type, OWL.ObjectProperty)))
                data_props = len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))
                sizes[name] = {
                    "classes": classes,
                    "properties": obj_props + data_props,
                }
            return sizes

        def compute_best_per_src(self, group_df: pd.DataFrame) -> set[tuple]:
            """Return set of (src_onto, method) tuples that are best mean_conf per src."""
            best = set()
            for src, src_df in group_df.groupby("src_onto"):
                if src_df.empty:
                    continue
                if src_df["mean_conf"].isna().all():
                    idx = src_df["total"].idxmax() # fallback to total matchings if no confidence scores
                    print(f"Warning: no confidence scores for source ontology {src}, using total matchings to determine best method")
                else:
                    idx = src_df["mean_conf"].idxmax()
                row = src_df.loc[idx]
                best.add((row["src_onto"], row["tgt_onto"], row["method"]))
            return best

        def per_method_stats_to_latex(self, stats_df: pd.DataFrame, robotics_ontos: list[str], general_ontos: list[str], ontology_sizes: dict[str, dict] | None = None, output_path: str | None = None) -> tuple[str, str]:
            """
            Produce two LaTeX tables from per_method_stats() output, split by target ontology group.
            One row per src-tgt pair as a header row, methods indented below.
            Best result per source ontology is bolded.
            :param stats_df: output of per_method_stats()
            :param robotics_ontos: list of target ontology names in the robotics group
            :param general_ontos: list of target ontology names in the general knowledge group
            :param ontology_sizes: optional dict from get_ontology_sizes()
            :param output_path: if given, write .tex file to this path (with _robotics and _general suffixes)
            :return: tuple of (robotics_latex, general_latex)
            """

            robotics_df = stats_df[stats_df["tgt_onto"].isin(robotics_ontos)]
            general_df = stats_df[stats_df["tgt_onto"].isin(general_ontos)]

            robotics_latex = self.build_latex_table(
                robotics_df,
                caption="Alignment results against robotics ontologies.",
                label="tab:alignment_robotics",
                ontology_sizes=ontology_sizes
            )
            general_latex = self.build_latex_table(
                general_df,
                caption="Alignment results against general knowledge ontologies.",
                label="tab:alignment_general",
                ontology_sizes=ontology_sizes
            )

            if output_path:
                output_path_robotics = output_path.replace(".tex", "_robotics.tex")
                output_path_general = output_path.replace(".tex", "_general.tex")
                Path(output_path_robotics).write_text(robotics_latex)
                Path(output_path_general).write_text(general_latex)

            return robotics_latex, general_latex


        def plot_alignment_diagnostics(self, stats_df: pd.DataFrame, robotics_ontos: list[str], general_ontos: list[str], ontology_sizes: dict[str, dict] | None = None, normalise: str = "none", output_path: str | None = None,) -> None:
            """
            Three-subplot diagnostic figure:
              Top-left:  coverage heatmap for robotics target ontologies
              Top-right: coverage heatmap for general knowledge target ontologies
              Bottom:    confidence distribution per method across all pairs
            :param stats_df: output of per_method_stats()
            :param robotics_ontos: list of target ontology names in the robotics group
            :param general_ontos: list of target ontology names in the general knowledge group
            :param ontology_sizes: dict from get_ontology_sizes(), required if normalise != "none"
            :param normalise: "none" (raw counts), "src", or "union"
            :param output_path: if given, save figure here
            """
            assert normalise in ("none", "src", "union")
            if normalise != "none" and ontology_sizes is None:
                raise ValueError("ontology_sizes required when normalise != 'none'")

            methods = sorted(stats_df["method"].unique())

            title_map = {
                "none": "Coverage (N matchings)",
                "src": "Coverage (prop. of src classes)",
                "union": "Coverage (prop. of src∪tgt classes)",
            }

            robotics_df = stats_df[stats_df["tgt_onto"].isin(robotics_ontos)]
            general_df = stats_df[stats_df["tgt_onto"].isin(general_ontos)]

            heat_r, pairs_r = self.build_heat_matrix(robotics_df, stats_df, methods, ontology_sizes, normalise)
            heat_g, pairs_g = self.build_heat_matrix(general_df, stats_df, methods, ontology_sizes, normalise)

            # Shared colour scale across both heatmaps for comparability
            vmax = 1.0 if normalise != "none" else max(
                np.nanmax(heat_r) if heat_r.size else 0,
                np.nanmax(heat_g) if heat_g.size else 0,
            )

            n_top_rows = max(len(pairs_r), len(pairs_g), 3)
            fig_height = n_top_rows * 0.5 + 5
            fig, axes = plt.subplots(
                1, 2,
                figsize=(14, fig_height),
            )

            self.draw_heatmap(axes[0], heat_r, pairs_r,
                          f"Robotics targets — {title_map[normalise]}\nGrey = missing", vmax, methods, normalise)
            self.draw_heatmap(axes[1], heat_g, pairs_g,
                          f"General targets — {title_map[normalise]}\nGrey = missing", vmax, methods, normalise)


            plt.suptitle("Ontology alignment diagnostics", fontsize=12)
            plt.tight_layout()

            if output_path:
                plt.savefig(output_path, bbox_inches="tight", dpi=150, format="pdf")
            plt.show()

        def run_analysis(self):
            """
            Run the analysis methods to generate the relevant files
            :return:
            """
            print("\n=== Per-Method Statistics ===")
            stats = self.per_method_stats()
            print(stats.to_string(index=False))
            stats.to_csv(f"{output_dir}/stats_per_method.csv", index=False)

            print("\n=== Consensus Matchings (≥2 methods) ===")
            consensus = self.compute_consensus(min_votes=2, conf_threshold=0.5)
            print(consensus.to_string(index=False))
            consensus.to_csv(f"{output_dir}/stats_consensus.csv", index=False)

            return stats, consensus

        def create_diagnostic_plots(self, stats_df: pd.DataFrame):
            """
            Create latex tables and diagnostic plots for the paper
            :param stats_df: the output of per_method_stats() to use for the diagnostics
            :return:
            """
            # If ontology_sizes.txt already exists, read it instead of recomputing
            size_file = Path(f"{plots_dir}/ontology_sizes.txt")
            if size_file.exists():
                print(f"Reading ontology sizes from {size_file}")
                sizes = {}
                for line in size_file.read_text().splitlines()[1:]:
                    name, rest = line.split(":")
                    cls_part, prp_part = rest.split(",")
                    sizes[name.strip()] = {
                        "classes": int(cls_part.strip().split()[0]),
                        "properties": int(prp_part.strip().split()[0])
                    }
            else:
                sizes = self.get_ontology_sizes(self.ontology_paths)
                size_lines = ["Ontology sizes (classes/properties):"]
                for name, sz in sizes.items():
                    size_lines.append(f"{name}: {sz['classes']} classes, {sz['properties']} properties")
                size_text = "\n".join(size_lines)
                size_file.write_text(size_text)
                print(size_text)

            normalise = "union" # or "src" or "union"
            output_file = f"{plots_dir}/alignment_diagnostics_{normalise}.pdf" if normalise != "none" else f"{plots_dir}/alignment_diagnostics_raw.pdf"
            self.plot_alignment_diagnostics(stats_df, self.robotics_ontos, self.general_ontos,
                                            ontology_sizes=sizes, normalise=normalise, output_path=output_file)
            self.per_method_stats_to_latex(stats_df, self.robotics_ontos, self.general_ontos,
                                           ontology_sizes=sizes, output_path=f"{plots_dir}/per_method_stats.tex")

        def map_method_name_to_abbreviations(self, method_name: str) -> str:
            """
            Map verbose method names to shorter abbreviations for better readability in plots and tables.
            Example: "kge/ConvEAligner/GraphTripleEncoder" → "KGR/ConvE/GraphTriple"
            """
            mapping = {
                "MistralLLMBERTRetrieverRAG": "MistralSBERT",
                "ConceptParentRAG": "CPRAG",
            }
            for key, abbrev in mapping.items():
                method_name = method_name.replace(key, abbrev)
            method_name = method_name.replace("Aligner", "").replace("Encoder", "")
            method_name = method_name.replace("llm/Mistral-7B-v0.3/all-MiniLM-L6-v2", "LLM Mistral-7B")
            return method_name

        def map_ontology_name_to_abbreviation(self, ontology_name: str) -> str:
            """
            Map verbose ontology names to shorter abbreviations for better readability in plots and tables.
            Example: "pddl-kg-ontology" → "PDDL-KG"
            """
            mapping = {
                "conceptnet": "ConceptNet",
                "dbpedia": "DBpedia",
                "DOLCEbasic": "DOLCE",
                "opencyc": "OpenCyc",
                "schemaorg": "Schema.org",
                "knowrob": "KnowRob",
                "ocra": "OCRA",
                "SOMA": "SOMA",
                "pddl-kg-ontology": "PDDL-KG",
                "tp-ont": "TP-ONT",
                "plan-ontology-rdf": "PlanOnto",
            }
            return mapping.get(ontology_name, ontology_name)


        def build_latex_table(self, group_df: pd.DataFrame, caption: str, label: str, ontology_sizes) -> str:
            if group_df.empty:
                return f"% No data for group: {label}\n"

            best = self.compute_best_per_src(group_df)
            pairs = group_df[["src_onto", "tgt_onto"]].drop_duplicates()

            # Column spec
            col_spec = "l|l|"
            if ontology_sizes:
                col_spec += "l|l|"
            col_spec += "l|r|r|r|r|r"

            # Column count for \resizebox and \cmidrule
            n_cols = 2 + (2 if ontology_sizes else 0) + 6

            lines = []
            lines.append(r"\begin{table}[ht]")
            lines.append(r"\centering")
            lines.append(rf"\resizebox{{\textwidth}}{{!}}{{%")
            lines.append(f"\\begin{{tabular}}{{{col_spec}}}")
            lines.append(r"\toprule")

            header = "Source & Target"
            if ontology_sizes:
                header += " & Classes & Props"
            header += r" & Method & N & $\bar{c}$ & High & Med & Low \\"
            lines.append(header)
            lines.append(r"\midrule")

            for pair_idx, (_, pair) in enumerate(pairs.iterrows()):
                src, tgt = pair["src_onto"], pair["tgt_onto"]
                src_name = self.map_ontology_name_to_abbreviation(src)
                tgt_name = self.map_ontology_name_to_abbreviation(tgt)
                pair_rows = group_df[
                    (group_df["src_onto"] == src) & (group_df["tgt_onto"] == tgt)
                    ].sort_values("method")

                # Method sub-rows, indented
                for _, row in pair_rows.iterrows():
                    is_best = (src, tgt, row["method"]) in best

                    def fmt(val, is_float=False):
                        s = f"{val:.2f}" if is_float else str(int(val))
                        return f"\\textbf{{{s}}}" if is_best else s

                    method_name = self.map_method_name_to_abbreviations(row["method"])
                    method_cell = f"\\quad {method_name}"
                    if is_best:
                        method_cell = f"\\quad \\textbf{{{method_name}}}"

                    # If it's the first method row for this pair, show the src/tgt names and sizes, otherwise leave blank to visually group them together
                    if row.name == pair_rows.index[0]:
                        # Pair header row
                        pair_line = f"\\textit{{{src_name}}} & \\textit{{{tgt_name}}}"
                        if ontology_sizes:
                            src_sz = ontology_sizes.get(src, {})
                            tgt_sz = ontology_sizes.get(tgt, {})
                            pair_line += (
                                f" & {src_sz.get('classes', '?')} + {tgt_sz.get('classes', '?')}"
                                f" & {src_sz.get('properties', '?')} + {tgt_sz.get('properties', '?')}"
                            )
                        # pair_line += r" & & & & & & \\"
                        # lines.append(pair_line)
                        line = pair_line + r" & "  # start of method row
                    else:
                        line = f" & & "  # src, tgt blank — pair shown in header row
                        if ontology_sizes:
                            line += " & & "  # sizes blank too
                    line += (
                        f"{method_cell}"
                        f" & {fmt(row['total'])}"
                        f" & {fmt(row['mean_conf'], is_float=True)}"
                        f" & {fmt(row['high_conf'])}"
                        f" & {fmt(row['med_conf'])}"
                        f" & {fmt(row['low_conf'])} \\\\"
                    )
                    lines.append(line)

                # Midrule between pairs (not after last)
                if pair_idx < len(pairs) - 1:
                    lines.append(r"\midrule")

            lines.append(r"\bottomrule")
            lines.append(r"\end{tabular}%")
            lines.append(r"}")  # close resizebox
            lines.append(
                f"\\caption{{{caption} "
                r"N = total matchings, $\bar{c}$ = mean confidence. "
                r"High/Med/Low = matchings above 0.8, 0.5--0.8, and below 0.5. "
                r"\textbf{Bold} = best mean confidence per source ontology."
                r"Sizes shown as src/tgt counts.}"
            )
            lines.append(f"\\label{{{label}}}")
            lines.append(r"\end{table}")
            return "\n".join(lines)

        def build_heat_matrix(self, df: pd.DataFrame, stats_df, methods, ontology_sizes, normalise) -> tuple[np.ndarray, list[str]]:
            """Build heat matrix and pair labels for a group subset."""
            pairs = [
                f"{self.map_ontology_name_to_abbreviation(r.src_onto)}/{self.map_ontology_name_to_abbreviation(r.tgt_onto)}"
                for r in df[["src_onto", "tgt_onto"]].drop_duplicates().itertuples()
            ]
            pair_index = {p: i for i, p in enumerate(pairs)}
            meth_index = {m: i for i, m in enumerate(methods)}
            heat = np.full((len(pairs), len(methods)), np.nan)

            for _, row in df.iterrows():
                src_name = self.map_ontology_name_to_abbreviation(row.src_onto)
                tgt_name = self.map_ontology_name_to_abbreviation(row.tgt_onto)
                pair = f"{src_name}/{tgt_name}"
                r, c = pair_index[pair], meth_index[row.method]
                value = row.total

                if normalise == "src":
                    src_classes = ontology_sizes.get(row.src_onto, {}).get("classes", np.nan)
                    value = value / src_classes if src_classes else np.nan
                elif normalise == "union":
                    src_classes = ontology_sizes.get(row.src_onto, {}).get("classes", 0)
                    tgt_classes = ontology_sizes.get(row.tgt_onto, {}).get("classes", 0)
                    union = src_classes + tgt_classes
                    value = value / union if union else np.nan

                heat[r, c] = value

            return heat, pairs

        def draw_heatmap(self, ax, heat: np.ndarray, pairs: list[str], title: str, vmax, methods, normalise):
            method_names = [self.map_method_name_to_abbreviations(m) for m in methods]
            masked = np.ma.masked_invalid(heat)
            cmap = plt.cm.YlGn.copy()
            cmap.set_bad(color="#eeeeee")
            im = ax.imshow(masked, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)
            ax.set_xticks(range(len(methods)))
            ax.set_xticklabels(method_names, rotation=30, ha="right", fontsize=8)
            ax.set_yticks(range(len(pairs)))
            ax.set_yticklabels(pairs, fontsize=7)
            ax.set_title(title, fontsize=9)
            plt.colorbar(im, ax=ax, shrink=0.7,
                         label="proportion" if normalise != "none" else "count")

            for r in range(len(pairs)):
                for c in range(len(methods)):
                    val = heat[r, c]
                    if not np.isnan(val):
                        label = f"{val:.2f}" if normalise != "none" else str(int(val))
                        threshold = 0.7 if normalise != "none" else masked.max() * 0.7
                        ax.text(c, r, label, ha="center", va="center",
                                fontsize=6, color="white" if val > threshold else "black")

        def make_latex_summary_table(self, df: pd.DataFrame, agreement_df: pd.DataFrame, ontology_sizes: dict, sort_by: str = "Matchings", bold_best: bool = True,):
            """
            Create LaTeX table with Ontology (src), Target ontology, Matchings, Coverage, Agreement ratio
            """

            table_df = df.copy()

            def compute_coverage(row):
                src = row["src_onto"]
                total = row["total"]
                src_classes = ontology_sizes.get(src, {}).get("classes", 0)

                return total / src_classes if src_classes else float("nan")

            table_df["coverage"] = table_df.apply(compute_coverage, axis=1)

            # Count alignments with >1 votes per (src, tgt)
            agreement_counts = (
                agreement_df
                .groupby(["src_onto", "tgt_onto"])
                .size()
                .reset_index(name="agree_count")
            )

            # Merge into main table
            table_df = table_df.merge(
                agreement_counts,
                on=["src_onto", "tgt_onto"],
                how="left"
            )

            table_df["agree_count"] = table_df["agree_count"].fillna(0)

            # Compute ratio
            table_df["agreement"] = table_df["agree_count"] / table_df["total"]

            table_df["src_onto"] = table_df["src_onto"].apply(self.map_ontology_name_to_abbreviation)
            table_df["tgt_onto"] = table_df["tgt_onto"].apply(self.map_ontology_name_to_abbreviation)
            table_df["method"] = table_df["method"].apply(self.map_method_name_to_abbreviations)

            table_df = table_df[[
                "src_onto",
                "tgt_onto",
                "method",
                "total",
                "coverage",
                "agree_count",
                "agreement",
            ]]

            # Select best method per (src, tgt)
            table_df = table_df.sort_values(
                by=["tgt_onto", "src_onto", "total", "agreement", "total"],
                ascending=[True, True, False, False, False]
            )
            table_df = table_df.drop_duplicates(subset=["src_onto", "tgt_onto"], keep="first")

            table_df = table_df.rename(columns={
                "src_onto": "Ontology",
                "tgt_onto": "Target",
                "method": "Method",
                "total": "Matchings",
                "coverage": "Coverage",
                "agree_count": "Agreement (count)",
                "agreement": "Agreement (\%)",
            })

            table_df["Coverage"] = table_df["Coverage"].astype(float).round(2)
            table_df["Agreement (\%)"] = table_df["Agreement (\%)"].astype(float).round(2)

            if sort_by in table_df.columns:
                table_df = table_df.sort_values(sort_by, ascending=False)

            if bold_best:
                for col in ["Matchings", "Coverage", "Agreement (count)", "Agreement (\%)"]:
                    max_val = table_df[col].max()
                    table_df[col] = table_df[col].apply(
                        lambda x: f"\\textbf{{{x}}}" if x == max_val else x
                    )

            latex = table_df.to_latex(
                index=False,
                escape=False,
                column_format="lllcccc",
                float_format="%.2f",
            )

            caption = "Ontology alignment summary"
            label = "tab:alignment_summary"

            latex_table = f"""
                \\begin{{table}}[t]
                \\centering
                {latex}
                \\caption{{{caption}}}
                \\label{{{label}}}
                \\end{{table}}
            """

            output_path = os.path.join(output_dir, "latex_summary_final.tex")
            with open(output_path, "w") as f:
                f.write(latex_table)
                print(f"LaTeX table saved to {output_path}")

            return latex_table

def parse_args():
    parser = argparse.ArgumentParser(description="Compute agreement statistics from ontology alignment matchings CSV.")
    parser.add_argument("--csv", type=str, default=None, help="Path to the matchings CSV file. If not given, will use the most recent one in the results directory.")
    parser.add_argument("--run_analysis", action="store_false", help="Whether to rerun the analysis and generate new CSV files. If false, will read the existing CSV files")
    return parser.parse_args()

if __name__ == "__main__":
    results_dir = os.path.join(os.getcwd(), os.pardir, os.pardir, "results", "ontology_alignment", "analysis")
    results_dir = Path(results_dir)

    args = parse_args()
    CSV = args.csv if args.csv else max(results_dir.glob("matchings_inspection_*.csv"), key=os.path.getctime)
    print(f"Using matchings CSV: {CSV}")
    output_dir = os.path.join(results_dir, "analysis")
    os.makedirs(output_dir, exist_ok=True)
    plots_dir = os.path.join(output_dir, "outputs")
    os.makedirs(plots_dir, exist_ok=True)

    analyser = AlignmentStats(CSV)
    run_analysis = args.run_analysis
    if run_analysis:
        print(f"Running analysis and generating new CSV files in {output_dir}...")
        stats, consensus = analyser.run_analysis()
    else:
        stats = pd.read_csv(f"{output_dir}/stats_per_method.csv")
        consensus = pd.read_csv(f"{output_dir}/stats_consensus.csv")
        # profile = pd.read_csv(f"{output_dir}/stats_ontology_agreement_profile.csv")

    # analyser.create_diagnostic_plots(stats)
    ontology_sizes = analyser.get_ontology_sizes(analyser.ontology_paths)
    analyser.make_latex_summary_table(stats, consensus, ontology_sizes, sort_by="coverage", bold_best=True)

