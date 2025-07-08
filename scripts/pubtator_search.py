#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "requests",
# ]
# ///
"""
Fast gene-variant-disease paper finder using PubTator3 bulk data.
Creates efficient lookup indices and performs instant searches.

Finds papers that:
1. Describe gene-disease associations (directly supported)
2. Also mention variants
"""

import requests
import json
import sys
import time
import os
import gzip
import pickle
import logging
import argparse
from typing import Optional, Dict
from collections import defaultdict


class FastPubTatorSearch:
    """Fast lookup system for PubTator3 data using precomputed indices."""
    
    def __init__(self, data_dir: str = "."):
        self.data_dir = data_dir
        self.base_url = "https://ftp.ncbi.nlm.nih.gov/pub/lu/PubTator3/"
        self.api_url = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api"
        self.logger = logging.getLogger(__name__)
        
        # Index files
        self.gene_disease_index = os.path.join(data_dir, "gene_disease_pmids.pkl")
        self.variant_pmids_index = os.path.join(data_dir, "variant_pmids.pkl")
        self.human_genes_index = os.path.join(data_dir, "human_genes.pkl")
        
        # Raw data files
        self.relation_file = os.path.join(data_dir, "relation2pubtator3.gz")
        self.variant_file = os.path.join(data_dir, "mutation2pubtator3.gz")
        self.gene_info_file = os.path.join(data_dir, "gene_info.gz")
    
    def ensure_indices_exist(self):
        """Check if indices exist, create them if not."""
        if not os.path.exists(self.human_genes_index):
            self.logger.info("Human genes index not found. Creating index...")
            self._create_human_genes_index()
        
        if not os.path.exists(self.gene_disease_index):
            self.logger.info("Gene-disease index not found. Creating index...")
            self._create_gene_disease_index()
        
        if not os.path.exists(self.variant_pmids_index):
            self.logger.info("Variant PMID index not found. Creating index...")
            self._create_variant_index()
    
    def _download_file(self, filename: str, base_url: str = None):
        """Download file if it doesn't exist."""
        if base_url is None:
            base_url = self.base_url
        
        filepath = os.path.join(self.data_dir, filename)
        if not os.path.exists(filepath):
            self.logger.info(f"Downloading {filename}...")
            try:
                response = requests.get(f"{base_url}{filename}", stream=True)
                response.raise_for_status()
                
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        
                self.logger.info(f"Downloaded {filename}")
            except Exception as e:
                self.logger.error(f"Failed to download {filename}: {e}")
                raise
    
    def _create_human_genes_index(self):
        """Create human genes index from NCBI gene_info file."""
        # Download NCBI gene_info file
        gene_info_url = "https://ftp.ncbi.nlm.nih.gov/gene/DATA/"
        self._download_file("gene_info.gz", gene_info_url)
        
        self.logger.info("Processing gene_info file for human genes...")
        gene_id_to_symbol = {}
        symbol_to_gene_id = {}
        
        with gzip.open(self.gene_info_file, 'rt') as f:
            for line_num, line in enumerate(f, 1):
                if line_num % 1000000 == 0:
                    self.logger.debug(f"Processed {line_num:,} gene entries...")
                
                if line.startswith('#'):
                    continue
                    
                parts = line.strip().split('\t')
                if len(parts) >= 3:
                    tax_id = parts[0]
                    gene_id = parts[1]
                    symbol = parts[2]
                    synonyms = parts[4] if len(parts) > 4 else ""
                    
                    # Only process human genes (taxid=9606)
                    if tax_id == "9606":
                        gene_id_to_symbol[gene_id] = symbol
                        symbol_to_gene_id[symbol.upper()] = gene_id
                        
                        # Also index synonyms
                        if synonyms and synonyms != "-":
                            for synonym in synonyms.split('|'):
                                if synonym.strip():
                                    symbol_to_gene_id[synonym.strip().upper()] = gene_id
        
        human_genes_data = {
            'gene_id_to_symbol': gene_id_to_symbol,
            'symbol_to_gene_id': symbol_to_gene_id,
            'human_gene_ids': set(gene_id_to_symbol.keys())
        }
        
        with open(self.human_genes_index, 'wb') as f:
            pickle.dump(human_genes_data, f)
        
        self.logger.info(f"Created human genes index with {len(gene_id_to_symbol):,} genes")
    
    def _create_gene_disease_index(self):
        """Create gene-disease association index from relations file, filtered for human genes."""
        self._download_file("relation2pubtator3.gz")
        
        # Load human genes data
        with open(self.human_genes_index, 'rb') as f:
            human_genes_data = pickle.load(f)
        human_gene_ids = human_genes_data['human_gene_ids']
        
        self.logger.info("Processing relations file for human gene-disease associations...")
        gene_disease_pmids = defaultdict(set)
        
        with gzip.open(self.relation_file, 'rt') as f:
            for line_num, line in enumerate(f, 1):
                if line_num % 1000000 == 0:
                    self.logger.debug(f"Processed {line_num:,} relations...")
                
                parts = line.strip().split('\t')
                if len(parts) >= 4:
                    pmid_str = parts[0]
                    relation_type = parts[1]
                    entity1 = parts[2]
                    entity2 = parts[3]
                    
                    try:
                        pmid = int(pmid_str)
                        # Look for gene-disease associations
                        if relation_type == "associate":
                            if entity1.startswith("Gene|") and entity2.startswith("Disease|"):
                                gene_id = entity1.replace("Gene|", "")
                                # Only include human genes
                                if gene_id in human_gene_ids:
                                    gene_disease_pmids[gene_id].add(pmid)
                            elif entity1.startswith("Disease|") and entity2.startswith("Gene|"):
                                gene_id = entity2.replace("Gene|", "")
                                # Only include human genes
                                if gene_id in human_gene_ids:
                                    gene_disease_pmids[gene_id].add(pmid)
                    except ValueError:
                        continue
        
        # Convert to dict and save
        gene_disease_dict = {gene_id: pmids for gene_id, pmids in gene_disease_pmids.items()}
        
        with open(self.gene_disease_index, 'wb') as f:
            pickle.dump(gene_disease_dict, f)
        
        self.logger.info(f"Created gene-disease index with {len(gene_disease_dict):,} human genes")
    
    def _create_variant_index(self):
        """Create variant PMID index from mutation file."""
        self._download_file("mutation2pubtator3.gz")
        
        self.logger.info("Processing variant file...")
        variant_pmids = set()
        
        with gzip.open(self.variant_file, 'rt') as f:
            for line_num, line in enumerate(f, 1):
                if line_num % 1000000 == 0:
                    self.logger.debug(f"Processed {line_num:,} variants...")
                
                pmid_str = line.split('\t')[0]
                try:
                    variant_pmids.add(int(pmid_str))
                except ValueError:
                    continue
        
        with open(self.variant_pmids_index, 'wb') as f:
            pickle.dump(variant_pmids, f)
        
        self.logger.info(f"Created variant index with {len(variant_pmids):,} unique PMIDs")
    
    def normalize_gene_symbol(self, gene_symbol: str) -> Optional[str]:
        """Normalize gene symbol to human NCBI Gene ID using local human genes index."""
        # Load human genes data
        with open(self.human_genes_index, 'rb') as f:
            human_genes_data = pickle.load(f)
        
        symbol_to_gene_id = human_genes_data['symbol_to_gene_id']
        gene_id_to_symbol = human_genes_data['gene_id_to_symbol']
        
        # Look up symbol (case-insensitive)
        gene_id = symbol_to_gene_id.get(gene_symbol.upper())
        
        if gene_id:
            official_symbol = gene_id_to_symbol.get(gene_id, gene_symbol)
            if official_symbol.upper() != gene_symbol.upper():
                self.logger.info(f"Using official symbol '{official_symbol}' for '{gene_symbol}'")
            return gene_id
        
        self.logger.warning(f"No human gene found for symbol '{gene_symbol}'")
        return None
    
    def load_indices(self):
        """Load precomputed indices."""
        self.logger.info("Loading indices...")
        
        with open(self.gene_disease_index, 'rb') as f:
            gene_disease_pmids = pickle.load(f)
        
        with open(self.variant_pmids_index, 'rb') as f:
            variant_pmids = pickle.load(f)
        
        self.logger.info(f"Loaded {len(gene_disease_pmids):,} genes with disease associations and {len(variant_pmids):,} variant PMIDs")
        return gene_disease_pmids, variant_pmids
    
    def search_gene_variant_papers(self, gene_symbol: str) -> Dict:
        """
        Find papers that mention both gene-disease associations and variants.
        
        Returns:
            Dict with search results and statistics
        """
        self.logger.info(f"Searching for gene: {gene_symbol}")
        
        # Ensure indices exist
        self.ensure_indices_exist()
        
        # Normalize gene symbol
        gene_id = self.normalize_gene_symbol(gene_symbol)
        if not gene_id:
            return {"error": f"Could not normalize gene symbol '{gene_symbol}'"}
        
        self.logger.info(f"Normalized to gene ID: {gene_id}")
        
        # Load indices
        gene_disease_pmids, variant_pmids = self.load_indices()
        
        # Get PMIDs for this gene's disease associations
        gene_disease_papers = gene_disease_pmids.get(gene_id, set())
        if not gene_disease_papers:
            return {
                "gene_symbol": gene_symbol,
                "gene_id": gene_id,
                "gene_disease_papers": 0,
                "variant_papers": len(variant_pmids),
                "intersection": 0,
                "pmids": []
            }
        
        # Find intersection with variant PMIDs
        intersection_pmids = gene_disease_papers.intersection(variant_pmids)
        
        return {
            "gene_symbol": gene_symbol,
            "gene_id": gene_id,
            "gene_disease_papers": len(gene_disease_papers),
            "variant_papers": len(variant_pmids),
            "intersection": len(intersection_pmids),
            "pmids": sorted(list(intersection_pmids))
        }


def main():
    """Main function."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger(__name__)
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Find papers that describe gene-disease associations and also mention variants."
    )
    parser.add_argument(
        "gene_symbol", 
        help="Gene symbol to search for (e.g., BRCA1, DES)"
    )
    parser.add_argument(
        "--index-dir", 
        default="./", 
        help="Directory for index files and downloads (default: ./)"
    )
    parser.add_argument(
        "--output", 
        help="Save results to JSON file"
    )
    
    args = parser.parse_args()
    
    gene_symbol = args.gene_symbol
    index_dir = args.index_dir
    output_file = args.output
    
    # Create searcher and perform search
    try:
        searcher = FastPubTatorSearch(index_dir)
        
        # Perform search
        start_time = time.time()
        results = searcher.search_gene_variant_papers(gene_symbol)
        search_time = time.time() - start_time
    except Exception as e:
        logger.error(f"Search failed with exception: {e}")
        sys.exit(1)
    
    # Print results
    if "error" in results:
        logger.error(f"Search failed: {results['error']}")
        sys.exit(1)
    
    print(f"\nResults for {results['gene_symbol']} (Gene ID: {results['gene_id']}):")
    print("=" * 60)
    print(f"Papers with gene-disease associations: {results['gene_disease_papers']:,}")
    print(f"Papers mentioning variants: {results['variant_papers']:,}")
    print(f"Papers with both (intersection): {results['intersection']:,}")
    
    if results['intersection'] > 0:
        coverage = (results['intersection'] / results['gene_disease_papers']) * 100
        print(f"Variant coverage: {coverage:.1f}% of gene-disease papers")
    
    logger.info(f"Search completed in {search_time:.2f} seconds")
    
    # Save results if output file specified
    if output_file:
        try:
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2)
            logger.info(f"Results saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save results to {output_file}: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()