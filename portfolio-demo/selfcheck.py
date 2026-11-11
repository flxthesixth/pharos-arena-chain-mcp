"""Run: python3 -B portfolio-demo/selfcheck.py (stdlib, no network)."""
import json
import threading
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from urllib.parse import urlencode
import server


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


questions = {
    'What is my wallet balance?': 'balances',
    'How many shares are in my positions?': 'positions',
    'Which vaults hold assets?': 'vaults',
    'Where is my USDC?': 'exposure',
    'Compare RockawayX versus SharpByte': 'compare',
    "What's my biggest position?": 'largest',
    'What am I earning in yield?': 'earnings',
}
http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
threading.Thread(target=http.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{http.server_port}'
count = 0


def get(path, expected=200, data=None):
    global count
    try:
        response = urlopen(Request(base + path, data=data), timeout=10)
    except HTTPError as exc:
        response = exc
    require(response.status == expected, f'{path}: status {response.status}, expected {expected}')
    require(response.headers['Cache-Control'] == 'no-store', 'Cache leak')
    count += 1
    return response.read()


def check_citations(value):
    if isinstance(value, dict):
        if 'contract' in value:
            require(value['block'] == 22661772 and server.portfolio.ADDRESS.fullmatch(value['contract']), 'Citation invalid')
            require(bool(value.get('method')), 'Method missing')
        for child in value.values():
            check_citations(child)


for question, intent in questions.items():
    result = json.loads(get('/api/answer?' + urlencode({'question': question, 'mode': 'recorded'})))
    require(result['mode'] == 'recorded' and result['answer']['intent'] == intent, 'Wrong intent or mode')
    check_citations(result['answer'])
    if intent == 'exposure':
        require(result['answer']['total_usdc_raw']['value'] == '2001991141463', 'Exposure differs from source')
    if intent == 'earnings':
        require(result['answer']['earnings']['value'] == 'unknown', 'Invented earnings')
for question, mode in [('BTC balance','recorded'), ('Where is my USDC?','bad'), ('','recorded'), ('x'*241,'recorded'), ('<script>alert(1)</script>','recorded')]:
    get('/api/answer?' + urlencode({'question': question, 'mode': mode}), 400)
for path in ['/server.py','/../pharos_portfolio_box3_20261110.py','/.git/config','/api/rpc','/api/answer?question=balances&question=largest&mode=recorded']:
    get(path, 400 if path.startswith('/api/answer') else 404)
get('/api/answer',400,b'{}')
# Controlled transport failures exercise live wrapper, never produce claimed live evidence.
original = server.live_answer
try:
    server.LAST_LIVE = 0
    server.live_answer = lambda *args: (_ for _ in ()).throw(OSError('simulated offline'))
    get('/api/answer?question=balances&mode=live',503)
    get('/api/answer?question=balances&mode=live',429)
finally:
    server.live_answer = original
    server.LAST_LIVE = 0
    http.shutdown()
    http.server_close()
print(json.dumps({'status':'PASS','http_checks':count,'intents':list(questions.values()),'optimized_safe':True}))
