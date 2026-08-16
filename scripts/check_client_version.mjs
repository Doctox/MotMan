// Contrôle de build : cohérence des trois sources de version de l'application.
//
// POURQUOI CE SCRIPT EXISTE : l'APK s'annonce au serveur avec
// ANDROID_VERSION_CODE (src/clientVersion.ts, en-tête x-motman-version-code),
// alors que le code réellement publié sur Google Play est celui de
// android/app/build.gradle. Le 16/08/2026, clientVersion.ts annonçait 5 / 1.0.4
// pendant que le bundle était en 6 / 1.0.5. Dans cette situation, monter
// `minimum_android_version_code` à 6 (procédure docs/GOOGLE_PLAY.md) affiche à
// TOUS les testeurs un écran « mise à jour obligatoire » sans issue possible côté
// client (src/RequiredAppUpdate.tsx). Le seul remède serait une requête SQL.
//
// Ce script fait donc ÉCHOUER le build (exit 1) dès que les trois sources
// divergent, plutôt que de laisser passer une désynchronisation silencieuse.

import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const ROOT = process.cwd()
const CLIENT_VERSION = path.join(ROOT, 'src', 'clientVersion.ts')
const BUILD_GRADLE = path.join(ROOT, 'android', 'app', 'build.gradle')
const PACKAGE_JSON = path.join(ROOT, 'package.json')

function fail(message) {
  console.error(`\n✖ Versions désynchronisées — build interrompu.\n  ${message}\n`)
  process.exit(1)
}

function read(file, label) {
  if (!fs.existsSync(file)) fail(`${label} introuvable : ${file}`)
  return fs.readFileSync(file, 'utf8')
}

function matchOne(text, pattern, label) {
  const found = text.match(pattern)
  if (!found) fail(`${label} : motif introuvable (${pattern}). Le format du fichier a changé, adaptez ce contrôle.`)
  return found[1]
}

const clientSource = read(CLIENT_VERSION, 'src/clientVersion.ts')
const gradleSource = read(BUILD_GRADLE, 'android/app/build.gradle')
const packageSource = read(PACKAGE_JSON, 'package.json')

const clientCode = Number(matchOne(clientSource, /ANDROID_VERSION_CODE\s*=\s*(\d+)/, 'src/clientVersion.ts'))
const clientName = matchOne(clientSource, /ANDROID_VERSION_NAME\s*=\s*'([^']+)'/, 'src/clientVersion.ts')
const gradleCode = Number(matchOne(gradleSource, /versionCode\s+(\d+)/, 'android/app/build.gradle'))
const gradleName = matchOne(gradleSource, /versionName\s+"([^"]+)"/, 'android/app/build.gradle')
const packageName = matchOne(packageSource, /"version"\s*:\s*"([^"]+)"/, 'package.json')

const problems = []
if (!Number.isInteger(clientCode) || clientCode <= 0) problems.push(`src/clientVersion.ts : ANDROID_VERSION_CODE invalide (${clientCode})`)
if (clientCode !== gradleCode) {
  problems.push(`versionCode : src/clientVersion.ts annonce ${clientCode}, android/app/build.gradle publie ${gradleCode}`)
}
if (clientName !== gradleName) {
  problems.push(`versionName : src/clientVersion.ts annonce « ${clientName} », android/app/build.gradle publie « ${gradleName} »`)
}
if (clientName !== packageName) {
  problems.push(`version : src/clientVersion.ts annonce « ${clientName} », package.json déclare « ${packageName} »`)
}

if (problems.length) {
  fail(`${problems.length} écart(s) :\n  - ${problems.join('\n  - ')}\n\n  Alignez les TROIS sources sur la même valeur avant de construire.`)
}

console.log(`✓ Versions alignées : versionCode ${clientCode}, versionName ${clientName} (clientVersion.ts = build.gradle = package.json).`)
