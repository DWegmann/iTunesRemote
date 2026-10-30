import { test, expect } from '@playwright/test'
import progressCases from '../../tests/import_progress_cases.json' with { type: 'json' }

test.beforeEach(async ({ page, request }) => {
  const response = await request.get('/api/v1/auth/password', {
    headers: { Authorization: 'Bearer isolated-ui-tests-only' },
  })
  const { password } = await response.json()
  await page.goto('/')
  await page.getByLabel('Passwort', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Deine Sammlung.' })).toBeVisible()
})

test('search, filter and save a confirmed rating', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.getByPlaceholder('Titel, Interpret oder Album suchen …').fill('Radiohead')
  await expect(page.locator('.track-row')).toHaveCount(6)
  await page.getByRole('button', { name: '5 Sterne für Nude', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('„Nude“ mit 5 Sternen gespeichert')
  const result = await page.request.get('/api/v1/tracks?query=Nude')
  expect((await result.json()).items[0].ratingRaw).toBe(100)
  await page.getByRole('button', { name: 'Details zu Nude', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: 'Eigene Bewertung entfernen', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('Noch keine eigene Bewertung.')
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
  await page.getByRole('button', { name: 'Schließen', exact: true }).click()
  expect(errors).toEqual([])
})

test('ratings appear immediately in the list and details while saving is pending', async ({ page }) => {
  let release: () => void = () => {}
  let pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/rating-queue', async route => {
    await pending
    await route.continue()
  })
  const row = page.locator('.track-row').filter({ has: page.getByRole('button', { name: 'Details zu Nude', exact: true }) })
  await row.getByRole('button', { name: '5 Sterne für Nude', exact: true }).click()
  await expect(row.getByRole('button', { name: '5 Sterne für Nude', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(row.locator('.star-button.on')).toHaveCount(5)
  await expect(row.getByLabel('Wird gespeichert')).toBeVisible()
  await expect(row.getByRole('button', { name: '1 Stern für Nude', exact: true })).toBeEnabled()
  await expect(page.getByRole('status')).not.toContainText('gespeichert')
  const cached = (await (await page.request.get('/api/v1/tracks?query=Nude')).json()).items[0]
  expect(cached.ratingRaw).toBe(0)
  await page.getByRole('combobox', { name: 'Sortierung', exact: true }).selectOption('title')
  await expect(page.locator('.track-main strong').first()).toHaveText('15 Step')
  await expect(row.getByRole('button', { name: '5 Sterne für Nude', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await row.getByRole('button', { name: 'Details zu Nude', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('5 von 5 Sternen · selbst vergeben')
  await expect(dialog.getByLabel('Wird gespeichert')).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Eigene Bewertung entfernen', exact: true })).toBeEnabled()
  await page.screenshot({ path: '../build/qa-pending-rating.png', animations: 'disabled' })
  release()
  await expect(page.getByRole('status')).toContainText('„Nude“ mit 5 Sternen gespeichert')
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
  pending = new Promise<void>(resolve => { release = resolve })
  await dialog.getByRole('button', { name: 'Eigene Bewertung entfernen', exact: true }).click()
  await expect(dialog).toContainText('Noch keine eigene Bewertung.')
  await expect(dialog.locator('.star-button.on')).toHaveCount(0)
  await expect(row.locator('.star-button.on')).toHaveCount(0)
  await expect(dialog.getByLabel('Wird gespeichert')).toBeVisible()
  await expect(page.getByRole('status')).not.toContainText('gespeichert')
  release()
  await expect(page.getByRole('status')).toContainText('Eigene Bewertung entfernt')
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
  await dialog.getByRole('button', { name: 'Schließen', exact: true }).click()
})

test('a confirmed rating stops saving before a slow status refresh finishes', async ({ page }) => {
  let release: () => void = () => {}
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/status', async route => {
    await pending
    await route.continue()
  })
  try {
    await page.getByRole('button', { name: '5 Sterne für Nude', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('„Nude“ mit 5 Sternen gespeichert')
    await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '4 Sterne für Nude', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: 'Details zu Nude', exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText('5 von 5 Sternen · selbst vergeben')
  } finally { release() }
  await page.getByRole('button', { name: 'Eigene Bewertung entfernen', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Eigene Bewertung entfernt')
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
  await page.getByRole('button', { name: 'Schließen', exact: true }).click()
})

test('rapid ratings keep controls available and send only the latest buffered choices', async ({ page }) => {
  let release: () => void = () => {}
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/rating-queue', async route => {
    await pending
    await route.continue()
  })
  for (const stars of [5, 4, 2]) {
    await page.getByRole('button', { name: `${stars} Sterne für Nude`, exact: true }).click()
  }
  await page.getByRole('button', { name: '3 Sterne für Reckoner', exact: true }).click()
  await expect(page.getByRole('button', { name: '2 Sterne für Nude', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('button', { name: '3 Sterne für Reckoner', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(2)
  await expect(page.getByRole('button', { name: '5 Sterne für Nude', exact: true })).toBeEnabled()
  await expect(page.getByRole('region', { name: 'Bewertungswarteschlange' })).toContainText('Bewertungen ausstehend')
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: '../build/qa-rating-queue.png', animations: 'disabled' })
  await page.setViewportSize({ width: 320, height: 800 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  await page.screenshot({ path: '../build/qa-rating-queue-mobile.png', animations: 'disabled' })
  release()
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
  for (const [title, raw] of [['Nude', 40], ['Reckoner', 60]] as const) {
    const track = (await (await page.request.get(`/api/v1/tracks?query=${title}`)).json()).items[0]
    expect(track.ratingRaw).toBe(raw)
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  for (const title of ['Nude', 'Reckoner']) {
    await page.getByRole('button', { name: `Details zu ${title}`, exact: true }).click()
    await page.getByRole('button', { name: 'Eigene Bewertung entfernen', exact: true }).click()
    await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
    await page.getByRole('button', { name: 'Schließen', exact: true }).click()
  }
})

test('accepted queue entries survive reloading and finish without resending the choice', async ({ page }) => {
  let held = true
  let uploads = 0
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/rating-queue')) uploads++ })
  await page.route('**/api/v1/rating-queue?**', async route => {
    const response = await route.fetch()
    const result = await response.json()
    await route.fulfill({ json: held ? { ...result, items: result.items.map((job: { state: string }) =>
      job.state === 'confirmed' ? { ...job, state: 'running', result: null } : job) } : result })
  })
  await page.getByRole('button', { name: '5 Sterne für Nude', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Bewertungswarteschlange' })).toContainText('im Hintergrund gespeichert')
  await expect.poll(async () => (await (await page.request.get('/api/v1/tracks?query=Nude')).json()).items[0].ratingRaw).toBe(100)
  await page.reload()
  await expect(page.getByRole('button', { name: '5 Sterne für Nude', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(1)
  held = false
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
  expect(uploads).toBe(1)
  await page.getByRole('button', { name: 'Details zu Nude', exact: true }).click()
  await page.getByRole('button', { name: 'Eigene Bewertung entfernen', exact: true }).click()
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
  await page.getByRole('button', { name: 'Schließen', exact: true }).click()
})

test('the Mac finishes accepted ratings after the browser tab closes', async ({ page, context }) => {
  const accepted = page.waitForResponse(response => response.request().method() === 'POST'
    && response.url().endsWith('/rating-queue') && response.status() === 202)
  await page.getByRole('button', { name: '4 Sterne für Nude', exact: true }).click()
  await accepted
  await page.close()
  await expect.poll(async () => (await (await context.request.get('/api/v1/tracks?query=Nude')).json()).items[0].ratingRaw).toBe(80)
  const reopened = await context.newPage()
  await reopened.goto('/')
  await expect(reopened.getByRole('button', { name: '4 Sterne für Nude', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(reopened.getByLabel('Wird gespeichert')).toHaveCount(0)
  await reopened.getByRole('button', { name: 'Details zu Nude', exact: true }).click()
  await reopened.getByRole('button', { name: 'Eigene Bewertung entfernen', exact: true }).click()
  await expect(reopened.getByLabel('Wird gespeichert')).toHaveCount(0)
  await reopened.getByRole('button', { name: 'Schließen', exact: true }).click()
})

test('a lost enqueue response survives reload and reuses its request ID', async ({ page }) => {
  let release: () => void = () => {}
  const pending = new Promise<void>(resolve => { release = resolve })
  const ids: string[] = []
  await page.route('**/api/v1/rating-queue', async route => {
    ids.push(route.request().postDataJSON().items[0].requestId)
    if (ids.length === 1) {
      await route.fetch()
      await route.abort('internetdisconnected')
    } else {
      await pending
      await route.continue()
    }
  })
  await page.getByRole('button', { name: '5 Sterne für Nude', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Der Mac ist gerade nicht erreichbar')
  await page.reload()
  await expect(page.getByRole('button', { name: '5 Sterne für Nude', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(1)
  release()
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
  expect(ids.length).toBe(2)
  expect(ids[0]).toBe(ids[1])
  const status = await (await page.request.get('/api/v1/status')).json()
  const jobs = await (await page.request.get(`/api/v1/rating-queue?libraryScope=${status.libraryScope}&ids=${ids[0]}`)).json()
  expect(jobs.items).toHaveLength(1)
  expect(jobs.items[0].state).toBe('confirmed')
  await page.getByRole('button', { name: 'Details zu Nude', exact: true }).click()
  await page.getByRole('button', { name: 'Eigene Bewertung entfernen', exact: true }).click()
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
  await page.getByRole('button', { name: 'Schließen', exact: true }).click()
})

for (const conflict of [false, true]) {
  test(`pending ratings restore ${conflict ? 'the current conflicting value' : 'the previous value on failure'}`, async ({ page }) => {
    const original = (await (await page.request.get('/api/v1/tracks?query=Nude')).json()).items[0]
    const current = conflict ? { ...original, ratingRaw: 40, ratingOrigin: 'user', ratingRevision: 'conflicting-rating' } : original
    let release: () => void = () => {}
    const pending = new Promise<void>(resolve => { release = resolve })
    await page.route('**/api/v1/rating-queue', async route => {
      await pending
      await route.fulfill({ status: conflict ? 409 : 503, json: { error: {
        code: conflict ? 'RATING_CONFLICT' : 'MUSIC_EVENT_FAILED', message: 'Simulierter Speicherfehler',
        details: conflict ? { track: current } : {},
      } } })
    })
    const row = page.locator('.track-row').filter({ has: page.getByRole('button', { name: 'Details zu Nude', exact: true }) })
    await row.getByRole('button', { name: '5 Sterne für Nude', exact: true }).click()
    await expect(row.getByRole('button', { name: '5 Sterne für Nude', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(row.getByLabel('Wird gespeichert')).toBeVisible()
    release()
    await expect(page.getByRole('alert')).toContainText('Simulierter Speicherfehler')
    await expect(row.locator('.star-button.on')).toHaveCount(current.ratingRaw / 20)
    await expect(row.getByLabel('Wird gespeichert')).toHaveCount(0)
    await expect(page.getByRole('status')).toContainText('nicht gespeichert')
    await row.getByRole('button', { name: 'Details zu Nude', exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText(conflict ? '2 von 5 Sternen · selbst vergeben' : 'Noch keine eigene Bewertung.')
    await page.getByRole('button', { name: 'Schließen', exact: true }).click()
    await page.getByRole('button', { name: 'Fehler verwerfen', exact: true }).click()
    await expect(page.getByRole('region', { name: 'Bewertungswarteschlange' })).toHaveCount(0)
  })
}

test('status polling after a rating and tab wake never starts a full import', async ({ page }) => {
  await page.clock.install()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Deine Sammlung.' })).toBeVisible()
  let next = await (await page.request.get('/api/v1/status')).json()
  let imports = 0
  await page.route('**/api/v1/library/refresh', async route => {
    imports++
    await route.fulfill({ json: next })
  })
  await page.getByRole('button', { name: '4 Sterne für Nude', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('„Nude“ mit 4 Sternen gespeichert')
  await expect(page.getByRole('button', { name: '4 Sterne für Nude', exact: true })).toBeEnabled()
  next = await (await page.request.get('/api/v1/status')).json()
  let checks = 0
  await page.route('**/api/v1/status', async route => {
    next = { ...next, counts: { ...next.counts, total: 100 + ++checks } }
    await route.fulfill({ json: next })
  })
  const total = page.getByRole('button', { name: /^Alle Titel/ }).locator('.nav-count')
  for (const expected of [101, 102]) {
    await page.clock.runFor(30_000)
    await expect(total).toHaveText(String(expected))
  }
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
  await expect(total).toHaveText('103')
  expect(imports).toBe(0)
  await page.getByRole('button', { name: 'Bibliothek aktualisieren', exact: true }).click()
  await expect.poll(() => imports).toBe(1)
  await page.getByRole('button', { name: 'Details zu Nude', exact: true }).click()
  await page.getByRole('button', { name: 'Eigene Bewertung entfernen', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('Noch keine eigene Bewertung.')
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
  await page.getByRole('button', { name: 'Schließen', exact: true }).click()
})

test('password login supports logout, errors, retry and session reload', async ({ page, request }) => {
  const credentials = await request.get('/api/v1/auth/password', {
    headers: { Authorization: 'Bearer isolated-ui-tests-only' },
  })
  const { password } = await credentials.json()
  await page.getByRole('button', { name: 'Verbindung & API', exact: true }).click()
  await page.getByRole('button', { name: 'Abmelden', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Mit deinem Mac verbinden' })).toBeVisible()
  await expect(page.locator('.track-row')).toHaveCount(0)
  await page.screenshot({ path: '../build/qa-password-login.png', animations: 'disabled' })
  await page.setViewportSize({ width: 320, height: 800 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  await page.screenshot({ path: '../build/qa-password-login-mobile.png', animations: 'disabled' })
  await page.getByLabel('Passwort', { exact: true }).fill('incorrect')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Das Passwort stimmt nicht.')
  await page.getByLabel('Passwort', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Deine Sammlung.' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Deine Sammlung.' })).toBeVisible()
})

test('ratings work over LAN HTTP without crypto.randomUUID', async ({ page }) => {
  await page.evaluate(() => {
    Object.defineProperty(crypto, 'randomUUID', { value: undefined, configurable: true })
  })
  await page.getByPlaceholder('Titel, Interpret oder Album suchen …').fill('Reckoner')
  await expect(page.locator('.track-row')).toHaveCount(1)
  await page.getByRole('button', { name: '4 Sterne für Reckoner', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('„Reckoner“ mit 4 Sternen gespeichert')
  await page.getByRole('button', { name: 'Details zu Reckoner', exact: true }).click()
  await page.getByRole('button', { name: 'Eigene Bewertung entfernen', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('Noch keine eigene Bewertung.')
  await expect(page.getByLabel('Wird gespeichert')).toHaveCount(0)
})

test('cached tracks stay searchable while a background import is running', async ({ page }) => {
  const current = await (await page.request.get('/api/v1/status')).json()
  const lists = await (await page.request.get('/api/v1/playlists')).json()
  let importing = true
  await page.route('**/api/v1/playlists', route => route.fulfill({
    json: { items: lists.items.map((list: { name: string }, index: number) => index === 0 && !importing ? { ...list, name: 'Aktualisierte Playlist' } : list) },
  }))
  await page.route('**/api/v1/status', route => route.fulfill({
    json: { ...current, connected: !importing, refreshing: importing },
  }))
  await page.route('**/api/v1/library/refresh', async route => {
    expect(route.request().postDataJSON().background).toBe(true)
    await route.fulfill({ json: { ...current, refreshing: importing } })
  })
  await page.getByRole('button', { name: 'Bibliothek aktualisieren', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Bibliotheksfortschritt' })).toContainText('im Hintergrund aktualisiert')
  await page.getByPlaceholder('Titel, Interpret oder Album suchen …').fill('Radiohead')
  await expect(page.locator('.track-row')).toHaveCount(6)
  const rating = page.getByRole('button', { name: '5 Sterne für Nude', exact: true })
  await expect(rating).toBeDisabled()
  await page.getByRole('combobox', { name: 'Sortierung' }).selectOption('addedDate')
  await expect(page.locator('.track-main strong').first()).toHaveText('Reckoner')
  await page.screenshot({ path: '../build/qa-background-import.png', animations: 'disabled' })
  importing = false
  await expect(page.locator('.cache-banner')).toHaveCount(0)
  await expect(rating).toBeEnabled()
  await expect(page.getByRole('button', { name: /Aktualisierte Playlist/ })).toBeVisible()
})

test('failed background import shows the error and preserves cached search', async ({ page }) => {
  const current = await (await page.request.get('/api/v1/status')).json()
  let importing = true
  await page.route('**/api/v1/status', route => route.fulfill({
    json: {
      ...current, connected: false, refreshing: importing,
      error: importing ? null : { code: 'REFRESH_FAILED', message: 'Simulierter Importfehler', details: {} },
    },
  }))
  await page.route('**/api/v1/library/refresh', route => route.fulfill({ json: { ...current, refreshing: true } }))
  await page.getByRole('button', { name: 'Bibliothek aktualisieren', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Bibliotheksfortschritt' })).toContainText('im Hintergrund aktualisiert')
  importing = false
  await expect(page.getByRole('alert')).toContainText('Simulierter Importfehler')
  await expect(page.locator('.cache-banner')).toContainText('Gespeicherter Bibliotheksstand')
  await page.getByPlaceholder('Titel, Interpret oder Album suchen …').fill('Miles Davis')
  await expect(page.locator('.track-row')).toHaveCount(5)
})

test('album stars are displayed and clearing restores their origin', async ({ page }) => {
  await page.getByPlaceholder('Titel, Interpret oder Album suchen …').fill('Blue in Green')
  await expect(page.locator('.track-row')).toHaveCount(1)
  await expect(page.locator('.inherited-label')).toHaveText('Vom Album')
  await page.getByRole('button', { name: '1 Stern für Blue in Green', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('gespeichert')
  await page.getByRole('button', { name: 'Details zu Blue in Green', exact: true }).click()
  await page.getByRole('button', { name: 'Eigene Bewertung entfernen', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('Diese Sterne sind vom Album übernommen.')
})

test('web progress uses the same phase messages as the Mac app', async ({ page }) => {
  const current = await (await page.request.get('/api/v1/status')).json()
  let progress = { ...current.progress, stage: 'opening', completed: 3, total: 7 }
  let active = true
  await page.route('**/api/v1/status', route => route.fulfill({ json: {
    ...current, connected: false, refreshing: active, progress,
  } }))
  await page.route('**/api/v1/library/refresh', route => route.fulfill({ json: {
    ...current, refreshing: true, progress,
  } }))
  await page.getByRole('button', { name: 'Bibliothek aktualisieren', exact: true }).click()
  const panel = page.getByRole('region', { name: 'Bibliotheksfortschritt' })
  for (const item of progressCases) {
    progress = { ...progress, stage: item.stage, total: item.total ?? 7, sequence: progress.sequence + 1 }
    active = !['done', 'failed'].includes(item.stage)
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
    await expect(panel.locator('.import-progress-phase')).toHaveText(item.message)
    const counted = ['native-tracks', 'tracks', 'playlists', 'snapshot-tracks', 'snapshot-playlists', 'ratings', 'indexing', 'index-serialize', 'index-playlists'].includes(item.stage) && progress.total > 0
    await expect(panel.getByRole('progressbar')).toHaveCount(active && counted ? 1 : 0)
  }
})

test('progress clocks continue without a new response and completion freezes them', async ({ page }) => {
  await page.clock.install()
  const current = await (await page.request.get('/api/v1/status')).json()
  let held: (() => void) | undefined
  let complete = false
  const progress = { ...current.progress, stage: 'snapshot-tracks', completed: 1000, total: 51375, elapsedSeconds: 91, stageElapsedSeconds: 45, idleSeconds: 25 }
  await page.route('**/api/v1/status', async route => {
    if (!complete) await new Promise<void>(resolve => { held = resolve })
    await route.fulfill({ json: { ...current, connected: false, refreshing: false, progress: { ...progress, stage: 'done', completed: 51375, sequence: progress.sequence + 1 } } })
  })
  await page.route('**/api/v1/library/refresh', route => route.fulfill({ json: { ...current, refreshing: true, progress } }))
  await page.getByRole('button', { name: 'Bibliothek aktualisieren', exact: true }).click()
  const panel = page.getByRole('region', { name: 'Bibliotheksfortschritt' })
  await expect(panel).toContainText('Titeldaten kopieren: 1.000 von 51.375')
  await expect(panel.locator('.import-progress-times')).toContainText('1 min 31 s')
  await page.clock.runFor(12_000)
  await expect(panel).toContainText('1 min 43 s')
  await expect(panel).toContainText('Status seit 12 s nicht aktualisiert')
  await expect(panel).toContainText('keine neue Fortschrittsmeldung')
  await page.screenshot({ path: '../build/qa-web-progress.png', animations: 'disabled' })
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
  }
  await page.screenshot({ path: '../build/qa-web-progress-mobile.png', animations: 'disabled' })
  complete = true
  held?.()
  await expect(panel.locator('.import-progress-phase')).toHaveText('51.375 Titel geladen')
  const finishedTiming = await panel.locator('.import-progress-times').textContent()
  await page.clock.runFor(5_000)
  await expect(panel.locator('.import-progress-times')).toHaveText(finishedTiming ?? '')
  await expect(panel.locator('.import-progress-diagnostic')).toHaveCount(0)
})

test('first import shows progress without a cache or timing data', async ({ page }) => {
  const current = await (await page.request.get('/api/v1/status')).json()
  let active = true
  await page.route('**/api/v1/status', route => route.fulfill({ json: {
    ...current, mode: 'music', connected: false, hasCache: false, refreshing: active,
    progress: { stage: active ? 'native-cleanup' : 'failed', completed: 0, total: 0, sequence: 1 },
  } }))
  await page.getByRole('button', { name: 'Verbindung & API', exact: true }).click()
  await page.getByRole('button', { name: 'Berechtigungen anfordern', exact: true }).click()
  await page.getByRole('button', { name: 'Schließen', exact: true }).click()
  const panel = page.getByRole('region', { name: 'Bibliotheksfortschritt' })
  await expect(panel).toContainText('Native Bibliotheksobjekte werden aufgeräumt')
  await expect(panel).toContainText('Deine Titel erscheinen nach dem ersten Import')
  await expect(panel.locator('.import-progress-times')).toHaveCount(0)
  await expect(panel.getByRole('progressbar')).toHaveCount(0)
  active = false
  await expect(panel).toContainText('Der erste Import wurde nicht abgeschlossen')
})

test('sorts by added date in both directions while keeping search and filters', async ({ page }) => {
  const sort = page.getByRole('combobox', { name: 'Sortierung', exact: true })
  await sort.selectOption({ label: 'Hinzugefügt: neueste zuerst' })
  await expect(page.locator('.track-main strong').first()).toHaveText('Familiar')
  await expect(page.locator('.track-main strong').last()).toHaveText('15 Step')
  await page.screenshot({ path: '../build/qa-added-date.png', animations: 'disabled' })
  await sort.selectOption({ label: 'Hinzugefügt: älteste zuerst' })
  await expect(page.locator('.track-main strong').first()).toHaveText('15 Step')
  await expect(page.locator('.track-main strong').last()).toHaveText('Familiar')
  await page.getByPlaceholder('Titel, Interpret oder Album suchen …').fill('Radiohead')
  await expect(page.locator('.track-row')).toHaveCount(6)
  await expect(page.locator('.track-main strong').last()).toHaveText('Reckoner')
  await sort.selectOption('addedDate')
  await expect(page.locator('.track-main strong').first()).toHaveText('Reckoner')
  await page.getByRole('combobox', { name: 'Bewertungsfilter', exact: true }).selectOption('unrated')
  await expect(page.locator('.track-row')).toHaveCount(3)
  await expect(page.locator('.track-main strong').first()).toHaveText('Reckoner')
  await expect(page.locator('.track-main strong').last()).toHaveText('15 Step')
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 800 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    await expect(sort).toBeVisible()
  }
})

test('local API credentials can be issued and revoked in the UI', async ({ page }) => {
  await page.getByRole('button', { name: 'Verbindung & API', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('Zugriff im lokalen Netzwerk')
  await page.getByLabel('Gerätename').fill('iPad QA')
  await page.getByRole('button', { name: 'Zugang erstellen', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('Zugang erstellt.')
  await page.getByRole('button', { name: 'Zugang für iPad QA widerrufen', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Zugang für iPad QA widerrufen', exact: true })).toHaveCount(0)
})

test('permissions can be requested from settings without touching the real library in demo mode', async ({ page }) => {
  await page.getByRole('button', { name: 'Verbindung & API', exact: true }).click()
  await page.getByRole('button', { name: 'Berechtigungen anfordern', exact: true }).click()
  await expect(page.getByRole('dialog').getByRole('status')).toContainText('Im Demomodus sind keine Freigaben nötig.')
  await expect(page.getByRole('button', { name: 'Berechtigungen anfordern', exact: true })).toBeEnabled()
})

test('connecting reports missing media access and only the explicit permission action requests it', async ({ page }) => {
  const previous = await (await page.request.get('/api/v1/status')).json()
  const missing = {
    ...previous, mode: 'music', connected: false, refreshing: false,
    error: { code: 'MEDIA_PERMISSION_REQUIRED', message: 'Die Medienfreigabe fehlt. Bitte Berechtigungen anfordern.', details: {} },
  }
  let permissionRequests = 0
  await page.route('**/api/v1/library/connect', route => route.fulfill({ json: missing }))
  await page.route('**/api/v1/status', route => route.fulfill({ json: missing }))
  await page.route('**/api/v1/permissions/request', route => {
    permissionRequests += 1
    return route.fulfill({ json: {
      mode: 'music', needsSettings: false, libraryConnected: false,
      media: { status: 'granted', message: 'Bibliothekszugriff ist verfügbar.' },
      automation: { status: 'granted', message: 'Automation ist verfügbar.' },
    } })
  })
  await page.getByRole('button', { name: 'Eigene Bibliothek verbinden', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Medienfreigabe fehlt')
  for (let count = 0; count < 2; count += 1) {
    await page.getByRole('button', { name: 'Verbinden', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('Medienfreigabe fehlt')
  }
  expect(permissionRequests).toBe(0)
  await page.getByRole('button', { name: 'Verbindung & API', exact: true }).click()
  await page.getByRole('button', { name: 'Berechtigungen anfordern', exact: true }).click()
  await expect(page.getByRole('dialog').getByRole('status')).toContainText('Bibliothekszugriff ist verfügbar.')
  expect(permissionRequests).toBe(1)
})

test('desktop and narrow screen stay usable without overflow', async ({ page }) => {
  await expect(page.locator('.track-row')).toHaveCount(34)
  await page.screenshot({ path: '../build/qa-desktop.png', animations: 'disabled' })
  await page.setViewportSize({ width: 320, height: 800 })
  await expect(page.getByRole('button', { name: 'Navigation öffnen', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  await page.getByRole('button', { name: 'Navigation öffnen', exact: true }).click()
  await page.getByRole('button', { name: /Unbewertet/ }).click()
  await expect(page.getByRole('heading', { name: 'Noch zu entdecken.' })).toBeVisible()
  await expect(page.locator('.sidebar')).toHaveCSS('transform', 'matrix(1, 0, 0, 1, -244, 0)')
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: '../build/qa-mobile.png', animations: 'disabled' })
})

test.describe('dark theme', () => {
  test.use({ colorScheme: 'dark', viewport: { width: 1280, height: 900 } })
  test('renders a fresh desktop view', async ({ page }) => {
    await expect(page.locator('.topbar')).toHaveCount(1)
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(33, 31, 30)')
    await page.screenshot({ path: '../build/qa-dark.png', animations: 'disabled' })
  })
  test('renders the active import phase in the dark theme', async ({ page }) => {
    const current = await (await page.request.get('/api/v1/status')).json()
    const next = { ...current, connected: false, refreshing: true, progress: {
      ...current.progress, stage: 'index-signature', elapsedSeconds: 114, stageElapsedSeconds: 14, idleSeconds: 4,
    } }
    await page.route('**/api/v1/status', route => route.fulfill({ json: next }))
    await page.route('**/api/v1/library/refresh', route => route.fulfill({ json: next }))
    await page.getByRole('button', { name: 'Bibliothek aktualisieren', exact: true }).click()
    const panel = page.getByRole('region', { name: 'Bibliotheksfortschritt' })
    await expect(panel).toContainText('Bibliotheksstände werden verglichen …')
    await expect(panel).toHaveCSS('background-color', 'rgb(40, 37, 34)')
    await expect(panel.getByRole('progressbar')).toHaveCount(0)
    await page.screenshot({ path: '../build/qa-web-progress-dark.png', animations: 'disabled' })
  })
})

test.describe('touch interface', () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } })
  test('provides separate 44 pixel rating targets', async ({ page }) => {
    const target = page.getByRole('button', { name: '4 Sterne für Get Lucky', exact: true })
    const box = await target.boundingBox()
    expect(box?.width).toBeGreaterThanOrEqual(44)
    expect(box?.height).toBeGreaterThanOrEqual(44)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    await target.tap()
    await expect(page.getByRole('status')).toContainText('„Get Lucky“ mit 4 Sternen gespeichert')
    await page.screenshot({ path: '../build/qa-touch.png', animations: 'disabled' })
  })
})
