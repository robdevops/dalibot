// Story QA: walks every route (deduping identical states) and reports endings and problems.
import fs from 'node:fs';
import { loadStory, advance } from './engine.mjs';
const json = fs.readFileSync(process.argv[2], 'utf8');
const eng = loadStory(json);
const endings = {}, problems = [], seen = new Set();
let routes = 0;
function walk(state, depth, path) {
  if (state) eng.story.state.LoadJson(state);
  let seg;
  try { seg = advance(eng, 0); } catch (e) { problems.push(`${path}: ${e.message}`); return; }
  const key = JSON.stringify(JSON.parse(seg.state), (k, v) => (k === 'turnIdx' || k === 'storySeed' || k === 'previousRandom' || k === 'turnIndices' ? undefined : v));
  if (seen.has(key)) return; seen.add(key);
  if (!seg.choices.length) {
    routes++;
    if (seg.ending) endings[seg.ending] = (endings[seg.ending] ?? 0) + 1;
    else problems.push(`${path}: story stopped with no choices and no # ending tag`);
    return;
  }
  if (depth > 60) { problems.push(`${path}: deeper than 60 choices`); return; }
  for (const c of seg.choices) {
    eng.story.state.LoadJson(seg.state);
    eng.story.ChooseChoiceIndex(c.index);
    walk(eng.story.state.ToJson(), depth + 1, `${path}>${c.index}`);
  }
}
walk(null, 0, 'start');
console.log({ distinctStates: seen.size, routesToEnd: routes, endings, problems });
