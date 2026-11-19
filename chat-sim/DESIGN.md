# Chat-sim engine: design

A mobile engine for real-time text adventures in the Lifeline mould: a character messages you, you pick short replies, and when they go off to do something they really are gone for 10 minutes or 3 hours, and your phone buzzes when they're back. The app is an engine. Stories (Ink JSON) and UI themes (JSON) are loaded into it as **cartridges**.

Everything in `example-cartridge/` and `prototype/` runs today. `prototype/engine.mjs` is the core timeline algorithm described below, working against real inkjs, and `explore.mjs` walks all 90 routes of the sample story.

---

## 1. The decision that matters most: notifications without a server or background code

The usual worry is that the app must run in the background to know when the character "comes back". It doesn't need to, because **an Ink story is deterministic between choices**. When the player picks a reply, the engine runs the story forward right away, up to the next choice or ending, and stamps each message with the wall-clock time it should appear:

```
player picks "Forget the radio"  at 21:40:28
  21:40:28  going out to the shed. the wind is unreal   (busy)
  22:05:28  made it. soaked through                      <- # wait: 25m  -> 🔔 at 22:05:28
  22:05:30  the generator's flooded...                   (typing delay)
  choices available at 22:05:31                          -> ride on the 🔔 as reply buttons
```

The app saves that segment and schedules **local notifications** for the wake-ups. Then the OS can kill the app. When the player opens it again, the UI shows every message whose time has passed and plays the rest live. No push server, no background fetch and no wake locks, so it works offline and costs nothing to run.

This is what `prototype/play.mjs` prints. Some consequences:

- **Technology choice:** we only need reliable *scheduled local notifications* plus a JS/Dart Ink runtime. We don't need background execution, and that is the part that is flaky on iOS and Android.
- **Few notifications:** one per wake-up (a message that follows a wait of 60 s or more), not one per message. iOS keeps at most 64 pending local notifications per app, and a segment rarely needs more than 3.
- **Reply from the notification:** the choices are known when the notification is scheduled, so they can be attached as action buttons (iOS shows up to 4, Android 3). If choices arrive within 5 minutes of a wake-up they ride on that notification rather than buzzing the phone again.
- **External functions run at simulation time.** `local_hour()` is answered from the *simulated* clock of the message being built, not from "now" (see §4.4).
- **Remote push is optional.** It is only needed later for live events or "new chapter" announcements, and it doesn't change the engine.

---

## 2. Technology choice

| | **React Native + Expo** | Flutter | Unity (+ ink-unity-integration) | Native ×2 (Swift/Kotlin) |
|---|---|---|---|---|
| Ink runtime | **inkjs**: the reference JS port, full feature parity, and it **includes the compiler**, so `.ink` source can be compiled on device in dev builds | Community Dart ports, less complete and less maintained; or embed inkjs in a JS engine (awkward) | Official Inkle plugin, first-class | ink-swift/ink-kotlin ports exist but are thin; or embed inkjs in JavaScriptCore/QuickJS |
| Scheduled local notifications with action buttons | `expo-notifications` (categories with actions) | `flutter_local_notifications`, also good | Unity Mobile Notifications package | Best possible |
| Iteration speed | Fast Refresh; **EAS Update** pushes JS + bundled stories over the air without store review; web build for playtesting in a browser | Hot reload is excellent; no first-party OTA (Shorebird is third-party) | Slow builds; heavy for a chat UI | Two codebases |
| Chat UI | FlashList or FlatList; easy to theme from JSON | Excellent rendering | Doable, but you fight the engine | Best feel, double the work |
| Same engine code in the CLI tooling | **Yes**: the engine package runs unchanged in Node (linter, route explorer, CI) | Dart CLI is possible, but the Ink port has the gaps above | No | No |

**Recommendation: React Native + Expo (dev client, not Expo Go), TypeScript.** What decides it is Ink. inkjs is the most faithful Ink runtime outside Unity, and its bundled compiler allows "edit `.ink`, see it on the phone in a second" with no `inklecate` step. Running the *same* engine package in Node also gives you automated route testing for free. Expo covers the notification needs, and EAS Update lets you ship engine fixes and story revisions without app-store releases. (Downloading stories as data is fine under store rules either way.)

Flutter would be the pick if the UI were the hard part; here the story runtime is. Unity is worth reconsidering only if the game grows 2D/3D scenes around the chat.

Core libraries: `inkjs`, `expo-notifications`, `expo-file-system`, `expo-sqlite` (saves) or `react-native-mmkv`, `@shopify/flash-list`, `expo-av`/`expo-audio` (sfx), `expo-haptics`, `zod` (validates cartridges and themes), `react-native-reanimated` (typing and message animation).

---

## 3. Architecture

```
┌───────────────────────────── app (Expo / React Native) ─────────────────────────────┐
│  UI shell: Library · Chat screen · Choice bar · Endings gallery · Settings · Dev menu │
│      ▲ renders Transcript + Presence, styled by Theme                                │
│      │                                                                               │
│  Session controller  ── reveals events whose time has passed; plays the rest live    │
│      │                                                                               │
│  ┌───┴──────────────── @chatsim/engine (pure TS, no RN imports) ──────────────────┐  │
│  │ CartridgeLoader  StoryRunner(inkjs)  TagParser  TimelineBuilder  NotificationPlan│ │
│  │ SaveModel(snapshots, rewind)  Clock(interface)  Validators(zod)                 │  │
│  └─────────────────────────────────────────────────────────────────────────────────┘ │
│      │ ports (interfaces)                                                            │
│  Adapters: Notifier(expo-notifications) · Store(sqlite) · Assets(file-system) · Audio │
└──────────────────────────────────────────────────────────────────────────────────────┘
        ▲ same engine package                         ▲ cartridges from: bundled / URL / dev server
┌───────┴──────── @chatsim/cli (Node) ───────┐   ┌────┴─────── dev server (Node) ─────────┐
│ compile · lint · explore routes · simulate │   │ watches .ink, compiles, pushes over WS │
└────────────────────────────────────────────┘   └────────────────────────────────────────┘
```

Monorepo: `packages/engine`, `packages/cli`, `apps/mobile`, `cartridges/*`.

The engine never reads the clock or touches the platform directly. It receives `now` and returns data such as "messages with timestamps" and "notifications to schedule". That makes it fully testable in Node with a fake clock, which is exactly what the prototype does.

---

## 4. Cartridge format

A cartridge is a folder or a `.zip`:

```
signal-fire/
  manifest.json      id, version, title, characters, endings, timing, theme ref
  story.ink.json     compiled Ink (ink JSON; check inkVersion against bundled inkjs)
  story.ink          optional source; dev builds compile it on device
  theme.json         optional; else engine default or user-chosen theme
  assets/            avatars, images, audio, fonts
```

See `example-cartridge/manifest.json` and `theme.json`. Both are validated with zod at load, and the same schemas are exported as JSON Schema so authors get autocomplete in VS Code. A cartridge is **data only**: no scripts. Ink external functions are limited to a fixed list the engine provides (§4.3), so a downloaded story can't run code.

### 4.1 What Ink already gives you (no engine work)

| Requirement | Ink feature |
|---|---|
| Branching dialogue | `*` / `+` choices, conditional choices `{trust >= 1}`, choice-only text in `[ ]` |
| Multiple endings | Several knots ending in `-> END`, each tagged `# ending: id` |
| Loops | `+` sticky choices and diverts back to a knot; visit counts (`{radio_loop}`) and variables to vary text and force an exit (`radio_loop` in the sample) |
| Multiple paths to the same place | Diverts converge on a knot (`to_the_shed` is reached three ways); gathers `-` rejoin inside a knot |
| Reusable bits | Tunnels `-> shed_report ->`, threads, functions |
| State | `VAR`, `LIST`, `TEMP`, visit counts, `RANDOM` (seeded; the seed is saved in the state, so replays are deterministic) |

### 4.2 Tag conventions (the engine's vocabulary)

Tags are `# key: value`. A tag on a line of its own attaches to the next line of text.

| Tag | Where | Meaning |
|---|---|---|
| `# wait: 25m` | message | **The character was away**: this message appears 25 min after the previous one. Units `s m h d`. A wait of 60 s or more schedules a notification. |
| `# presence: busy` | message | After this message, show "Wren is busy" (also `online`, `offline`) |
| `# typing: 4s` | message | Override the typing time (default: length × 45 ms, clamped 1.2–6 s; set in the manifest) |
| `# speaker: wren` | message | Who is talking; persists until changed. The default comes from the global `# chat:` tag. Values match `manifest.characters`. |
| `# system` | message | Render as a status line, not a bubble |
| `# image: x.png` / `# audio: x.m4a` | message | Media message (path inside `assets/`) |
| `# notify: text` | message | Custom notification text (the default is the message itself, truncated) |
| `# silent` | message | Never notify for this message, even after a wait |
| `# ending: id` | last line | Records the ending (gallery and achievements); must match `manifest.endings` |
| `# checkpoint: id` | message | Named rewind point shown in the "rewind" menu |
| `# achievement: id` | message | Unlock |
| `# request_notifications` | message | In-story moment to show the OS permission prompt, e.g. "can I ping you when I'm back?" |
| `# title:`, `# author:`, `# chat:` | file top (global) | Metadata; ignored on lines |

Unknown tags are a **lint error** in the CLI and ignored at runtime, so a typo like `# wiat` is caught before release.

### 4.3 External functions (whitelisted)

`player_name()`, `local_hour()`, `local_weekday()`, `days_since_start()`, `has_ending(id)` (for cross-playthrough content), `rand_seeded(n)`. Each is bound with a fallback value so the story also runs in Inky.

### 4.4 Rules that follow from computing ahead

1. **Time-dependent text goes on the line after a wait.** Ink evaluates a line's text and its tags in the same `Continue()`, so the clock only moves when the waited line is delivered. The sample's `beacon` knot shows the pattern.
2. **Every route must reach a choice or `END`.** A choiceless loop would never stop computing ahead. The runner caps a segment at 500 lines and the CLI flags it.
3. **No dependence on things that change after the choice.** For example, "if the player opened the app" can't be known ahead. Model it as a choice instead (Lifeline-style "[Still there?]").

---

## 5. Runtime

### 5.1 Timeline builder (see `prototype/engine.mjs`, `advance()`)

```
advance(story, startAt):
  t = startAt
  while story.canContinue (cap 500):
    text, tags = story.Continue(), parse(story.currentTags)
    tag-only line   -> carry its tags to the next message
    t += wait(tags) or typing(tags, text)
    emit {at: t, speaker, text, media, presence, notify: wait ≥ notifyGap}
  return {events, choices, choicesAt: t + 0.8s, ending, inkStateJson}
```

### 5.2 Save model

```ts
Save {
  cartridgeId, cartridgeVersion, seed,
  segments: Segment[]            // every computed segment: events with timestamps, choices
  picks: {choiceIndex, choiceText, at}[]
  inkState: string               // state at the current choice point
  snapshots: {checkpointId|pickNo, inkState, transcriptLen}[]   // for rewind
  scheduledNotificationIds: string[]
  endingsSeen: string[]          // per cartridge, survives restarts of the story
}
```

The transcript is derived from the segments. The UI shows `events.filter(e => e.at <= now)`. Everything is written in one sqlite transaction **before** notifications are scheduled, so a crash never leaves a notification for a message that wasn't saved.

### 5.3 Lifecycle

- **On choice:** cancel this story's pending notifications, `ChooseChoiceIndex`, `advance()`, save, schedule the new plan.
- **On app foreground or notification tap:** recompute what's visible from `now`. Already-due messages appear immediately (the last 2–3 get a short catch-up animation). Future ones play live with a typing indicator.
- **Reply from a notification action:** treat it as a choice made at the tap time. v1 opens the app to apply it (`opensAppToForeground: true`, reliable). v2 can try handling it in the background on iOS and Android once tested on real devices.
- **Rewind** (Lifeline's "go back after a death"): restore a snapshot, truncate segments and picks, cancel notifications, and continue as a new choice.
- **Time travel by the player** (changing the device clock) is allowed: it's their game. A *fast mode* setting (all waits ÷ N or instant) is just a multiplier in the timeline builder. It's also a natural premium unlock.
- **Cartridge update mid-playthrough:** save `cartridgeVersion`. On mismatch, replay the recorded `picks` against the new story. If it diverges (a choice no longer exists), offer "continue from the last matching checkpoint". This is the same replay used for hot reload (§7).

### 5.4 Platform notes

- **Permissions:** iOS needs a request; Android 13+ needs `POST_NOTIFICATIONS`. Ask in-story via `# request_notifications`, not on first launch.
- **Android timing:** use inexact, allow-while-idle scheduling. Doze can shift delivery by a few minutes, which is fine for this genre and avoids the `SCHEDULE_EXACT_ALARM` permission (denied by default on Android 14+ for non-alarm apps). Opening the app always shows the correct state anyway, because state comes from timestamps, not from the notification.
- **Notification channels (Android):** one per cartridge, so players can mute a story.
- **iOS 64-notification cap:** schedule at most ~20 per story. If a segment needs more (unusual), schedule the first ones and add the rest when the app is next opened.
- **Watch and lock screen:** notification actions already work on Apple Watch and Wear OS mirrors, which was Lifeline's signature. A native watch app is a later add-on.

---

## 6. UI and theming

- **Screens:** Library (installed cartridges, progress, endings found), Chat, Endings gallery, Settings (speed, sound, haptics, theme override, text size), Dev menu (dev builds only).
- **Chat:** inverted FlashList, typing indicator, presence banner, choice bar with 2–3 buttons that animates in at `choicesAt`, and media messages.
- **Theme JSON** (`example-cartridge/theme.json`): `layout` (`messenger` | `terminal` | `sms`), colour tokens, fonts (bundled in the cartridge), bubble shape and avatars, prefixes, typing-indicator style, message animation (`fade`, `typewriter`), sounds, status bar. The UI reads only tokens. There are no theme-specific components beyond the 3 layouts, so new themes need no code. A cartridge ships a theme, but the player can override it (accessibility: high contrast, larger text).
- **Accessibility:** Dynamic Type and font scaling, screen reader announces new messages (with a "replay" control), reduce-motion disables typewriter effects.

---

## 7. Iteration workflow (the "iterate quickly" part)

1. **Write in Inky or VS Code** (ink syntax extension). The story also runs in Inky because externals have fallbacks.
2. **`chatsim dev ./cartridges/signal-fire`** watches `.ink`, `theme.json` and assets, compiles with the inkjs compiler, and pushes to the app over a WebSocket on the LAN. Compile errors show as an overlay on the phone.
3. **Hot reload keeps your place:** the app replays your recorded picks against the new story and stops where it diverges. You don't have to replay from the start after each edit.
4. **Dev menu:** time speed (1×, 60×, instant), "skip wait", jump to any knot, a variable inspector and editor, "force choice", notification preview (fire the next scheduled one now), and the reset or rewind list.
5. **Web playtest build** (Expo web) for writers without a phone. Same engine, notifications replaced by a toast.
6. **CI with the same engine** (`prototype/explore.mjs` is the seed of it): `chatsim lint` (unknown tags, missing assets, unknown speakers or endings, choiceless loops, routes without an ending tag) and `chatsim explore` (walks all routes with state dedupe and reports ending counts, longest real-time route, unreachable knots). For the sample: 195 distinct states, 90 routes, endings `alone 48 / saved 24 / dark 18`, 0 problems.
7. **Shipping:** engine changes go out by EAS Update (OTA); new or updated cartridges are fetched from a URL catalogue, independent of app releases.

---

## 8. Testing

- **Engine unit tests** in Node with a fake clock: tag parsing, typing and wait arithmetic, notification planning (merge rule, cap), replay and divergence, save round-trip.
- **Golden route tests:** for each cartridge, fixed pick sequences produce a snapshot of the timeline (like `play.mjs`'s output).
- **Exploration in CI** for every cartridge (§7.6).
- **Device checklist:** kill the app, reboot the phone (rescheduling isn't needed because the OS keeps local notifications, but verify), Doze or Low Power mode, timezone change, notification permission denied (story must still be playable), and replying from a notification on the lock screen.

---

## 9. Milestones

1. **Engine core** (TypeScript port of `prototype/`, tests, zod schemas): about 1 week.
2. **Playable app:** chat screen, one theme layout, saves, local notifications, bundled cartridge.
3. **Dev loop:** dev server, hot reload with replay, dev menu, web build.
4. **Content pipeline:** CLI lint and explore in CI, remote cartridge catalogue, cartridge updates mid-playthrough.
5. **Polish:** terminal and SMS layouts, notification reply actions, endings gallery, rewind UI, accessibility pass.
6. **Later:** multiple simultaneous conversations (a `# chat:` tag per line, already reserved), remote push for live events, watch app, localisation (one compiled story per locale in the cartridge).

## 10. Open questions

- One conversation at a time (pure Lifeline), or several characters texting in parallel? The engine handles either, but parallel stories need a per-chat timeline and a merged notification budget.
- Monetisation: fast mode, extra cartridges, or rewinds? This affects the save model only lightly.
- Will authors need choice timeouts ("reply within 2 min or Wren decides")? This is possible with a `# timeout: 2m` choice tag plus a `# default` choice, but it can't be shown in a notification reliably.
