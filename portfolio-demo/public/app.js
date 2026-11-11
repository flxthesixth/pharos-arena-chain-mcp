'use strict';
const questions = ['What is my wallet balance?', 'How many shares are in my positions?', 'Which vaults hold assets?', 'Where is my USDC?', 'Compare RockawayX versus SharpByte', "What's my biggest position?", 'What am I earning in yield?'];
const $ = id => document.getElementById(id);
for (const question of questions) {
  const button = document.createElement('button');
  button.type = 'button'; button.textContent = question;
  button.addEventListener('click', () => { $('question').value = question; $('ask').requestSubmit(); });
  $('examples').append(button);
}
function facts(value, path = '') {
  if (!value || typeof value !== 'object') return;
  if (Object.hasOwn(value, 'value')) {
    const item = document.createElement('p');
    item.textContent = `${path}: ${value.value}${value.contract ? ` | contract: ${value.contract} | block: ${value.block} | method: ${value.method}` : ''}${value.reason ? ` | ${value.reason}` : ''}`;
    $('facts').append(item);
  }
  for (const [key, child] of Object.entries(value)) if (child && typeof child === 'object') facts(child, path ? `${path}.${key}` : key);
}
$('ask').addEventListener('submit', async event => {
  event.preventDefault();
  // ponytail: single in-flight question; cancel/parallel UI only if needed later.
  if ($('submit').disabled) return;
  $('submit').disabled = true;
  $('status').textContent = $('mode').value === 'live' ? 'Reading public RPC; failures remain unknown. May take up to 40 seconds.' : 'Replaying recorded RPC through original Python parser…';
  $('facts').replaceChildren(); $('json').textContent = ''; $('provenance').textContent = '';
  try {
    const params = new URLSearchParams({question: $('question').value, mode: $('mode').value});
    const response = await fetch(`/api/answer?${params}`, {signal: AbortSignal.timeout(45000)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Read unavailable');
    $('provenance').textContent = `${data.mode.toUpperCase()} — ${data.provenance}`;
    facts(data.answer); $('json').textContent = JSON.stringify(data.answer, null, 2);
    $('status').textContent = `Answered: ${data.answer.intent} | block ${data.answer.block} | ${data.mode === 'recorded' ? 'RECORDED, NOT LIVE' : 'LIVE RPC'}`;
  } catch (error) {
    $('status').textContent = `Unavailable: ${error.message}. No values guessed.`;
  } finally { $('submit').disabled = false; }
});
