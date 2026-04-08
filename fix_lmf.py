#!/usr/bin/env python3
"""Post-process pyown LMF output: fix reversed hypernym/hyponym relations
and upgrade DOCTYPE declaration to WN-LMF-1.4."""

import sys
from lxml import etree

# pyown maps hyponymOf→"hyponym" and hypernymOf→"hypernym", but in WN-LMF the
# relType describes the relation FROM the source TO the target.  A synset that
# "hyponymOf B" is more specific than B, so B is its hypernym; the relation
# FROM that synset TO B should therefore be "hypernym", not "hyponym".
SWAP_MAP = {
    "hypernym":          "hyponym",
    "hyponym":           "hypernym",
    "instance_hypernym": "instance_hyponym",
    "instance_hyponym":  "instance_hypernym",
}

DOCTYPE_14 = (
    "<!DOCTYPE LexicalResource SYSTEM "
    "'https://globalwordnet.github.io/schemas/WN-LMF-1.4.dtd'>"
)


def fix_lmf(input_path: str, output_path: str) -> None:
    tree = etree.parse(input_path)
    root = tree.getroot()

    for elem in root.iter("SynsetRelation"):
        rel_type = elem.get("relType")
        if rel_type in SWAP_MAP:
            elem.set("relType", SWAP_MAP[rel_type])

    xml_bytes = etree.tostring(
        root,
        encoding="UTF-8",
        pretty_print=True,
        xml_declaration=True,
        doctype=DOCTYPE_14,
    )
    with open(output_path, "wb") as fh:
        fh.write(xml_bytes)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} INPUT.xml OUTPUT.xml", file=sys.stderr)
        sys.exit(1)
    fix_lmf(sys.argv[1], sys.argv[2])
