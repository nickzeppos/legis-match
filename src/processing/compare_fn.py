"""
TODO
"""

import numpy as np


def enhanced_match_score(token1, token2, weights):
    # Exact match case
    if token1 == token2:
        # Higher weight for matches in quoted text
        if "<QUOTE>" in token1 or "<QUOTED_BLOCK>" in token1:
            return weights["match"] * 1.5

        # # Higher weight for numbers (section numbers, dollar amounts, etc.)
        # if any(c.isdigit() for c in token1):
        #     return weights["match"] * 2.0

        # # Higher weight for specific terms that indicate structural significance
        # important_terms = ["amended", "striking", "inserting", "adding"]
        # if any(term in token1 for term in important_terms):
        #     return weights["match"] * 1.25

        # Regular match
        return weights["match"]

    # Not a match
    return weights["mismatch"]


def smith_waterman(target, candidate):
    """
    Comparing two text sequences using the Smith-Waterman local alignment algorithm.

    In general, this version follows the Wilkerson (2015) approach by:
    - Using **affine gap penalties** (separate costs for opening vs. extending a gap).
    - Ensuring **local alignment traceback stops at zero scores**.


    Args:
        target (list of str): Tokenized reference sequence.
        candidate (list of str): Tokenized sequence to compare.

    Returns:
        dict: { "score": int, "aligned_target": str, "aligned_candidate": str }
    """

    # Smith-Waterman scoring parameters. Here I'm using Wilkerson (2015) weights.
    weights = {
        "match": 2,  # Matching words
        "mismatch": -1,  # Mismatched words
        "gap_open": -5,  # Opening a gap
        "gap_extend": -0.5,  # Extending an existing gap
    }

    # Get lengths of tokenized sequences
    m, n = len(target), len(candidate)

    # Initialize score and traceback matrices
    score_matrix = np.zeros((m + 1, n + 1))
    traceback_matrix = np.zeros((m + 1, n + 1), dtype=int)

    # Track best score and position for traceback
    best_score = 0
    best_pos = (0, 0)

    # Fill matrices
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            # Calculate possible scores
            match = score_matrix[i - 1, j - 1] + \
                enhanced_match_score(target[i-1], candidate[j-1], weights)

            # Affine gap handling: gap open vs. gap extend
            delete = max(
                score_matrix[i - 1, j] + weights["gap_open"],
                score_matrix[i - 1, j] + weights["gap_extend"],
            )
            insert = max(
                score_matrix[i, j - 1] + weights["gap_open"],
                score_matrix[i, j - 1] + weights["gap_extend"],
            )

            # Compute cell score (Smith-Waterman rule: no negative scores)
            max_score = max(0, match, delete, insert)
            score_matrix[i, j] = max_score

            # Store traceback direction
            if max_score == match:
                traceback_matrix[i, j] = 1  # Diagonal (match/mismatch)
            elif max_score == delete:
                traceback_matrix[i, j] = 2  # Up (gap in candidate)
            elif max_score == insert:
                traceback_matrix[i, j] = 3  # Left (gap in target)

            # Track best score for traceback
            if max_score > best_score:
                best_score = max_score
                best_pos = (i, j)

    # Backtrack to recover best-aligned sequences
    aligned_target = []
    aligned_candidate = []
    i, j = best_pos

    while (
        i > 0 and j > 0 and score_matrix[i, j] > 0
    ):  # Stop at first zero (local alignment)
        if traceback_matrix[i, j] == 1:  # Diagonal (match/mismatch)
            aligned_target.append(target[i - 1])
            aligned_candidate.append(candidate[j - 1])
            i -= 1
            j -= 1
        elif traceback_matrix[i, j] == 2:  # Up (gap in candidate)
            aligned_target.append(target[i - 1])
            aligned_candidate.append("-")  # Gap symbol
            i -= 1
        elif traceback_matrix[i, j] == 3:  # Left (gap in target)
            aligned_target.append("-")
            aligned_candidate.append(candidate[j - 1])
            j -= 1

    return {
        "score": best_score,
        "aligned_target": " ".join(reversed(aligned_target)),
        "aligned_candidate": " ".join(reversed(aligned_candidate)),
    }
