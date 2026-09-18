"""Smoke tests for the Turtle subset parser."""

from __future__ import annotations

import os
import tempfile
import unittest

from consult.turtle import iter_triples, local_name, synset_id_from


SAMPLE = """
@prefix own-pt: <https://w3id.org/own/own-pt/instances/> .
@prefix owns: <https://w3id.org/own/schema/> .

own-pt:word-casa-n a owns:Word ;
    owns:lemma "casa"@pt ;
    owns:pos "n" .

own-pt:synset-00001740-n a owns:BaseConcept,
        owns:NounSynset ;
    owns:gloss "o que é percebido."@pt,
        "segunda glosa"@pt ;
    owns:example "Uma casa."@pt ;
    owns:synsetId "00001740-n" .

own-pt:synset-00001740-n owns:containsWordSense own-pt:wordsense-00001740-n-1,
        own-pt:wordsense-00001740-n-2 .

own-pt:synset-00003316-v owns:hyponymOf own-pt:synset-00005041-v .
"""


class TurtleParserTest(unittest.TestCase):
    def test_sample_triples(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".ttl", delete=False) as handle:
            handle.write(SAMPLE)
            path = handle.name
        try:
            triples = list(iter_triples(path))
        finally:
            os.remove(path)

        lemmas = [obj for subj, pred, obj in triples if pred == "owns:lemma"]
        self.assertEqual(lemmas, [("casa", "pt")])

        types = [local_name(obj) for subj, pred, obj in triples if pred == "a" and isinstance(obj, str)]
        self.assertIn("Word", types)
        self.assertIn("BaseConcept", types)
        self.assertIn("NounSynset", types)

        glosses = [obj[0] for subj, pred, obj in triples if pred == "owns:gloss"]
        self.assertEqual(glosses, ["o que é percebido.", "segunda glosa"])

        senses = [local_name(obj) for subj, pred, obj in triples if pred == "owns:containsWordSense"]
        self.assertEqual(senses, ["wordsense-00001740-n-1", "wordsense-00001740-n-2"])

        rels = [(local_name(subj), local_name(obj)) for subj, pred, obj in triples if pred == "owns:hyponymOf"]
        self.assertEqual(rels, [("synset-00003316-v", "synset-00005041-v")])
        self.assertEqual(synset_id_from("own-pt:wordsense-00001740-n-1"), "00001740-n")


if __name__ == "__main__":
    unittest.main()
