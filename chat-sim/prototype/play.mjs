// Plays one route with fixed choices and prints the timeline + notifications that would be scheduled.
import fs from 'node:fs';
import { loadStory, advance, notificationsFor } from './engine.mjs';
const json = fs.readFileSync(process.argv[2], 'utf8');
const picks = (process.argv[3] ?? '').split(',').filter(Boolean).map(Number);
const eng = loadStory(json, { playerName: 'Sam', tz: 'Australia/Melbourne' });
let t = Date.parse('2026-11-19T21:00:00+11:00');
const fmt = (ms) => new Date(ms).toLocaleTimeString('en-AU', { timeZone: 'Australia/Melbourne', hour12: false });
for (let turn = 0; ; turn++) {
  const seg = advance(eng, t);
  for (const e of seg.events) console.log(`${fmt(e.at)} ${e.notify ? '🔔' : '  '} ${e.speaker}: ${e.text}${e.image ? ` [img ${e.image}]` : ''}${e.presence ? ` (${e.presence})` : ''}`);
  for (const n of notificationsFor(seg, 'Wren')) console.log(`         schedule notification @ ${fmt(n.at)}: "${n.body}"${n.actions ? ' actions=' + JSON.stringify(n.actions) : ''}`);
  if (seg.ending) { console.log(`== ending: ${seg.ending}`); break; }
  const pick = picks[turn] ?? 0;
  console.log(`         choices: ${seg.choices.map((c) => `[${c.index}] ${c.text}`).join('  ')}  -> player picks ${pick} after 2 min`);
  eng.story.ChooseChoiceIndex(pick);
  t = seg.choicesAt + 120e3;
}
