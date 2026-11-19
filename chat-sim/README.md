# chat-sim

Design and working prototype for a Lifeline-style chat game engine: Ink stories and JSON themes loaded as cartridges, with real-time waits delivered as local notifications.

- [DESIGN.md](DESIGN.md): the design (technology choice, cartridge format, Ink tag conventions, runtime, iteration workflow)
- `example-cartridge/`: a sample story ("Signal Fire") with manifest and theme
- `prototype/`: the engine core in plain JS on inkjs

```bash
cd prototype && npm install
npm run compile                 # .ink -> ink JSON
npm run play -- 1,1,2,1,0       # one route: timeline + notifications that would be scheduled
npm run explore                 # walk every route: endings reached, dead ends, loops
```
