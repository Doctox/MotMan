import { mkdir, rm } from 'node:fs/promises'
import { resolve } from 'node:path'

const directory = resolve('output/playwright/state')
await mkdir(directory, { recursive: true })
await Promise.all([
  rm(resolve(directory, 'matches.json'), { force: true }),
  rm(resolve(directory, 'social.json'), { force: true }),
])
