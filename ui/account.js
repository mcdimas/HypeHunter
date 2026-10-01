/* Public entry and personal profile use the same tokens as the workspace. */
function publicBrand() {
  return `<a class="auth-brand" href="/" data-route aria-label="Hype Hunter, главная">${icon("target")}<span>HYPE HUNTER</span></a>`;
}

function scriptIllustration() {
  return `<figure class="auth-visual" aria-label="Адаптация сценария">
    <div class="script-example">
      <div class="example-original"><span class="example-label">Оригинал · EN</span><p lang="en">“Your reels are dying in the first three seconds. Here’s why.”</p></div>
      <div class="example-connector">${icon("arrow-bend-down-right")}<span>В вашу следующую идею</span></div>
      <div class="example-script"><img src="/assets/login-ribbon.png" width="940" height="1672" alt="" fetchpriority="high" />
        <div class="example-copy"><span class="example-label">Русский сценарий</span><h2>Первые три секунды решают всё</h2><p>Начните с вопроса, в котором зритель узнает себя. А потом покажите, что изменится к концу ролика.</p><div class="example-cta"><span class="example-label">CTA</span><p>Сохраните, чтобы проверить свой следующий ролик.</p></div></div>
      </div>
    </div>
  </figure>`;
}

function futureSignInButtons() {
  return `<div class="future-sign-in" aria-label="Другие способы входа, скоро">
    <span class="auth-divider">Позже появятся</span>
    <button class="button future-method" type="button" disabled><img class="yandex-logo" src="/assets/yandex-logo.svg" width="24" height="24" alt="" />Войти через Яндекс<span class="soon-label">Скоро</span></button>
    <button class="button future-method" type="button" disabled>${icon("envelope-simple")}Войти по почте с кодом<span class="soon-label">Скоро</span></button>
  </div>`;
}

function loginPage() {
  document.title = "Вход | Hype Hunter";
  const challenge=state.authChallenge, status=state.authStatus;
  const label={pending:"Откройте бота и нажмите Start",awaiting_code:"Введите код в боте",code_verified:"Подтвердите вход в боте",approved:"Завершаем вход…",denied:"Вход отклонён",expired:"Время запроса истекло"}[status]||"Ожидаем подтверждения в Telegram";
  const active=challenge&&!['expired','denied','consumed'].includes(status);
  const botName=challenge?new URL(challenge.bot_url).pathname.slice(1):"";
  const botWebURL=challenge?`https://web.telegram.org/k/#@${encodeURIComponent(botName)}`:"";
  return `<main id="main-content" class="auth-layout"><section class="auth-entry">${publicBrand()}
    <div class="auth-content"><h1>${challenge?"Один шаг до входа":"Вход за пару секунд"}</h1>
    <p class="auth-description">${challenge?"Подтвердите запрос в Telegram и вернитесь в этот браузер.":"Без пароля. Подтвердите вход в Telegram. Для первого входа создадим аккаунт автоматически."}</p>
    ${state.authError?`<p class="form-error auth-error" role="alert">${escapeHtml(state.authError)}</p>`:""}
    ${challenge?`<div class="auth-step">
      <p class="auth-state" role="status">${escapeHtml(label)}</p>
      ${active?`<span class="auth-code-label">Ваш одноразовый код</span><strong class="auth-code">${escapeHtml(challenge.code)}</strong>
        <a class="button primary" href="${escapeHtml(challenge.bot_url)}" target="_blank" rel="noopener noreferrer">${icon("telegram-logo")}Открыть Telegram-бота</a>
        <a class="button secondary" href="${escapeHtml(botWebURL)}" target="_blank" rel="noopener noreferrer">${icon("globe")}Открыть чат в Telegram Web</a>
        <details class="auth-help" open><summary>Без приложения Telegram</summary>
          <p>В чате с <strong>@${escapeHtml(botName)}</strong> отправьте команду ниже, затем код с этой страницы.</p>
          <label class="visually-hidden" for="telegram-start-command">Команда для бота</label>
          <div class="command-field"><input id="telegram-start-command" readonly value="/start ${escapeHtml(challenge.challenge_id)}" autocomplete="off" spellcheck="false" /><button class="icon-button" type="button" data-action="copy-telegram-command" aria-label="Скопировать команду">${icon("copy")}</button></div>
        </details>`:`<p class="muted">Код больше не действует. Создайте новый запрос.</p>`}
      <button class="auth-restart" type="button" data-action="restart-login">Начать заново</button>
    </div>`:`<button class="button primary auth-primary" type="button" data-action="begin-telegram" ${state.authBusy?"disabled":""}>${icon("telegram-logo")}${state.authBusy?"Создаём запрос…":"Продолжить через Telegram"}</button>${futureSignInButtons()}`}
    </div><a class="auth-back" href="/" data-route>${icon("arrow-left")}На главную</a>
  </section>${scriptIllustration()}</main>`;
}

function userAvatar(className="account-avatar") {
  const initials=(state.user.display_name||"?").split(/\s+/).slice(0,2).map(v=>v[0]||"").join("").toUpperCase();
  return `<span class="${className}"><span>${escapeHtml(initials)}</span>${state.user.avatar_path?`<img src="${escapeHtml(state.user.avatar_path)}" alt="" data-avatar-image />`:""}</span>`;
}

function sessionDevice(agent) {
  const platform=/iPad/.test(agent)?"iPad":/iPhone/.test(agent)?"iPhone":/Android/.test(agent)?"Android":/Windows/.test(agent)?"Windows":/Macintosh/.test(agent)?"Mac":/Linux/.test(agent)?"Linux":"Устройство";
  const browser=/Edg\//.test(agent)?"Edge":/Firefox\//.test(agent)?"Firefox":/Chrome\//.test(agent)?"Chrome":/Safari\//.test(agent)?"Safari":"Браузер";
  return `${browser} · ${platform}`;
}

function accountHeading(title,description,symbol) {
  return `<header class="account-section-heading"><span class="account-section-icon">${icon(symbol)}</span><div><h2>${title}</h2><p>${description}</p></div></header>`;
}

function accountPage() {
  document.title = "Профиль | Hype Hunter";
  const security=new URLSearchParams(location.search).get("tab")==="security";
  return shell(`<div class="account-content"><header class="page-header"><div><span class="eyebrow">Личный кабинет</span><h1>Профиль</h1><p>Ваши данные и доступ к Hype Hunter.</p></div></header>
    <nav class="account-tabs" aria-label="Разделы профиля"><a href="/account" data-route ${!security?'aria-current="page"':''}>${icon("user-circle")}Основные данные</a><a href="/account?tab=security" data-route ${security?'aria-current="page"':''}>${icon("shield-check")}Вход и безопасность</a></nav>
    ${security?accountSecurity():accountDetails()}
    <section class="account-id-strip"><div><strong>ID вашего аккаунта</strong><p>Поможет найти аккаунт при обращении за помощью.</p></div><button class="account-id" type="button" data-action="copy-account-id" aria-label="Скопировать ID аккаунта ${state.user.id}"><span>ID</span> ${state.user.id} ${icon("copy")}</button></section>
    <section class="account-exit"><div><h2>Выйти из аккаунта</h2><p>Завершить сеанс только на этом устройстве.</p></div><button class="button secondary" type="button" data-action="logout">${icon("sign-out")}Выйти</button></section>
    </div>`,"account-workspace");
}

function accountDetails() {
  return `<section class="account-panel">${accountHeading("Основные данные","Так вы будете отображаться в Hype Hunter.","user")}
    <form data-profile-form>
      <div class="account-photo-row">${userAvatar()}<div><div class="account-photo-actions"><label class="button secondary compact photo-picker ${state.photoBusy?'busy':''}"><input class="visually-hidden" type="file" accept="image/jpeg,image/png" data-profile-photo aria-label="Загрузить фото профиля" ${state.photoBusy?'disabled':''} />${icon("camera")}${state.photoBusy?"Загружаем…":"Изменить фото"}</label>${state.user.avatar_path?`<button class="text-link" type="button" data-action="remove-avatar" ${state.photoBusy?'disabled':''}>Убрать</button>`:""}</div><p>JPG или PNG, до 2 МБ</p></div></div>
      <div class="account-fields"><label for="profile-name">Имя<input id="profile-name" name="display_name" autocomplete="name" maxlength="80" required value="${escapeHtml(state.profileName??state.user.display_name)}" ${state.profileBusy?'disabled':''} /></label>
      <label for="profile-email">Email <span class="field-hint">${state.user.email?"Подтверждён":"Не подключён"}</span><input id="profile-email" type="text" readonly value="${escapeHtml(state.user.email||"Появится после подключения почты")}" aria-describedby="email-note" /></label></div>
      <p class="account-note" id="email-note">${icon("info")}Сейчас для входа используется Telegram. Подключение почты появится позже.</p>
      <div class="account-form-footer"><p class="${state.profileError?'form-error':'profile-save-state'}" data-profile-message role="status">${escapeHtml(state.profileError||state.profileSaved||"")}</p><button class="button primary" type="submit" ${state.profileBusy?'disabled':''}>${state.profileBusy?"Сохраняем…":"Сохранить изменения"}</button></div>
    </form></section>`;
}

function accountSecurity() {
  return `<section class="account-panel">${accountHeading("Способы входа","Вход без пароля. Ваши материалы связаны с одним аккаунтом.","lock-key")}
    <div class="identity-row"><span class="identity-icon">${icon("telegram-logo")}</span><div><strong>Telegram</strong><p>${state.user.telegram_username?'@'+escapeHtml(state.user.telegram_username):"Ваш подтверждённый аккаунт"}</p></div><span class="identity-connected">${icon("check-circle")}Подключён</span></div>
    <div class="identity-row future"><span class="identity-icon"><img class="yandex-logo" src="/assets/yandex-logo.svg" width="24" height="24" alt="" /></span><div><strong>Яндекс ID</strong><p>Вход через аккаунт Яндекса</p></div><button type="button" class="button secondary compact" disabled>Скоро</button></div>
    <div class="identity-row future"><span class="identity-icon">${icon("envelope-simple")}</span><div><strong>Email</strong><p>Код на российскую почту</p></div><button type="button" class="button secondary compact" disabled>Скоро</button></div>
    </section><section class="account-panel">${accountHeading("Активные сеансы","Завершите сеанс, если больше не используете устройство.","devices")}
    <div class="account-sessions">${state.sessions.map(s=>`<div class="account-session"><span class="session-icon">${icon(/Android|iPhone|iPad/.test(s.user_agent)?"device-mobile":"desktop")}</span><div class="session-copy"><strong>${escapeHtml(sessionDevice(s.user_agent))}</strong><p>${s.current?'Это устройство':`Активность ${formatDateTime(s.last_seen_at)}`}</p></div>${s.current?'<span class="current-session">Текущий</span>':`<button type="button" class="button secondary compact" data-action="revoke-session" data-session-id="${s.id}">Завершить</button>`}</div>`).join("")||'<p class="muted">Нет активных сеансов.</p>'}</div>
    <div class="account-session-footer"><button class="button secondary" type="button" data-action="logout-all">Выйти на всех устройствах</button></div></section>`;
}

async function saveProfile() {
  if(state.profileBusy)return;
  const userId=state.user.id;
  state.profileBusy=true;state.profileError="";state.profileSaved="";render();
  try {
    const saved=await apiRequest("/auth/profile",{method:"PATCH",body:JSON.stringify({display_name:state.profileName??state.user.display_name})});
    if(state.user?.id===userId){state.user.display_name=saved.display_name;state.profileName=null;state.profileSaved="Изменения сохранены";}
  } catch(error) {if(state.user?.id===userId)state.profileError=error.message;}
  finally {state.profileBusy=false;if(state.user?.id===userId)render();}
}

async function uploadProfilePhoto(file) {
  if(!file)return;
  const userId=state.user.id;
  if(!["image/jpeg","image/png"].includes(file.type)||file.size>2*1024*1024){state.profileError="Выберите JPG или PNG размером до 2 МБ";render();return;}
  state.photoBusy=true;state.profileError="";state.profileSaved="";render();
  try {
    const saved=await apiRequest("/auth/profile/avatar",{method:"PUT",headers:{"Content-Type":file.type},body:file});
    if(state.user?.id===userId){state.user.avatar_path=saved.avatar_path;state.profileSaved="Фото сохранено";}
  } catch(error) {if(state.user?.id===userId)state.profileError=error.message;}
  finally {state.photoBusy=false;if(state.user?.id===userId)render();}
}

function loginReturnPath(value) {
  if(typeof value!=="string"||!value.startsWith("/")||value.startsWith("//")||/[\\\x00-\x1f]/.test(value))return "/today";
  const path=value.split("?",1)[0];
  return ["/today","/library","/content-plan","/competitors","/account"].includes(path)||/^\/remixes\/[a-zA-Z0-9_-]{1,255}$/.test(path)?value.slice(0,512):"/today";
}

function routeAccess() {
  if(!state.user&&!['/','/login'].includes(state.route)){
    const destination=loginReturnPath(location.pathname+location.search);
    history.replaceState({},"","/login?"+new URLSearchParams({return_to:destination}));state.route="/login";
  } else if(state.user&&state.route==="/login"){
    const destination=loginReturnPath(new URLSearchParams(location.search).get("return_to"));
    history.replaceState({},"",destination);state.route=normalizeRoute(location.pathname);
  }
}
