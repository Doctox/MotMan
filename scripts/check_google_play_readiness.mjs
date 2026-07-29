import { existsSync, readFileSync, statSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import process from 'node:process'

const root = path.resolve(import.meta.dirname, '..')
const staticOnly = process.argv.includes('--static')
const results = []

function record(status, label, detail) {
  results.push({ status, label, detail })
}

function read(relativePath) {
  return readFileSync(path.join(root, relativePath), 'utf8')
}

function assertStatic(condition, label, detail) {
  record(condition ? 'ok' : 'blocker', label, detail)
}

const capacitor = JSON.parse(read('capacitor.config.json'))
const variables = read('android/variables.gradle')
const gradle = read('android/app/build.gradle')
const manifest = read('android/app/src/main/AndroidManifest.xml')
const mainActivity = read('android/app/src/main/java/com/motman/game/MainActivity.java')
const baseCss = read('src/base.css')
const menuFoundationCss = read('src/menu/menu-foundation.css')
const gameActionsCss = read('src/styles/game-actions.css')

assertStatic(capacitor.appId === 'com.motman.game', 'Identifiant Android', capacitor.appId)
assertStatic(capacitor.appName === 'MotMan', 'Nom Android', capacitor.appName)
assertStatic(
  /WindowInsetsCompat\.Type\.systemBars\(\)/.test(mainActivity) &&
    /WindowInsetsCompat\.Type\.displayCutout\(\)/.test(mainActivity) &&
    /setPadding\(/.test(mainActivity),
  'Insets natifs Android',
  'WebView cadrée hors des barres système et des encoches',
)
assertStatic(
  /\.native-runtime[^{}]*\.native-runtime body[^{}]*\.native-runtime #root\{height:100%;min-height:0;overflow:hidden\}/.test(baseCss) &&
    /\.native-runtime \.mm-shell\{height:100%;min-height:0\}/.test(menuFoundationCss) &&
    /\.native-runtime \.multiplayer-shell:not\(\.is-finished\)\{[\s\S]*?height:100%;[\s\S]*?max-height:100%;/.test(gameActionsCss),
  'Viewport natif Android',
  'Menu, plateau et commandes utilisent la hauteur sûre de la WebView',
)
assertStatic(
  capacitor.android?.adjustMarginsForEdgeToEdge === 'force',
  'Marges des barres système Android',
  'Insets forcés pour protéger les commandes en mode bord à bord',
)
assertStatic(/compileSdkVersion\s*=\s*36/.test(variables), 'compileSdk', 'API 36')
assertStatic(/targetSdkVersion\s*=\s*36/.test(variables), 'targetSdk', 'API 36')
assertStatic(/versionCode\s+[1-9]\d*/.test(gradle), 'versionCode', 'Valeur positive')
assertStatic(/versionName\s+"[^"]+"/.test(gradle), 'versionName', gradle.match(/versionName\s+"([^"]+)"/)?.[1] ?? 'absent')
assertStatic(/android:allowBackup="false"/.test(manifest), 'Sauvegardes Android', 'Désactivées')
assertStatic(/android:usesCleartextTraffic="false"/.test(manifest), 'Trafic HTTP', 'Interdit')
assertStatic(/android\.permission\.INTERNET/.test(manifest), 'Permission réseau', 'INTERNET')

for (const relativePath of [
  'public/legal/confidentialite.html',
  'public/legal/conditions.html',
  'public/legal/credits.html',
  'public/legal/suppression-compte.html',
]) {
  assertStatic(existsSync(path.join(root, relativePath)), `Page légale ${path.basename(relativePath)}`, relativePath)
}

const accountDeletion = read('public/legal/suppression-compte.html')
assertStatic(
  /docteurtox@gmail\.com/.test(accountDeletion) && /Données supprimées/.test(accountDeletion),
  'Suppression de compte publique',
  'Contact et périmètre de suppression présents',
)

if (!staticOnly) {
  const googleServicesPath = path.join(root, 'android/app/google-services.json')
  if (!existsSync(googleServicesPath)) {
    record('blocker', 'Firebase Android', 'android/app/google-services.json absent')
  } else {
    try {
      const services = JSON.parse(readFileSync(googleServicesPath, 'utf8'))
      const packages = (services.client ?? [])
        .map(client => client?.client_info?.android_client_info?.package_name)
        .filter(Boolean)
      record(
        packages.includes('com.motman.game') ? 'ok' : 'blocker',
        'Firebase Android',
        packages.includes('com.motman.game') ? 'Package com.motman.game configuré' : 'Package com.motman.game absent du fichier',
      )
    } catch {
      record('blocker', 'Firebase Android', 'google-services.json invalide')
    }
  }

  const signingNames = [
    'MOTMAN_KEYSTORE_PATH',
    'MOTMAN_KEYSTORE_PASSWORD',
    'MOTMAN_KEY_ALIAS',
    'MOTMAN_KEY_PASSWORD',
  ]
  const missingSigning = signingNames.filter(name => !process.env[name])
  if (missingSigning.length === signingNames.length) {
    record('manual', 'Signature automatisée', 'Non configurée ; Android Studio reste utilisable pour signer manuellement')
  } else if (missingSigning.length) {
    record('blocker', 'Signature automatisée', `Configuration partielle : ${missingSigning.join(', ')} absent(s)`)
  } else if (!existsSync(process.env.MOTMAN_KEYSTORE_PATH)) {
    record('blocker', 'Signature automatisée', 'Le keystore indiqué est introuvable')
  } else {
    record('ok', 'Signature automatisée', 'Quatre variables présentes et keystore accessible')
  }

  const configuredBundlePath = process.env.MOTMAN_AAB_PATH
    ? path.resolve(root, process.env.MOTMAN_AAB_PATH)
    : null
  const bundleCandidates = [
    configuredBundlePath,
    path.join(root, 'android/app/release/app-release.aab'),
    path.join(root, 'android/app/build/outputs/bundle/release/app-release.aab'),
  ]
    .filter(Boolean)
    .filter(existsSync)
    .sort((left, right) => statSync(right).mtimeMs - statSync(left).mtimeMs)
  const bundlePath = bundleCandidates[0]
  if (!bundlePath) {
    record('blocker', 'Bundle candidat', 'Exécuter npm run mobile:aab')
  } else {
    const javaRoots = [
      process.env.JAVA_HOME,
      'C:\\Program Files\\Android\\Android Studio1\\jbr',
      'C:\\Program Files\\Android\\Android Studio\\jbr',
    ].filter(Boolean)
    const jarsigner = javaRoots
      .map(javaRoot => path.join(javaRoot, 'bin', process.platform === 'win32' ? 'jarsigner.exe' : 'jarsigner'))
      .find(existsSync)
    if (!jarsigner) {
      record('blocker', 'Signature du bundle', 'jarsigner introuvable')
    } else {
      const verification = spawnSync(jarsigner, ['-verify', bundlePath], { encoding: 'utf8' })
      const signed = verification.status === 0 && !/jar is unsigned/i.test(`${verification.stdout}\n${verification.stderr}`)
      const relativeBundlePath = path.relative(root, bundlePath)
      record('blocker', 'Signature du bundle', signed ? `${relativeBundlePath} signé` : `${relativeBundlePath} non signé`)
      if (signed) results.at(-1).status = 'ok'
    }
  }

  record('manual', 'Firebase serveur', 'Vérifier FIREBASE_SERVICE_ACCOUNT_JSON dans les secrets Edge Functions')
  record('manual', 'Google Play Billing', 'Obligatoire avant de vendre des plumes ; non implémenté actuellement')
  record('manual', 'Fiche Play Store', 'Icône 512, bannière 1024×500 et captures téléphone/tablette à fournir')
  record('manual', 'Play Console', 'Data Safety, IARC, audience, accès test et test fermé à compléter')
}

const icons = { ok: 'OK', blocker: 'BLOQUANT', manual: 'MANUEL' }
for (const result of results) {
  console.log(`[${icons[result.status]}] ${result.label} — ${result.detail}`)
}

const blockers = results.filter(result => result.status === 'blocker')
console.log(`\nBilan : ${results.filter(result => result.status === 'ok').length} vérifications validées, ${blockers.length} blocage(s), ${results.filter(result => result.status === 'manual').length} contrôle(s) manuel(s).`)
if (blockers.length) process.exitCode = 1
