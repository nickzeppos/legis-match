"""
Benchmarking various parts of legis-match
"""

import os
import random
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from statistics import mean
from typing import List, Tuple

import numpy as np

from src.encode import encode_normalized_text
from src.processing.compare_fn import smith_waterman
from src.processing.legis_parse import process_section
from src.processing.parse_fn import get_all_sections
from src.utils import get_core_bill_xml

NUM_RUNS = 100
LOG_FILE = "benchmark_results.txt"

os.environ["TOKENIZERS_PARALLELISM"] = "false"

# logging w/ print and then piping stdout to log_file


class Logger:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()


# Attach logger to stdout at log file path
sys.stdout = Logger(LOG_FILE)


def file_name_to_key(path: str):
    """
    XML file name to bill key, get_core_bill_xml.
    File name is, e.g., 118hr27ih.xml
    Corresponding bill key would be:
        { congress_number: 118,
          bill_number: 27,
          bill_type: 'hr',
          bill_version: 'ih' }
    """
    # base name from path
    base_name = os.path.basename(path)
    # remove extension
    base_name = os.path.splitext(base_name)[0]
    # regex to match bill key
    # bil version can be 2 or 3
    regex = r"(\d{3})([a-z]{2})(\d+)([a-z]{2,3})"
    match = re.match(regex, base_name)
    if not match:
        raise ValueError(f"Invalid file name format: {path}")
    # extract groups
    groups = match.groups()
    # create bill key dict
    bill_key = {
        "congress_number": int(groups[0]),
        "bill_number": int(groups[2]),
        "bill_type": groups[1],
        "bill_version": groups[3],
    }

    return bill_key


def load_string_pool() -> List[str]:
    """
    Load all the xml files in the data dir, parse them, and get normalized outputs.
    """
    # path to dir containing all xml files
    paths = os.listdir("data/")
    bill_keys = [file_name_to_key(path) for path in paths]
    string_pool = []

    # log out number of files
    print(f"Found {len(paths)} files in data dir.")

    print("Bechmarking parser...")
    print(f"Num runs: {NUM_RUNS}")

    section_counts = {}
    for bill_key in bill_keys:
        congress_number = bill_key["congress_number"]
        bill_number = bill_key["bill_number"]
        bill_type = bill_key["bill_type"]
        bill_version = bill_key["bill_version"]
        core_xml = get_core_bill_xml(
            congress_number, bill_number, bill_type, bill_version
        )
        sections = get_all_sections(core_xml)
        processed_sections = [process_section(
            section) for i, section in sections.items()]
        new_pool_additions = [
            section["normalized_output"] for section in processed_sections
        ]

        # get section count
        section_count = len(new_pool_additions)
        # update section count stats
        if section_count not in section_counts:
            section_counts[section_count] = 1
        else:
            section_counts[section_count] += 1

        string_pool.extend(new_pool_additions)

    print(f"Num sections: {len(string_pool)}")
    # ordered by count
    section_counts = dict(sorted(section_counts.items()))
    # print out section counts
    for key, value in section_counts.items():
        print(f"section_count: {key}:, instances: {value}")

    return string_pool, [s.split() for s in string_pool]


def benchmark_sw(func, string_pool: List[str], runs=NUM_RUNS) -> List[float]:
    """
    Given a function, a pool of strings, and a number of runs,
    test function performance with sample pairs the pool.
    """
    # init a durations acc
    acc = []

    # for each run
    for i in range(runs):

        # sample two prepared sections from the pool
        s1, s2 = random.sample(string_pool, 2)

        # run func
        start = time.perf_counter()
        func(s1, s2)
        end = time.perf_counter()
        duration = end - start
        acc.append(duration)

        print(f"Run {i + 1}: {duration:.4f}s")
        print(f'len1: {len(s1)}, len2: {len(s2)}')

    print(f"Avg: {mean(acc):.4f}s\n")
    print(f"Min: {min(acc):.4f}s\n")
    print(f"Max: {max(acc):.4f}s\n")
    return acc


def benchmark_sw_max_target(func, string_pool: List[str], runs=NUM_RUNS) -> List[float]:
    """
    Given a function, a pool of strings, and a number of runs,
    test func performance by drawing a random section from the pool. Always compare to longest section.\
    """

    # find longest string in string_pool
    longest_section = max(string_pool, key=len)
    print(f"Longest section length: {len(longest_section)}")
    # init a durations acc
    acc = []
    # for each run
    for i in range(runs):

        # sample two prepared sections from the pool
        s1 = random.choice(string_pool)

        # run func
        start = time.perf_counter()
        func(s1, longest_section)
        end = time.perf_counter()
        duration = end - start

        # assemble rest of dur payload
        # str lengths
        len1 = len(s1)
        len2 = len(longest_section)

        acc.append(duration)
        print(f"Run {i + 1}: {duration:.4f}s")


def smith_wat(s1: str, s2: str):
    """
    Wrapper for custom smith waterman algo implementation
    """
    # add name for recovery in benchmark fn
    result = smith_waterman(s1, s2)
    assert "score" in result


def worker_sw(pair: Tuple[List[str], List[str]], func) -> float:
    """
    worker at top level otherwise run into pickling issues
    """
    s1, s2 = pair
    start = time.perf_counter()
    func(s1, s2)
    end = time.perf_counter()
    return end - start


def parallel_benchmark_sw(func, string_pool: List[List[str]], runs: int = 10, workers: int = 8) -> List[float]:
    """
    benchmark custom sw iwth random draw, parallelized
    """
    acc = []
    pairs = [tuple(random.sample(string_pool, 2)) for _ in range(runs)]
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker_sw, pair, func) for pair in pairs]
        for i, future in enumerate(as_completed(futures), 1):
            duration = future.result()
            acc.append(duration)
            print(f"Run {i}: {duration:.4f}s")
            print(f'len1: {len(pairs[i-1][0])}, len2: {len(pairs[i-1][1])}')

    return acc


def worker_sw_max_target(sample: List[str], longest: List[str], func) -> float:
    """
    worker at top level otherwise run into pickling issues
    """
    start = time.perf_counter()
    func(sample, longest)
    end = time.perf_counter()
    return end - start


def parallel_benchmark_sw_max_target(func, string_pool: List[List[str]], runs: int = 10, workers: int = 8) -> List[float]:
    """
    benchmark custom sw with forced inclusion of maximum length string in sample, parallelized
    """
    longest = max(string_pool, key=len)
    print(f"Longest section length: {len(longest)}")
    acc = []
    samples = [random.choice(string_pool) for _ in range(runs)]

    with ProcessPoolExecutor(max_workers=workers) as executor:
        # Submit tasks to the executor
        futures = {
            executor.submit(worker_sw_max_target, sample, longest, func): sample
            for sample in samples
        }
        for future in as_completed(futures):
            sample = futures[future]
            try:
                duration = future.result()
                acc.append(duration)
                print(f"len1: {len(sample)}, len2: {len(longest)}")
                print(f"Task completed: {duration:.4f}s")
            except Exception as e:
                print(f"Task failed with exception: {e}")

    print(f"Avg: {mean(acc):.4f}s\n")
    print(f"Min: {min(acc):.4f}s\n")
    print(f"Max: {max(acc):.4f}s\n")
    return acc


# entrypoint
if __name__ == "__main__":
    pool, tokenized_pool = load_string_pool()
    # print("Benchmarking custom sw: random draw")
    # benchmark_sw(smith_wat, pool)
    print("Benchmarking custom sw: parallel random draw")
    parallel_benchmark_sw(smith_wat, tokenized_pool)

    # print("Benchmarking custom sw: forced max length target")
    # benchmark_sw_max_target(smith_wat, pool)
    print("Benchmarking custom sw: parallel forced max length target")
    parallel_benchmark_sw_max_target(smith_wat, tokenized_pool)
