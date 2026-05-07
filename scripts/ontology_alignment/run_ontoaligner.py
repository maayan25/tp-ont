# Author: Ma'ayan Armony <maayan.armony@kcl.ac.uk>, based on tutorial from  OntoAligner documentation: https://ontoaligner.readthedocs.io/aligner/rag.html (retrieved on 2026-02-19)
# Class to align ontologies using the RAG-based approach from OntoAligner


import json
import os
from argparse import ArgumentParser
from dataclasses import dataclass, field
from typing import Type, Optional

import torch
from ontoaligner import OntoAlignerPipeline
from ontoaligner.ontology import GenericOntology, GenericOMDataset, GraphTripleOMDataset, PropertyOMDataset, \
    ProcessingStrategy
from ontoaligner.utils import metrics, xmlify
from ontoaligner.aligner import MistralLLMBERTRetrieverRAG, SimpleFuzzySMLightweight, AutoModelDecoderLLM, \
    ConceptLLMDataset, ConvEAligner, PropMatchAligner
from ontoaligner.encoder import ConceptParentRAGEncoder, ConceptChildrenLightweightEncoder, ConceptLLMEncoder, \
    GraphTripleEncoder, PropertyEncoder, PropMatchEncoder
from ontoaligner.postprocess import rag_hybrid_postprocessor, rag_heuristic_postprocessor, graph_postprocessor
from torch.utils.data import DataLoader

@dataclass
class AlignmentConfig:
    """
    Configuration for the ontology alignment pipeline
    """
    method: str # "kge", "fuzzy", "llm" or "rag"
    task: Type
    encoder: Type
    aligner: Type
    postprocessors: list
    evaluate: bool = False
    task_config: dict = field(default_factory=dict)
    aligner_config: dict = field(default_factory=dict)
    aligner_load_config: dict = field(default_factory=dict) # e.g. {"llm_path": "mistralai/Mistral-7B-v0.3", "ir_path": "all-MiniLM-L6-v2"}
    llm_config: dict = field(default_factory=dict)
    postprocessor_kwargs: list[dict] = field(default_factory=list)

class OntologyAlignmentPipeline:
    """
    Ontology Alignment Pipeline using OntoAligner's pipeline:
    1. Load and parse Ontologies
    2. Encode them
    3. Configure the Retriever and LLM
    4. Generate Predictions
    5. Postprocess Matches and optionally evaluate against reference matchings
    """
    def __init__(self, onto_paths,  alignment_config: AlignmentConfig, matchings_dir, reference_matching=None):
        self.task = alignment_config.task()
        self.dataset = self.task.collect(
            source_ontology_path=onto_paths["source_ontology_path"],
            target_ontology_path=onto_paths["target_ontology_path"],
        )

        self.src_onto = self.dataset["source"]
        self.tgt_onto = self.dataset["target"]

        self.config = alignment_config
        self.aligner_config = alignment_config.aligner_config
            # self.llm_config = alignment_config.llm_config

        self.reference_matching = reference_matching

        self.matchings_dir = os.path.join(matchings_dir, self.config.method, f"{self.config.aligner.__name__}", f"{self.config.encoder.__name__}")
        os.makedirs(self.matchings_dir, exist_ok=True)

        self.save_parsed_ontologies()

        self.encoded_ontology = self.encode_ontologies()
        # self.encoded_src, self.encoded_tgt
        # print(f"Type of encoded ontology: {type(self.encoded_ontology)}")
        # print(f"Encoded ontology: {self.encoded_ontology}")

        self.align_ontologies()


    def encode_ontologies(self):
        """
        Encodes the source and target ontologies using the specified encoder.
        :return: the encoded ontologies
        """
        encoder_model = self.config.encoder()
        return encoder_model(source=self.src_onto, target=self.tgt_onto)

    # def prepare_dataset(self, encoded_ontology):
        # """
        # Prepares the dataset using the encoded ontologies.
        # :param encoded_ontology: the encoded ontologies
        # :return: the prepared dataset
        # """
        # llm_dataset = ConceptLLMDataset(source_onto=self.encoded_src, target_onto=self.encoded_tgt)
        #
        # # Create a DataLoader for batching LLM prompts, from example: https://github.com/sciknoworg/OntoAligner/blob/main/examples/llm_matching.py
        # dataloader = DataLoader(
        #     llm_dataset,
        #     batch_size=2048,  # Batch size for processing prompts
        #     shuffle=False,
        #     collate_fn=llm_dataset.collate_fn  # Custom collation function for batching
        # )

    def run_model(self, encoded_ontology):
        """
        Runs an aligner to generate predictions based on the encoded ontologies.
        :param encoded_ontology: the encoded ontologies
        :return: the generated predictions
        """
        # Initialise a model for ontology alignment
        if self.config.method == "rag":
            aligner = self.config.aligner(retriever_config=self.aligner_config, llm_config=self.config.llm_config)
            aligner.load(**self.config.aligner_load_config)
        elif self.config.method == "llm":
            aligner = self.config.aligner(**self.config.llm_config)
            aligner.load(**self.config.aligner_load_config)
        elif self.config.method == "kge":
            aligner = self.config.aligner(**self.aligner_config)
        elif self.config.method == "propmatch":
            aligner = self.config.aligner(**self.aligner_config)
            aligner.load(**self.config.aligner_load_config)
        else:
            raise ValueError(f"Unsupported alignment method: {self.config.method}")

        predicts = aligner.generate(input_data=encoded_ontology)
        return predicts

    def postprocess_matches(self, predicts):
        """
        Postprocesses the generated predictions using the specified postprocessing methods.
        :param predicts: the generated predictions from the model
        :return: the postprocessed matches and their configurations
        """
        results = []

        # Use empty dicts as deafult kwargs if they are not specified
        all_kwargs = self.config.postprocessor_kwargs or [{}] * len(self.config.postprocessors)

        for postprocessor, kwargs in zip(self.config.postprocessors, all_kwargs):
            if postprocessor.__name__ == "graph_postprocessor":
                matches = postprocessor(predicts=predicts, **kwargs)
                print(f"First 5 matchings after {postprocessor.__name__}: {matches[:5]}")
            else:
                matches, config = postprocessor(predicts=predicts, **kwargs)
                print(f"{postprocessor.__name__} config: {config}")

            if self.config.evaluate and self.reference_matching:
                evaluation = metrics.evaluation_report(
                    predicts=matches,
                    references=self.reference_matching
                )
                print(f"{postprocessor.__name__} evaluation:", json.dumps(evaluation, indent=4))

            results.append((postprocessor.__name__, matches))

        return results

    def save_matches(self, processsed_matches):
        """
        Saves the postprocessed matches in XML.
        :param processsed_matches: the postprocessed matches from all methods, in a list
        :return:
        """
        for name, matches in processsed_matches:
            xml_str = xmlify.xml_alignment_generator(matchings=matches)
            output_path = f"{self.matchings_dir}/{name}_matchings.xml"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(xml_str)
            print(f"{name} matches saved to {output_path}")

    def align_ontologies(self):
        """
        Executes the full ontology alignment pipeline.
        :return:
        """
        # encoded_ontologies = (self.encoded_src, self.encoded_tgt)
        predicts = self.run_model(self.encoded_ontology) # TODO need to unpack first?
        matches = self.postprocess_matches(predicts)
        self.save_matches(matches)

    def save_parsed_ontologies(self):
        src_output = os.path.join(self.matchings_dir, f"source_ontology_parsed.txt")
        tgt_output = os.path.join(self.matchings_dir, "target_ontology_parsed.txt")

        src = "\n".join([f"{item}\n" for item in self.src_onto])
        tgt = "\n".join([f"{item}\n" for item in self.tgt_onto])

        with open(src_output, "w", encoding="utf-8") as f:
            f.write(str(src))
        print(f"Parsed source ontology saved to {src_output}")

        with open(tgt_output, "w", encoding="utf-8") as f:
            f.write(str(tgt))
        print(f"Parsed target ontology saved to {tgt_output}")

def parse_args():
    parser = ArgumentParser(description="Convert a KG from JSON format to Turtle format")
    parser.add_argument("--pddl_onto", type=str, default="ontologies/planning/AI-Planning-Ontology/plan-ontology-rdf.owl", help="Path of the planning ontology to align from the root directory")
    parser.add_argument("--knowledge_onto", type=str, default="ontologies/robotics/SOMA/SOMA.owl.rdf", help="PAth to the general knowledge ontology to align from the root directory")
    parser.add_argument("--config", type=str, default="kge", help="Alignment method to use: 'rag', 'kge', 'propmatch' or 'fuzzy'")

    return parser.parse_args()

def main():
    root_dir = os.path.join(os.getcwd(), os.pardir, os.pardir)

    args = parse_args()
    pddl_onto = os.path.join(root_dir, args.pddl_onto)
    pddl_onto_name = os.path.basename(pddl_onto).split(".")[0]
    print(f"Using PDDL ontology: {pddl_onto_name} from path: {pddl_onto}")

    knowledge_onto = os.path.join(root_dir, args.knowledge_onto)
    knowledge_onto_name = os.path.basename(knowledge_onto).split(".")[0]
    print(f"Using knowledge ontology: {knowledge_onto_name} from path: {knowledge_onto}")

    # ontoaligner_dir = os.path.join(os.getcwd(), os.pardir, os.pardir, "OntoAligner")
    results_dir = os.path.join(root_dir, "results", "ontology_alignment")
    os.makedirs(results_dir, exist_ok=True)

    matchings_dir = os.path.join(results_dir, pddl_onto_name, knowledge_onto_name)
    os.makedirs(matchings_dir, exist_ok=True)

    dataset = GenericOMDataset # TODO doesn't work with ConceptLLMDataset. TypeError: LLMDataset.__init__() missing 2 required positional arguments: 'source_onto' and 'target_onto'
    # model = MistralLLMBERTRetrieverRAG
    model = AutoModelDecoderLLM

    config = args.config

    builtin_pipe = ["llm"]
    our_pipe = ["kge", "rag", "propmatch"]

    if config in builtin_pipe:
        run_ontoaligner_pipeline(pddl_onto, knowledge_onto, matchings_dir, dataset=dataset, model=model)
    elif config in our_pipe:
        run_our_pipeline(pddl_onto, knowledge_onto, matchings_dir, config)
    else:
        print("Unknown config:", config)
        exit(1)


def run_ontoaligner_pipeline(src_onto, tgt_onto, matchings_dir, dataset, model):
    """
    Use the built-in OntoAlignerPipeline to run the RAG-based ontology alignment with the specified config.
    Supports: "lightweight" (fuzzy), "retrieval", "llm" and "rag" (normal, fewshot, in-context vector)
    :param src_onto: path to the source ontology
    :param tgt_onto: path to the target ontology
    :param matchings_dir: directory to save the generated matchings
    :param dataset: the dataset class to use for preparing the data for the model (e.g. ConceptLLMDataset for LLM-based alignment)
    :param model:
    :return:
    """
    # TODO add choosing fuzzy or LLM
    pipeline = OntoAlignerPipeline(
        task_class=dataset,
        source_ontology_path=src_onto,
        target_ontology_path=tgt_onto,
        reference_matching_path="reference.xml",
        output_dir = matchings_dir,
        output_format = "xml"
    )

    llm_path = "Qwen/Qwen2.5-3B" # Qwen/Qwen3-4B, google/gemma-2-2b-it # TODO change back to mistral for final runs 'mistralai/Mistral-7B-v0.3'
    retriever_path = "all-MiniLM-L6-v2"
    matchings = pipeline(method="llm",
                         llm_path=llm_path,
                         retriever_path=retriever_path,
                         model_class=model,
                         device='cuda',
                         batch_size=15,
                         return_matching=True,
                         evaluate=False,
                         save_matchings=True
                         )
    # print(f"Matchings: {matchings}")
    fix_llm_results_location(matchings_dir, llm_path, retriever_path)

def fix_llm_results_location(matchings_dir, llm_path, retriever_path):
    """
    Change the location of the generated matchings for LLM-based alignment, to save them in a directory that identifies the LLM and retriever used for alignment.
    i.e. if the matchings are currently saved in "results/pddl_onto/knowledge_onto/llm/matchings.xml", move them to "results/pddl_onto/knowledge_onto/llm/llm_model/retriever_model/matchings.xml"
    :param matchings_dir: the directory where matchings are currently saved
    :param llm_path: the path to the LLM used for alignment
    :param retriever_path: the path to the retriever used for alignment
    :return: None
    """
    llm_model = llm_path.split("/")[-1]
    retriever_model = retriever_path.split("/")[-1]
    new_dir = os.path.join(matchings_dir, "llm", llm_model, retriever_model)
    os.makedirs(new_dir, exist_ok=True)

    old_path = os.path.join(matchings_dir, "llm", "matchings.xml")
    new_path = os.path.join(new_dir, "matchings.xml")
    if os.path.exists(old_path):
        os.rename(old_path, new_path)
        print(f"Moved matchings from {old_path} to {new_path}")
    else:
        print(f"Warning: expected matchings file not found at {old_path}, cannot move to {new_path}")

def run_our_pipeline(src_onto_path, tgt_onto_path, matchings_dir, config_name):
    """
    Run custom pipeline using the specified configurations for encoding, alignment, postprocessing and evaluation.
    Use for KGE-based or PropMatch alignment
    :param src_onto_path: path to the source ontology
    :param tgt_onto_path: path to the target ontology
    :param matchings_dir: directory to save the generated matchings
    :return:
    """
    config = choose_config(config_name)

    # TODO PropertyOMDataset doesn't parse (doesn't recognise domains and ranges?)
    #  debug further - works for DOLCE but not for mine or conceptnet
    # if config.method == "propmatch":
    #     task = PropertyOMDataset(processing_strategy=ProcessingStrategy.NONE)
    #     dataset = task.collect(
    #         source_ontology_path=src_onto_path,
    #         target_ontology_path=tgt_onto_path,
    #     )
    # print(f"Dataset collected with {len(dataset['source'])} source entities and {len(dataset['target'])} target entities.")

    paths = {
        "source_ontology_path": src_onto_path,
        "target_ontology_path": tgt_onto_path,
    }

    OntologyAlignmentPipeline(onto_paths=paths, alignment_config=config, matchings_dir=matchings_dir)

def choose_config(config_name) -> AlignmentConfig:
    if config_name == "rag":
        return AlignmentConfig(
            method="rag",
            task=GenericOMDataset,
            encoder=ConceptParentRAGEncoder,
            aligner=MistralLLMBERTRetrieverRAG,
            postprocessors=[rag_heuristic_postprocessor, rag_hybrid_postprocessor],
            evaluate=True,
            postprocessor_kwargs=[
                {"topk_confidence_ratio": 3, "topk_confidence_score": 3},  # heuristic
                {"ir_score_threshold": 0.1, "llm_confidence_th": 0.8},  # hybrid
            ],
            aligner_load_config={"llm_path": "TinyLlama/TinyLlama-1.1B-Chat-v1.0", "ir_path": "all-MiniLM-L6-v2"}, # TODO testing, change back!
            # llm_models={"llm_path": "mistralai/Mistral-7B-v0.3", "ir_path": "all-MiniLM-L6-v2"},
            aligner_config= {"device": 'cuda', "top_k": 5, "threshold": 0.1},
            llm_config = {
                "device": "cuda",
                "max_length": 300,
                "max_new_tokens": 10,
                "batch_size": 32,
                "answer_set": {
                    "yes": ["yes", "correct", "true", "positive", "valid"],
                    "no": ["no", "incorrect", "false", "negative", "invalid"]
                }
            }
            )
    elif config_name == "kge":
        return AlignmentConfig(
            method="kge",
            task=GraphTripleOMDataset,
            encoder=GraphTripleEncoder,
            aligner=ConvEAligner,
            postprocessors=[graph_postprocessor],
            aligner_config={ # from example config: https://github.com/sciknoworg/OntoAligner/blob/main/examples/kge.py
            "device": 'cuda' if torch.cuda.is_available() else 'cpu',
            'embedding_dim': 300,  # Size of embedding vectors
            'num_epochs': 50,  # Total number of training epochs
            'train_batch_size': 128,  # Batch size for training
            'eval_batch_size': 64,  # Batch size for evaluation
            'num_negs_per_pos': 5,  # Number of negative samples for each positive sample
            'random_seed': 42,  # Seed for reproducibility
            },
            postprocessor_kwargs= [{"threshold": 0.5}]
        )
    elif config_name == "propmatch":
        # TODO debug parsing, returns empty
        return AlignmentConfig(
            method="propmatch",
            task = PropertyOMDataset,
            encoder=PropMatchEncoder,
            aligner=PropMatchAligner,
            postprocessors=[graph_postprocessor],
            task_config={"processing_strategy": ProcessingStrategy.MOST_COMMON_PAIRS}, # domain and range are explicit in the ontology so shouldn't try to infer them
            aligner_config={ # from docs tutorial: ontoaligner.readthedocs.io/aligner/propmatch.html
                "fmt": 'glove',      # Embedding format
                "threshold": 0.5,      # Minimum similarity for matches
                "steps": 3,             # Iterative refinement steps
                "sim_weight": [0, 1, 2], # Use domain, label, and range
                "device": 'cuda' if torch.cuda.is_available() else 'cpu',
                },
            aligner_load_config={ # GloVe, Word2Vec bin gave an error
                "wordembedding_path": 'data/glove.6B.50d.txt',
                "sentence_transformer_id": 'sentence-transformers/all-MiniLM-L6-v2'
            },
            postprocessor_kwargs= [{"threshold": 0.5}]
        )
    elif config_name == "fuzzy":
        return  AlignmentConfig(
            method="fuzzy",
            task=GenericOMDataset,
            encoder=ConceptChildrenLightweightEncoder,
            aligner=SimpleFuzzySMLightweight,
            postprocessors=[rag_heuristic_postprocessor],
            postprocessor_kwargs=[{"fuzzy_sm_threshold": 0.5}],
            evaluate=False,
        )
    else:
        raise ValueError(f"Unsupported config name: {config_name}")


if __name__ == "__main__":
    main()
