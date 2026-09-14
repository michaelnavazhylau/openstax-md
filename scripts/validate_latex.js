#!/usr/bin/env node
/**
 * Independent LaTeX validation: parse every math span in the compiled Markdown
 * with KaTeX (the renderer OpenStax uses on openstax.org).
 *
 *   npm install katex && node scripts/validate_latex.js build/calculus
 *
 * Exit code is non-zero if any span fails to parse.
 */
const fs = require("fs");
const path = require("path");

let katex;
try {
  katex = require("katex");
} catch {
  console.error("katex not installed: run `npm install katex` first");
  process.exit(2);
}

const dir = process.argv[2];
if (!dir || !fs.existsSync(dir)) {
  console.error("usage: node scripts/validate_latex.js <compiled-output-dir>");
  process.exit(2);
}

const files = [];
(function walk(d) {
  for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, entry.name);
    if (entry.isDirectory()) walk(p);
    else if (entry.name.endsWith(".md")) files.push(p);
  }
})(dir);

/**
 * Find math spans without tripping over escaped dollars (currency in the prose
 * is escaped as \$) and without letting an inline span cross a blank line.
 */
function findSpans(text) {
  const spans = [];
  let i = 0;
  while (i < text.length) {
    if (text[i] === "\\") {
      i += 2;
      continue;
    }
    if (text[i] !== "$") {
      i += 1;
      continue;
    }
    const display = text[i + 1] === "$";
    const start = i + (display ? 2 : 1);
    let j = start;
    let closed = false;
    while (j < text.length) {
      const ch = text[j];
      if (ch === "\\") {
        j += 2;
        continue;
      }
      if (ch === "\n" && !display && text[j + 1] !== "\n") {
        break; // inline math cannot span lines
      }
      if (ch === "$") {
        if (!display) {
          closed = true;
          break;
        }
        if (text[j + 1] === "$") {
          closed = true;
          break;
        }
      }
      j += 1;
    }
    if (!closed) {
      i = start;
      continue;
    }
    spans.push({ display, body: text.slice(start, j) });
    i = display ? j + 2 : j + 1;
  }
  return spans;
}

let spans = 0;
const errors = [];
const warnings = new Map();

for (const file of files) {
  const text = fs.readFileSync(file, "utf8");
  for (const { display, body } of findSpans(text)) {
    spans += 1;
    const realWarn = console.warn;
    console.warn = () => {};
    try {
      katex.renderToString(body, {
        throwOnError: true,
        displayMode: display,
        strict: (code, msg) => {
          const key = `${code}: ${msg.split("\n")[0]}`;
          if (!warnings.has(key)) warnings.set(key, { n: 0, example: body.slice(0, 90) });
          warnings.get(key).n += 1;
        },
      });
    } catch (err) {
      errors.push({
        file: path.relative(dir, file),
        body: body.replace(/\n/g, " ").slice(0, 120),
        message: String(err.message).replace(/\s+/g, " ").slice(0, 160),
      });
    } finally {
      console.warn = realWarn;
    }
  }
}

console.log(`files: ${files.length}`);
console.log(`math spans parsed by KaTeX: ${spans}`);
console.log(`parse errors: ${errors.length}`);
console.log(`unsupported-input categories: ${warnings.size}`);
for (const e of errors.slice(0, 20)) console.log(`  ERROR ${e.file}: ${e.message}\n        ${e.body}`);
for (const [key, info] of [...warnings].sort((a, b) => b[1].n - a[1].n).slice(0, 8)) {
  console.log(`  ${info.n}x ${key}\n        e.g. ${info.example}`);
}

process.exit(errors.length ? 1 : 0);
