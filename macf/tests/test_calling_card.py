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


def _home_declaration(tmp_path, agent):
    pd_dir = tmp_path / ".maceff" / "pd"
    pd_dir.mkdir(parents=True, exist_ok=True)
    path = pd_dir / "declaration.json"
    path.write_text('{"version": 1,  "agent": "%s", "units": []}\n' % agent)
    return path


def test_a_host_declaration_naming_its_own_card_the_old_way_is_cut_over_once(tmp_path, monkeypatch):
    """A host daemon restarting onto this code would refuse its own declaration and stay down,
    so the old form of THIS home's card is rewritten in place once, the original kept and the
    rewrite recorded; then only the new form is read."""
    from macf.pd import core
    events = []
    monkeypatch.setattr(core, "append_event", lambda event, data: events.append((event, data)))
    path = _home_declaration(tmp_path, "ExampleAgent@0a1b2c")
    original = path.read_text()
    kept = core.cutover_declaration(tmp_path, "ExampleAgent_0a1b2c")
    assert kept is not None and kept.read_text() == original
    assert path.read_text() == original.replace("ExampleAgent@0a1b2c", "ExampleAgent_0a1b2c")
    assert events == [("pd_declaration_rewritten", {
        "agent": "ExampleAgent_0a1b2c", "from": "ExampleAgent@0a1b2c", "path": str(path),
        "kept": str(kept), "reason": "MIS-0002-R165 cut-over"})]
    assert core.load_declaration(tmp_path, "ExampleAgent_0a1b2c").agent == "ExampleAgent_0a1b2c"
    assert core.cutover_declaration(tmp_path, "ExampleAgent_0a1b2c") is None
    assert len(events) == 1 and kept.read_text() == original


def test_another_agents_old_card_is_not_cut_over_and_stays_refused(tmp_path, monkeypatch):
    from macf.pd import core
    from macf.pd.core import DeclarationRefused
    monkeypatch.setattr(core, "append_event", lambda *a: pytest.fail("nothing to record"))
    path = _home_declaration(tmp_path, "OtherAgent@0a1b2c")
    before = path.read_text()
    assert core.cutover_declaration(tmp_path, "ExampleAgent_0a1b2c") is None
    assert path.read_text() == before
    assert not list(path.parent.glob("*" + core.CUTOVER_KEPT_SUFFIX))
    with pytest.raises(DeclarationRefused, match="old calling-card form"):
        core.load_declaration(tmp_path, "ExampleAgent_0a1b2c")


def test_a_declaration_already_in_the_new_form_is_left_alone(tmp_path, monkeypatch):
    from macf.pd import core
    monkeypatch.setattr(core, "append_event", lambda *a: pytest.fail("nothing to record"))
    path = _home_declaration(tmp_path, "ExampleAgent_0a1b2c")
    before = path.read_text()
    assert core.cutover_declaration(tmp_path, "ExampleAgent_0a1b2c") is None
    assert path.read_text() == before


def test_a_rendered_declaration_is_never_rewritten(tmp_path, monkeypatch):
    """The deployment's rendered copy is out of the agent's reach and re-rendered in the new form
    at start; the cut-over touches only the agent's own file."""
    from macf.pd import core
    rendered = tmp_path / "rendered.json"
    rendered.write_text('{"version": 1, "agent": "ExampleAgent@0a1b2c", "units": []}')
    monkeypatch.setattr(core, "declaration_path", lambda home: rendered)
    monkeypatch.setattr(core, "append_event", lambda *a: pytest.fail("nothing to record"))
    assert core.cutover_declaration(tmp_path, "ExampleAgent_0a1b2c") is None
    assert "ExampleAgent@0a1b2c" in rendered.read_text()


def test_an_operator_rule_stored_under_the_old_card_still_holds():
    """R166 for the operator's silence and route rules: a rule recorded before the cut-over names
    the old card and must still fold into the rules in force after it."""
    from macf.pd.stream import fold_rules
    events = [{"event": "pd_stream_rule", "data": {"agent": "ExampleAgent@0a1b2c", "act": "silence",
                                                    "target": "pd_entry_*", "asked_by": {"kind": "operator"}}},
              {"event": "pd_stream_rule", "data": {"agent": "OtherAgent@0a1b2c", "act": "silence",
                                                    "target": "zone_*", "asked_by": {"kind": "operator"}}}]
    assert fold_rules(events, "ExampleAgent_0a1b2c").silenced == ["pd_entry_*"]


def test_the_cut_over_keeps_the_file_mode_and_leaves_an_invalid_result_alone(tmp_path, monkeypatch):
    from macf.pd import core
    monkeypatch.setattr(core, "append_event", lambda *a: None)
    path = _home_declaration(tmp_path, "ExampleAgent@0a1b2c")
    path.chmod(0o600)
    kept = core.cutover_declaration(tmp_path, "ExampleAgent_0a1b2c")
    assert path.stat().st_mode & 0o777 == 0o600 and kept.stat().st_mode & 0o777 == 0o600
    bad = _home_declaration(tmp_path / "b", "ExampleAgent@0a1b2c")
    bad.write_text('{"version": 1, "agent": "ExampleAgent@0a1b2c", "units": [], "nonsense": 1}')
    assert core.cutover_declaration(tmp_path / "b", "ExampleAgent_0a1b2c") is None
    assert "ExampleAgent@0a1b2c" in bad.read_text()
