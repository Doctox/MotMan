import fs from 'node:fs'
import postcss from 'postcss'

const files = ['src/styles.css', 'src/menu.css']
const shouldWrite = process.argv.includes('--write')

function atRuleContext(node) {
  const parts = []
  let parent = node.parent
  while (parent && parent.type !== 'root') {
    if (parent.type === 'atrule') parts.push(`@${parent.name} ${parent.params}`)
    parent = parent.parent
  }
  return parts.reverse().join('|')
}

function compactFile(file) {
  const source = fs.readFileSync(file, 'utf8')
  const root = postcss.parse(source, { from: file })
  const latestDeclarations = new Map()
  let declarationsRemoved = 0
  let keyframesRemoved = 0

  root.walkRules(rule => {
    if (rule.parent?.type === 'atrule' && /keyframes$/i.test(rule.parent.name)) return

    const ruleKey = `${atRuleContext(rule)}::${rule.selector}`
    let declarations = latestDeclarations.get(ruleKey)
    if (!declarations) {
      declarations = new Map()
      latestDeclarations.set(ruleKey, declarations)
    }

    rule.walkDecls(declaration => {
      const previous = declarations.get(declaration.prop)
      if (!previous) {
        declarations.set(declaration.prop, declaration)
        return
      }

      // A normal declaration cannot supersede an earlier !important one.
      if (previous.important && !declaration.important) return

      previous.remove()
      declarations.set(declaration.prop, declaration)
      declarationsRemoved += 1
    })
  })

  const latestKeyframes = new Map()
  root.walkAtRules(/keyframes$/i, keyframes => {
    const key = `${atRuleContext(keyframes)}::${keyframes.name}:${keyframes.params}`
    const previous = latestKeyframes.get(key)
    if (previous) {
      previous.remove()
      keyframesRemoved += 1
    }
    latestKeyframes.set(key, keyframes)
  })

  root.walkRules(rule => {
    if (!rule.nodes?.length) rule.remove()
  })

  const output = root.toString()
  if (shouldWrite && output !== source) fs.writeFileSync(file, output)

  return {
    file,
    declarationsRemoved,
    keyframesRemoved,
    bytesBefore: Buffer.byteLength(source),
    bytesAfter: Buffer.byteLength(output),
  }
}

const results = files.map(compactFile)
for (const result of results) console.log(JSON.stringify(result))
if (!shouldWrite) console.log('Analyse uniquement. Ajoutez --write pour appliquer le nettoyage.')
