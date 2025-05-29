#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import difflib
import re
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter
from sklearn.metrics import confusion_matrix
from typing import Dict, List, Tuple, Set

# Remove import from main.py
# from main import extract_text_from_pdf

def normalize_text(text: str) -> str:
    """Normalize text for more accurate comparison"""
    # Replace multiple spaces with a single space
    text = re.sub(r'\s+', ' ', text)
    
    # Remove special characters that might be different between the two texts
    text = re.sub(r'[^\w\s.,;:!?()[\]{}\'\"<>@#$%^&*+=|\\~`-]', '', text)
    
    # Normalize numbers and separators
    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    text = re.sub(r'(\d)[.,](\d)', r'\1\2', text)
    
    return text.strip().lower()

def get_word_sets(text: str) -> Set[str]:
    """Extract meaningful words from text for comparison"""
    # Normalize and split text into words
    words = re.findall(r'\b\w+\b', normalize_text(text))
    # Filter out common noise and very short words
    filtered_words = [word for word in words if len(word) > 1]
    return set(filtered_words)

def calculate_detailed_metrics(reference_text: str, extracted_text: str) -> Dict:
    """
    Calculate detailed text comparison metrics between reference and extracted text.
    
    Args:
        reference_text (str): The reference text (ground truth)
        extracted_text (str): The text extracted from PDF
        
    Returns:
        Dict: Dictionary of detailed metrics
    """
    # Normalize texts for comparison
    norm_reference = normalize_text(reference_text)
    norm_extracted = normalize_text(extracted_text)
    
    # Basic metrics
    metrics = {}
    
    # Character-level metrics
    seq_matcher = difflib.SequenceMatcher(None, norm_reference, norm_extracted)
    metrics['character_accuracy'] = seq_matcher.ratio() * 100
    
    # Line-level metrics
    ref_lines = [line.strip() for line in reference_text.splitlines() if line.strip()]
    ext_lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
    
    norm_ref_lines = [normalize_text(line) for line in ref_lines]
    norm_ext_lines = [normalize_text(line) for line in ext_lines]
    
    # Match lines at different similarity thresholds
    similarity_thresholds = [0.5, 0.7, 0.8, 0.9, 0.95, 1.0]
    line_matches = {threshold: 0 for threshold in similarity_thresholds}
    
    # For each reference line, find the best matching extracted line
    for ref_line in norm_ref_lines:
        best_similarity = 0
        for ext_line in norm_ext_lines:
            similarity = difflib.SequenceMatcher(None, ref_line, ext_line).ratio()
            if similarity > best_similarity:
                best_similarity = similarity
        
        # Count the match at appropriate threshold
        for threshold in sorted(similarity_thresholds):
            if best_similarity >= threshold:
                line_matches[threshold] += 1
    
    total_ref_lines = len(ref_lines)
    for threshold in similarity_thresholds:
        metrics[f'line_match_{int(threshold*100)}pct'] = (line_matches[threshold] / total_ref_lines * 100) if total_ref_lines else 0
    
    # Word-level metrics
    ref_word_set = get_word_sets(reference_text)
    ext_word_set = get_word_sets(extracted_text)
    
    common_words = ref_word_set.intersection(ext_word_set)
    metrics['word_recall'] = (len(common_words) / len(ref_word_set) * 100) if ref_word_set else 0
    metrics['word_precision'] = (len(common_words) / len(ext_word_set) * 100) if ext_word_set else 0
    
    if metrics['word_recall'] + metrics['word_precision'] > 0:
        metrics['word_f1'] = (2 * metrics['word_recall'] * metrics['word_precision'] / 
                            (metrics['word_recall'] + metrics['word_precision']))
    else:
        metrics['word_f1'] = 0
    
    # Structure metrics
    metrics['length_ratio'] = min(len(extracted_text) / len(reference_text), 
                                len(reference_text) / len(extracted_text)) * 100 if reference_text and extracted_text else 0
    
    metrics['line_count_ratio'] = min(len(ext_lines) / len(ref_lines), 
                                   len(ref_lines) / len(ext_lines)) * 100 if ref_lines and ext_lines else 0
    
    # Error analysis - common issues
    metrics['missing_line_breaks'] = abs(len(ext_lines) - len(ref_lines))
    
    # Compare punctuation counts
    ref_punctuation = Counter(c for c in reference_text if c in ",.;:!?-()[]{}\"'")
    ext_punctuation = Counter(c for c in extracted_text if c in ",.;:!?-()[]{}\"'")
    
    metrics['punctuation_accuracy'] = sum((ref_punctuation & ext_punctuation).values()) / max(sum(ref_punctuation.values()), 1) * 100
    
    return metrics

def generate_side_by_side_comparison(reference_text: str, extracted_text: str, output_path: str, max_lines: int = 100):
    """
    Generate a side-by-side comparison of the reference and extracted text
    
    Args:
        reference_text (str): The reference text
        extracted_text (str): The extracted text
        output_path (str): Path to save the comparison
        max_lines (int): Maximum number of lines to compare
    """
    ref_lines = reference_text.splitlines()[:max_lines]
    ext_lines = extracted_text.splitlines()[:max_lines]
    
    differ = difflib.HtmlDiff()
    html_diff = differ.make_file(ref_lines, ext_lines, 
                                 fromdesc="Reference Text", 
                                 todesc="Extracted Text")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_diff)

def analyze_errors(reference_text: str, extracted_text: str, output_path: str):
    """
    Analyze common errors between reference and extracted text
    
    Args:
        reference_text (str): The reference text
        extracted_text (str): The extracted text
        output_path (str): Path to save the error analysis
    """
    # Normalize texts for comparison
    norm_reference = normalize_text(reference_text)
    norm_extracted = normalize_text(extracted_text)
    
    # Split into words
    ref_words = re.findall(r'\b\w+\b', norm_reference)
    ext_words = re.findall(r'\b\w+\b', norm_extracted)
    
    # Find words in reference but not in extracted
    missing_words = set([w for w in ref_words if w not in ext_words])
    # Find words in extracted but not in reference
    added_words = set([w for w in ext_words if w not in ref_words])
    
    # Word frequency analysis
    ref_word_freq = Counter(ref_words)
    ext_word_freq = Counter(ext_words)
    
    # Words with different frequencies
    diff_freq_words = []
    for word in set(ref_word_freq.keys()) & set(ext_word_freq.keys()):
        if ref_word_freq[word] != ext_word_freq[word]:
            diff_freq_words.append((word, ref_word_freq[word], ext_word_freq[word]))
    
    # Sort by frequency difference
    diff_freq_words.sort(key=lambda x: abs(x[1] - x[2]), reverse=True)
    
    # Character substitution analysis
    char_subs = []
    min_len = min(len(norm_reference), len(norm_extracted))
    for i in range(min_len):
        if norm_reference[i] != norm_extracted[i]:
            context_start = max(0, i - 5)
            context_end = min(min_len, i + 5)
            char_subs.append((
                norm_reference[i], 
                norm_extracted[i], 
                norm_reference[context_start:context_end], 
                norm_extracted[context_start:context_end]
            ))
    
    # Line match analysis
    ref_lines = [line.strip() for line in reference_text.splitlines() if line.strip()]
    ext_lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
    
    # Sample of lines that don't match exactly
    non_matching_lines = []
    for i, ref_line in enumerate(ref_lines[:50]):  # Check first 50 lines
        best_match = None
        best_score = 0
        best_idx = -1
        for j, ext_line in enumerate(ext_lines):
            score = difflib.SequenceMatcher(None, ref_line, ext_line).ratio()
            if score > best_score:
                best_score = score
                best_match = ext_line
                best_idx = j
        
        if 0.5 <= best_score < 1.0:
            non_matching_lines.append((i, best_idx, ref_line, best_match, best_score))
    
    # Write error analysis to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=============== PDF EXTRACTION ERROR ANALYSIS ===============\n\n")
        
        f.write("TOP 20 MISSING WORDS (in reference but not in extracted):\n")
        for word in sorted(missing_words, key=len, reverse=True)[:20]:
            f.write(f"  - {word}\n")
        
        f.write("\nTOP 20 ADDED WORDS (in extracted but not in reference):\n")
        for word in sorted(added_words, key=len, reverse=True)[:20]:
            f.write(f"  - {word}\n")
        
        f.write("\nTOP 20 WORDS WITH DIFFERENT FREQUENCIES:\n")
        f.write(f"{'WORD':<20} {'REF COUNT':<10} {'EXT COUNT':<10} {'DIFF':<10}\n")
        f.write("-" * 50 + "\n")
        for word, ref_count, ext_count in diff_freq_words[:20]:
            f.write(f"{word:<20} {ref_count:<10} {ext_count:<10} {ref_count - ext_count:<10}\n")
        
        f.write("\nSAMPLE CHARACTER SUBSTITUTIONS:\n")
        f.write(f"{'REF':<5} {'EXT':<5} {'REF CONTEXT':<15} {'EXT CONTEXT':<15}\n")
        f.write("-" * 50 + "\n")
        for ref_char, ext_char, ref_context, ext_context in char_subs[:20]:
            f.write(f"{ref_char:<5} {ext_char:<5} {ref_context:<15} {ext_context:<15}\n")
            
        f.write("\nSAMPLE SIMILAR BUT NOT EXACT LINE MATCHES:\n")
        f.write(f"{'SCORE':<6} {'REF LINE':<50} | {'EXT LINE':<50}\n")
        f.write("-" * 107 + "\n")
        for i, j, ref, ext, score in non_matching_lines[:20]:
            ref_short = ref[:47] + "..." if len(ref) > 50 else ref
            ext_short = ext[:47] + "..." if len(ext) > 50 else ext
            f.write(f"{score:.2f}  {ref_short:<50} | {ext_short:<50}\n")

def evaluate_extraction(reference_file, extracted_file, output_dir=None):
    """
    Evaluate text extraction by comparing extracted text with a reference text
    
    Args:
        reference_file (str): Path to the reference text file
        extracted_file (str): Path to the extracted text file
        output_dir (str, optional): Directory to save evaluation results
    """
    # Set default output directory if not provided
    if not output_dir:
        output_dir = os.path.dirname(extracted_file)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Output files for analysis
    detailed_metrics_path = os.path.join(output_dir, "detailed_metrics.txt")
    comparison_path = os.path.join(output_dir, "comparison.html")
    error_analysis_path = os.path.join(output_dir, "error_analysis.txt")
    
    print(f"Starting evaluation...")
    start_time = time.time()
    
    # Read reference text
    if not os.path.exists(reference_file):
        print(f"ERROR: Reference file not found: {reference_file}")
        return
    
    with open(reference_file, 'r', encoding='utf-8') as f:
        reference_text = f.read()
    
    # Read extracted text
    if not os.path.exists(extracted_file):
        print(f"ERROR: Extracted file not found: {extracted_file}")
        return
    
    with open(extracted_file, 'r', encoding='utf-8') as f:
        extracted_text = f.read()
    
    # Calculate detailed metrics
    metrics = calculate_detailed_metrics(reference_text, extracted_text)
    
    # Generate side-by-side comparison
    print("Generating side-by-side comparison...")
    generate_side_by_side_comparison(reference_text, extracted_text, comparison_path)
    
    # Analyze errors
    print("Analyzing extraction errors...")
    analyze_errors(reference_text, extracted_text, error_analysis_path)
    
    # Report results
    print("\n========== EVALUATION RESULTS ==========")
    print(f"Character-level accuracy: {metrics['character_accuracy']:.2f}%")
    print(f"Word recall: {metrics['word_recall']:.2f}%")
    print(f"Word precision: {metrics['word_precision']:.2f}%")
    print(f"Word F1 score: {metrics['word_f1']:.2f}%")
    
    print("\nLine-level matches at different similarity thresholds:")
    for threshold in [50, 70, 80, 90, 95, 100]:
        print(f"  - {threshold}% similarity: {metrics[f'line_match_{threshold}pct']:.2f}%")
    
    print(f"\nPunctuation accuracy: {metrics['punctuation_accuracy']:.2f}%")
    print(f"Content length ratio: {metrics['length_ratio']:.2f}%")
    print(f"Line count ratio: {metrics['line_count_ratio']:.2f}%")
    print(f"Missing line breaks: {metrics['missing_line_breaks']}")
    
    # Save detailed metrics to file
    with open(detailed_metrics_path, 'w', encoding='utf-8') as f:
        f.write("========== DETAILED PDF EXTRACTION METRICS ==========\n\n")
        for metric, value in sorted(metrics.items()):
            f.write(f"{metric}: {value:.2f}%\n")
    
    print(f"\nDetailed metrics saved to: {detailed_metrics_path}")
    print(f"Side-by-side comparison saved to: {comparison_path}")
    print(f"Error analysis saved to: {error_analysis_path}")
    print(f"Evaluation completed in {time.time() - start_time:.2f} seconds")
    
    return metrics

if __name__ == "__main__":
    # Example usage
    reference_file = r"d:\DATN_HUST\test\sample.txt"
    extracted_file = r"d:\DATN_HUST\test\output\output.txt"
    output_dir = r"d:\DATN_HUST\test\output"
    
    evaluate_extraction(reference_file, extracted_file, output_dir) 