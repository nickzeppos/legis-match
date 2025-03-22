# LegisMatch

## TOC

- [Objective](#objective)
- [Overview, briefly and non-ish technical](#overview-briefly-and-non-ish-technical)
- [Overview, involved and more technical](#overview-involved-and-more-technical)
  - [Parsing and Normalization](#parsing-and-normalization)
    - [XML](#xml)
    - [Text](#text)
  - [Encoding and Candidate Selection](#encoding-and-candidate-selection)
  - [Alignment Detection + Recovery](#alignment-detection--recovery)
  - [Rendering](#rendering)
- [Misc. type defs](#misc-type-defs)
- [Notes](#notes)

## Objective

**LegisMatch** is, in general, an attempt to transform partially structured legislative text (XML)[^1] into a format more convenient for analysis, especially analysis concerned with similarity between provisions found in different bills.

More precisely, you could think of it like this: Given a desired target bill _B_, containing section _S_, we want to find candidate sections _S'1_, _S'2_, ... across some universe of candidate bills _C_ that are similar to _S_. What similar means specifically is a bit unimportant right now, so just hold the general idea. [^2]

## Overview, briefly and non-ish technical

Bill text comes in as xml. Section-by-section, it passes through a series of transformations to produce a meaningful, structured representation.[^3] Normalized text properties from that output (header and body) are used to generate lookup keys for the section, which are stored alongside the rest of the parsed data.

Now that the parsed data is in the DB, we can compute section-level simlarity scores. Given a target section, we perform a two-step process: (1) retrieve _n_ candidates based on similarity computed jointly on the lookup keys, and (2) compute shared alignments between target and candidate sections.

The alignment procedure produces two things: (1) a similarity score, which is used to rank the candidates during the rendering phase, and (2) positional metadata that is used to recover the overlapping regions between the candidate and target sections in their original forms. Both are stored in the DB, sharing a link between target and candidate.

## Overview, involved and more technical

### Parsing and Normalization

#### XML

As our starting point, let's take a look at a section of a bill.[^4] Here's an example, in plain text:

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
            </subsection>
            <subsection>
                <enum>(c)</enum>
                <header>Authority</header>
                <text>This section may be carried out using any amounts authorized to be appropriated to the Secretary of State, including amounts authorized to carry out chapter 4 of part II of the Foreign Assistance Act of 1961(<external-xref legal-doc="usc" parsable-cite="usc/22/2346">22 U.S.C. 2346 et seq.<external-xref>).</text>
            </subsection>
        </section>
```

The XML provides some meaningful structural data, so let's walk through it quickly.

Currently we have special rules for handling the following XML nodes: enum, header, external-xref, quote, and quoted-block. In general, these nodes go through one of two procedures: (1) a masking procedure, where the content of the node is replaced with a special token, or (2) a tagging procedure, where the content of the node is wrapped in between a pair of special tokens, denoting begginning and end.

The intuition behind masking, as opposed to tagging is simple: if the text content is unlikely to be useful (or potentially even misleading) for the purposes of local alignment, we mask it. If the text content is likely to be useful (and potentially even more useful than other unmaksed content), we tag it. The latter is particularly important for the local alignment phase, where we can adjust similarity rewards and penalties based on whether content is occurring inside a tagged region of the text sequence.[^5]

Data representing the masking and tagging procedures is maintained moving forward, making the process reversible. Finally, the header and the text resulting from the masking and tagging procedure go through a normalization process. All of the fields pass forward in a single JSON object.

A rough type definition is as follows:

```ts
interface ParsedSection {
  section_id: string;
  section_number: number;
  header: string;
  normalized_header: string;
  masks: [
    {
      type: MaskType;
      original_text: string;
      // Given some mask type, addional props:
      // type === "DOLLAR_AMOUNT" ? => plain_language_number: string;
      // type === "INTERNAL_XREF" ? => parsable_cite: string;
    }
  ];
  tags: [
    {
      type: TagType;
      enclosed_text: string;
      // Given some tag type, additional props:
      // type === "KEY_TERM" ? => object_responsible: string;
      // type === "EXTERNAL_XREF" ? => legal_doc: LegalDocAttributeType;
      // type === "EXTERNAL_XREF" ? => parsable_cite: string;
      // type === "ENTITY" ? => expanded_form: string;
      // type === "QUOTE" ? => amendatory_op: 'strike' | 'insert'
      // type === "QUOTE" ? => parsable_xref: string;
      // type === "QUOTED_BLOCK" ? => amendatory_op: 'strike' | 'insert'
      // type === "QUOTED_BLOCK" ? => parsable_xref: string;
    }
  ];
  output: string;
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
    { "type": "ENUM", "original_text": "(1)" },
    { "type": "ENUM", "original_text": "(c)" }
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

#### Text

**TODO**

The general thrust here is that there are meaningful things still in the text that the xml schema does not make explicit. You acn see hints of this in the unimplemented values of the `MaskType` and `TagType` type definitions, in the [types](#types) section. So, we have to try to do whatever additional tagging and masking we want by some other means. In general, I have approached this problem in the past by hand-tagging and training a model. That's sort of what I plan to do for this project, but I think I'm going to do it in a phased way. For now, I'm going to just skip it and see how the outputs look without this additoinal parsing. If we're underperforming or whenver I get to this point of the work, I'll drop-in LLM's functioning as approximate autogregressive classifiers. Then, if that's not working or prohibitevly expensive, or whenever I have the time, I'll actually go train the models.

### Encoding and Candidate Selection

The data payload described above is stored in a DB, alongside two lookup keys: one corresponding to the normalized header, and the other corresponding to the normalized output. The lookup keys are generated by passing the normalized header and output fields to a BERT-based embedding model. Embeddings are stored alongside the data payload in the DB.

Since we have embedding vectors, the candidate selection method is pretty simple: Given a target section _S_, the system retrieves _n_ candidate sections _S'1_, _S'2_, ... _S'n_ based on cosine similarity computed on the lookup keys.[^6]

### Alignment Detection + Recovery

With target and a tractable number of candidates in hand, we're free to compute alignment scores in complex time (i.e., a sequence-based approach, like smith-waterman). Our implementation uses affine gap penalties (different costs for opening vs. extending gaps) and applies custom match boosting for domain-specific features like quoted or quoted-block content. Our penalty/reward weights follow the Wilkerson (2015) variation on local alignment.

The alignment procedure also produces positional data, which can be used to recover the original text of the candidate section for the front-end.

Alignment scores and positional metadata are persisted, so we don't have to re-compute on user request.

### Rendering

**TODO**

Our DB now has, for a bill and its sections, a set of high-ranking candidate sections and their pre-computed alignment scores, along with positional metadata to help us render the overlapping regions.

First run of this is just going to be text-based, two columns. Very much just like a document diff tool, with colored highlighting, and the ability to cycle through the candidate sections for a given target section. Only difference is that the underlying diff function is a bit more sophisticated.

I do want to build this out a bit, and the positional data I'm forwarding right now is not super complex. Ideally, I'd like overlapping regions to be highlighted in a way that reflects the chain of computation under the alignment score. I.e., lightening the hue over portions of the aligned region where penalties are introduced, and so on. But that's for later.

### Types

```ts
type MaskType =
  | "ENUM"
  | "INTERNAL_XREF" // TODO
  | "DOLLAR_AMOUNT" // TODO
  | "DATE"; // TODO
type TagType =
  | "QUOTE"
  | "EXTERNAL_XREF"
  | "QUOTED-BLOCK"
  | "ENTITY" // TODO
  | "KEY_TERM" // TODO
  | "DEADLINE"; // TODO

type LegalDocAttributeType =
  // For us, almost always "usc" | "public-law" | "statute-at-large"
  | "usc"
  | "public-law"
  | "statute-at-large"
  | "bill"
  | "act"
  | "executive-order"
  | "regulation"
  | "senate-rule"
  | "house-rule"
  | "treaty-ust"
  | "treaty-tias"
  | "usc-appendix"
  | "usc-act"
  | "usc-chapter"
  | "usc-subtitle";
```

## Notes

[^1]: You can read more about the XML schema at [xml.house.gov](https://xml.house.gov/).
[^2]: One of the goals of the project is to be able to iteratively define simlarity in two directions: (1) on the functional side, i.e., different similarity metrics and weights, and (2) on the data side, to manipulate combinations of inputs.
[^3]: Why have a chosen a section, as opposed higher (title) or lower (paragraph) level of granularity? The answer is that it's an arbitrary decision, so I want to flag it as such! Sections are the unit of analysis I'm comitting to, but am totally open to rethinking this decision.
[^4]: For the most part, this is one of the places where we're doing a lot of our original thinking, the other being a how we approach local alignment, provided this parsed object. After parsing, a lot of our pre-rendering work uses "off the shelf" solutions (pre-trained BERT embeddings, cosine similarity, LSH, etc.).
[^5]: By example, content contained in an <enum> node is unlikely to be meaningful for local alignment. That something is some specific subsection or paragraph is a function of the larger document it is occurring in, and does not correlate to a change in the function of the section itself. So, we mask enum nodes. On the other hand, content contained in a <quote> node is very likely to be meaningful for local alignment. <quote> nodes often co-occur with amendatory operations. If two sections are making changes with similar or shared language to extant law, it's very notable! So, we tag quote nodes.
[^6]: Can be sped using LSH indexing, but that's a method to grapple with scale, so will remain a TODO during prototyping.
