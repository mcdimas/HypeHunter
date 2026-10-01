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
  return `<div class="future-sign-in" aria-label="Другие способы входа">
    <span class="auth-divider">Другие способы входа</span>
    <button class="button ${state.authProviders?.yandex?'secondary':'future-method'}" type="button" data-action="begin-yandex" ${!state.authProviders?.yandex||state.authBusy?'disabled':''}><img class="yandex-logo" src="/assets/yandex-logo.svg" width="24" height="24" alt="" />Войти через Яндекс${state.authProviders?.yandex?'':'<span class="soon-label">Скоро</span>'}</button>
    <button class="button ${state.authProviders?.email?'secondary':'future-method'}" type="button" data-action="begin-email" ${!state.authProviders?.email||state.authBusy?'disabled':''}>${icon("envelope-simple")}Войти по почте с кодом${state.authProviders?.email?'':'<span class="soon-label">Скоро</span>'}</button>
  </div>`;
}

function loginPage() {
  document.title = "Вход | Hype Hunter";
  const challenge=state.authChallenge, status=state.authStatus;
  const label={pending:"Откройте бота и нажмите Start",awaiting_code:"Введите код в боте",code_verified:"Подтвердите вход в боте",approved:"Завершаем вход…",denied:"Вход отклонён",expired:"Время запроса истекло"}[status]||"Ожидаем подтверждения в Telegram";
  const active=challenge&&!['expired','denied','consumed'].includes(status);
  const botName=challenge?new URL(challenge.bot_url).pathname.slice(1):"";
  const botWebURL=challenge?`https://web.telegram.org/k/#@${encodeURIComponent(botName)}`:"";
  return `<main id="main-content" class="auth-layout"><section class="auth-entry">${publicBrand()}<button class="theme-public-button icon-button" type="button" data-theme="toggle" aria-label="Сменить тему">${icon('sun')}</button>
    <div class="auth-content"><h1>${state.emailLogin?(state.emailLogin.challenge?"Проверьте почту":"Вход по почте"):challenge?"Один шаг до входа":"Вход за пару секунд"}</h1>
    <p class="auth-description">${state.emailLogin?(state.emailLogin.challenge?`Отправили шестизначный код на ${escapeHtml(state.emailLogin.email)}. Введите его здесь, в этом браузере.`:"Пришлём одноразовый код. Если аккаунт с этой почтой уже есть, откроем его. Иначе создадим новый."):challenge?"Подтвердите запрос в Telegram и вернитесь в этот браузер.":"Без пароля. Выберите удобный способ входа. Для первого входа создадим аккаунт автоматически."}</p>
    ${state.authError||oauthError()?`<p class="form-error auth-error" role="alert">${escapeHtml(state.authError||oauthError())}</p>`:""}
    ${state.emailLogin?emailLoginForm():challenge?`<div class="auth-step">
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
    <p class="auth-legal">Начиная пользоваться сервисом, вы принимаете <a href="/legal/offer/" target="_blank" rel="noopener">условия использования</a>. О том, как мы обрабатываем данные, — в <a href="/legal/privacy/" target="_blank" rel="noopener">политике обработки персональных данных</a>.</p>
    </div><a class="auth-back" href="/" data-route>${icon("arrow-left")}На главную</a>
  </section>${scriptIllustration()}</main>`;
}

function emailLoginForm(){
  const flow=state.emailLogin, sent=flow.challenge;
  const remaining=Math.max(0,Math.ceil(((flow.resendAt||0)-Date.now())/1000));
  return `<form class="email-login-form" data-email-form>
    <label for="email-login-input">${sent?'Код из письма':'Email'}</label>
    ${sent?`<input id="email-login-input" name="code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" minlength="6" maxlength="6" required placeholder="000000" aria-describedby="email-login-help" />`:`<input id="email-login-input" name="email" type="email" autocomplete="email" maxlength="254" required placeholder="name@mail.ru" value="${escapeHtml(flow.email||'')}" aria-describedby="email-login-help" />`}
    <p class="muted" id="email-login-help">${sent?`Код действует ${flow.challenge.expires_in_minutes} минут. Если письма нет, проверьте папку «Спам».`:'Поддерживаются Яндекс, Mail.ru и Рамблер.'}</p>
    <button class="button primary auth-primary" type="submit" ${state.authBusy?'disabled':''}>${state.authBusy?'Подождите…':sent?'Войти':'Получить код'}</button>
    ${sent?`<button class="button secondary" type="button" data-action="resend-email" ${remaining||state.authBusy?'disabled':''}>${remaining?`Отправить повторно через ${remaining} с`:'Отправить код ещё раз'}</button><button class="auth-restart" type="button" data-action="change-email" ${state.authBusy?'disabled':''}>Изменить адрес</button>`:''}
    <button class="auth-restart" type="button" data-action="cancel-email" ${state.authBusy?'disabled':''}>Другой способ входа</button>
  </form>`;
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
  const tab=new URLSearchParams(location.search).get("tab")||"profile";
  const tabs=[["profile","Профиль"],["subscription","Подписка и лимиты"],["scenarios","Настройки сценариев"],["notifications","Уведомления"],["security","Вход и безопасность"],["danger","Опасная зона"]];
  return shell(`<div class="account-content"><header class="page-header"><div><span class="eyebrow">Личный кабинет</span><h1>Профиль</h1><p>Ваши данные и доступ к Hype Hunter.</p></div></header>
    <nav class="account-tabs" aria-label="Разделы профиля">${tabs.map(([key,label])=>`<a href="/account${key==='profile'?'':'?tab='+key}" data-route ${tab===key?'aria-current="page"':''}>${label}</a>`).join('')}</nav>
    ${tab==='security'?accountSecurity():tab==='subscription'?testBillingMarkup()+accountSubscription():tab==='scenarios'?accountPreferencesForm(false):tab==='notifications'?accountPreferencesForm(true):tab==='danger'?accountDanger():accountDetails()+accountAppearance()}
    <section class="account-id-strip"><div><strong>ID вашего аккаунта</strong><p>Поможет найти аккаунт при обращении за помощью.</p></div><button class="account-id" type="button" data-action="copy-account-id" aria-label="Скопировать ID аккаунта ${state.user.id}"><span>ID</span> ${state.user.id} ${icon("copy")}</button></section>
    <section class="account-exit"><div><h2>Выйти из аккаунта</h2><p>Завершить сеанс только на этом устройстве.</p></div><button class="button secondary" type="button" data-action="logout">${icon("sign-out")}Выйти</button></section>
    </div>`,"account-workspace");
}

function accountAppearance() {
  return `<section class="account-panel">${accountHeading("Оформление","Выбор темы сохраняется в этом браузере.","sun")}<div class="preference-segments">${[['dark','moon','Тёмная'],['light','sun','Светлая']].map(([theme,symbol,label])=>`<button type="button" data-theme="${theme}" aria-pressed="${currentTheme()===theme}">${icon(symbol)}${label}</button>`).join('')}</div></section>`;
}

function testBillingMarkup() {
  if(!state.testBilling?.owner&&!state.testBilling?.available)return '';
  if(!state.testBilling.available)return `<section class="account-panel test-billing"><h2>Тестовая подписка — 1 ₽</h2><p role="status">Настройки тестового магазина ЮKassa пока не готовы. Для запуска нужны корректные shopId и секретный ключ из одного тестового магазина.</p><button class="button primary" type="button" disabled>Тестовая подписка — 1 ₽</button><p class="muted">Реальные деньги не списываются. Автопродления нет.</p></section>`;
  const payment=state.testBilling.payment;
  const labels={pending:'Ожидает оплаты',waiting_for_capture:'Ожидает подтверждения ЮKassa',succeeded:'Тестовая оплата прошла',canceled:'Тестовая оплата отменена'};
  return `<section class="account-panel test-billing"><h2>Тестовая подписка — 1 ₽</h2><p>Только для проверки ЮKassa. Реальные деньги не списываются. Используйте тестовую карту, не настоящую.</p><p>Без автопродления. Тест не меняет ваш тариф, бесплатный лимит и материалы.</p>${payment?`<p class="test-payment-status" role="status">${labels[payment.status]||'Проверяем платёж…'}${payment.test_access_until?` · Тестовый период до ${formatDateTime(payment.test_access_until)}`:''}</p>`:''}<div class="test-billing-actions"><button class="button primary" type="button" data-action="test-checkout" ${state.billingBusy?'disabled':''}>${state.billingBusy?'Подождите…':payment?.status==='pending'?'Продолжить тестовую оплату — 1 ₽':'Тестовая подписка — 1 ₽'}</button>${payment?`<button class="button secondary" type="button" data-action="test-payment-refresh" ${state.billingBusy?'disabled':''}>Проверить статус</button>`:''}</div><p class="muted">Тестовая карта: 5555 5555 5555 4444 · срок 12/30 · CVC 123. Настоящий чек НПД в этом режиме не формируется.</p></section>`;
}

async function beginTestCheckout() {
  if(state.billingBusy||!state.testBilling?.available)return;
  state.billingBusy=true;render();
  try {const result=await apiRequest('/billing/test/checkout',{method:'POST'});state.testBilling.payment=result;if(result.confirmation_url){location.assign(result.confirmation_url);return;}showToast(result.status==='succeeded'?'Тестовая оплата подтверждена':'Платёж завершён. Для новой попытки нажмите кнопку ещё раз.');}
  catch(error){showToast(error.message,'error');}
  finally {state.billingBusy=false;render();}
}

async function refreshTestPayment() {
  if(state.billingBusy||!state.testBilling?.payment)return;
  state.billingBusy=true;render();
  try {const result=await apiRequest('/billing/test/payments/'+encodeURIComponent(state.testBilling.payment.id)+'/refresh',{method:'POST'});state.testBilling.payment=result;showToast(result.status==='succeeded'?'Тестовая оплата подтверждена':result.status==='canceled'?'Тестовая оплата отменена':'ЮKassa пока ожидает оплату');}
  catch(error){showToast(error.message,'error');}
  finally {state.billingBusy=false;render();}
}

function accountSubscription() {
  const trial=state.trial, early=trial?.limit===null;
  return `<section class="account-panel plan-current"><h2>${early?'Ранний доступ':'Бесплатный'} <span class="plan-tag">Текущий тариф</span></h2><p>${early?'Для вашего существующего аккаунта сохранены прежние условия доступа.':trial?`Использовано ${trial.used} из ${trial.limit} бесплатных роликов · Осталось ${trial.remaining}`:'Загружаем лимиты…'}</p>${!early&&trial?`<progress value="${trial.used}" max="${trial.limit}" aria-label="Использовано бесплатных роликов"></progress><p class="muted">Лимит выдаётся один раз после регистрации и не сбрасывается при удалении материалов.</p>`:''}</section><div class="account-plans">${[['Старт','Для первых проб','1 999',40],['Про','Для ежедневной работы','3 900',100]].map(([name,desc,price,count],i)=>`<section class="account-panel pricing-option ${i?'recommended':''}">${i?'<span class="recommended-label">Рекомендуем</span>':''}<h2>${name}</h2><p>${desc}</p><div class="account-price">${price} <span>₽/мес</span></div><ul>${[`${count} материалов в месяц`,'Reels и Threads в одной библиотеке','Перевод и редактор своих текстов','Доска и календарь публикаций'].map(feature=>`<li>${icon('check-circle')}${feature}</li>`).join('')}</ul><button class="button ${i?'primary':'secondary'}" disabled>Оплата скоро</button></section>`).join('')}</div><p class="account-note">Подключение оплаты через ЮKassa готовится. Сейчас платные тарифы недоступны, деньги не списываются.</p>`;
}

function preferenceSwitch(name,title,description,value) {
  return `<label class="preference-switch"><input type="checkbox" name="${name}" role="switch" ${value?'checked':''}><span class="switch-track" aria-hidden="true"></span><span><strong>${title}</strong><small>${description}</small></span></label>`;
}

function preferenceChoices(name,title,options,value) {
  return `<fieldset class="preference-group"><legend>${title}</legend><div class="preference-segments">${options.map(([key,label])=>`<label><input type="radio" name="${name}" value="${key}" ${value===key?'checked':''} required><span>${label}</span></label>`).join('')}</div></fieldset>`;
}

function accountPreferencesForm(notifications) {
  const p=state.preferences;
  if(!p)return '<section class="account-panel"><p role="status">Загружаем настройки…</p></section>';
  return `<section class="account-panel"><form data-preferences-form="${notifications?'notifications':'scenarios'}">${notifications?
    preferenceSwitch('notifications_new_ideas','Новые идеи готовы','Письмо, когда загрузятся новые материалы конкурентов.',p.notifications_new_ideas)+preferenceSwitch('notifications_reminder','Напоминание о неснятом','Если сценарий находится в «Готово» больше трёх дней.',p.notifications_reminder)+preferenceSwitch('notifications_weekly','Сводка недели','Что разобрано, подготовлено и опубликовано.',p.notifications_weekly):
    preferenceChoices('scenario_tone','Тон сценария',[['neutral','Нейтральный'],['conversational','Разговорный'],['bold','Смелый']],p.scenario_tone)+preferenceChoices('hook_length','Длина хука',[['short','Короткий · 4–6 слов'],['medium','Средний · 6–9 слов'],['long','Длинный · до 12 слов']],p.hook_length)+preferenceSwitch('use_personal_cta','Подставлять имя и оффер в CTA','Ваш призыв вместо призыва конкурента.',p.use_personal_cta)+`<div class="account-fields"><label>Бренд или имя<input name="brand_name" maxlength="80" value="${escapeHtml(p.brand_name)}" placeholder="Например, кофейня «Утро»"></label><label>Ваш оффер<input name="offer" maxlength="500" value="${escapeHtml(p.offer)}" placeholder="Что предлагаете и как с вами связаться"></label></div>`}
    <p class="preferences-notice">${icon('info')}${notifications?'Предпочтения сохраняются. Рассылка уведомлений ещё не подключена — эти переключатели пока не запускают отправку писем.':'Настройки сохраняются. Применение к новым AI-сценариям подключим после восстановления перевода. Уже готовые тексты не изменятся.'}</p><div class="account-form-footer"><span class="muted" role="status" data-preferences-status></span><button class="button primary" type="submit">Сохранить настройки</button></div></form></section>`;
}

async function savePreferences(form) {
  const userId=state.user.id, data=new FormData(form), notifications=form.dataset.preferencesForm==='notifications';
  const payload={...state.preferences};
  const names=notifications?['notifications_new_ideas','notifications_reminder','notifications_weekly']:['scenario_tone','hook_length','use_personal_cta','brand_name','offer'];
  for(const name of names)payload[name]=typeof payload[name]==='boolean'?data.has(name):String(data.get(name)||'').trim();
  const button=form.querySelector('[type="submit"]'), status=form.querySelector('[data-preferences-status]');
  button.disabled=true;status.textContent='Сохраняем…';
  try {const saved=await apiRequest('/auth/preferences',{method:'PUT',body:JSON.stringify(payload)});if(state.user?.id===userId){state.preferences=saved;status.textContent='Настройки сохранены';}}
  catch(error){if(state.user?.id===userId){status.textContent=error.message;showToast(error.message,'error');}}
  finally {button.disabled=false;}
}

function accountDanger() {
  return `<section class="account-panel account-danger"><h2>Удалить все рабочие данные</h2><p>Конкуренты, загруженные материалы, сценарии и контент-план будут удалены. Аккаунт, способы входа и настройки останутся. Бесплатный лимит не восстановится.</p><details><summary class="button secondary">${icon('trash')}Удалить данные</summary><form data-clear-workspace-form><label for="clear-confirmation">Для подтверждения введите УДАЛИТЬ</label><input id="clear-confirmation" name="confirmation" autocomplete="off" required pattern="УДАЛИТЬ" placeholder="УДАЛИТЬ"><p>Это действие нельзя отменить через интерфейс.</p><button class="button danger" type="submit">Удалить все данные навсегда</button><p role="status" data-clear-status></p></form></details></section>`;
}

async function clearWorkspace(form) {
  const button=form.querySelector('[type="submit"]'), status=form.querySelector('[data-clear-status]');button.disabled=true;
  try {await apiRequest('/workspace',{method:'DELETE',body:JSON.stringify({confirmation:new FormData(form).get('confirmation')})});state.reels=[];state.remixes=[];state.competitors=[];state.imports=[];state.translations=null;await loadRouteData();showToast('Рабочие данные удалены. Аккаунт сохранён.');}
  catch(error){status.textContent=error.message;button.disabled=false;}
}

function accountDetails() {
  return `<section class="account-panel">${accountHeading("Основные данные","Так вы будете отображаться в Hype Hunter.","user")}
    <form data-profile-form>
      <div class="account-photo-row">${userAvatar()}<div><div class="account-photo-actions"><label class="button secondary compact photo-picker ${state.photoBusy?'busy':''}"><input class="visually-hidden" type="file" accept="image/jpeg,image/png" data-profile-photo aria-label="Загрузить фото профиля" ${state.photoBusy?'disabled':''} />${icon("camera")}${state.photoBusy?"Загружаем…":"Изменить фото"}</label>${state.user.avatar_path?`<button class="text-link" type="button" data-action="remove-avatar" ${state.photoBusy?'disabled':''}>Убрать</button>`:""}</div><p>JPG или PNG, до 2 МБ</p></div></div>
      <div class="account-fields"><label for="profile-name">Имя<input id="profile-name" name="display_name" autocomplete="name" maxlength="80" required value="${escapeHtml(state.profileName??state.user.display_name)}" ${state.profileBusy?'disabled':''} /></label>
      <label for="profile-email">Email <span class="field-hint">${state.user.email_provider==="yandex"?"Из Яндекс ID":state.user.email?"Подтверждён":"Не подключён"}</span><input id="profile-email" type="text" readonly value="${escapeHtml(state.user.email||"Появится после подключения почты")}" aria-describedby="email-note" /></label></div>
      <p class="account-note" id="email-note">${icon("info")}Способы входа находятся в разделе «Вход и безопасность». ${state.user.email_provider==="yandex"?"Адрес получен из Яндекс ID. Подтверждение кода на этот адрес откроет тот же аккаунт.":state.user.email_provider==="email"?"Адрес подтверждён одноразовым кодом.":"Подключение почты к текущему аккаунту пока недоступно."}</p>
      <div class="account-form-footer"><p class="${state.profileError?'form-error':'profile-save-state'}" data-profile-message role="status">${escapeHtml(state.profileError||state.profileSaved||"")}</p><button class="button primary" type="submit" ${state.profileBusy?'disabled':''}>${state.profileBusy?"Сохраняем…":"Сохранить изменения"}</button></div>
    </form></section>`;
}

function accountSecurity() {
  return `<section class="account-panel">${accountHeading("Способы входа","Вход без пароля. Ваши материалы связаны с одним аккаунтом.","lock-key")}
    ${oauthError()?`<p class="form-error" role="alert">${escapeHtml(oauthError())}</p>`:''}
    <div class="identity-row"><span class="identity-icon">${icon("telegram-logo")}</span><div><strong>Telegram</strong><p>${state.user.telegram_username?'@'+escapeHtml(state.user.telegram_username):"Вход через Telegram"}</p></div><span class="identity-connected">${state.user.providers?.includes('telegram')?icon("check-circle")+'Подключён':'Не подключён'}</span></div>
    <div class="identity-row"><span class="identity-icon"><img class="yandex-logo" src="/assets/yandex-logo.svg" width="24" height="24" alt="" /></span><div><strong>Яндекс ID</strong><p>Вход через аккаунт Яндекса</p></div>${state.user.providers?.includes('yandex')?`<span class="identity-connected">${icon("check-circle")}Подключён</span>`:`<button type="button" class="button secondary compact" data-action="link-yandex" ${state.authProviders?.yandex?'':'disabled'}>${state.authProviders?.yandex?'Подключить':'Скоро'}</button>`}</div>
    <div class="identity-row"><span class="identity-icon">${icon("envelope-simple")}</span><div><strong>Email</strong><p>${escapeHtml(state.user.email||'Вход по одноразовому коду')}</p></div><span class="identity-connected">${state.user.providers?.includes('email')?icon('check-circle')+'Подключён':state.user.email_provider==='yandex'?'Через адрес Яндекса':'Не подключён'}</span></div>
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
