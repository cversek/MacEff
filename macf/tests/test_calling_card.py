"""The calling card's rules, one test per requirement (MIS-0002-R157 to R166).

R162 (a new account takes the lowercased card) is tested in test_homes.py, beside minting ahead
and the homes volume's marker that it needs.
"""
import pytest

from macf import calling_card as cc
from macf.calling_card import CardError

UUID = "0A1B2C3D-4E5F-6789-ABCD-EF0123456789"


def test_card_is_name_underscore_shortid():
    """R157: the agent's name, one underscore, the short id; capitals kept."""
    assert cc.build("ExampleAgent", UUID) == "ExampleAgent_0a1b2c"
    assert cc.is_card("ExampleAgent_0a1b2c")
    assert not cc.is_card("ExampleAgent@0a1b2c")


@pytest.mark.parametrize("name, ok", [
    ("E", True), ("Example2Agent", True), ("A" + "b" * 23, True),
    ("A" + "b" * 24, False), ("Example_Agent", False), ("Example-Agent", False),
    ("Example@Agent", False), ("2Example", False), ("Zoë", False), ("", False),
])
def test_name_is_a_letter_then_at_most_23_letters_or_digits(name, ok):
    """R158: one ASCII letter, then at most 23 ASCII letters or digits."""
    assert (cc.name_problem(name) is None) is ok
    if not ok:
        with pytest.raises(CardError):
            cc.build(name, UUID)


def test_shortid_is_the_first_six_hex_of_the_identity_file():
    """R159: the first six hexadecimal characters of the identity file, in lowercase."""
    assert cc.split(cc.build("ExampleAgent", UUID)) == ("ExampleAgent", "0a1b2c")
    with pytest.raises(CardError, match="hexadecimal"):
        cc.build("ExampleAgent", "not-a-uuid")


def test_case_sensitive_names_keep_the_card_exactly():
    """R160: a launchd label, unit name, path, socket or record takes the card exactly."""
    from macf.pd.names import pd_id
    card = "ExampleAgent_0a1b2c"
    assert cc.derived(card) == card
    assert pd_id(card) == card


def test_lowercase_targets_take_the_card_lowercased():
    """R161: a Unix account or a mail local part takes the card lowercased, nothing else."""
    assert cc.lowercase("ExampleAgent_0a1b2c") == "exampleagent_0a1b2c"


def test_dns_label_replaces_only_the_underscore():
    """R163: the lowercased card, with its underscore replaced by a hyphen."""
    assert cc.dns_label("ExampleAgent_0a1b2c") == "exampleagent-0a1b2c"
    with pytest.raises(CardError):
        cc.dns_label("ExampleAgent@0a1b2c")


def test_a_declared_card_compares_without_case():
    """R164: what is declared or configured compares without regard to case."""
    assert cc.read_declared("exampleagent_0A1B2C") == "exampleagent_0A1B2C"
    assert cc.same("exampleagent_0A1B2C", "ExampleAgent_0a1b2c")
    assert not cc.same("ExampleAgent_0a1b2d", "ExampleAgent_0a1b2c")


@pytest.mark.parametrize("text, says", [
    ("ExampleAgent@0a1b2c", "old calling-card form: write it as ExampleAgent_0a1b2c"),
    ("ExampleAgent", "expected Name_shortid"),
    ("Example_Agent_0a1b2c", "expected Name_shortid"),
])
def test_a_declared_card_in_another_form_is_refused(text, says):
    """R165: any other form is refused, the old one included, naming the form expected."""
    with pytest.raises(CardError, match=says):
        cc.read_declared(text)


def test_stored_history_maps_the_old_form():
    """R166: a reader of history maps Name@shortid to Name_shortid rather than refuse it."""
    assert cc.from_history("ExampleAgent@0a1b2c") == "ExampleAgent_0a1b2c"
    assert cc.from_history("ExampleAgent_0a1b2c") == "ExampleAgent_0a1b2c"
    assert cc.from_history("ExampleAgent@unknown") == "ExampleAgent_unknown"
    assert cc.from_history("not a card") == "not a card"
    # How every reader of the event log asks: an old record still names its agent.
    assert cc.is_agent("ExampleAgent@0a1b2c", "ExampleAgent_0a1b2c")
    assert cc.is_agent("ExampleAgent_0a1b2c", "ExampleAgent_0a1b2c")
    assert not cc.is_agent("OtherAgent@0a1b2c", "ExampleAgent_0a1b2c")
    assert not cc.is_agent(None, "ExampleAgent_0a1b2c")


def test_a_declaration_in_the_old_form_is_refused_and_history_still_reads(tmp_path):
    """R165 and R166 where they matter most: the daemon refuses a declaration that names its
    agent the old way, saying what to write, while its event log's old records still count."""
    from macf.pd import core
    from macf.pd.core import DeclarationRefused
    pd_dir = tmp_path / ".maceff" / "pd"
    pd_dir.mkdir(parents=True)
    (pd_dir / "declaration.json").write_text(
        '{"version": 1, "agent": "ExampleAgent@0a1b2c", "units": []}')
    with pytest.raises(DeclarationRefused, match="write it as ExampleAgent_0a1b2c"):
        core.load_declaration(tmp_path, "ExampleAgent_0a1b2c")
    (pd_dir / "declaration.json").write_text(
        '{"version": 1, "agent": "exampleagent_0A1B2C", "units": []}')
    assert core.load_declaration(tmp_path, "ExampleAgent_0a1b2c").agent == "exampleagent_0A1B2C"
