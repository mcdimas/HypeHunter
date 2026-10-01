/* Public demo: editorial examples and an explicitly selected snapshot of Nick Saraev’s public reels. No account API calls. */
const LANDING_REELS = [
  {
    "id": "3976687439442723344",
    "title": "Comment \"CODING\" to get these 4 plugins to level up your vibe coding.",
    "views": 682352,
    "likes": 13176,
    "comments": 9812,
    "url": "https://www.instagram.com/p/DcwCCgivcIQ/",
    "transcript": "Don't start vibe coding with Claude Code unless you've installed these four plugins. The first is Ponytail, which optimizes Claude Code's output and cuts your token usage by over 50% without losing you any accuracy at all. The second is OmniRoute, which gives Claude Code almost unlimited usage by connecting it to over 300 other free AI providers. So the moment that your usage limit runs out, it'll automatically switch you to the next best model and give you up to 1.6 billion free tokens every single month. The third is Graphify, which turns your entire codebase into a knowledge graph so your agent doesn't have to waste tokens by rereading files again and again. And finally, there's AgentSkills, which is a pack of 24 skills that let you vibe code like a real senior engineer built by the former AI engineering director at Google. It has dedicated skills for planning, coding, testing, and publishing, and it activates the right one at the specific stages of coding it needs all on its own. So if you want to try them all out for yourselves, just comment coding and I'll send the link to you directly."
  },
  {
    "id": "3989720162404130006",
    "title": "Comment \"CLAUDE\" to get this Free Tool to run Claude Code with almost unlimited usage.",
    "views": 270554,
    "likes": 6738,
    "comments": 11843,
    "url": "https://www.instagram.com/p/DdeVVlpT9zW/",
    "transcript": "You can now run Claude code completely free with almost unlimited usage. So somebody on GitHub just built an AI tool that gives you over 7 billion free AI tokens every single month. And that includes models from ChatGPT, Gemini, GLM, Kimi, Grok, Mistral, Quinn, and even more. It's called Free LLM API, and it links your Claude code to over 600 free AI models all through one really easy setup. So the moment your Claude limit runs out, it'll automatically switch you over to the next best model to keep your session going. Plus, it'll leave a note behind as it switches so the new model will already have all your contacts. Want to try it for yourselves? Just comment Claude down below and I'll send you the link directly."
  },
  {
    "id": "3975938982864010077",
    "title": "Comment \"CLAUDE\" to get this Free AI Scraper.",
    "views": 261610,
    "likes": 5320,
    "comments": 4248,
    "url": "https://www.instagram.com/p/DctX3CCPLtd/",
    "transcript": "This free AI tool lets you scrape anything off the internet without paying for anything. It's called ScrapeGraph AI and it's an open source Python library with over 30,000 stars on GitHub. You just give it a website link and describe what you want in plain English, and then a minute later it'll come back with a clean list of everything that you asked for. So with this you can find leads from LinkedIn, track your competitors or their ads, or do simple research. Plus it's free, open source, and works with Claude Code and all the other leading AI coding agents. So if you guys want to try this for yourselves, just comment Claude down below and I'll DM you the link directly."
  }
];
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
let landingPlanStage=0, landingPlanDate="", landingPlanText=null;
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

function landingReelDemo() {
  const winner=LANDING_REELS[0], number=value=>value==null?"—":new Intl.NumberFormat("ru-RU").format(value);
  return `<div class="workflow-compare" data-workflow-animation><div class="workflow-panel-heading"><h3>Найдите ролики, которые уже залетели</h3>${icon("sort-descending")}</div><p>Система отберёт лучшие в загруженной выборке — с метриками и полным транскриптом речи.</p><div class="workflow-reel-stage">${[LANDING_REELS[1],winner,LANDING_REELS[2]].map((reel,i)=>`<a class="workflow-reel ${i===1?'winner':''}" href="${reel.url}" target="_blank" rel="noopener noreferrer" aria-label="${escapeHtml(reel.title)} — ${number(reel.views)} просмотров">${i===1?'<span class="winner-badge">№1</span>':''}<img src="/ui/landing-assets/${reel.id}.jpg" width="180" height="240" alt="${escapeHtml(reel.title)}" /><span class="reel-views">${icon("play")}${number(reel.views)}</span></a>`).join("")}</div><div class="workflow-real-metrics"><span>${icon("eye")} ${number(winner.views)}</span><span>${icon("heart")} ${number(winner.likes)}</span><span>${icon("chat-circle")} ${number(winner.comments)}</span></div><details class="workflow-transcript"><summary>${icon("text-align-left")} Полный транскрипт ${icon("caret-down")}</summary><p lang="en">${escapeHtml(winner.transcript)}</p></details><p class="workflow-note">@nick_saraev · реальные показатели на момент загрузки. Лучшие среди загруженных роликов.</p></div>`;
}

function landingAdaptDemo() {
  const sample=LANDING_EXAMPLES[landingFormat];
  return `<div class="workflow-edit" data-workflow-animation><div class="workflow-panel-heading"><h3>Чужая идея. Ваш голос.</h3><img class="workflow-robot" src="/ui/landing-assets/robot-apple.png" width="40" height="40" alt="Робот" /></div><p>Нейросеть переведёт ролик и перепишет хук, скрипт и CTA под вашу нишу.</p><div class="workflow-niche">Ниша для примера: <strong>кофейня</strong></div><div class="workflow-rewrite"><span class="copy-label">Хук оригинала · EN</span><p lang="en"><span class="workflow-strike">${sample.original}</span></p><span class="copy-label workflow-your-hook">Твой хук · RU</span><p class="workflow-typed-hook" data-demo-type="${escapeHtml(sample.hook)}">${sample.hook}</p></div><div class="workflow-adapt-result"><div><span class="copy-label">Твой скрипт</span><p>${sample.script}</p></div><div><span class="copy-label">Твой CTA</span><p>${sample.cta}</p></div></div><details class="workflow-try-edit"><summary>Попробовать свою редакцию</summary><label for="landing-hook">Ваш хук<textarea id="landing-hook" rows="3" maxlength="4000" data-landing-edit>${escapeHtml(landingEdits[landingFormat]??sample.hook)}</textarea></label><div class="workflow-edit-footer"><span data-landing-edit-count>${Array.from(landingEdits[landingFormat]??sample.hook).length} / 4000</span><button class="text-link" type="button" data-landing-reset>Вернуть пример</button></div></details></div>`;
}

function landingPlanDemo() {
  const sample=LANDING_EXAMPLES.threads, text=landingPlanText??[sample.hook,sample.script,sample.cta].join("\n\n");
  return `<div class="workflow-plan"><div class="workflow-panel-heading"><h3>От идеи до готового Threads</h3>${icon("chats-circle")}</div><p>Пройдите путь сами — нажимайте на этапы и подготовьте свой пост.</p><div class="workflow-plan-lanes" aria-label="Этапы подготовки Threads">${["Идеи","В работе","Готово"].map((label,i)=>`<button type="button" class="${landingPlanStage===i?'active':''}" data-plan-stage="${i}" aria-pressed="${landingPlanStage===i}">${label}</button>`).join("")}</div><article class="workflow-draft"><span class="format-label">${icon("chats-circle")}Threads</span><h4>${sample.draft}</h4>${landingPlanStage===0?`<p>Один вопрос гостя — идея для полезного поста вашей кофейни.</p><button type="button" class="button primary" data-plan-stage="1">Взять в работу ${icon("arrow-right")}</button>`:landingPlanStage===1?`<label class="copy-label" for="landing-thread-draft">Доработайте текст</label><textarea id="landing-thread-draft" data-plan-text rows="5" maxlength="4000">${escapeHtml(text)}</textarea><label class="workflow-date" for="landing-thread-date">Дата публикации<input id="landing-thread-date" data-plan-date type="date" value="${escapeHtml(landingPlanDate)}" /></label><button type="button" class="button primary" data-plan-stage="2">Готово к публикации ${icon("check")}</button>`: `<span class="workflow-ready">${icon("check-circle")} Пост готов</span><p class="workflow-ready-text">${escapeHtml(text)}</p><p>${landingPlanDate?'Запланировано: '+escapeHtml(landingPlanDate.split('-').reverse().join('.')):'Можно публиковать в удобное время'}</p><button type="button" class="text-link" data-plan-stage="1">Вернуться к тексту</button>`}</article><p class="workflow-note" aria-live="polite">${["Шаг 1 из 3 · Сохраните идею для поста.","Шаг 2 из 3 · Отредактируйте текст и выберите дату.","Шаг 3 из 3 · Готово! Опубликуйте пост вручную в Threads." ][landingPlanStage]} Это демо: изменения не сохраняются в аккаунт.</p></div>`;
}

function landingWorkflowPanel() {
  return [
    () => `<div class="workflow-source" data-workflow-animation><div class="workflow-source-icon">${icon("users")}</div><h3>Начните с одного аккаунта</h3><p>Добавьте ссылку на Instagram или Threads из вашей ниши.</p><div class="workflow-profile" aria-label="Пример ссылки: instagram.com/nick_saraev">${icon("link")}<span class="workflow-profile-text" data-demo-url aria-hidden="true">instagram.com/nick_saraev</span>${icon("plus")}</div><div class="workflow-formats">${icon("instagram-logo")} Instagram Reels <span></span>${icon("chats-circle")} Threads</div><p class="workflow-note">До 20 последних материалов за одну загрузку.</p></div>`,
    landingReelDemo, landingAdaptDemo, landingPlanDemo
  ][landingStep]();
}

function landingPage() {
  document.title="Hype Hunter | Идеи, сценарии и контент-план для Reels и Threads";
  return `<div class="landing">
    <header class="landing-header"><div class="landing-container landing-nav">${publicBrand()}<nav aria-label="Навигация лендинга"><a href="#how-it-works">Как это работает</a><a href="#pricing">Тарифы</a></nav><div class="landing-nav-actions"><a class="landing-signin" href="${state.user?"/account":"/login"}" data-route>${state.user?"Кабинет":"Войти"}</a>${landingConnect("primary",false)}</div></div></header>
    <main id="main-content">
      <section class="landing-hero landing-container"><h1 aria-label="Получайте клиентов, заявки и просмотры из Reels и Threads"><span aria-hidden="true"><span class="landing-title-line"><span class="landing-title-prefix">Получайте</span><span class="landing-type-slot"><span data-landing-type>клиентов</span><span class="landing-caret"></span></span></span><span class="landing-title-tail">из Reels и Threads</span></span></h1><p class="landing-lead">Автоматизируйте рутину продюсера стоимостью <strong>от 80 000 ₽ в месяц:</strong> поиск идей, перевод и подготовку текстов.</p><div class="landing-hero-actions">${landingConnect()}<a class="button secondary" href="#how-it-works">Как это работает</a><a class="button secondary" href="https://github.com/mcdimas/HypeHunter" target="_blank" rel="noopener noreferrer">${icon("github-logo")}GitHub</a></div>
      <p class="landing-free-note">5 роликов бесплатно после регистрации · карта не нужна</p><section class="landing-example" aria-label="Пример Reels и Threads" data-landing-example>${landingExample()}</section></section>
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
  let demoTimer, demoFrame=0;
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
  function demoTick() {
    clearTimeout(demoTimer);
    const panel=root.querySelectorAll("[data-workflow-animation]")[0];
    if(!panel)return;
    panel.style.animationPlayState=document.hidden?"paused":"running";
    panel.querySelectorAll("*").forEach(el=>el.style.animationPlayState=document.hidden?"paused":"running");
    const url=panel.querySelector("[data-demo-url]"), hook=panel.querySelector("[data-demo-type]");
    if(motion.matches){if(url)url.textContent="instagram.com/nick_saraev";if(hook)hook.textContent=hook.dataset.demoType;return;}
    if(document.hidden)return;
    if(url){const value="instagram.com/nick_saraev",phase=demoFrame%110;url.textContent=value.slice(0,phase<value.length?phase:phase<72?value.length:Math.max(0,value.length-(phase-72)));}
    if(hook){const value=hook.dataset.demoType,phase=demoFrame%190;hook.textContent=value.slice(0,Math.max(0,phase-27));}
    demoFrame++;demoTimer=setTimeout(demoTick,65);
  }
  function refreshDemo(){demoFrame=0;demoTick();}
  function resume() {
    clearTimeout(timer);
    demoTick();
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
    const plan=event.target.closest("[data-plan-stage]");
    if(plan){landingPlanStage=Number(plan.dataset.planStage);root.querySelector("[data-landing-workflow]").innerHTML=landingWorkflowPanel();root.querySelector('.workflow-plan-lanes [data-plan-stage="'+landingPlanStage+'"]').focus({preventScroll:true});}
    if(format||step)refreshDemo();
    if(reset){landingEdits[landingFormat]=null;root.querySelector("[data-landing-workflow]").innerHTML=landingWorkflowPanel();root.querySelector(".workflow-try-edit").open=true;root.querySelector("[data-landing-edit]").focus({preventScroll:true});refreshDemo();}
  };
  const input=event=>{if(event.target.matches("[data-plan-text]"))landingPlanText=event.target.value;if(event.target.matches("[data-plan-date]"))landingPlanDate=event.target.value;if(event.target.matches("[data-landing-edit]")){landingEdits[landingFormat]=event.target.value;root.querySelector("[data-landing-edit-count]").textContent=`${Array.from(event.target.value).length} / 4000`;}};
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
  landingEffectsCleanup=()=>{clearTimeout(demoTimer);clearTimeout(timer);observer?.disconnect();root.removeEventListener("click",click);root.removeEventListener("input",input);root.removeEventListener("keydown",keyboard);document.removeEventListener("visibilitychange",resume);motion.removeEventListener("change",resume);};
}
