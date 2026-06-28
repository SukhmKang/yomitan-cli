// Serializes Yomitan's japanese-transforms descriptor into a flat JSON file that
// the Python LanguageTransformer (jp_cli/language_transformer.py) consumes.
//
// The descriptor under scripts/yomitan/ is Yomitan's file, vendored verbatim.
// This keeps that file the single source of truth: re-run this script after
// updating it to regenerate jp_cli/japanese_transforms.json.
//
//   node scripts/generate_transforms.mjs

import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { japaneseTransforms } from './yomitan/japanese-transforms.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const outPath = join(here, '..', 'jp_cli', 'japanese_transforms.json')

// Yomitan rules carry a compiled RegExp plus an opaque deinflect closure. We
// re-derive the literal affix from the regexp source and recover the output
// suffix/word, so Python can apply the same transform without running JS.
function serializeRule(rule, transformId, index) {
  const source = rule.isInflected.source
  if (rule.type === 'suffix') {
    return {
      type: 'suffix',
      inflected: source.replace(/\$$/, ''),
      deinflected: rule.deinflected,
      conditionsIn: rule.conditionsIn,
      conditionsOut: rule.conditionsOut,
    }
  }
  if (rule.type === 'wholeWord') {
    return {
      type: 'wholeWord',
      inflected: source.replace(/^\^/, '').replace(/\$$/, ''),
      deinflected: rule.deinflect(''),
      conditionsIn: rule.conditionsIn,
      conditionsOut: rule.conditionsOut,
    }
  }
  // prefixInflection is unused by the Japanese descriptor; fail loudly if added.
  throw new Error(`Unsupported rule type "${rule.type}" at ${transformId}.rules[${index}]`)
}

const conditions = {}
for (const [type, condition] of Object.entries(japaneseTransforms.conditions)) {
  conditions[type] = {
    isDictionaryForm: Boolean(condition.isDictionaryForm),
    subConditions: condition.subConditions ?? null,
  }
}

const transforms = []
for (const [id, transform] of Object.entries(japaneseTransforms.transforms)) {
  transforms.push({
    id,
    rules: transform.rules.map((rule, i) => serializeRule(rule, id, i)),
  })
}

const out = { language: japaneseTransforms.language, conditions, transforms }
writeFileSync(outPath, JSON.stringify(out, null, 1) + '\n')

const ruleCount = transforms.reduce((n, t) => n + t.rules.length, 0)
console.log(`Wrote ${outPath}`)
console.log(`  ${Object.keys(conditions).length} conditions, ${transforms.length} transforms, ${ruleCount} rules`)
