// Prototype of the platform-free engine core (the part that would live in packages/engine).
// Plain JS + inkjs so it runs under Node; the real thing would be TypeScript.
import { Story } from 'inkjs';

const UNITS = { s: 1e3, m: 60e3, h: 3600e3, d: 86400e3 };
export const parseDuration = (v) => {
  const m = /^(\d+(?:\.\d+)?)\s*([smhd])$/.exec(String(v).trim());
  if (!m) throw new Error(`bad duration "${v}"`);
  return Number(m[1]) * UNITS[m[2]];
};

// "# key: value" -> {key: value}; bare "# key" -> {key: true}
export function parseTags(tags = []) {
  const out = {};
  for (const t of tags) {
    const i = t.indexOf(':');
    if (i < 0) out[t.trim()] = true;
    else out[t.slice(0, i).trim()] = t.slice(i + 1).trim();
  }
  return out;
}

const GLOBAL_KEYS = new Set(['title', 'author', 'chat']);
const typingTime = (text) => Math.min(6000, Math.max(1200, text.length * 45));

/**
 * Load a story and bind the engine's whitelisted external functions.
 * The clock is simulated: functions see the time of the message being built, not "now".
 */
export function loadStory(json, { playerName = 'friend', tz } = {}) {
  const story = new Story(json);
  const sim = { t: Date.now() };
  // Who is talking persists between segments; the global "# chat:" tag gives the default
  const g = parseTags(story.globalTags ?? []);
  sim.speaker = g.chat ?? null;
  story.BindExternalFunction('player_name', () => playerName, true);
  story.BindExternalFunction('local_hour', () =>
    Number(new Intl.DateTimeFormat('en-GB', { hour: 'numeric', hourCycle: 'h23', timeZone: tz }).format(sim.t)), true);
  return { story, sim };
}

/**
 * Run the story forward from its current state until the next choice point or an ending,
 * stamping each message with the wall-clock time it should appear.
 * Nothing here waits: the whole segment is computed at once, which is what lets the app
 * schedule local notifications for it and then be killed.
 */
export function advance({ story, sim }, startAt, { maxSteps = 500, notifyGap = 60e3 } = {}) {
  sim.t = startAt;
  const events = [];
  let steps = 0, ending = null, carry = {};
  while (story.canContinue) {
    if (++steps > maxSteps) throw new Error(`no choice after ${maxSteps} lines: infinite loop?`);
    const text = story.Continue().trim();
    const tags = { ...carry, ...parseTags(story.currentTags) };
    for (const k of GLOBAL_KEYS) delete tags[k];
    if (tags.speaker) sim.speaker = tags.speaker;
    if (tags.ending) ending = tags.ending;
    if (!text) { carry = tags; continue; } // tag-only line: apply to the next message
    carry = {};
    const wait = tags.wait ? parseDuration(tags.wait) : 0;
    sim.t += wait || (tags.typing ? parseDuration(tags.typing) : typingTime(text));
    events.push({
      at: sim.t, speaker: sim.speaker, text,
      image: tags.image, presence: tags.presence,
      notify: wait >= notifyGap, // a wake-up after real waiting -> local notification
    });
  }
  const choices = story.currentChoices.map((c) => ({ index: c.index, text: c.text }));
  return { events, choices, choicesAt: sim.t + 800, ending, state: story.state.ToJson() };
}

/**
 * Notifications to schedule for a segment: one per wake-up (a message after a real wait).
 * If choices follow a wake-up within `mergeWithin`, they ride on that notification as reply
 * actions instead of buzzing the phone again seconds later.
 */
export function notificationsFor(seg, title, { mergeWithin = 5 * 60e3 } = {}) {
  const n = seg.events.filter((e) => e.notify).map((e) => ({ at: e.at, title, body: e.text }));
  if (!seg.choices.length) return n;
  const actions = seg.choices.map((c) => c.text);
  const last = n.at(-1);
  if (last && seg.choicesAt - last.at <= mergeWithin) last.actions = actions;
  else if (n.length) n.push({ at: seg.choicesAt, title, body: seg.events.at(-1).text, actions });
  return n;
}
