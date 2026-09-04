import argparse
import json
from pathlib import Path

import genanki

# ============================================================
# CONFIG
# ============================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
SENTENCES_DIR = REPO_ROOT / "output" / "sentences"
DECKS_DIR = REPO_ROOT / "output" / "decks"

JLPT_LEVELS = ("1", "2", "3", "4", "5")

# Fixed IDs so re-running this script updates existing notes/decks in
# Anki instead of creating duplicates. Do not change these.
MODEL_ID = 1205482600
DECK_ID_BASE = 1120821691

MODEL = genanki.Model(
    MODEL_ID,
    "JLPT Sentence",
    fields=[
        {"name": "Japanese"},
        {"name": "Reading"},
        {"name": "English"},
    ],
    templates=[
        {
            "name": "Recognition",
            "qfmt": '<div class="japanese">{{Japanese}}</div>',
            "afmt": (
                '<div class="japanese">{{Japanese}}</div>'
                '<hr id="answer">'
                '<div class="reading">{{Reading}}</div>'
                '<div class="english">{{English}}</div>'
            ),
        },
    ],
    css=(
        ".card { text-align: center; font-size: 20px; }\n"
        ".japanese { font-size: 32px; }\n"
        ".reading { color: #888; margin-top: 8px; }\n"
        ".english { margin-top: 8px; }\n"
    ),
)


# ============================================================
# BUILD
# ============================================================

def build_reading(tokens):
    """
    Reconstruct a whole-sentence reading by concatenating each token's
    reading in order (punctuation is already stripped out upstream by
    the fetch pipeline's tokenizer).
    """

    return "".join(token["reading"] for token in tokens)


def build_deck(level):
    sentences_file = SENTENCES_DIR / f"N{level}_sentences.json"

    if not sentences_file.exists():
        raise FileNotFoundError(
            f"{sentences_file} not found — run fetch/fetch_sentence.py --level {level} first."
        )

    with open(sentences_file, encoding="utf-8") as f:
        sentences = json.load(f)

    deck = genanki.Deck(
        DECK_ID_BASE + int(level),
        f"JLPT N{level} Sentence Reading",
    )

    for item in sentences:

        note = genanki.Note(
            model=MODEL,
            fields=[
                item["japanese"],
                build_reading(item["tokens"]),
                item["english"] or "",
            ],
            guid=genanki.guid_for(item["id"]),
        )

        deck.add_note(note)

    DECKS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = DECKS_DIR / f"N{level}.apkg"

    genanki.Package(deck).write_to_file(output_file)

    print(f"Saved {len(sentences)} cards to {output_file}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Build an Anki deck (.apkg) from a fetched JLPT sentence file.",
    )
    parser.add_argument(
        "--level",
        choices=JLPT_LEVELS,
        default="5",
        help="JLPT level to build a deck for (1 = hardest, 5 = easiest). Default: 5.",
    )
    args = parser.parse_args()

    build_deck(args.level)
