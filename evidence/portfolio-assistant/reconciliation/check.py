"""Offline reconciliation; no RPC, capture, render, or historical-file writes."""
import hashlib
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch

if not __debug__:
    raise SystemExit('Reconciliation requires non-optimized Python')

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import pharos_portfolio_box3_20261110 as portfolio


def load(path):
    return json.loads((ROOT / path).read_text())


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def citations(data):
    """Require exact contract/block/method for every financial citation."""
    def walk(value):
        if isinstance(value, dict):
            if 'value' in value and 'sources' not in value and 'reason' not in value:
                assert set(value) == {'value', 'contract', 'block', 'method'}, value
                assert value['block'] == data['block']
                assert portfolio.ADDRESS.fullmatch(value['contract'])
                assert value['method']
                assert value['value'] == 'unknown' or value['value'].isdigit()
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(data)
    for name, item in data.get('wallet_balances', {}).items():
        assert item['contract'] == (portfolio.USDC if name == 'USDC_raw' else portfolio.NATIVE)
        assert item['method'] == ('balanceOf(address)' if name == 'USDC_raw' else 'eth_getBalance (native PROS)')
    for name, vault in data.get('vaults', {}).items():
        assert vault['vault'] == portfolio.VAULTS[name] and vault['asset'] == portfolio.USDC
        for key, method in [('shares', 'balanceOf(address)'), ('underlying_usdc_raw', 'convertToAssets(uint256)')]:
            assert vault[key]['contract'] == portfolio.VAULTS[name]
            assert vault[key]['method'] == method
    if 'total_usdc_raw' in data:
        parts = [v['underlying_usdc_raw'] for v in data['vaults'].values()]
        parts += list(data.get('wallet_balances', {}).values())
        assert data['total_usdc_raw']['contract'] == portfolio.USDC
        assert int(data['total_usdc_raw']['value']) == sum(int(v['value']) for v in parts)


def replay(answers, trace):
    results = []
    for expected in answers:
        rows = iter(trace)
        def call(method, params):
            row = next(rows)
            assert (method, params) == (row['method'], row['params'])
            return row['result']
        actual = portfolio.answer(expected['wallet'], expected['question'], call)
        assert next(rows, None) is None
        citations(expected)
        citations(actual)
        results.append(actual)
    assert len(results) == 7
    return results


def check():
    bundle = 'video-demos/portfolio-assistant/'
    evidence = 'evidence/portfolio-assistant/'
    old = load(evidence + 'questions-pinned-replay.json')
    current = replay(old, load(evidence + 'rpc-trace.json'))
    deltas = []
    for before, after in zip(old, current):
        expected = json.loads(json.dumps(before))
        changes = []
        if before['intent'] == 'exposure':
            expected['total_usdc_raw']['method'] = 'sum(selected USDC positions); components cited separately'
            changes.append('/total_usdc_raw/method')
        if before['intent'] == 'largest':
            expected['wallet_balances'] = {'USDC_raw': old[0]['wallet_balances']['USDC_raw']}
            changes.append('/wallet_balances')
        assert after == expected, before['question']
        deltas.append({'question': before['question'], 'allowed_changed_paths': changes})
    saved = {'answers': load(evidence + 'steps1-3-producer/questions-fresh-trace-replay.json'),
             'trace_source': evidence + 'steps1-3-producer/fresh-live-rpc-trace.json'}
    if isinstance(saved['answers'], dict):
        saved['answers'] = saved['answers']['answers']
    assert replay(saved['answers'], load(saved['trace_source'])) == saved['answers']
    result = {'mode': 'Offline saved-response replay; not fresh RPC or authenticated capture',
              'original_answers': len(current), 'original_deltas': deltas,
              'later_exact_answers': len(saved['answers']), 'financial_value_mismatches': [],
              'ready_to_publish': False}
    if '--local-bundle' not in sys.argv:
        return result
    recorded = load(bundle + 'recorded-replay.json')
    assert replay(recorded['answers'], load(recorded['trace_source'])) == recorded['answers']
    result['video_recorded_exact_answers'] = len(recorded['answers'])
    record = load(bundle + 'captured-live.json')
    assert record['exit_code'] == 0 and record['stderr'] == ''
    captured = json.loads(record['stdout'])
    citations(captured)
    # ponytail: capture has no raw RPC trace; state replay checks answer formatting only.
    with patch.object(portfolio, 'snapshot', return_value=captured):
        assert portfolio.answer(captured['wallet'], captured['question']) == captured
    assert captured['block'] == 22707754
    assert captured['wallet_balances']['USDC_raw']['value'] == '1974365593'
    assert captured['vaults']['RockawayX']['shares']['value'] == '1981531086279423740862327'
    assert captured['vaults']['RockawayX']['underlying_usdc_raw']['value'] == '2000163148679'
    assert captured['vaults']['SharpByte']['shares']['value'] == '0'
    assert captured['vaults']['SharpByte']['underlying_usdc_raw']['value'] == '0'
    assert captured['total_usdc_raw']['value'] == '2002137514272'
    manifest = load(bundle + 'manifest.json')
    for path, sha in manifest['source_sha256'].items():
        assert digest(path) == sha, path
    r1 = load(bundle + 'render-manifest-r1.json')
    for name, sha in r1['inputs'].items():
        path = name if name == 'pharos_portfolio_box3_20261110.py' else bundle + name
        assert digest(path) == sha, path
    for name, sha in load(bundle + 'capture-hashes.json').items():
        assert digest(bundle + name) == sha, name
    accepted = 'b16168dc560578acf69581dc0c3b98729f803b767cd851bf58f90d276027c578'
    assert digest(bundle + 'portfolio-assistant-review-r1.mp4') == r1['video_sha256'] == accepted
    return {**result,
            'captured_state_answer_equality': True, 'capture_raw_rpc_trace_available': False,
            'capture_block': captured['block'], 'capture_total_usdc_raw': captured['total_usdc_raw']['value'],
            'r1_inputs_and_source_hashes_match': True, 'accepted_video_sha256': accepted,
            'security_provenance_hold': ['capture.py assertions bypassed under python -O',
                                         'Authenticated capture-time remote-driver baseline absent'],
            'capture_authenticity_established': False, 'ready_to_publish': False}


if __name__ == '__main__':
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')), \
         patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')), \
         patch.object(socket, 'getaddrinfo', side_effect=AssertionError('network forbidden')):
        print(json.dumps(check(), indent=2))
