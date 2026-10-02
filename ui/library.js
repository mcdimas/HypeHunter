// Source library: server-side search, filtering and ordering for both platforms.
function safeUrl(value) {
  if (!value) return "#";
  try {
    const url = new URL(value, location.origin);
    return ["http:", "https:"].includes(url.protocol) ? escapeHtml(url.href) : "#";
  } catch { return "#"; }
}

function sourceLink(source, content, className = "") {
  return source.original_url
    ? `<a class="${className}" href="${safeUrl(source.original_url)}" target="_blank" rel="noopener noreferrer">${content}</a>`
    : `<span class="${className}">${content}</span>`;
}

function thumbnailMarkup(source, className = "") {
  const src = source.media_path || source.thumbnail_url;
  return `<span class="reel-thumb ${className}">${src ? `<img src="${safeUrl(src)}" alt="" loading="lazy" referrerpolicy="no-referrer" />` : icon("film-strip")}${source.duration_seconds != null ? `<span>${formatDuration(source.duration_seconds)}</span>` : ""}</span>`;
}

function metric(iconName, label, value) {
  return `<span title="${label}" aria-label="${label}: ${value == null ? "нет данных" : formatCount(value)}">${icon(iconName)}<b>${value == null ? "н/д" : formatViews(value)}</b></span>`;
}

function sourceMetrics(source) {
  return `<div class="source-stats">${source.platform === "threads" ? "" : metric("eye", "Просмотры", source.views)}${metric("heart", "Лайки", source.likes_count)}${metric("chat-circle", source.platform === "threads" ? "Ответы" : "Комментарии", source.comments_count)}${source.platform === "threads" ? metric("repeat", "Репосты", source.shares_count) : ""}</div>`;
}

function translationState(source) {
  const labels = { completed: "Переведено", running: "Переводится", pending: "Ожидает перевода", failed: "Перевод недоступен" };
  return `<span class="translation-label ${escapeHtml(source.translation_status)}">${icon(source.translation_status === "completed" ? "check" : source.translation_status === "failed" ? "warning-circle" : "clock")}${labels[source.translation_status] || "Нет перевода"}</span>`;
}

function libraryFooter() {
  const rangeStart = state.reelTotal ? (state.page - 1) * state.pageSize + 1 : 0;
  const pages = [...new Set([1, state.page - 1, state.page, state.page + 1, state.pageCount])].filter(p => p > 0 && p <= state.pageCount);
  return `<footer class="library-footer"><span>${rangeStart}–${Math.min(state.page * state.pageSize, state.reelTotal)} из ${state.reelTotal}</span><nav class="pagination" aria-label="Страницы библиотеки"><button class="page-button" data-page="${state.page - 1}" aria-label="Предыдущая страница" ${state.page <= 1 ? "disabled" : ""}>${icon("caret-left")}</button>${pages.map((p, i) => `${i && p - pages[i - 1] > 1 ? "<span>…</span>" : ""}<button class="page-button ${p === state.page ? "active" : ""}" data-page="${p}" ${p === state.page ? 'aria-current="page"' : ""}>${p}</button>`).join("")}<button class="page-button" data-page="${state.page + 1}" aria-label="Следующая страница" ${state.page >= state.pageCount ? "disabled" : ""}>${icon("caret-right")}</button></nav></footer>`;
}

function sourceMenu(source) {
  return `<div class="row-menu"><button class="icon-button" data-menu="reel-${source.id}" aria-label="Действия с материалом ${escapeHtml(source.title)}" aria-expanded="${state.openMenu === `reel-${source.id}`}">${icon("dots-three")}</button>${state.openMenu === `reel-${source.id}` ? `<div class="menu-popover" role="menu"><button role="menuitem" data-action="view-reel-text" data-reel-id="${source.id}">${icon("text-align-left")} Читать полностью</button><button role="menuitem" data-action="view-translation-error" data-reel-id="${source.id}">${icon("translate")} Состояние перевода</button><button role="menuitem" class="danger-menu-item" data-action="delete-reel" data-reel-id="${source.id}">${icon("trash")} Удалить источник</button></div>` : ""}</div>`;
}

function sourceAvatar(source) {
  const competitor = state.competitors.find(c => c.id === source.competitor_id) || { handle: source.author };
  return avatarMarkup(competitor);
}
function librarySource(source) {
  const isThread = source.platform === "threads";
  const original = source.original_script || source.caption || "";
  const translated = source.translation_status === "completed" ? source.translated_script : null;
  const used = source.remix_count > 0 ? `<a class="used-label" href="/content-plan" data-route>${icon("clock")} В плане · ${source.remix_count}</a>` : "";
  const translation = translated ? escapeHtml(isThread ? translated : source.translated_hook || translated) : `<span class="muted">${source.translation_status === "failed" ? "Перевод недоступен. Оригинал сохранён." : "Перевод ещё не готов"}</span>`;
  const fullText = `<details class="source-full"><summary>Читать полностью</summary><div class="full-text-pair"><div><span class="copy-label">Оригинал</span><p>${escapeHtml(original)}</p></div><div><span class="copy-label">Перевод</span><p>${escapeHtml(translated || "Перевод ещё не получен")}</p></div></div></details>`;
  const actions = `<div class="library-actions"><button class="button primary" data-action="remix" data-reel-id="${source.id}">Remix</button>${sourceMenu(source)}</div>`;
  if (!isThread && state.libraryView === "list") {
    return `<article class="library-item reel-item">
      <div class="material-cell">${sourceLink(source,thumbnailMarkup(source),"cover-link")}<div class="library-copy">${sourceLink(source,`<h2>${escapeHtml(source.title)}</h2>`,"source-title-link")}<p class="source-excerpt original-excerpt">${escapeHtml(source.original_hook || original || "Расшифровка пока недоступна")}</p><div class="russian-preview"><span>RU</span><p class="source-excerpt">${translation}</p></div>${fullText}</div></div>
      <div class="author-cell">${sourceAvatar(source)}<div>${sourceLink(source,escapeHtml(source.author),"source-author")}<time>${formatAdded(source.published_at)}</time></div></div>
      <div class="metrics-cell">${sourceMetrics(source)}</div><div class="translation-cell">${translationState(source)}${used}</div>${actions}</article>`;
  }
  return `<article class="library-item ${isThread ? "thread-item" : "reel-item"}">
    ${isThread ? "" : sourceLink(source,thumbnailMarkup(source),"cover-link")}
    <div class="library-copy"><div class="source-byline">${sourceAvatar(source)}<div>${sourceLink(source,escapeHtml(source.author),"source-author")}<time>${formatAdded(source.published_at)}</time></div>${used}</div>
      ${isThread ? "" : sourceLink(source,`<h2>${escapeHtml(source.title)}</h2>`,"source-title-link")}
      <div class="library-text-pair"><div><span class="copy-label">Оригинал</span><p class="source-excerpt">${escapeHtml(original || "Расшифровка пока недоступна")}</p></div><div class="russian-preview"><span class="copy-label">Перевод</span><p class="source-excerpt">${translation}</p></div></div>${fullText}
    </div><div class="source-bottom">${sourceMetrics(source)}${isThread ? sourceLink(source,`Оригинал ${icon("arrow-up-right")}`,"text-link") : translationState(source)}${actions}</div>
  </article>`;
}

function homeResults() {
  if (state.loadingReels) return `<div class="page-state" role="status">${icon("circle-notch", "spin")} Загружаем материалы…</div>`;
  if (!state.reels.length) return `<div class="empty-state">${icon("books")}<h2>Материалов пока нет</h2><p>${state.query || state.competitorId !== "all" || state.period !== "all" ? "Измените поиск или фильтры." : "Добавьте конкурента, чтобы собрать первые публикации."}</p><a class="button primary" href="/competitors" data-route>К конкурентам</a></div>`;
  return `<div class="library-results ${state.tab === "threads" ? "threads-grid" : state.libraryView === "grid" ? "reels-grid" : "reels-list"}">${state.tab === "reels" && state.libraryView === "list" ? `<div class="library-table-head" aria-hidden="true"><span>Материал</span><span>Автор</span><span>Показатели</span><span>Статус</span><span></span></div>` : ""}${state.reels.map(librarySource).join("")}</div>${libraryFooter()}`;
}

function homePage() {
  document.title = "Библиотека | Hype Hunter";
  return shell(`<header class="page-header"><div><h1>Библиотека</h1><p>Материалы конкурентов, которые можно взять в работу.</p></div><a class="button primary" href="/competitors" data-route>${icon("plus")} Добавить конкурента</a></header>
    <div class="tabs-row"><div class="tabs" role="tablist" aria-label="Формат библиотеки">${["reels", "threads"].map(type => `<button class="tab ${state.tab === type ? "active" : ""}" role="tab" aria-selected="${state.tab === type}" tabindex="${state.tab === type ? 0 : -1}" data-tab="${type}">${icon(type === "reels" ? "film-strip" : "chats-circle")} ${type === "reels" ? "Reels" : "Threads"}</button>`).join("")}</div><span class="muted" data-library-count>${materialCount(state.reelTotal)}</span></div>
    <div class="toolbar"><label class="search-field">${icon("magnifying-glass")}<input type="search" value="${escapeHtml(state.query)}" placeholder="Поиск по тексту, переводу, автору" aria-label="Поиск в библиотеке" data-search /></label><select data-source-filter aria-label="Конкурент"><option value="all">Все конкуренты</option>${state.competitors.filter(c => c.platform === state.tab).map(c => `<option value="${c.id}" ${String(c.id) === String(state.competitorId) ? "selected" : ""}>${escapeHtml(c.handle)}</option>`).join("")}</select><select data-library-period aria-label="Период">${[["all", "За всё время"], ["7", "За 7 дней"], ["30", "За 30 дней"], ["90", "За 90 дней"]].map(([v,l]) => `<option value="${v}" ${state.period === v ? "selected" : ""}>${l}</option>`).join("")}</select><select data-library-sort aria-label="Сортировка">${[["newest", "Сначала новые"], ["oldest", "Сначала старые"], ...(state.tab === "reels" ? [["views", "По просмотрам"]] : [["shares", "По репостам"]]), ["likes", "По лайкам"], ["comments", state.tab === "reels" ? "По комментариям" : "По ответам"]].map(([v,l]) => `<option value="${v}" ${state.sort === v ? "selected" : ""}>${l}</option>`).join("")}</select>${state.tab === "reels" ? `<div class="view-switch" aria-label="Вид библиотеки"><button class="icon-button ${state.libraryView === "list" ? "active" : ""}" data-library-view="list" aria-label="Список" aria-pressed="${state.libraryView === "list"}">${icon("list-bullets")}</button><button class="icon-button ${state.libraryView === "grid" ? "active" : ""}" data-library-view="grid" aria-label="Сетка" aria-pressed="${state.libraryView === "grid"}">${icon("squares-four")}</button></div>` : ""}</div>
    <div data-home-results>${homeResults()}</div><p class="selection-note">Показатели относятся к загруженной выборке. «н/д» означает, что источник не вернул данные.</p>`, "library-page");
}

function progressMarkup() {
  const active = state.imports.filter(j => ["queued", "running"].includes(j.status));
  if (state.importing) return `<div class="import-live" role="status">${icon("circle-notch", "spin")} Сохраняем аккаунт и ставим загрузку в очередь…</div>`;
  return active.map(job => `<div class="import-live" role="status" aria-live="polite"><div>${icon("circle-notch", "spin")}<strong>${escapeHtml(job.competitor_handle)}</strong><span>${escapeHtml(job.stage_message)}</span></div><button class="button secondary compact" data-action="cancel-import" data-import-id="${job.id}" ${state.cancellingImportId === job.id ? "disabled" : ""}>Остановить</button></div>`).join("");
}

function competitorRows() {
  return state.competitors.map(c => {
    const active = state.imports.find(j => j.competitor_id === c.id && ["running","queued"].includes(j.status));
    return `<tr><td><div class="account-cell">${avatarMarkup(c)}<div><a href="${safeUrl(c.profile_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(c.handle)}</a></div></div></td><td><span class="platform-cell">${icon(c.platform === "threads" ? "chats-circle" : "instagram-logo")}${c.platform === "threads" ? "Threads" : "Reels"}</span></td><td>${c.reel_count}</td><td>${c.last_import_at ? formatDateTime(c.last_import_at) : "Ещё не загружался"}</td><td><span class="status-chip ${active ? "in_progress" : c.is_active ? "ready" : ""}">${active ? "Загрузка" : c.is_active ? "Отслеживается" : "Приостановлен"}</span></td><td><div class="row-actions"><button class="text-link" data-action="open-reels" data-competitor-id="${c.id}">Смотреть</button><button class="icon-button" data-action="refresh" data-competitor-id="${c.id}" aria-label="Обновить ${escapeHtml(c.handle)}" ${active || state.refreshingId === c.id ? "disabled" : ""}>${icon("arrow-clockwise")}</button><div class="row-menu"><button class="icon-button" data-menu="competitor-${c.id}" aria-label="Действия с ${escapeHtml(c.handle)}">${icon("dots-three")}</button>${state.openMenu === `competitor-${c.id}` ? `<div class="menu-popover" role="menu"><button role="menuitem" data-action="pause-profile" data-competitor-id="${c.id}" data-active="${c.is_active}">${icon(c.is_active ? "pause" : "play")}${c.is_active ? "Приостановить" : "Возобновить"}</button><button role="menuitem" class="danger-menu-item" data-action="delete-competitor" data-competitor-id="${c.id}">${icon("trash")}Удалить источник</button></div>` : ""}</div></div></td></tr>`;
  }).join("") || `<tr><td colspan="6"><div class="empty-state"><h2>Добавьте первого конкурента</h2><p>Его последние публикации появятся в библиотеке.</p></div></td></tr>`;
}

function importRows() {
  return state.imports.slice(0, 10).map(j => `<tr><td>${escapeHtml(j.competitor_handle)}<small>${j.platform === "threads" ? "Threads" : "Reels"}</small></td><td><span class="status-chip ${j.status === "failed" ? "failed" : j.stage === "partial" ? "in_progress" : j.status === "completed" ? "ready" : ""}">${j.stage === "partial" ? "Частичный результат" : importStatusLabel(j.status)}</span><details class="job-details"><summary>Подробности</summary><p>${escapeHtml(j.stage_message)}</p>${j.result_summary?.shortfall_reason ? `<p>${escapeHtml(j.result_summary.shortfall_reason)}</p>` : ""}</details></td><td>${j.imported_count} / ${j.requested_count}</td><td>${formatDateTime(j.created_at)}</td><td>${["running","queued"].includes(j.status) ? `<button class="button secondary compact" data-action="cancel-import" data-import-id="${j.id}">Остановить</button>` : ""}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">Загрузок пока нет</td></tr>`;
}

function translationMarkup() {
  const summary = state.translations?.summary;
  if (!summary) return "";
  return `<details class="translation-details"><summary>${icon("translate")} Переводы <span class="muted">${summary.translated} готовы${summary.failed ? ` · ${summary.failed} с ошибкой` : ""}</span></summary><p>${summary.configured ? "Новые тексты переводятся после загрузки." : "Сервис перевода требует подключения на сервере. Оригиналы доступны, ручное редактирование работает."}</p>${(state.translations.batches || []).slice(0,5).map(b => `<details class="job-details"><summary>Пакет #${b.id}: ${b.status === "completed" ? "готов" : b.status === "failed" ? "ошибка" : "в работе"} · ${b.translated_count}/${b.item_count}</summary>${b.error_message ? `<p>${escapeHtml(translationErrorSummary(b.error_message))}</p>` : ""}</details>`).join("")}</details>`;
}

function trialMarkup() {
  const trial = state.trial;
  if (trial?.limit == null) return "";
  if(trial.plan)return `<p class="form-help" role="status">${trial.plan==='pro'?'Про':'Старт'}: осталось ${trial.remaining} из ${trial.limit} материалов до ${formatDateTime(trial.access_until)}. Общий лимит для Reels и Threads. Повторный перевод не расходует лимит.</p>`;
  return `<p class="form-help" role="status">Бесплатные Reels: ${trial.used} из ${trial.limit} использовано. ${trial.remaining ? "Выберем самые просматриваемые среди 20 последних доступных Reels. Перевод и работа с черновиками включены; карта не нужна." : 'Переводы и черновики остаются доступны. Для новых загрузок <a href="/account?tab=subscription" data-route>выберите пакет</a>.'}</p>`;
}

function competitorsPage() {
  document.title = "Конкуренты | Hype Hunter";
  return shell(`<header class="page-header"><div><h1>Конкуренты</h1><p>Добавляйте аккаунты и обновляйте их материалы.</p></div></header>
    <section class="import-card"><div data-trial-summary>${trialMarkup()}</div><div class="tabs-row"><div class="tabs">${[["reels","Instagram Reels","instagram-logo"],["threads","Threads","chats-circle"]].map(([v,l,i])=>`<button class="tab ${state.importPlatform===v?"active":""}" data-import-platform-tab="${v}" aria-pressed="${state.importPlatform===v}">${icon(i)}${l}</button>`).join("")}</div></div>
      <form data-competitor-form><div class="import-form-row"><label class="search-field">${icon("link")}<input id="instagram-account" name="account" aria-label="Профиль конкурента" value="${escapeHtml(state.competitorValue)}" placeholder="Ссылка на профиль или @username" required maxlength="512" /></label>${state.trial?.limit != null&&!state.trial.plan ? `<span class="muted">До ${state.trial.remaining} лучших Reels</span>` : `<select data-import-limit aria-label="Лимит загрузки">${[1,3,10,20].map(n=>`<option value="${n}" ${state.importLimit===n?"selected":""}>До ${n} новых</option>`).join("")}</select>`}<button class="button primary" ${state.importing?"disabled":""}>${state.importing?`${icon("circle-notch","spin")} Добавляем`:"Загрузить"}</button></div><p class="form-help">Если источник вернёт меньше материалов, неиспользованный остаток сохранится. Уже загруженные материалы не дублируются. Повторный перевод не расходует лимит.</p>${state.competitorError?`<p class="form-error" role="alert">${escapeHtml(state.competitorError)}</p>`:""}</form></section>
    <section class="panel competitors-list"><div class="table-scroll"><table class="data-table competitors-table"><thead><tr><th>Аккаунт</th><th>Формат</th><th>Материалов</th><th>Обновление</th><th>Состояние</th><th></th></tr></thead><tbody data-competitors-body>${competitorRows()}</tbody></table></div></section>
    <div data-import-tracker>${progressMarkup()}</div>
    <details class="panel import-history"><summary>${icon("clock-counter-clockwise")} История загрузок <span class="muted">${state.imports.length}</span>${icon("caret-down")}</summary><div class="table-scroll"><table class="data-table imports-table"><thead><tr><th>Источник</th><th>Результат</th><th>Материалы</th><th>Дата</th><th></th></tr></thead><tbody data-imports-body>${importRows()}</tbody></table></div></details><div data-translation-tracker>${translationMarkup()}</div>`, "competitors-page");
}
