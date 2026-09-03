import argparse
import json
import re
from pathlib import Path

from sudachipy import Dictionary, SplitMode

# ============================================================
# CONFIG
# ============================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

KANJI_FILE = DATA_DIR / "kanjis.json"
VOCAB_FILE = DATA_DIR / "vocab.json"
GRAMMAR_FILE = DATA_DIR / "grammar.json"
EXCEPTIONS_FILE = DATA_DIR / "exceptions.json"

JLPT_LEVELS = ("1", "2", "3", "4", "5")

# Tokens with these part-of-speech tags are grammatical scaffolding
# (particles, auxiliary verbs), not vocabulary.
GRAMMATICAL_POS = {"助詞", "助動詞"}

# Proper nouns (place/personal names, etc.) aren't part of any JLPT
# kanji/vocabulary list, but are routinely used at every level.
PROPER_NOUN_POS = "固有名詞"

# Tokens that carry no lexical or grammatical meaning for our purposes.
IGNORED_POS = {"補助記号", "空白", "記号"}

KANJI_RE = re.compile(r"[一-龯々]")

_tokenizer = Dictionary().create()


# ============================================================
# HELPERS
# ============================================================

def normalize_reading(reading):
    """Convert a katakana reading (as returned by Sudachi) to hiragana."""
    return "".join(
        chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c
        for c in reading
    )


def get_kanji(text):
    return set(KANJI_RE.findall(text))


# ============================================================
# LOAD JLPT DATA
# ============================================================

def load_jlpt_data(level):
    """
    Load kanji/vocab/grammar/exceptions for a single JLPT level
    ("1" through "5", 5 being the easiest).
    """

    level = str(level)

    if level not in JLPT_LEVELS:
        raise ValueError(f"Unknown JLPT level: {level!r} (expected one of {JLPT_LEVELS})")

    with open(KANJI_FILE, encoding="utf-8") as f:
        kanji_data = json.load(f)

    with open(VOCAB_FILE, encoding="utf-8") as f:
        vocab_data = json.load(f)

    with open(GRAMMAR_FILE, encoding="utf-8") as f:
        grammar_data = json.load(f)

    with open(EXCEPTIONS_FILE, encoding="utf-8") as f:
        exceptions_data = json.load(f)

    kanji = set(kanji_data[level])

    # Sudachi resolves a surface form to a single canonical reading, which
    # doesn't necessarily match the reading that puts a word at this level
    # (e.g. 私 is N5 as わたし but N1 as あたし; 明日 is N5 as あした but
    # N4 as あす). We can't reliably recover which reading was intended
    # from the surface text alone, so words are matched here regardless
    # of reading.
    vocab = set(vocab_data[level].keys())

    # Flatten every grammar category (copula, polite_verbs,
    # basic_particles, basic_patterns, ...) into one lookup set.
    grammar = set()
    for entries in grammar_data.get(level, {}).values():
        grammar.update(entries)

    # Words that should count as vocabulary for this level even though
    # they aren't (yet) in vocab.json's list for it (e.g. 何時, only
    # listed under N1, is a named N5 exception). Keyed by word only (see
    # the note above on why the reading isn't used to gate the match) but
    # the reading is kept here for reference/debugging.
    exceptions = {
        entry["word"]: entry["reading"]
        for entry in exceptions_data.get(level, [])
    }

    return {
        "level": level,
        "kanji": kanji,
        "vocab": vocab,
        "grammar": grammar,
        "exceptions": exceptions,
    }


# ============================================================
# TOKENIZATION
# ============================================================

def tokenize(sentence):
    """
    Tokenize a sentence once, returning the lexical morphemes used by
    every check below (kanji, vocab, grammar).
    """

    morphemes = _tokenizer.tokenize(sentence, SplitMode.C)

    tokens = []

    for m in morphemes:

        pos = m.part_of_speech()

        if pos[0] in IGNORED_POS:
            continue

        tokens.append({
            "surface": m.surface(),
            "dictionary": m.dictionary_form(),
            "reading": normalize_reading(m.reading_form()),
            "pos": pos,
        })

    return tokens


def _is_known_word(token, data):
    words = (token["dictionary"], token["surface"])
    return any(w in data["vocab"] or w in data["exceptions"] for w in words)


# ============================================================
# CHECKS
# ============================================================

def check_kanji(tokens, data):
    """
    Every kanji used must belong to this level's kanji list, unless the
    word it's part of is itself vocabulary for this level (e.g. 私 at N5)
    or a named exception (e.g. 何時 at N5) — a word can be taught at a
    given level while using a kanji that, in isolation, is classified
    above it. Proper nouns (place/personal names) aren't covered by any
    JLPT kanji list and are exempted.
    """

    for token in tokens:

        if token["pos"][1] == PROPER_NOUN_POS:
            continue

        if _is_known_word(token, data):
            continue

        kanji = get_kanji(token["surface"])

        if not kanji.issubset(data["kanji"]):
            return False

    return True


def check_vocab(tokens, data):
    """
    Every content word must be vocabulary for this level (by dictionary
    form or surface form) or a named exception, whether or not it's
    written with kanji — a hiragana word (e.g. すばしっこい, じょうぶ) can
    be well above this level too. Grammatical tokens are left to
    check_grammar.
    """

    for token in tokens:

        if token["pos"][0] in GRAMMATICAL_POS:
            continue

        if token["pos"][1] == PROPER_NOUN_POS:
            continue

        if _is_known_word(token, data):
            continue

        return False

    return True


def check_grammar(tokens, data):
    """
    Every particle/auxiliary-verb token must be within this level's
    grammar (data/grammar.json), covering copula, polite verb endings,
    basic particles and basic patterns.
    """

    for token in tokens:

        if token["pos"][0] not in GRAMMATICAL_POS:
            continue

        if token["surface"] in data["grammar"] or token["dictionary"] in data["grammar"]:
            continue

        return False

    return True


def is_jlpt_sentence(sentence, data):
    """
    Returns (accepted: bool, reason: str | None, tokens: list) for the
    JLPT level `data` was loaded with (see load_jlpt_data).
    """

    tokens = tokenize(sentence)

    if not check_kanji(tokens, data):
        return False, "kanji", tokens

    if not check_vocab(tokens, data):
        return False, "vocab", tokens

    if not check_grammar(tokens, data):
        return False, "grammar", tokens

    return True, None, tokens


# ============================================================
# SELF-TEST
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Check sample sentences against a JLPT level's kanji/vocab/grammar.",
    )
    parser.add_argument(
        "--level",
        choices=JLPT_LEVELS,
        default="5",
        help="JLPT level to check against (1 = hardest, 5 = easiest). Default: 5.",
    )
    args = parser.parse_args()

    data = load_jlpt_data(args.level)

    samples = [
        "明日、東京に行きます。",
        "何時に来ますか。",
        "私はご飯を食べたいです。",
        "これは新しい問題を解決しなければならない。",
    ]

    print(f"Checking against N{data['level']}\n")

    for sentence in samples:
        accepted, reason, tokens = is_jlpt_sentence(sentence, data)
        status = "OK" if accepted else f"REJECTED ({reason})"
        print(f"{sentence}  ->  {status}")
