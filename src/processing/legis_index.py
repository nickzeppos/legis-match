from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import datasketch
import numpy as np


def build_tfidf_index(all_sections):
    # Create TF-IDF vectorizer
    vectorizer = TfidfVectorizer(min_df=2, max_df=0.95)

    # Fit and transform all sections
    section_texts = [section['normalized_output'] for section in all_sections]
    tfidf_matrix = vectorizer.fit_transform(section_texts)

    return vectorizer, tfidf_matrix


def find_candidate_sections(query_section, vectorizer, tfidf_matrix, all_sections, top_n=500):
    # Transform query section
    query_vector = vectorizer.transform([query_section['normalized_output']])

    # Calculate cosine similarities
    similarities = cosine_similarity(query_vector, tfidf_matrix).flatten()

    # Get indices of top N similar sections
    top_indices = np.argsort(similarities)[-top_n:][::-1]

    # Return candidate sections
    return [all_sections[i] for i in top_indices]


def build_header_index(all_sections):
    header_index = {}
    for i, section in enumerate(all_sections):
        header = section.get('normalized_header', '')
        words = set(header.split())
        for word in words:
            if word not in header_index:
                header_index[word] = []
            header_index[word].append(i)
    return header_index


def find_sections_by_header(query_section, header_index, all_sections):
    query_header = query_section.get('normalized_header', '')
    query_words = set(query_header.split())

    # Count sections that share header words
    section_counts = {}
    for word in query_words:
        if word in header_index:
            for section_idx in header_index[word]:
                section_counts[section_idx] = section_counts.get(
                    section_idx, 0) + 1

    # Sort by count of shared words
    sorted_sections = sorted(section_counts.items(),
                             key=lambda x: x[1], reverse=True)

    return [all_sections[idx] for idx, _ in sorted_sections]


def create_minhash_index(all_sections, num_perm=128):
    # Create LSH index
    lsh = datasketch.MinHashLSH(threshold=0.5, num_perm=num_perm)

    # Create MinHash for each section and add to LSH
    for i, section in enumerate(all_sections):
        text = section['normalized_output']
        # Create shingles (character n-grams)
        shingles = [text[i:i+4] for i in range(len(text)-3)]

        # Create MinHash
        m = datasketch.MinHash(num_perm=num_perm)
        for s in shingles:
            m.update(s.encode('utf-8'))

        # Add to LSH
        lsh.insert(str(i), m)

    return lsh


def query_minhash_lsh(query_section, lsh, all_sections, num_perm=128):
    text = query_section['normalized_output']

    # Create shingles
    shingles = [text[i:i+4] for i in range(len(text)-3)]

    # Create MinHash
    m = datasketch.MinHash(num_perm=num_perm)
    for s in shingles:
        m.update(s.encode('utf-8'))

    # Query LSH
    result_indices = lsh.query(m)

    # Convert indices back to sections
    return [all_sections[int(idx)] for idx in result_indices]


def build_quote_index(all_sections):
    quote_index = {}
    for i, section in enumerate(all_sections):
        tags = section.get('tags', [])
        for tag in tags:
            if tag['type'] == 'QUOTE':
                quote = tag['enclosed_text']
                if quote not in quote_index:
                    quote_index[quote] = []
                quote_index[quote].append(i)
    return quote_index


def find_sections_by_quotes(query_section, quote_index, all_sections):
    tags = query_section.get('tags', [])
    candidate_indices = set()

    for tag in tags:
        if tag['type'] == 'QUOTE':
            quote = tag['enclosed_text']
            if quote in quote_index:
                candidate_indices.update(quote_index[quote])

    return [all_sections[i] for i in candidate_indices]


def find_candidates(query_section, all_sections, indexes, max_candidates=100):
    """
    Combined approach using multiple filters to identify candidate sections

    Args:
        query_section: The section to find matches for
        all_sections: List of all potential sections
        indexes: Dict containing all precomputed indexes
        max_candidates: Maximum number of candidates to return

    Returns:
        List of candidate sections
    """
    candidates = set()

    # 1. Try exact quote matching (high precision)
    quote_candidates = find_sections_by_quotes(
        query_section, indexes['quote_index'], all_sections)
    candidates.update([section['section_id'] for section in quote_candidates])

    # 2. Try header matching
    header_candidates = find_sections_by_header(
        query_section, indexes['header_index'], all_sections)
    candidates.update([section['section_id']
                      for section in header_candidates[:50]])

    # 3. LSH for approximate matching
    lsh_candidates = query_minhash_lsh(
        query_section, indexes['lsh_index'], all_sections)
    candidates.update([section['section_id'] for section in lsh_candidates])

    # 4. TF-IDF for remaining slots
    if len(candidates) < max_candidates:
        tfidf_candidates = find_candidate_sections(
            query_section, indexes['vectorizer'], indexes['tfidf_matrix'],
            all_sections, max_candidates)

        # Add until we reach max_candidates
        for section in tfidf_candidates:
            candidates.add(section['section_id'])
            if len(candidates) >= max_candidates:
                break

    # Convert IDs back to full sections
    id_to_section = {section['section_id']: section for section in all_sections}
    return [id_to_section[section_id] for section_id in candidates]


def build_all_indexes(all_sections):
    """Build all indexes for fast retrieval"""
    indexes = {}

    # TF-IDF index
    indexes['vectorizer'], indexes['tfidf_matrix'] = build_tfidf_index(
        all_sections)

    # Header word index
    indexes['header_index'] = build_header_index(all_sections)

    # MinHash LSH index
    indexes['lsh_index'] = create_minhash_index(all_sections)

    # Quote index
    indexes['quote_index'] = build_quote_index(all_sections)

    return indexes
