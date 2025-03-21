# LegisMatch

## Objective

**LegisMatch** is, in general, an attempt to transform partially structured legislative text (XML)[^1] into a format more convenient for analysis, especially analysis concerned with similarity between provisions found in different bills.

More precisely, you could think of it like this: Given a desired target bill _B_, containing section _S_, we want to find candidate sections _S'1_, _S'2_, ... across some universe of candidate bills _C_ that are similar to _S_. What similar means specifically is a bit unimportant right now, so just hold the general idea in your mind. [^2]

## Overview, briefly and non-ish technical

Bill text comes in as xml. Section-by-section, it passes through a series of transformations to produce a meaningful structured representation.[^3] Part of that output is used to generate lookup keys for the section, which are stored alongside the full payload in a DB.

When a user selects a candidate section, the system performs a two-step process: (1) it retreives _n_ candidates based on similarity computed on the lookup keys, and THEN (2) it computes sequence based similarity between the target and each candidate section. These two steps can be thought of as using two different forms of similarity: (1) cheap and (2) expensive.

## Overview, involved and more technical

### Parsing and Normalization

As our starting piont, let's take a look at a section of a bill. Here's an example, in plain text:

```text
2. Establishment of an ASEAN Center
    (a) Defined term
        In this section, the term "ASEAN" means the Association of Southeast Asian Nations.
    (b) Functions
        Notwithstanding any other provision of law, Secretary of State and the US-ASEAN Center established pursuant to subsection (b) may—
            (1) provide grants for research to support and elevate the importance of the US-ASEAN partnership;
    (c) Authority
        This section may be carried out using any amounts authorized to be appropriated to the Secretary of State, including amounts authorized to carry out chapter 4 of part II of the Foreign Assistance Act of 1961 (22 U.S.C. 2346 et seq.).
```

What does that look like in XML?

```xml
        <section id="HB98E4FFBE5B2435DBA88C41603D1B6A5">
            <enum>2.</enum>
            <header>Establishment of an ASEAN Center</header>
            <subsection>
                <enum>(a)</enum>
                <header>Defined term</header>
                <text>In this section, the term <quote>ASEAN</quote> means the Association of Southeast Asian Nations.</text>
            </subsection>
            <subsection>
                <enum>(b)</enum>
                <header>Functions</header>
                <text>Notwithstanding any other provision of law, Secretary of State and the US-ASEAN Center established pursuant to subsection (b) may—</text>
                <paragraph>
                    <enum>(1)</enum>
                    <text>provide grants for research to support and elevate the importance of the US-ASEAN partnership;</text>
                </paragraph>
            <subsection>
                <enum>(c)</enum>
                <header>Authority</header>
                <text>This section may be carried out using any amounts authorized to be
                    appropriated to the Secretary of State, including amounts authorized to carry
                    out chapter 4 of part II of the Foreign Assistance Act of 1961 (<external-xref legal-doc="usc" parsable-cite="usc/22/2346">22 U.S.C. 2346 et seq.<external-xref>).</text>
            </subsection>

        </section>
```

The XML provides some meaningful structural data, so let's walk through it quickly.

Currently we have special rules for handling the following XML nodes: enum, header, external-xref, quote. In general, these nodes go through one of two procedures: (1) a masking procedure, where the content of the node is replaced with a special token, or (2) a tagging procedure, where the content of the node is wrapped in between a pair of special tokens, denoting begginning and end.

Data representing the masking and tagging procedures is maintained moving forward, making the process reversible. Finally, the header and the text resulting from the masking and tagging procedure go through a normalization process. All of the fields pass forward in a single JSON object. A rough type definition is as follows:

```ts
interface ParsedSection {
  // id attribute for the parent section node
  section_id: string;
  // section number in full bill, provided by the first enum node encountered
  section_number: number;
  // section header
  header: string;
  // section header, normalized
  normalized_header: string;
  // masks applied to the section text
  masks: [
    {
      // Internal xrefs unimplemented
      type:
        | "ENUM"
        | "INTERNAL_XREF" // TODO
        | "DEADLINE" // TODO
        | "DATE"; // TODO

      original_text: string;
    }
  ];
  // tags applied to the section text
  tags: [
    {
      type:
        | "QUOTE"
        | "EXTERNAL_XREF"
        | "QUOTED-BLOCK"
        | "DOLLAR_AMOUNT" // TODO
        | "KEY_TERM" // TODO
        | "ENTITY"; // TODO
      enclosed_text: string;

      // type == "QUOTE"
      associated_amendatory_operation: Optional<"strike" | "insert">;

      // type === "EXTERNAL_XREF"
      legal_doc: Optional<"usc" | "statute" | "code">;
      parsable_cite: Optional<string>;

      // type === "KEY_TERM"
      object_responsible: Optional<string>;
    }
  ];
  // section text, with masks and tags applied
  output: string;
  // section text, with masks and tags applied, normalized
  normalized_output: string;
}
```

The output, given the XML content introduced above, looks like this:

```json
{
  "section_id": "HB98E4FFBE5B2435DBA88C41603D1B6A5",
  "section_number": 2,
  "header": "Establishment of an ASEAN Center",
  "normalized_header": "establishment of an asean center",
  "masks": [
    { "type": "ENUM", "original_text": "(a)" },
    { "type": "ENUM", "original_text": "(b)" },
    { "type": "ENUM", "original_text": "(c)" },
    { "type": "ENUM", "original_text": "(1)" },
    { "type": "ENUM", "original_text": "(2)" },
    { "type": "ENUM", "original_text": "(3)" },
    { "type": "ENUM", "original_text": "(4)" },
    { "type": "ENUM", "original_text": "(5)" },
    { "type": "ENUM", "original_text": "(6)" },
    { "type": "ENUM", "original_text": "(d)" },
    { "type": "ENUM", "original_text": "(e)" }
  ],
  "tags": [
    { "type": "QUOTE", "enclosed_text": "ASEAN" },
    {
      "type": "EXTERNAL_XREF",
      "enclosed_text": "22 U.S.C. 2346 et seq.",
      "legal_doc": "usc",
      "parsable_cite": "usc/22/2346"
    }
  ],
  "output": "MASK_ENUM Defined term In this section, the term <QUOTE>ASEAN</QUOTE> means the Association of Southeast Asian Nations. MASK_ENUM Functions Notwithstanding any other provision of law, Secretary of State and the US-ASEAN Center established pursuant to subsection (b) may— MASK_ENUM provide grants for research to support and elevate the importance of the US-ASEAN partnership; Authority This section may be carried out using any amounts authorized to be appropriated to the Secretary of State, including amounts authorized to carry out chapter 4 of part II of the Foreign Assistance Act of 1961 (<EXTERNAL_XREF>22 U.S.C. 2346 et seq.</EXTERNAL_XREF>).",
  "normalized_output": "defined term in this section the term <QUOTE>ASEAN</QUOTE> means the association of southeast asian nations. functions notwithstanding any other provision of law secretary of state and the us-asean center established pursuant to subsection b may— provide grants for research to support and elevate the importance of the us-asean partnership authority this section may be carried out using any amounts authorized to be appropriated to the secretary of state including amounts authorized to carry out chapter 4 of part ii of the foreign assistance act of 1961 <EXTERNAL_XREF>22 U.S.C. 2346 et seq.</EXTERNAL_XREF>."
}
```

### Encoding and Candidate Selection

The data payload described above is stored in a DB, alongside two lookup keys: one corresponding to the normalized header, and the other corresponding to the normalized output. The lookup keys are generated by passing the normalized header and output fields to a BERT-based embedding model. Embeddings are stored alongside the data payload in the DB.

Since we have embedding vectors, the candidate selection method is pretty simple: Given a target section _S_, the system retrieves _n_ candidate sections _S'1_, _S'2_, ... _S'n_ based on cosine similarity computed on the lookup keys.[^4]

### Alignment Detection + Recovery

With target and a tractable number of candidates in hand, we're free to compute alignment scores in complex time (i.e., a sequence-based approach, like smith-waterman). Our implementation uses affine gap penalties (different costs for opening vs. extending gaps) and applies custom match boosting for domain-specific features like quoted or quoted-block content. Our penalty/reward weights follow the Wilkerson (2015) variation on local alignment.

The alignment procedure also produces positional data, which can be used to recover the original text of the candidate section for the front-end.

Alignment scores and positional metadata are persisted, so we don't have to re-compute on user request.

### Rendering

TODO

## Notes

[^1]: You can read more about the XML schema at [xml.house.gov](https://xml.house.gov/).  
[^2]: One of the goals of the project is to be able to iteratively define simlarity in two directions: (1) on the functional side, i.e., different similarity metrics and weights, and (2) on the data side, to manipulate combinations of inputs.  
[^3]: Why have a chosen a section, as opposed higher (title) or lower (paragraph) level of granularity? The answer is that it's an arbitrary decision, so I want to flag it as such! Sections are the unit of analysis I'm comitting to, but am totally open to rethinking this decision.  
[^4]: Can be sped using LSH indexing, but that's a method to grapple with scale, so will remain a TODO during prototyping.
