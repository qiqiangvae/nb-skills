#!/usr/bin/env node
/**
 * fix-session-preset.mjs
 *
 * Safely rewrite the preset recorded in a DSH session's `session.jsonl.zstd`
 * WITHOUT disturbing its multi-frame Zstandard container format.
 *
 * WHY THIS EXISTS
 * ---------------
 * DSH stores one session per directory under:
 *     ~/.dsh/sessions/<projectKey>/<sessionId>/session.jsonl.zstd
 *
 * The file is a CONCATENATION of many independently-decodable, checksummed
 * zstd frames. The first frame MUST contain exactly one header line
 * (`assertZstdHeaderFrame` rejects anything else). A session's effective
 * preset is resolved by `resolveSessionPreset` (see
 * @deepseek-ai/dsh-agent-presets/lib/types/session.js): it walks the event
 * log BACKWARDS and returns the `agentPreset` of the LAST
 * `agent-preset/selected` event, falling back to the header's `agentPreset`.
 *
 * If that recorded preset id no longer exists (e.g. a custom preset directory
 * was deleted from ~/.dsh/.agent-presets/), resuming the session fails with:
 *     Error: agent-presets: preset "X" not found (available: ...)
 *
 * THE MISTAKE NOT TO MAKE
 * -----------------------
 * Do NOT decompress the whole file and recompress it with the `zstd` CLI
 * (`zstd -f`). That collapses the 2000+ frames into ONE frame, so the first
 * frame is no longer "exactly one header line" and the frame-boundary scan
 * breaks — DSH throws and the harness can crash. This script instead:
 *   1. scans frames exactly like DSH's `scanZstdFrames`,
 *   2. finds the single frame containing the `agent-preset/selected` line,
 *   3. rewrites ONLY that frame's plaintext (oldPreset -> newPreset),
 *   4. recompresses that ONE frame with a checksum (matching the write path),
 *   5. splices it back in, leaving all other frames byte-identical.
 *
 * USAGE
 * -----
 *   node fix-session-preset.mjs <sessionDirOrZstdFile> <oldPreset> <newPreset>
 *
 *   node fix-session-preset.mjs \
 *     "$HOME/.dsh/sessions/--Users-me-Code-proj--/abc-123/session.jsonl.zstd" \
 *     pp-liangshen pingpong
 *
 * The script writes the repaired file to a sibling `<name>.fixed.zstd` and
 * prints a verification report. It NEVER overwrites the input in place — you
 * review and copy the fixed file over yourself (after backing up).
 */

import { zstdDecompressSync, zstdCompressSync, constants } from "node:zlib";
import { readFileSync, writeFileSync, statSync } from "node:fs";
import { dirname, join, basename } from "node:path";

const ZSTD_MAGIC = 4247762216; // 0xFD2FB528 little-endian

function fail(msg) {
  console.error(`[fix-session-preset] ERROR: ${msg}`);
  process.exit(1);
}

/**
 * Reproduce DSH's scanZstdFrames: walk the concatenated-frame container and
 * return { frames: [{start,end}], tornStart }.
 */
function scanZstdFrames(buffer) {
  const frames = [];
  let offset = 0;
  while (offset < buffer.length) {
    const start = offset;
    if (buffer.length - offset < 4) return { frames, tornStart: start };
    if (buffer.readUInt32LE(offset) !== ZSTD_MAGIC) {
      fail(`invalid frame magic at byte ${offset} — not a DSH zstd container`);
    }
    offset += 4;
    const descriptor = buffer.readUInt8(offset);
    offset += 1;
    const contentSizeFlag = descriptor >>> 6;
    const singleSegment = (descriptor & 32) !== 0;
    const checksum = (descriptor & 4) !== 0;
    const dictionaryFlag = descriptor & 3;
    const dictionaryBytes = dictionaryFlag === 3 ? 4 : dictionaryFlag;
    const contentSizeBytes =
      contentSizeFlag === 0 ? (singleSegment ? 1 : 0) : 1 << contentSizeFlag;
    const remainingHeaderBytes =
      (singleSegment ? 0 : 1) + dictionaryBytes + contentSizeBytes;
    if (buffer.length - offset < remainingHeaderBytes) {
      return { frames, tornStart: start };
    }
    offset += remainingHeaderBytes;
    for (;;) {
      if (buffer.length - offset < 3) return { frames, tornStart: start };
      const blockHeader = buffer.readUIntLE(offset, 3);
      offset += 3;
      const lastBlock = (blockHeader & 1) !== 0;
      const blockType = (blockHeader >>> 1) & 3;
      const blockSize = blockHeader >>> 3;
      const payloadBytes = blockType === 1 ? 1 : blockSize;
      if (buffer.length - offset < payloadBytes) {
        return { frames, tornStart: start };
      }
      offset += payloadBytes;
      if (lastBlock) break;
    }
    if (checksum) {
      if (buffer.length - offset < 4) return { frames, tornStart: start };
      offset += 4;
    }
    frames.push({ start, end: offset });
  }
  return { frames };
}

const args = process.argv.slice(2);
if (args.length !== 3) {
  fail(`usage: node fix-session-preset.mjs <session.jsonl.zstd> <oldPreset> <newPreset>\ngot: ${JSON.stringify(args)}`);
}
const [target, oldPreset, newPreset] = args;

// Allow pointing at a directory (the session dir) or the file directly.
let filePath = target;
if (statSync(target).isDirectory()) filePath = join(target, "session.jsonl.zstd");

console.log(`[fix-session-preset] input : ${filePath}`);
console.log(`[fix-session-preset] preset: "${oldPreset}" -> "${newPreset}"`);

const buf = readFileSync(filePath);
const { frames, tornStart } = scanZstdFrames(buf);
console.log(`[fix-session-preset] frames: ${frames.length}${tornStart !== undefined ? ` (torn tail at ${tornStart})` : ""}`);

const needle = `"agentPreset":"${oldPreset}"`;
console.log(`[fix-session-preset] looking for frame containing: ${needle}`);

let matched = 0;
let output = buf;
for (let i = frames.length - 1; i >= 0; i--) {
  const f = frames[i];
  let plain;
  try {
    plain = zstdDecompressSync(buf.subarray(f.start, f.end)).toString("utf8");
  } catch (e) {
    fail(`frame #${i} failed to decode (corrupt?): ${e.message}`);
  }
  if (!plain.includes(`agent-preset/selected`)) continue;
  // Only rewrite the *latest* selection carrying the old id.
  if (!plain.includes(needle)) continue;
  const fixed = plain.replace(needle, `"agentPreset":"${newPreset}"`);
  const reframed = zstdCompressSync(Buffer.from(fixed), {
    params: { [constants.ZSTD_c_checksumFlag]: 1 },
  });
  console.log(
    `[fix-session-preset] rewriting frame #${i} (bytes ${f.start}-${f.end}, ` +
      `${f.end - f.start}B -> ${reframed.length}B)`
  );
  output = Buffer.concat([output.subarray(0, f.start), reframed, output.subarray(f.end)]);
  matched += 1;
  break; // newest selection wins; stop after first from the tail
}

if (matched === 0) {
  fail(`no frame containing ${needle}; is "${oldPreset}" the right id?`);
}

const outPath = join(dirname(filePath), `${basename(filePath, ".zstd")}.fixed.zstd`);
writeFileSync(outPath, output);

// ---- verification ----
const verify = readFileSync(outPath);
const { frames: vFrames, tornStart: vTorn } = scanZstdFrames(verify);
let full = "";
let ok = true;
for (let i = 0; i < vFrames.length; i++) {
  const f = vFrames[i];
  try {
    full += zstdDecompressSync(verify.subarray(f.start, f.end)).toString("utf8");
  } catch {
    ok = false;
    console.log(`[fix-session-preset] VERIFY FAIL: frame #${i} does not decode`);
    break;
  }
}
const firstFrame = zstdDecompressSync(
  verify.subarray(vFrames[0].start, vFrames[0].end)
).toString("utf8");
const headerOk = firstFrame.length > 0 && firstFrame.indexOf("\n") === firstFrame.length - 1;
const stillOld = full.includes(needle);
const hasNew = full.includes(`"agentPreset":"${newPreset}"`);

console.log(`\n[fix-session-preset] === verification of ${outPath} ===`);
console.log(`  frames            : ${vFrames.length} (input had ${frames.length})`);
console.log(`  torn tail         : ${vTorn === undefined ? "none" : "at " + vTorn}`);
console.log(`  all frames decode : ${ok ? "OK" : "FAIL"}`);
console.log(`  header frame      : ${headerOk ? "OK (single line)" : "FAIL"}`);
console.log(`  old preset present: ${stillOld ? "YES (BAD)" : "no (good)"}`);
console.log(`  new preset present: ${hasNew ? "yes" : "NO (BAD)"}`);
console.log(
  "\n[fix-session-preset] Next steps (manual, safe):\n" +
    "  1. cp <input> <input>.orig\n" +
    "  2. cp <output> <input>\n" +
    "  3. reload/resume the session"
);
