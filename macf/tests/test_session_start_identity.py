"""SessionStart states the agent's identity first, on every path (#467).

The agent ID was present in the fresh-session context only as one line inside
the proprioception dump, and a personality file naming another agent in prose
outweighed it. These tests pin that the identity arrives as its own block, at
the very start of the injected context, on every SessionStart path -- and that
an unresolvable ID is said out loud rather than left for the agent to fill in
from whatever file it reads next.
"""
import json
from contextlib import ExitStack
from unittest.mock import patch

import pytest

HOOK = 'macf.hooks.handle_session_start'


@pytest.fixture
def quiet_hook():
    """Stub the hook's slow or stateful collaborators; leave identity real-ish."""
    with ExitStack() as stack:
        p = lambda name, **kw: stack.enter_context(patch(f'{HOOK}.{name}', **kw))
        p('get_current_session_id', return_value='sess-identity')
        p('detect_compaction', return_value=False)
        p('detect_auto_mode', return_value=(False, 'default'))
        p('get_latest_consciousness_artifacts')
        p('format_consciousness_recovery_message', return_value='RECOVERY BODY')
        p('format_session_migration_message', return_value='MIGRATION BODY')
        p('format_fresh_session_manual_recovery_message', return_value='MIGRATION BODY')
        migration = p('detect_session_migration', return_value=(False, '', ''))
        p('get_cycle_number_from_events', return_value=7)
        p('get_temporal_context', return_value={
            'timestamp_formatted': 'T', 'day_of_week': 'D', 'time_of_day': 'M'})
        p('get_rich_environment_string', return_value='Env')
        p('get_breadcrumb', return_value='s_x/c_7/p_y/t_1')
        p('get_last_session_end_time_from_events', return_value=None)
        p('get_token_info', return_value={})
        p('format_token_context_full', return_value='Tokens')
        p('format_manifest_awareness', return_value='Manifest')
        p('format_proprioception_awareness', return_value='Proprioception')
        p('format_macf_footer', return_value='Footer')
        p('get_compaction_count_from_events', return_value={'count': 0})
        p('append_event')
        stack.enter_context(patch('macf.cycle_carry.carry_state_forward'))
        stack.enter_context(patch(
            'macf.task.events.get_active_tasks_from_filesystem', return_value={}))
        stack.enter_context(patch('macf.transcript_monitor.daemon.is_running',
                                  return_value=True))
        stack.enter_context(patch.dict('os.environ', {'USER': 'pa_seat4'}))
        yield {'migration': migration}


def _context(result):
    return result['hookSpecificOutput']['additionalContext']


def _run(stdin=None):
    from macf.hooks.handle_session_start import run
    return run(json.dumps(stdin) if stdin else '')


@pytest.mark.parametrize('stdin', [None, {'source': 'startup'}, {'source': 'resume'}],
                         ids=['fresh-no-input', 'startup', 'resume'])
def test_fresh_and_resume_open_with_identity(quiet_hook, stdin):
    with patch(f'{HOOK}.get_agent_identity', return_value='Seat4@7efebd'):
        ctx = _context(_run(stdin))
    first_block = ctx.split('</system-reminder>')[0]
    assert ctx.startswith('<system-reminder>\n')
    assert 'Seat4@7efebd' in first_block
    assert 'pa_seat4' in first_block
    assert 'macf_tools env' in first_block
    # The identity comes before the session banner, not after it.
    assert ctx.index('Seat4@7efebd') < ctx.index('Session Start')


def test_compaction_recovery_opens_with_identity(quiet_hook):
    with patch(f'{HOOK}.get_agent_identity', return_value='Seat4@7efebd'):
        ctx = _context(_run({'source': 'compact', 'session_id': 'sess-identity'}))
    assert ctx.startswith('<system-reminder>\n')
    assert ctx.index('Seat4@7efebd') < ctx.index('RECOVERY BODY')


def test_migration_opens_with_identity(quiet_hook):
    quiet_hook['migration'].return_value = (True, '', 'prev-session')
    with patch(f'{HOOK}.get_agent_identity', return_value='Seat4@7efebd'):
        ctx = _context(_run({'source': 'startup', 'session_id': 'sess-identity'}))
    assert ctx.startswith('<system-reminder>\n')
    assert ctx.index('Seat4@7efebd') < ctx.index('MIGRATION BODY')


def test_identity_block_says_it_outranks_prose(quiet_hook):
    with patch(f'{HOOK}.get_agent_identity', return_value='Seat4@7efebd'):
        first_block = _context(_run()).split('</system-reminder>')[0]
    assert 'CLAUDE.md' in first_block
    assert 'authoritative' in first_block


def test_unresolved_id_is_said_not_papered_over(quiet_hook):
    with patch(f'{HOOK}.get_agent_identity', return_value='pa_seat4@unknown'):
        first_block = _context(_run()).split('</system-reminder>')[0]
    assert 'could not be resolved' in first_block
    assert 'Do not adopt' in first_block
    assert 'pa_seat4@unknown' not in first_block


def test_identity_failure_never_breaks_session_start(quiet_hook):
    with patch(f'{HOOK}.get_agent_identity', side_effect=OSError('id file unreadable')):
        result = _run()
    assert result['continue'] is True
    ctx = _context(result)
    assert 'Session Start' in ctx
    assert 'could not be resolved' in ctx.split('</system-reminder>')[0]
