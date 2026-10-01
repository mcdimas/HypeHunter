const PLAN_STATES = { idea: "Идеи", in_progress: "В работе", ready: "Готово", published: "Опубликовано" };
const STAGES = { script: "Сценарий", filming: "Съёмка", editing: "Монтаж", text: "Редактура текста" };
const PROJECT_ZONE = "Europe/Moscow";
function projectDay(value = new Date()) {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: PROJECT_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
}
function projectTime(value) {
  return new Intl.DateTimeFormat("ru-RU", { timeZone: PROJECT_ZONE, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}
function dateInput(value) { return value ? `${projectDay(value)}T${projectTime(value)}` : ""; }
function plannedISO(value) { return value ? new Date(`${value}:00+03:00`).toISOString() : null; }
function formatLabel(value) { return value === "threads" ? "Threads" : "Reels"; }
function statusSelect(remix) {
  return `<select class="status-select ${remix.status}" data-remix-status="${escapeHtml(remix.slug)}" aria-label="Статус: ${escapeHtml(remix.title)}">${Object.entries(PLAN_STATES).map(([key,label]) => `<option value="${key}" ${remix.status === key ? "selected" : ""}>${label}</option>`).join("")}</select>`;
}
function shiftDay(day, amount) {
  const date = new Date(day + "T12:00:00Z");
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}
function weekStart(day = projectDay()) {
  const date = new Date(day + "T12:00:00Z");
  return shiftDay(day, -((date.getUTCDay() + 6) % 7));
}
function planURL() {
  return "/content-plan?" + new URLSearchParams({ view: state.planView, format: state.planFormat, q: state.planQuery, week: state.calendarWeek });
}
function stageLabel(remix) { return remix.status === "in_progress" ? STAGES[remix.production_stage] || "Подготовка" : PLAN_STATES[remix.status]; }
function planCard(remix, compact = false) {
  const source = remix.source_reel;
  const excerpt = remix.brief || (remix.format === "threads" ? remix.thread_text || remix.hook : remix.hook || remix.script);
  return `<article class="plan-card ${compact ? "calendar-card" : ""}" draggable="true" data-drag-slug="${escapeHtml(remix.slug)}">
    <div class="plan-meta"><span class="format-label">${icon(remix.format === "threads" ? "chats-circle" : "film-strip")}${formatLabel(remix.format)}</span>${compact && remix.scheduled_at ? `<time>${projectTime(remix.scheduled_at)}</time>` : `<button class="icon-button" data-action="delete-draft" data-slug="${escapeHtml(remix.slug)}" aria-label="Удалить черновик ${escapeHtml(remix.title)}">${icon("trash")}</button>`}</div>
    <a class="plan-title" href="/remixes/${encodeURIComponent(remix.slug)}" data-route>${escapeHtml(remix.title)} ${icon("caret-right")}</a>
    ${!compact && excerpt ? `<p class="plan-excerpt">${escapeHtml(excerpt)}</p>` : ""}
    ${remix.status === "in_progress" ? `<span class="stage-pill ${escapeHtml(remix.production_stage)}">${icon(remix.production_stage === "filming" ? "video-camera" : remix.production_stage === "editing" ? "scissors" : "note-pencil")}${stageLabel(remix)}</span>` : ""}
    ${!compact && remix.scheduled_at ? `<time class="plan-date">${icon("calendar-blank")}${formatDateTime(remix.scheduled_at)}</time>` : ""}
    ${!compact && source ? `<div class="source-reference">${sourceLink(source, `${source.platform === "reels" ? thumbnailMarkup(source) : `<span class="reference-icon">${icon("chats-circle")}</span>`}<span><small>Референс</small>${escapeHtml(source.author)} ${icon("arrow-square-out")}</span>`)}</div>` : ""}
    <div class="plan-card-controls">${statusSelect(remix)}</div>
  </article>`;
}
function planItems() {
  const query = state.planQuery.trim().toLocaleLowerCase("ru");
  return state.remixes.filter(r => (state.planFormat === "all" || r.format === state.planFormat) && (!query || [r.title, r.brief, r.hook, r.script, r.thread_text].some(v => (v || "").toLocaleLowerCase("ru").includes(query))));
}
function boardMarkup(items) {
  const icons = { idea: "lightbulb", in_progress: "circle-half", ready: "check-circle", published: "paper-plane-tilt" };
  return `<div class="board-scroll"><div class="kanban-board">${Object.entries(PLAN_STATES).map(([key,label]) => {
    const entries = items.filter(r => r.status === key);
    return `<section class="kanban-column ${key}" data-drop-status="${key}" aria-label="${label}"><header><h2>${icon(icons[key])}${label}<span>${entries.length}</span></h2></header><div class="kanban-body">${entries.map(r => planCard(r)).join("") || `<p class="column-empty">Пока пусто<br>Перетащите сюда публикацию</p>`}</div></section>`;
  }).join("")}</div></div><p class="board-hint">${icon("arrows-out-cardinal")} Перетащите карточку, чтобы изменить этап, или выберите статус в карточке.</p>`;
}
function calendarMarkup(items) {
  const days = Array.from({length:7}, (_,i) => shiftDay(state.calendarWeek, i));
  const shortDate = day => new Date(day + "T12:00:00Z").toLocaleDateString("ru-RU", {day:"numeric",month:"long",timeZone:"UTC"});
  const range = `${shortDate(days[0])} — ${shortDate(days[6])}`;
  return `<div class="calendar-heading"><p class="muted">Перетащите публикацию на нужный день</p><div class="row-actions"><button class="icon-button" data-action="previous-week" aria-label="Предыдущая неделя">${icon("caret-left")}</button><h2>${range}</h2><button class="icon-button" data-action="next-week" aria-label="Следующая неделя">${icon("caret-right")}</button><button class="button secondary compact" data-action="current-week">Сегодня</button></div></div>
    <div class="calendar-scroll"><div class="calendar-grid">${days.map((key,i) => {
      const entries = items.filter(r => r.scheduled_at && projectDay(r.scheduled_at) === key).sort((a,b) => a.scheduled_at.localeCompare(b.scheduled_at));
      return `<section class="calendar-day ${key === projectDay() ? "today" : ""}" data-drop-date="${key}" aria-label="${shortDate(key)}"><time datetime="${key}"><span>${["Пн","Вт","Ср","Чт","Пт","Сб","Вс"][i]}</span> ${Number(key.slice(-2))}</time>${entries.map(r => planCard(r,true)).join("")}<button class="calendar-add ${entries.length ? "has-entries" : ""}" data-action="new-remix" data-date="${key}" aria-label="Добавить идею на ${shortDate(key)}">${icon("plus-circle")}<span>Добавить<br>публикацию</span></button></section>`;
    }).join("")}</div></div>
    <section class="panel unscheduled-panel" data-drop-date="none"><div class="section-heading"><h2>Без даты <span class="muted">· ${items.filter(r=>!r.scheduled_at).length}</span></h2></div><div class="unscheduled-list">${items.filter(r=>!r.scheduled_at).map(r=>planCard(r)).join("") || `<p class="muted">Все публикации запланированы</p>`}</div></section>`;
}
function contentPlanPage() {
  document.title = "Контент-план | Hype Hunter";
  const formats = [["all","Все"],["reels","Reels"],["threads","Threads"]];
  return shell(`<header class="page-header"><div><h1>Контент-план</h1><p>${state.planView === "calendar" ? "Планируйте даты своих публикаций." : "Все публикации и их текущий этап."}</p></div><button class="button primary" data-action="new-remix">${icon("plus")} Новая идея</button></header>
    <div class="plan-toolbar"><div class="tabs">${formats.map(([v,l])=>`<button class="tab ${state.planFormat===v?"active":""}" data-plan-format-tab="${v}" aria-pressed="${state.planFormat===v}">${l}<span>${state.remixes.filter(r=>v==="all"||r.format===v).length}</span></button>`).join("")}</div><div class="plan-tools"><div class="view-switch">${[["board","Доска","kanban"],["calendar","Календарь","calendar-blank"]].map(([v,l,i])=>`<button class="button ${state.planView===v?"active":""}" data-plan-view="${v}" aria-pressed="${state.planView===v}">${icon(i)}${l}</button>`).join("")}</div><label class="search-field">${icon("magnifying-glass")}<input type="search" data-plan-search value="${escapeHtml(state.planQuery)}" aria-label="Найти публикацию" placeholder="Найти публикацию" /></label></div></div>
    <div data-plan-results>${state.planView==="calendar"?calendarMarkup(planItems()):boardMarkup(planItems())}</div><p class="selection-note">Москва (UTC+3). Даты — для планирования. Публикацию отмечаете вручную.</p>`, "content-plan-page");
}
function workRow(remix, today = false) {
  return `<a class="work-row" href="/remixes/${encodeURIComponent(remix.slug)}" data-route>${today && remix.scheduled_at ? `<time>${projectTime(remix.scheduled_at)}</time>` : ""}<span class="work-icon">${icon(remix.format==="threads"?"chats-circle":"film-strip")}</span><span class="work-copy"><strong>${escapeHtml(remix.title)}</strong><small>${formatLabel(remix.format)} · ${stageLabel(remix)}${!today && remix.scheduled_at ? ` · ${formatDateTime(remix.scheduled_at)}` : ""}</small></span><span class="work-open">Открыть</span></a>`;
}
function todayPage() {
  document.title = "Сегодня | Hype Hunter";
  const unfinished = state.remixes.filter(r=>r.status!=="published");
  const recent = [...unfinished].sort((a,b)=>b.updated_at.localeCompare(a.updated_at))[0];
  const scheduled = unfinished.filter(r=>r.scheduled_at).sort((a,b)=>a.scheduled_at.localeCompare(b.scheduled_at));
  const today = scheduled.filter(r=>projectDay(r.scheduled_at)===projectDay());
  const upcoming = scheduled.filter(r=>projectDay(r.scheduled_at)>projectDay()).slice(0,3);
  const overdue = scheduled.filter(r=>projectDay(r.scheduled_at)<projectDay());
  const active = unfinished.filter(r=>r.status==="in_progress");
  return shell(`<div class="today-intro"><header class="page-header"><div><h1>Сегодня</h1><p class="today-date">${new Date().toLocaleDateString("ru-RU",{timeZone:PROJECT_ZONE,weekday:"long",day:"numeric",month:"long"})}</p><p>Что стоит сделать дальше.</p><div class="today-counts"><a href="/library" data-route>${icon("files")}<span><b>${state.sourceTotal}</b><small>в библиотеке</small></span></a><a href="/content-plan" data-route>${icon("clock")}<span><b>${active.length}</b><small>в работе</small></span></a><a href="/content-plan" data-route>${icon("check-circle")}<span><b>${unfinished.filter(r=>r.status==="ready").length}</b><small>готово</small></span></a></div></div></header>
    ${recent ? `<section class="resume-panel">${recent.source_reel?.platform==="reels"?`<div class="resume-reference">${thumbnailMarkup(recent.source_reel)}<small>Референс</small></div>`:`<span class="resume-icon">${icon(recent.format==="threads"?"chats-circle":"note-pencil")}</span>`}<div class="resume-copy"><span class="eyebrow">Продолжить работу</span><h2>${escapeHtml(recent.title)}</h2><p>${formatLabel(recent.format)} · ${stageLabel(recent)}<br>Изменён ${formatDateTime(recent.updated_at)}</p><a class="button primary" href="/remixes/${encodeURIComponent(recent.slug)}" data-route>Открыть редактор</a></div></section>` : `<section class="resume-panel"><div><span class="eyebrow">Первая публикация</span><h2>Начните со своей идеи</h2><p>Запишите мысль или выберите референс из библиотеки.</p><button class="button primary" data-action="new-remix">${icon("plus")} Создать идею</button></div></section>`}</div>
    <div class="today-columns"><section class="panel today-work"><div class="section-heading"><h2>На сегодня</h2><a href="/content-plan?view=calendar" data-route aria-label="Открыть календарь">${icon("calendar-blank")}</a></div>${today.map(r=>workRow(r,true)).join("") || `<p class="section-empty">На сегодня публикаций нет. Выберите дату в календаре или продолжите работу над черновиком.</p>`}${active.length ? `<h3 class="subsection-heading">В работе <span>${active.length}</span></h3>${active.filter(r=>!today.some(t=>t.id===r.id)).slice(0,today.length?1:3).map(r=>workRow(r)).join("")}` : ""}${overdue.length?`<details class="overdue"><summary>Прошедшие даты без отметки: ${overdue.length}</summary>${overdue.map(r=>workRow(r)).join("")}</details>`:""}</section>
    <section class="panel"><div class="section-heading"><h2>Новые находки</h2><a href="/library" data-route>Все ${icon("arrow-right")}</a></div><div class="today-sources">${state.reels.slice(0,3).map(s=>`<article><div class="finding-cover">${s.platform==="threads"?`<span class="text-cover">${icon("article")}</span>`:sourceLink(s,thumbnailMarkup(s))}</div><div class="finding-copy"><h3>${sourceLink(s,escapeHtml(s.translated_hook || s.title))}</h3><span class="muted">${escapeHtml(s.author)} · ${formatLabel(s.platform)}</span>${sourceMetrics(s)}</div><button class="button primary compact" data-action="remix" data-reel-id="${s.id}">Remix</button></article>`).join("") || `<p class="section-empty">Здесь появятся материалы ваших конкурентов. <a class="text-link" href="/competitors" data-route>Добавить источник</a></p>`}</div></section></div>
    <section class="panel upcoming-panel"><div><div class="section-heading"><h2>Ближайшие публикации</h2></div>${upcoming.map(r=>workRow(r)).join("") || `<p class="section-empty">Будущие даты ещё не выбраны. <a class="text-link" href="/content-plan?view=calendar" data-route>Открыть календарь ${icon("arrow-right")}</a></p>`}</div><a class="text-link" href="/competitors" data-route>К конкурентам ${icon("arrow-right")}</a></section>`, "today-page");
}
