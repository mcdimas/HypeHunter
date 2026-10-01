/* Public examples are editorial fixtures, never private library data. No API calls. */
const LANDING_EXAMPLES = {
  reels: {
    label: "Reels", icon: "film-strip", original: "Stop selling coffee. Show people their perfect morning.",
    hook: "Продавайте не кофе. Покажите утро, ради которого к вам вернутся.",
    script: "Первый глоток, тёплая чашка и две минуты без спешки. Снимите три коротких кадра, чтобы зритель почувствовал атмосферу вашей кофейни.",
    cta: "Заходите за своим спокойным утром. Кофе уже готов.",
    draft: "Утро, за которым хочется вернуться", stage: "Сценарий"
  },
  threads: {
    label: "Threads", icon: "chats-circle", original: "Your best content idea is the question a customer asked you today.",
    hook: "Лучшая идея для контента уже есть в вопросах ваших клиентов.",
    script: "Сегодня гость спросил, почему дома кофе получается кислым. Вместо длинной лекции сделали короткую памятку: чуть мельче помол, чуть горячее вода. Один вопрос превращается в полезный пост.",
    cta: "А какой вопрос о кофе вы давно хотели задать?",
    draft: "Почему кофе дома получается кислым", stage: "Редактура"
  }
};
let landingFormat = "reels", landingStep = 0, landingEffectsCleanup = () => {};
const landingEdits = {reels: null, threads: null};

function landingConnect(classes="primary", arrow=true) {
  return `<a class="button ${classes}" href="${state.user?"/today":"/login"}" data-route>${state.user?"Открыть приложение":"Подключиться"}${arrow?icon("arrow-right"):""}</a>`;
}

function landingFormatTabs() {
  return `<div class="landing-format-tabs" role="tablist" aria-label="Формат примера">${Object.entries(LANDING_EXAMPLES).map(([key,item])=>`<button id="example-tab-${key}" role="tab" type="button" aria-selected="${landingFormat===key}" aria-controls="landing-example-panel" tabindex="${landingFormat===key?0:-1}" data-landing-format="${key}">${icon(item.icon)}${item.label}</button>`).join("")}</div>`;
}

function landingExample() {
  const sample=LANDING_EXAMPLES[landingFormat];
  return `<div class="landing-example-toolbar">${landingFormatTabs()}</div>
    <div id="landing-example-panel" role="tabpanel" aria-labelledby="example-tab-${landingFormat}" class="landing-example-body">
      <div class="landing-example-source">${landingFormat==="reels"?'<video src="/assets/landing-creator.mp4" poster="/assets/landing-creator.webp" width="480" height="640" autoplay muted loop playsinline preload="metadata" aria-label="Автор снимает короткое видео в кофейне. Иллюстрация."><img src="/assets/landing-creator.webp" width="480" height="640" alt="Автор снимает короткое видео в кофейне. Иллюстрация." /></video>':`<div class="landing-thread-source">${icon("chats-circle")}<span>Исходная мысль</span><p lang="en">${sample.original}</p></div>`}</div>
      <div class="landing-example-copy"><div class="landing-original"><span class="copy-label">${landingFormat==="reels"?"Оригинал":"Перевод идеи"}</span><p ${landingFormat==="reels"?'lang="en"':''}>${landingFormat==="reels"?sample.original:"Ищите темы в вопросах, которые клиенты задают вам каждый день."}</p></div>
        <div class="landing-adapted"><span class="copy-label">${icon("sparkle")} Ваша версия для бизнеса</span><h2>${sample.hook}</h2><p>${sample.script}</p><div class="landing-example-cta"><span class="copy-label">Призыв к действию</span><p>${sample.cta}</p></div></div>
      </div>
    </div>`;
}

function landingWorkflowPanel() {
  const sample=LANDING_EXAMPLES[landingFormat];
  const panels=[
    `<div class="workflow-source"><div class="workflow-source-icon">${icon("users")}</div><h3>Начните с одного аккаунта</h3><p>Добавьте ссылку на Instagram или Threads из вашей ниши.</p><div class="workflow-profile">${icon("link")}<span>Ссылка на профиль конкурента</span>${icon("plus")}</div><div class="workflow-formats">${icon("instagram-logo")} Instagram Reels <span></span>${icon("chats-circle")} Threads</div><p class="workflow-note">До 20 последних материалов за одну загрузку.</p></div>`,
    `<div class="workflow-compare"><div class="workflow-panel-heading"><h3>Сначала посмотрите на отклик</h3>${icon("sort-descending")}</div><p>Сравнивайте загруженную выборку по просмотрам, лайкам и комментариям.</p><div class="workflow-comparison-row"><span>${icon("film-strip")} Reels</span><strong>Просмотры</strong><span>${icon("heart")} Лайки</span></div><div class="workflow-comparison-row"><span>${icon("chats-circle")} Threads</span><strong>Лайки и ответы</strong><span>${icon("arrows-clockwise")} Репосты</span></div><div class="workflow-insight">${icon("lightbulb")}Заметьте, какая тема и подача сработали. Возьмите идею, а не чужой текст.</div><p class="workflow-note">Показываем только доступные показатели, без выдуманных цифр.</p></div>`,
    `<div class="workflow-edit"><div class="workflow-panel-heading"><h3>Попробуйте изменить хук</h3>${icon("pencil-simple")}</div><label for="landing-hook">Ваша редакция<textarea id="landing-hook" rows="3" maxlength="4000" data-landing-edit>${escapeHtml(landingEdits[landingFormat]??sample.hook)}</textarea></label><div class="workflow-edit-footer"><span data-landing-edit-count>${Array.from(landingEdits[landingFormat]??sample.hook).length} / 4000</span><button class="text-link" type="button" data-landing-reset>Вернуть пример</button></div><p class="workflow-note">Это пример редактора. Правки здесь не сохраняются в аккаунт.</p><p class="workflow-insight">${icon("chats-circle")}Из сценария можно подготовить Threads. Из текста Threads можно развить идею Reels.</p></div>`,
    `<div class="workflow-plan"><div class="workflow-panel-heading"><h3>Доведите идею до публикации</h3>${icon("calendar-blank")}</div><div class="workflow-plan-lanes"><span>Идеи</span><span class="active">В работе</span><span>Готово</span></div><article class="workflow-draft"><span class="format-label">${icon(sample.icon)}${sample.label}</span><h4>${sample.draft}</h4><span class="status-chip in_progress">${sample.stage}</span><p>${icon("calendar-blank")}Выберите дату в календаре</p></article><p class="workflow-note">Публикуйте вручную, отмечайте готовность в плане и оценивайте отклик в соцсети.</p></div>`
  ];
  return panels[landingStep];
}

function landingPage() {
  document.title="Hype Hunter | Идеи, сценарии и контент-план для Reels и Threads";
  return `<div class="landing">
    <header class="landing-header"><div class="landing-container landing-nav">${publicBrand()}<nav aria-label="Навигация лендинга"><a href="#how-it-works">Как это работает</a><a href="#pricing">Тарифы</a></nav><div class="landing-nav-actions"><a class="landing-signin" href="${state.user?"/account":"/login"}" data-route>${state.user?"Кабинет":"Войти"}</a>${landingConnect("primary",false)}</div></div></header>
    <main id="main-content">
      <section class="landing-hero landing-container"><h1 aria-label="Получайте клиентов, заявки и просмотры из Reels и Threads"><span aria-hidden="true"><span class="landing-title-line"><span class="landing-title-prefix">Получайте</span><span class="landing-type-slot"><span data-landing-type>клиентов</span><span class="landing-caret"></span></span></span><span class="landing-title-tail">из Reels и Threads</span></span></h1><p class="landing-lead">Автоматизируйте рутину продюсера стоимостью <strong>от 80 000 ₽ в месяц:</strong> поиск идей, перевод и подготовку текстов.</p><div class="landing-hero-actions">${landingConnect()}<a class="button secondary" href="#how-it-works">Как это работает</a><a class="button secondary" href="https://github.com/mcdimas/HypeHunter" target="_blank" rel="noopener noreferrer">${icon("github-logo")}GitHub</a></div>
      <section class="landing-example" aria-label="Пример Reels и Threads" data-landing-example>${landingExample()}</section></section>
      <section class="landing-section landing-container" id="how-it-works"><header class="landing-section-heading landing-reveal"><h2>Не начинайте с пустого листа</h2><p>От чужой удачной идеи до своей публикации.<br>Всё в одном рабочем пространстве.</p></header>
        <div class="landing-workflow landing-reveal"><div class="workflow-steps" role="tablist" aria-label="Как работает Hype Hunter" aria-orientation="vertical">${[
          ["Добавьте конкурентов","Ссылки на Reels и Threads из вашей ниши."],
          ["Найдите то, что сработало","Сравните тексты и показатели загруженных публикаций."],
          ["Адаптируйте под свой бизнес","Доработайте перевод, хук, сценарий и призыв к действию."],
          ["Соберите свой контент-план","Назначьте дату и двигайте публикацию до готовности."]
        ].map(([title,text],i)=>`<button type="button" role="tab" id="workflow-tab-${i}" aria-controls="workflow-panel" aria-selected="${i===landingStep}" tabindex="${i===landingStep?0:-1}" data-landing-step="${i}"><span class="workflow-number">${i+1}</span><span><strong>${title}</strong><small>${text}</small></span>${icon("caret-right")}</button>`).join("")}</div><div id="workflow-panel" role="tabpanel" aria-labelledby="workflow-tab-${landingStep}" class="workflow-panel" data-landing-workflow>${landingWorkflowPanel()}</div></div>
      </section>
      <section class="landing-economy landing-container landing-reveal"><div><span class="landing-kicker">Больше времени на ваш бизнес</span><h2>Идеи и тексты.<br>Без отдельного продюсера.</h2><p>Оставьте себе съёмку, экспертизу и общение с клиентами. Поиск референсов, перевод и работу над сценарием соберите в Hype Hunter.</p></div><div class="landing-costs"><div><span>Работа продюсера</span><strong>от 80 000 <small>₽/мес.</small></strong></div><div class="landing-cost-product"><span>Hype Hunter</span><strong>от 1 999 <small>₽/мес.</small></strong></div></div></section>
      <section class="landing-section landing-container" id="pricing"><header class="landing-section-heading landing-reveal"><h2>Выберите свой темп</h2><p>Один инструмент для Reels и Threads.<br>От первых идей до регулярного контента.</p></header><div class="landing-pricing landing-reveal">${[
        {name:"Старт",price:"1 999",description:"Для первых регулярных публикаций",limit:"40 материалов в месяц",featured:false},
        {name:"Про",price:"3 900",description:"Для активной работы с контентом",limit:"100 материалов в месяц",featured:true}
      ].map(plan=>`<article class="landing-price-card ${plan.featured?'featured':''}"><div class="landing-plan-title"><h3>${plan.name}</h3>${plan.featured?'<span>Больше материалов</span>':''}</div><p class="landing-plan-description">${plan.description}</p><p class="landing-price">${plan.price}<span>₽/мес.</span></p><ul>${[plan.limit,"Reels и Threads в одной библиотеке","Перевод и редактор своих текстов","Доска и календарь публикаций"].map(feature=>`<li>${icon("check")} ${feature}</li>`).join("")}</ul>${landingConnect(plan.featured?'primary':'secondary',false)}</article>`).join("")}</div><p class="landing-pricing-note">Подписки и оплата готовятся к запуску. Сейчас кнопка открывает регистрацию; деньги не списываются. Объёмы указаны для будущих тарифов.</p></section>
      <section class="landing-faq landing-container landing-reveal" aria-labelledby="faq-title"><h2 id="faq-title">Коротко о главном</h2><div>${[
        ["Какие публикации я получу?","Последние материалы выбранного аккаунта. Их можно отсортировать по доступным показателям и найти лучшие в загруженной выборке. Это не поиск по всей истории конкурента."],
        ["Можно работать только с Threads?","Да. У текстовых публикаций есть оригинал, доступные реакции и отдельный путь редактирования. Текст можно доработать для Threads или использовать как идею Reels."],
        ["Нужно копировать чужие публикации?","Нет. Изучайте тему, структуру и подачу, а затем добавляйте свои примеры, опыт и предложение. Исходник и ваша редакция сохраняются отдельно."],
        ["Сервис сам публикует контент?","Нет. Hype Hunter помогает подготовить и спланировать публикации. Вы публикуете их самостоятельно и вручную отмечаете результат в контент-плане."],
        ["Гарантированы ли клиенты и просмотры?","Нет. Результат зависит от вашего предложения, качества контента и аудитории. Сервис сокращает подготовительную работу; доступность импорта и перевода зависит от внешних сервисов."]
      ].map(([q,a])=>`<details><summary>${q}${icon("plus")}</summary><p>${a}</p></details>`).join("")}</div></section>
      <section class="landing-final landing-container landing-reveal"><h2>Ваша следующая публикация<br>начинается с хорошей идеи.</h2><p>Найдите референс. Добавьте свой взгляд. Подготовьте к выходу.</p>${landingConnect()}</section>
    </main>
    <footer class="landing-footer"><div class="landing-container landing-footer-grid"><div>${publicBrand()}<p>Идеи, сценарии и контент-план<br>для Reels и Threads.</p><small>© ${new Date().getFullYear()} Hype Hunter</small></div><div class="landing-legal"><h2>Реквизиты</h2><p>Демичев Дмитрий Дмитриевич<br>ИНН 772460063060</p><a href="mailto:demichev4work@ya.ru">demichev4work@ya.ru</a><a href="https://t.me/demichevdigital" target="_blank" rel="noopener noreferrer">Telegram ${icon("arrow-up-right")}</a></div><div class="landing-footer-links"><h2>Продукт</h2><a href="#how-it-works">Как это работает</a><a href="#pricing">Тарифы</a><a href="https://github.com/mcdimas/HypeHunter" target="_blank" rel="noopener noreferrer">Исходный код на GitHub</a><span>Оферта <small>Готовится</small></span><span>Политика конфиденциальности <small>Готовится</small></span></div></div></footer>
  </div>`;
}

function stopLandingEffects() { landingEffectsCleanup(); landingEffectsCleanup=()=>{}; }

function mountLanding() {
  const root=app.querySelector(".landing");
  if(!root)return;
  const motion=matchMedia("(prefers-reduced-motion: reduce)");
  const word=root.querySelector("[data-landing-type]"), words=["клиентов","заявки","просмотры"];
  let timer, wordIndex=0, position=words[0].length, deleting=true, observer;
  function tick() {
    if(document.hidden||motion.matches)return;
    const current=words[wordIndex];
    position+=deleting?-1:1;
    word.textContent=current.slice(0,Math.max(0,position));
    let delay=deleting?48:90;
    if(position===0){deleting=false;wordIndex=(wordIndex+1)%words.length;delay=240;}
    else if(position===current.length&&!deleting){deleting=true;delay=2200;}
    timer=setTimeout(tick,delay);
  }
  function resume() {
    clearTimeout(timer);
    if(motion.matches){wordIndex=0;position=words[0].length;deleting=true;word.textContent=words[0];return;}
    if(!document.hidden)timer=setTimeout(tick,1800);
  }
  if(!motion.matches&&typeof IntersectionObserver!=="undefined") {
    observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add("is-visible");observer.unobserve(entry.target);}}),{threshold:.12});
    root.querySelectorAll(".landing-reveal").forEach(el=>{el.classList.add("will-reveal");observer.observe(el);});
  }
  const click=event=>{
    const format=event.target.closest("[data-landing-format]"),step=event.target.closest("[data-landing-step]"),reset=event.target.closest("[data-landing-reset]");
    if(format&&LANDING_EXAMPLES[format.dataset.landingFormat]){
      landingFormat=format.dataset.landingFormat;
      root.querySelector("[data-landing-example]").innerHTML=landingExample();
      root.querySelector(`#example-tab-${landingFormat}`).focus({preventScroll:true});
      root.querySelector("[data-landing-workflow]").innerHTML=landingWorkflowPanel();
    }
    if(step){
      landingStep=Number(step.dataset.landingStep);
      root.querySelectorAll("[data-landing-step]").forEach(el=>{const active=Number(el.dataset.landingStep)===landingStep;el.setAttribute("aria-selected",String(active));el.tabIndex=active?0:-1;});
      const panel=root.querySelector("[data-landing-workflow]");panel.innerHTML=landingWorkflowPanel();panel.setAttribute("aria-labelledby",`workflow-tab-${landingStep}`);
    }
    if(reset){landingEdits[landingFormat]=null;root.querySelector("[data-landing-workflow]").innerHTML=landingWorkflowPanel();root.querySelector("[data-landing-edit]").focus({preventScroll:true});}
  };
  const input=event=>{if(event.target.matches("[data-landing-edit]")){landingEdits[landingFormat]=event.target.value;root.querySelector("[data-landing-edit-count]").textContent=`${Array.from(event.target.value).length} / 4000`;}};
  const keyboard=event=>{
    const current=event.target.closest('[role="tab"]');if(!current)return;
    const list=current.closest('[role="tablist"]'), tabs=Array.from(list.querySelectorAll('[role="tab"]')),index=tabs.indexOf(current);
    let next;
    if(["ArrowDown","ArrowRight"].includes(event.key))next=(index+1)%tabs.length;
    if(["ArrowUp","ArrowLeft"].includes(event.key))next=(index+tabs.length-1)%tabs.length;
    if(event.key==="Home")next=0;if(event.key==="End")next=tabs.length-1;
    if(next!==undefined){event.preventDefault();tabs[next].focus();tabs[next].click();}
  };
  root.addEventListener("click",click);root.addEventListener("input",input);root.addEventListener("keydown",keyboard);
  document.addEventListener("visibilitychange",resume);motion.addEventListener("change",resume);resume();
  // Restore a direct section link after the session bootstrap replaces the page.
  if(["#how-it-works","#pricing"].includes(location.hash))root.querySelector(location.hash)?.scrollIntoView({behavior:"instant"});
  landingEffectsCleanup=()=>{clearTimeout(timer);observer?.disconnect();root.removeEventListener("click",click);root.removeEventListener("input",input);root.removeEventListener("keydown",keyboard);document.removeEventListener("visibilitychange",resume);motion.removeEventListener("change",resume);};
}
