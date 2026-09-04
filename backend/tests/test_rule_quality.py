"""Tests for the deterministic rule validator — the gate that keeps rules specific."""

from app.services.rule_quality import (
    backfill,
    balance_teams,
    build_entity_index,
    is_near_duplicate,
    mentions_entity,
    unknown_proper_nouns,
    validate_rules,
)

ENTITIES = [
    "Paul Atreides", "Chani", "Jessica", "Stilgar", "Feyd-Rautha",
    "Fremen", "Arrakis", "Sietch Tabr", "Water of Life", "sandworm",
    "sandstorm", "desert", "spice", "Bene Gesserit", "Voice",
]


def _descs(rules):
    return [r["description"] for r in rules]


def test_good_rules_all_pass():
    good = [
        "A sandworm appears on screen.",
        "Chani rolls her eyes at the prophecy.",
        "Stilgar calls Paul Atreides a sign.",
        "Feyd-Rautha kills someone with a blade.",
        "Jessica speaks with the Bene Gesserit Voice.",
        "Someone says the word 'spice'.",
        "A sandstorm sweeps the desert.",
        "The Water of Life is drunk.",
    ]
    accepted, rejections = validate_rules(
        {"rules": [{"team": 0, "description": d} for d in good]}, ENTITIES
    )
    assert len(accepted) == 8, rejections
    assert not rejections


def test_generic_filler_is_rejected():
    """The exact bland rules the old fallback list served must not survive."""
    bad = [
        "Drink whenever the music swells dramatically.",
        "Drink whenever there's a dramatic pause.",
        "Drink every time there's a close-up shot.",
        "Drink whenever the scene changes location.",
        "Drink when the title character appears on screen.",
        "Drink whenever a phone rings or buzzes.",
    ]
    accepted, rejections = validate_rules(
        {"rules": [{"team": 0, "description": d} for d in bad]}, ENTITIES
    )
    assert accepted == []
    assert len(rejections) == len(bad)


def test_rule_naming_nothing_real_is_rejected():
    accepted, rejections = validate_rules(
        {"rules": [{"team": 0, "description": "Someone opens a door."}]}, ENTITIES
    )
    assert accepted == []
    assert rejections[0][0] == "no-entity"


def test_invented_character_is_rejected():
    """Anti-hallucination: a real entity does not license an invented name."""
    accepted, rejections = validate_rules(
        {"rules": [{"team": 0, "description": "Paul Atreides duels Jamis."}]},
        ENTITIES,
        plot="Paul leads the Fremen against the Harkonnens on Arrakis.",
    )
    assert accepted == []
    assert rejections[0][0].startswith("invented-name")


def test_name_present_in_plot_is_allowed():
    accepted, _ = validate_rules(
        {"rules": [{"team": 0, "description": "Paul Atreides duels Jamis."}]},
        ENTITIES,
        plot="Paul kills Jamis in a duel and joins the Fremen.",
    )
    assert len(accepted) == 1


def test_compound_and_unrepeatable_rules_are_rejected():
    for desc in (
        "Paul Atreides rides a sandworm and the Fremen cheer loudly.",
        "Chani speaks after Stilgar finishes his prayer.",
        "Paul Atreides rides a sandworm for the first time.",
    ):
        accepted, rejections = validate_rules(
            {"rules": [{"team": 0, "description": desc}]}, ENTITIES
        )
        assert accepted == [], desc
        assert rejections, desc


def test_overlong_rule_is_rejected():
    long = "Paul Atreides " + "rides across the endless desert of Arrakis " * 3
    accepted, rejections = validate_rules(
        {"rules": [{"team": 0, "description": long}]}, ENTITIES
    )
    assert accepted == []
    assert rejections[0][0] == "length"


def test_unsafe_rule_is_rejected():
    accepted, rejections = validate_rules(
        {"rules": [{"team": 0, "description": "Chani appears, finish your drink."}]},
        ENTITIES,
    )
    assert accepted == []
    assert rejections[0][0].startswith("unsafe")


def test_near_duplicates_are_dropped():
    dupes = [
        {"team": 0, "description": "A sandworm appears on screen."},
        {"team": 1, "description": "A sandworm appears on the screen!"},
    ]
    accepted, rejections = validate_rules({"rules": dupes}, ENTITIES)
    assert len(accepted) == 1
    assert rejections[0][0] == "near-duplicate"


def test_partial_set_is_kept_not_discarded():
    """Five good specific rules must beat eight generic ones."""
    mixed = [
        {"team": 0, "description": "A sandworm appears on screen."},
        {"team": 0, "description": "Drink when the music swells."},
        {"team": 0, "description": "Chani draws her knife."},
    ]
    accepted, rejections = validate_rules({"rules": mixed}, ENTITIES)
    assert len(accepted) == 2
    assert len(rejections) == 1


def test_backfill_tops_up_to_eight_and_stays_specific():
    accepted, _ = validate_rules(
        {"rules": [{"team": 0, "description": "A sandworm appears on screen."}]},
        ENTITIES,
    )
    filled = backfill(accepted, ENTITIES, target=8)
    assert len(filled) == 8
    index = build_entity_index(ENTITIES)
    for r in filled:
        assert mentions_entity(r["description"], index), r


def test_teams_are_always_balanced():
    rules = [{"team": 0, "description": f"Rule {i}"} for i in range(8)]
    balanced = balance_teams(rules)
    assert sum(1 for r in balanced if r["team"] == 0) == 4
    assert sum(1 for r in balanced if r["team"] == 1) == 4


def test_odd_count_never_produces_half_a_team():
    balanced = balance_teams([{"team": 0, "description": f"R{i}"} for i in range(7)])
    assert len(balanced) % 2 == 0
    assert sum(1 for r in balanced if r["team"] == 0) == len(balanced) // 2


def test_partial_name_matches_full_entity():
    index = build_entity_index(ENTITIES)
    assert mentions_entity("Atreides raises a fist.", index)


def test_common_capitalised_words_are_not_flagged_as_invented():
    index = build_entity_index(ENTITIES)
    assert unknown_proper_nouns("Chani says A word to Stilgar.", index) == []


def test_is_near_duplicate_allows_distinct_rules():
    assert not is_near_duplicate(
        "Chani draws her knife.", ["A sandworm appears on screen."]
    )
