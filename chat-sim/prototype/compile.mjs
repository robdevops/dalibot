// Compiles .ink source to ink JSON with the compiler bundled in inkjs (no inklecate needed).
import fs from 'node:fs';
import { Compiler } from 'inkjs/full';
const [src, out] = process.argv.slice(2);
const c = new Compiler(fs.readFileSync(src, 'utf8'));
const story = c.Compile();
if (c.errors.length) { console.error(c.errors.join('\n')); process.exit(1); }
for (const w of c.warnings) console.warn(w);
fs.writeFileSync(out, story.ToJson());
console.log(`wrote ${out}`);
