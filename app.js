const app = document.querySelector("#app");
const toastRegion = document.querySelector("#toast-region");
const state = {
  route: normalizeRoute(location.pathname), tab: "reels", query: "", competitorId: "all", period: "all", sort: "newest", libraryView: "list", page: 1, pageSize: 12, pageCount: 1,
  reels: [], reelTotal: 0, sourceTotal: 0, competitors: [], imports: [], translations: null, remixes: [], activeRemix: null,
  loadingReels: false, loadingEditor: false, error: "", mobileNav: false, openMenu: null, dialog: null,
  importing: false, refreshingId: null, cancellingImportId: null, competitorValue: "", competitorError: "", importPlatform: "reels", importLimit: 20,
  planView: "board", planFormat: "all", planQuery: "", calendarWeek: weekStart(), dirty: false, saveError: "", editorReturn: restoredReturnPath(),
  user: null, csrf: "", authChallenge: null, authStatus: "", authError: "", authBusy: false, sessions: [], emailLogin: null,
  profileName: null, profileBusy: false, photoBusy: false, profileError: "", profileSaved: ""
};
let searchTimer, draftTimer, importPollTimer, authPollTimer, savePromise, authPollInFlight;
let requestId = 0, routeRequestId = 0, accountVersion = 0, loginAttempt = 0, draftRevision = 0;
function cancelledRequest() { return new DOMException("", "AbortError"); }
function restoredReturnPath() { try { const id=sessionStorage.getItem("auth-user-id"), value=sessionStorage.getItem(`editor-return:${id}`); return value && /^\/(library|content-plan)(\?|$)/.test(value) ? value : "/content-plan"; } catch { return "/content-plan"; } }
function recoveryKey(slug) { return `draft:${state.user?.id}:${slug}`; }
function clearAccountMemory() {
  state.emailLogin=null;state.trial=null;
  clearTimeout(importPollTimer);clearTimeout(authPollTimer);clearTimeout(draftTimer);clearTimeout(searchTimer);
  accountVersion++;requestId++;routeRequestId++;loginAttempt++;
  toastRegion.replaceChildren();
  Object.assign(state,{user:null,reels:[],reelTotal:0,sourceTotal:0,competitors:[],imports:[],translations:null,remixes:[],activeRemix:null,sessions:[],dirty:false,authChallenge:null,authStatus:"",authError:"",authBusy:false,error:"",saveError:"",loadingReels:false,loadingEditor:false,mobileNav:false,dialog:null,openMenu:null,profileName:null,profileError:"",profileSaved:"",profileBusy:false,photoBusy:false,importing:false,refreshingId:null,cancellingImportId:null,competitorValue:"",competitorError:""});
  try { for(const key of Object.keys(sessionStorage))if(key.startsWith("draft:")||key.startsWith("editor-return:")||key==="auth-user-id")sessionStorage.removeItem(key); } catch {}
}
function normalizeRoute(path) {
  if (path.startsWith("/remixes/")) return path;
  return ["/today","/login","/library","/competitors","/content-plan","/account"].includes(path) ? path : "/";
}
function escapeHtml(value) { return String(value ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;"); }
function icon(name, cls="") { return `<i class="ph ph-${name} ${cls}" aria-hidden="true"></i>`; }
async function apiRequest(path, options={}) {
  const version=accountVersion;
  const method=(options.method||"GET").toUpperCase();
  const response = await fetch(`/api${path}`, { ...options, headers: { Accept:"application/json", ...(options.body?{"Content-Type":"application/json"}:{}), ...(!["GET","HEAD"].includes(method)&&state.csrf?{"X-CSRF-Token":state.csrf}:{}), ...options.headers } });
  if(version!==accountVersion)throw cancelledRequest();
  if (!response.ok) {
    let message = `Ошибка запроса (${response.status})`;
    try { const p = await response.json(); message = typeof p.detail==="string" ? p.detail : p.detail?.map?.(e=>`${e.loc?.at(-1)}: ${e.msg}`).join("; ") || message; } catch {}
    if(version!==accountVersion)throw cancelledRequest();
    const error=new Error(message);error.status=response.status;throw error;
  }
  const data=response.status===204 ? null : await response.json();
  if(version!==accountVersion)throw cancelledRequest();
  return data;
}
function formatViews(v) { return v>=1e6?`${(v/1e6).toLocaleString("ru-RU",{maximumFractionDigits:1})} млн`:v>=1e3?`${(v/1e3).toLocaleString("ru-RU",{maximumFractionDigits:1})} тыс.`:String(v??"н/д"); }
function materialCount(n) { const f = new Intl.PluralRules("ru").select(n); return `${n} ${{one:"материал",few:"материала",many:"материалов",other:"материала"}[f]}`; }
function formatCount(v) { return v==null?"нет данных":Number(v).toLocaleString("ru-RU"); }
function formatDuration(v) { return `${Math.floor(v/60)}:${String(v%60).padStart(2,"0")}`; }
function formatAdded(v) { return v?new Date(v).toLocaleDateString("ru-RU",{timeZone:PROJECT_ZONE,day:"numeric",month:"short",year:"numeric"}):"Дата неизвестна"; }
function formatDateTime(v) { return v?new Date(v).toLocaleString("ru-RU",{timeZone:PROJECT_ZONE,day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"}):"Нет даты"; }
function importStatusLabel(s) { return ({completed:"Завершено",queued:"В очереди",running:"Загрузка",waiting_for_token:"Нужен токен Apify",failed:"Ошибка",cancelled:"Остановлено",partial:"Частичный результат"})[s]||s; }
function translationErrorSummary(s) { return /region|territory|403/i.test(s||"")?"Сервис перевода недоступен из региона сервера. Оригиналы сохранены.":s||"Перевод ещё не получен"; }
function avatarMarkup(c) { return `<span class="avatar"><span>${escapeHtml((c.handle||"").replace("@","").slice(0,2).toUpperCase())}</span>${c.avatar_url?`<img src="${safeUrl(c.avatar_url)}" alt="" data-avatar-image loading="lazy" />`:""}</span>`; }
function libraryURL() {
  return "/library?"+new URLSearchParams({tab:state.tab,q:state.query,competitor:state.competitorId,period:state.period,sort:state.sort,view:state.libraryView,page:state.page});
}
function readRouteQuery() {
  const p=new URLSearchParams(location.search);
  if(state.route==="/library"){
    state.tab=p.get("tab")==="threads"?"threads":"reels"; state.query=p.get("q")||""; state.competitorId=p.get("competitor")||"all";
    state.period=["7","30","90"].includes(p.get("period"))?p.get("period"):"all";
    state.sort=["newest","oldest","views","likes","comments","shares"].includes(p.get("sort"))?p.get("sort"):"newest";
    state.libraryView=p.get("view")==="grid"?"grid":"list"; state.page=Math.max(1,Number(p.get("page"))||1);
  }
  if(state.route==="/content-plan"){state.planView=p.get("view")==="calendar"?"calendar":"board";state.planFormat=["reels","threads"].includes(p.get("format"))?p.get("format"):"all";state.planQuery=p.get("q")||"";const week=p.get("week");state.calendarWeek=week && /^\d{4}-\d{2}-\d{2}$/.test(week) && !Number.isNaN(Date.parse(week))?weekStart(week):weekStart();}
}
function navLink(path,label,i) { return `<a href="${path}" class="nav-link ${(state.route.startsWith("/remixes/")?new URL(state.editorReturn,location.origin).pathname:state.route)===path.split("?")[0]?"active":""}" data-route>${icon(i)}${label}</a>`; }
function sidebar() { return `<button class="mobile-overlay" data-action="close-nav" aria-label="Закрыть навигацию"></button><aside class="sidebar" ${matchMedia("(max-width:680px)").matches&&!state.mobileNav?"inert":""}><a class="brand" href="/today" data-route><span class="brand-mark">${icon("target")}</span>HYPE HUNTER</a><p class="studio-label">Моя студия</p><nav aria-label="Основная навигация">${navLink("/today","Сегодня","house")}${navLink(libraryURL(),"Библиотека","video")}${navLink("/content-plan","Контент-план","calendar-blank")}<span class="nav-label">Источники</span>${navLink("/competitors","Конкуренты","users")}</nav><div class="sidebar-foot"><a href="/account" data-route aria-label="Профиль: ${escapeHtml(state.user?.display_name||"Аккаунт")}" ${state.route==="/account"?'aria-current="page"':''}>${userAvatar("sidebar-avatar")}<span>${escapeHtml(state.user?.display_name||"Аккаунт")}<small>Личный кабинет</small></span>${icon("caret-right")}</a></div></aside>`; }
function dialogMarkup() {
  const d=state.dialog; if(!d)return"";
  return `<div class="dialog-backdrop"><section class="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><button class="icon-button dialog-close" data-action="close-dialog" aria-label="Закрыть">${icon("x")}</button><h2 id="dialog-title">${escapeHtml(d.title)}</h2><p class="dialog-text">${escapeHtml(d.text)}</p><div class="dialog-actions"><button class="button secondary" data-action="close-dialog">${d.confirmAction?"Отмена":"Закрыть"}</button>${d.confirmAction?`<button class="button ${d.destructive?"danger":"primary"}" data-action="${d.confirmAction}">${escapeHtml(d.confirmLabel||"Подтвердить")}</button>`:""}</div></section></div>`;
}
function shell(content,cls="") { return `<div class="app-shell ${state.mobileNav?"nav-open":""}"><header class="mobile-bar"><a href="/today" data-route>Hype Hunter</a><button class="icon-button" data-action="toggle-nav" aria-label="Меню" aria-expanded="${state.mobileNav}">${icon("list")}</button></header>${sidebar()}<main id="main-content" class="workspace ${cls}">${content}</main>${dialogMarkup()}</div>`; }
function render() {
  stopLandingEffects();
  app.innerHTML=state.route==="/"?landingPage():!state.user?loginPage():state.error?shell(`<div class="empty-state"><h1>Не удалось загрузить данные</h1><p>${escapeHtml(state.error)}</p><button class="button primary" data-action="retry">Повторить</button></div>`):
    state.route==="/account"?accountPage():state.route==="/competitors"?competitorsPage():state.route==="/content-plan"?contentPlanPage():state.route.startsWith("/remixes/")?editorPage():state.route==="/library"?homePage():todayPage();
  autoSizeTextareas();
  if(state.route==="/")mountLanding();
  if(state.dialog)app.querySelector(".dialog-close")?.focus();
}
function autoSizeTextareas(root=app) { root.querySelectorAll("textarea[data-autogrow]").forEach(el=>{el.style.height="auto";el.style.height=`${Math.max(el.scrollHeight,el.id==="draft-title"?40:80)}px`;}); }
function showToast(message,kind="success") { if(!message)return;const el=document.createElement("div");el.className=`toast ${kind}`;el.textContent=message;toastRegion.replaceChildren(el);setTimeout(()=>el.remove(),5000); }
async function loadReels({quiet=false}={}) {
  if(state.route!=="/library"||!state.user)return;
  const id=++requestId;state.loadingReels=true;
  if(state.route==="/library")history.replaceState({},"",libraryURL());
  if(!quiet)render();
  const p=new URLSearchParams({page:state.page,page_size:state.pageSize,platform:state.tab,period:state.period,sort:state.sort});
  if(state.query.trim())p.set("q",state.query.trim());if(state.competitorId!=="all")p.set("competitor_id",state.competitorId);
  try{const data=await apiRequest(`/reels?${p}`);if(id!==requestId)return;Object.assign(state,{reels:data.items,reelTotal:data.total,pageCount:data.page_count,page:data.page});if(state.route==="/library")history.replaceState({},"",libraryURL());const counter=app.querySelector("[data-library-count]");if(counter)counter.textContent=materialCount(state.reelTotal);}
  finally{if(id===requestId){state.loadingReels=false;if(quiet&&app.querySelector("[data-home-results]"))app.querySelector("[data-home-results]").innerHTML=homeResults();else render();}}
}
async function loadRemixes(){state.remixes=await apiRequest("/remixes");}
async function loadCompetitors(){const [competitors,trial]=await Promise.all([apiRequest("/competitors"),apiRequest("/trial")]);state.competitors=competitors;state.trial=trial;}
async function loadImports(){state.imports=await apiRequest("/imports");}
async function loadTranslations(){state.translations=await apiRequest("/translations");}
function scheduleImportPolling(){
  clearTimeout(importPollTimer);
  if(state.route!=="/competitors")return;
  importPollTimer=setTimeout(async()=>{
    try{await Promise.all([loadCompetitors(),loadImports(),loadTranslations()]);if(state.route!=="/competitors")return;
      for(const [selector,fn] of [["[data-trial-summary]",trialMarkup],["[data-import-tracker]",progressMarkup],["[data-competitors-body]",competitorRows],["[data-imports-body]",importRows],["[data-translation-tracker]",translationMarkup]]){
        const el=app.querySelector(selector);if(el && !el.contains(document.activeElement) && !el.querySelector("details[open]"))el.innerHTML=fn();
      }
    }catch(e){showToast(e.message,"error");}finally{if(state.route==="/competitors")scheduleImportPolling();}
  },4000);
}
async function loadRouteData(){
  const id=++routeRequestId;
  requestId++;clearTimeout(searchTimer);
  state.error="";clearTimeout(importPollTimer);
  routeAccess();
  if(state.route!=="/login"){loginAttempt++;clearTimeout(authPollTimer);state.authChallenge=null;state.emailLogin=null;state.authStatus="";state.authBusy=false;}
  if(state.route==="/"||!state.user){render();return;}
  if(state.route==="/account"){const sessions=await apiRequest("/auth/sessions");if(id!==routeRequestId)return;state.sessions=sessions;render();}
  else if(state.route==="/library")await loadReels();
  else if(state.route==="/competitors"){await Promise.all([loadCompetitors(),loadImports(),loadTranslations()]);if(id!==routeRequestId)return;render();scheduleImportPolling();}
  else if(state.route==="/content-plan"){await loadRemixes();if(id!==routeRequestId)return;render();}
  else if(state.route.startsWith("/remixes/")){
    state.loadingEditor=true;render();
    const remix=await apiRequest(`/remixes/${encodeURIComponent(decodeURIComponent(state.route.slice(9)))}`);
    if(id!==routeRequestId)return;
    state.activeRemix=remix;
    state.loadingEditor=false;state.dirty=false;state.saveError="";
    try{const recovery=JSON.parse(sessionStorage.getItem(recoveryKey(state.activeRemix.slug))||"null");
      if(recovery){Object.assign(state.activeRemix,recovery.fields);state.dirty=true;state.saveError="Восстановлен несохранённый текст. Нажмите «Сохранить».";}}
    catch{}
    render();
  }else{const [r]=await Promise.all([apiRequest("/reels?page=1&page_size=4&sort=newest"),loadRemixes()]);if(id!==routeRequestId)return;state.reels=r.items;state.sourceTotal=r.total;render();}
}
async function navigate(path,replace=false){
  if(state.dirty&&!await saveActiveRemix({toast:false}))return;
  const url=new URL(path,location.origin);
  if(url.origin!==location.origin)return;
  if(state.route==="/login"&&url.pathname!=="/login"){clearTimeout(authPollTimer);state.authChallenge=null;state.authStatus="";}
  if(!state.route.startsWith("/remixes/")&&url.pathname.startsWith("/remixes/")){state.editorReturn=location.pathname+location.search;try{sessionStorage.setItem(`editor-return:${state.user.id}`,state.editorReturn);}catch{}}
  history[replace?"replaceState":"pushState"]({},"",url.pathname+url.search);
  state.route=normalizeRoute(url.pathname);state.openMenu=null;state.dialog=null;state.mobileNav=false;readRouteQuery();
  await loadRouteData();window.scrollTo(0,0);
}
const editableFields=["title","brief","hook","script","cta","thread_text"];
function keepRecovery(){if(!state.activeRemix)return;try{sessionStorage.setItem(recoveryKey(state.activeRemix.slug),JSON.stringify({fields:Object.fromEntries(editableFields.map(k=>[k,state.activeRemix[k]]))}));}catch{}}
function saveLabel(text,error=false){const el=app.querySelector("[data-save-status]");if(el){el.textContent=text;el.className=error?"form-error":text==="Сохранено"?"save-success":"muted";}}
async function saveActiveRemix({toast=true}={}){
  clearTimeout(draftTimer);
  if(savePromise){await savePromise;if(state.dirty)return saveActiveRemix({toast});return !state.saveError;}
  if(!state.activeRemix)return true;
  if(!state.dirty){if(toast)showToast("Черновик сохранён в контент-плане");return true;}
  const r=state.activeRemix,revision=draftRevision;
  const fields=Object.fromEntries(editableFields.map(k=>[k,r[k]]));
  const limits={title:255,brief:4000,hook:4000,script:12000,cta:4000,thread_text:500};
  const names={title:"Название",brief:"Идея",hook:"Хук",script:"Сценарий",cta:"CTA",thread_text:"Текст Threads"};
  const tooLong=editableFields.find(key=>Array.from(fields[key]||"").length>limits[key]);
  if(!fields.title.trim()||tooLong){
    state.saveError=tooLong?`${names[tooLong]}: максимум ${limits[tooLong]} символов. Сократите текст, чтобы сохранить.`:"Введите название публикации";
    keepRecovery();saveLabel(state.saveError,true);return false;
  }
  saveLabel("Сохраняется…");
  savePromise=(async()=>{
    try{
      const saved=await apiRequest(`/remixes/${encodeURIComponent(r.slug)}`,{method:"PATCH",body:JSON.stringify({...fields,expected_updated_at:r.updated_at})});
      if(state.activeRemix?.slug===r.slug){
        state.activeRemix=revision===draftRevision?saved:{...saved,...Object.fromEntries(editableFields.map(k=>[k,state.activeRemix[k]]))};
        state.dirty=revision!==draftRevision;state.saveError="";
        if(!state.dirty){try{sessionStorage.removeItem(recoveryKey(r.slug));}catch{}}
        saveLabel(state.dirty?"Есть несохранённые изменения":"Сохранено");
      }
      if(toast)showToast("Черновик сохранён в контент-плане");return true;
    }catch(e){if(e.name==="AbortError")return false;state.saveError=`Не удалось сохранить: ${e.message}`;keepRecovery();saveLabel(state.saveError,true);if(toast)showToast(state.saveError,"error");return false;}
  })();
  const ok=await savePromise;savePromise=null;return ok;
}
async function updatePlan(slug,changes){
  if(state.activeRemix?.slug===slug && !await saveActiveRemix({toast:false}))return;
  const existing=state.activeRemix?.slug===slug?state.activeRemix:state.remixes.find(r=>r.slug===slug);
  const saved=await apiRequest(`/remixes/${encodeURIComponent(slug)}`,{method:"PATCH",body:JSON.stringify({...changes,expected_updated_at:existing?.updated_at})});
  if(state.activeRemix?.slug===slug)state.activeRemix=saved;
  state.remixes=state.remixes.map(r=>r.slug===slug?saved:r);render();return saved;
}
function openDialog(value){state.openMenu=null;state.dialog=value;render();}
async function derivedDraft(format){
  if(!await saveActiveRemix({toast:false}))return;
  const r=state.activeRemix;
  if(format==="threads"&&!r.thread_text.trim())throw new Error("Сначала подготовьте текст Threads");
  const draft=await apiRequest(`/remixes/${r.slug}/derive`,{method:"POST",body:JSON.stringify({format})});
  await navigate(`/remixes/${draft.slug}`);
}
async function editorOperation(operation){
  if(!await saveActiveRemix({toast:false}))return;
  state.activeRemix=await apiRequest(`/remixes/${state.activeRemix.slug}/${operation}?confirm=true`,{method:"POST"});
  state.dialog=null;render();showToast(operation==="rewrite"?"Исходный перевод восстановлен":"Текст подготовлен — проверьте и отредактируйте его");
}
app.addEventListener("click",async event=>{
  const target=event.target.closest("button,a");if(!target)return;
  try{
    if(target.matches("[data-route]")){if(event.ctrlKey||event.metaKey||event.shiftKey)return;event.preventDefault();await navigate(target.href);return;}
    if(!state.user){
      if(target.dataset.action==="begin-telegram"||target.dataset.action==="restart-login")await beginTelegramLogin();
      if(target.dataset.action==="begin-yandex")await beginYandexLogin();
      if(target.dataset.action==="begin-email"){loginAttempt++;clearTimeout(authPollTimer);state.authChallenge=null;state.authError="";state.emailLogin={email:""};render();app.querySelector('#email-login-input')?.focus();}
      if(target.dataset.action==="cancel-email"){loginAttempt++;state.emailLogin=null;state.authError="";render();}
      if(target.dataset.action==="change-email"){state.emailLogin={email:state.emailLogin?.email||""};state.authError="";render();app.querySelector('#email-login-input')?.focus();}
      if(target.dataset.action==="resend-email")await submitEmailLogin(null,true);
      if(target.dataset.action==="copy-telegram-command"){
        const field=app.querySelector("#telegram-start-command");
        if(field){try{await navigator.clipboard.writeText(field.value);showToast("Команда скопирована. Отправьте её боту в Telegram.");}catch{field.focus();field.select();showToast("Скопируйте выделенную команду и отправьте её боту.");}}
      }
      return;
    }
    if(target.dataset.menu){state.openMenu=state.openMenu===target.dataset.menu?null:target.dataset.menu;render();return;}
    if(target.dataset.tab){state.tab=target.dataset.tab;state.page=1;state.competitorId="all";state.sort="newest";await loadReels();return;}
    if(target.dataset.page){state.page=Number(target.dataset.page);await loadReels();return;}
    if(target.dataset.libraryView){state.libraryView=target.dataset.libraryView;history.replaceState({},"",libraryURL());render();return;}
    if(target.dataset.planView){state.planView=target.dataset.planView;history.replaceState({},"",planURL());render();return;}
    if(target.dataset.planFormatTab){state.planFormat=target.dataset.planFormatTab;history.replaceState({},"",planURL());render();return;}
    if(target.dataset.importPlatformTab){state.importPlatform=target.dataset.importPlatformTab;render();return;}
    const action=target.dataset.action;
    if(action==="link-yandex"){await beginYandexLogin("link");return;}
    if(action==="toggle-nav"||action==="close-nav"){state.mobileNav=action==="toggle-nav"?!state.mobileNav:false;render();}
    else if(action==="logout"||action==="logout-all"){
      await apiRequest(action==="logout"?"/auth/logout":"/auth/logout-all",{method:"POST"});
      clearAccountMemory();history.replaceState({},"","/login");state.route="/login";render();
    }
    else if(action==="revoke-session"){
      await apiRequest(`/auth/sessions/${target.dataset.sessionId}/revoke`,{method:"POST"});
      if(Number(target.dataset.sessionId)===state.user.session_id){clearAccountMemory();history.replaceState({},"","/login");state.route="/login";render();}
      else{state.sessions=await apiRequest("/auth/sessions");render();}
    }
    else if(action==="remove-avatar"){
      const saved=await apiRequest("/auth/profile/avatar",{method:"DELETE"});state.user.avatar_path=saved.avatar_path;state.profileSaved="Фото убрано";state.profileError="";render();
    }
    else if(action==="copy-account-id"){
      try{await navigator.clipboard.writeText(String(state.user.id));showToast("ID аккаунта скопирован");}catch{showToast(`Ваш ID: ${state.user.id}`);}
    }
    else if(action==="close-dialog"){state.dialog=null;render();}
    else if(action==="retry"){await bootstrap();}
    else if(action==="new-remix"||action==="remix"){
      const r=await apiRequest("/remixes",{method:"POST",body:JSON.stringify(action==="remix"?{source_reel_id:Number(target.dataset.reelId)}:{title:"Новая идея",format:state.route==="/content-plan"&&state.planFormat==="threads"?"threads":"reels"})});if(target.dataset.date){await apiRequest(`/remixes/${r.slug}`,{method:"PATCH",body:JSON.stringify({scheduled_at:plannedISO(`${target.dataset.date}T12:00`),expected_updated_at:r.updated_at})});}await navigate(`/remixes/${r.slug}`);
    }
    else if(action==="view-reel-text"||action==="view-translation-error"){
      const r=state.reels.find(r=>r.id===Number(target.dataset.reelId));openDialog({title:action==="view-reel-text"?r?.title:"Состояние перевода",text:action==="view-reel-text"?(r?.original_script||r?.caption||"Нет текста"):(r?.translation_status==="completed"?"Перевод готов":translationErrorSummary(r?.translation_error))});
    }
    else if(action==="delete-reel"||action==="delete-competitor"||action==="delete-draft"){
      const kind=action.slice(7),id=target.dataset.reelId||target.dataset.competitorId||target.dataset.slug;
      openDialog({title:kind==="draft"?"Удалить собственный черновик?":"Удалить источник?",text:kind==="draft"?"Текст и план этой публикации будут удалены. Оригинал конкурента останется.":"Источник и его загруженные материалы будут удалены. Ваши черновики останутся, но потеряют связь с оригиналом.",confirmAction:"confirm-delete",confirmLabel:"Удалить",destructive:true,kind,id});
    }
    else if(action==="confirm-delete"){
      const {kind,id}=state.dialog;
      await apiRequest(`/${kind==="draft"?"remixes":kind==="reel"?"reels":"competitors"}/${encodeURIComponent(id)}`,{method:"DELETE"});
      state.dialog=null;await Promise.all([loadCompetitors(),loadRemixes()]);await loadRouteData();showToast("Удалено");
    }
    else if(action==="open-reels"){
      const c=state.competitors.find(c=>c.id===Number(target.dataset.competitorId));
      state.tab=c.platform;state.competitorId=String(c.id);state.page=1;state.query="";state.period="all";await navigate(libraryURL());
    }
    else if(action==="refresh"){
      state.refreshingId=Number(target.dataset.competitorId);render();
      await apiRequest("/imports",{method:"POST",body:JSON.stringify({competitor_id:state.refreshingId,requested_count:state.importLimit})});
      state.refreshingId=null;await loadImports();render();scheduleImportPolling();showToast("Загрузка поставлена в очередь");
    }
    else if(action==="cancel-import"){state.cancellingImportId=Number(target.dataset.importId);render();try{await apiRequest(`/imports/${target.dataset.importId}/cancel`,{method:"POST"});await loadImports();showToast("Импорт остановлен. Сохранённые материалы остаются.");}finally{state.cancellingImportId=null;render();}}
    else if(action==="pause-profile"){await apiRequest(`/competitors/${target.dataset.competitorId}`,{method:"PATCH",body:JSON.stringify({is_active:target.dataset.active!=="true"})});await loadCompetitors();state.openMenu=null;render();}
    else if(action==="save-remix")await saveActiveRemix();
    else if(action==="clear-date")await updatePlan(state.activeRemix.slug,{scheduled_at:null});
    else if(action==="rewrite"||action==="prepare-thread"){
      openDialog({title:action==="rewrite"?"Вернуть исходный перевод?":"Подготовить текст для Threads?",text:action==="rewrite"?"Ваши текущие хук, сценарий и CTA будут заменены переводом источника. Текст Threads не изменится.":"Текст в правой колонке будет заменён фрагментом вашей текущей редакции длиной до 500 символов. Публикация в соцсети не выполняется.",confirmAction:action==="rewrite"?"confirm-rewrite":"confirm-prepare",confirmLabel:action==="rewrite"?"Вернуть перевод":"Подготовить"});
    }
    else if(action==="confirm-rewrite")await editorOperation("rewrite");
    else if(action==="confirm-prepare")await editorOperation("prepare-thread");
    else if(action==="derive-threads"||action==="derive-reels")await derivedDraft(action.slice(7));
    else if(["previous-week","next-week","current-week"].includes(action)){
      state.calendarWeek=action==="current-week"?weekStart():shiftDay(state.calendarWeek,action==="next-week"?7:-7);history.replaceState({},"",planURL());render();
    }
  }catch(e){state.importing=false;state.refreshingId=null;showToast(e.message,"error");}
});
app.addEventListener("input",event=>{
  const el=event.target;
  if(el.matches("[data-search]")){state.query=el.value;state.page=1;clearTimeout(searchTimer);searchTimer=setTimeout(()=>loadReels({quiet:true}).catch(e=>showToast(e.message,"error")),300);}
  else if(el.matches("[data-plan-search]")){state.planQuery=el.value;history.replaceState({},"",planURL());app.querySelector("[data-plan-results]").innerHTML=state.planView==="calendar"?calendarMarkup(planItems()):boardMarkup(planItems());}
  else if(el.id==="instagram-account")state.competitorValue=el.value;
  else if(el.id==="profile-name"){state.profileName=el.value;state.profileSaved="";state.profileError="";const message=app.querySelector("[data-profile-message]");if(message)message.textContent="";}
  else if(el.dataset.draftField&&state.activeRemix){
    state.activeRemix[el.dataset.draftField]=el.value;draftRevision++;state.dirty=true;state.saveError="";keepRecovery();saveLabel("Есть несохранённые изменения");
    if(el.dataset.draftField==="thread_text"){const count=app.querySelector("[data-character-count]");count.textContent=`${Array.from(el.value).length}/500`;count.classList.toggle("form-error",Array.from(el.value).length>500);}
    autoSizeTextareas(el.parentElement);clearTimeout(draftTimer);draftTimer=setTimeout(()=>saveActiveRemix({toast:false}),800);
  }
});
app.addEventListener("change",async event=>{
  const el=event.target;
  try{
    if(el.matches("[data-profile-photo]")){await uploadProfilePhoto(el.files?.[0]);return;}
    if(el.matches("[data-source-filter],[data-library-period],[data-library-sort]")){
      const key=el.matches("[data-source-filter]")?"competitorId":el.matches("[data-library-period]")?"period":"sort";state[key]=el.value;state.page=1;await loadReels();
    }else if(el.matches("[data-import-limit]"))state.importLimit=Number(el.value);
    else if(el.dataset.remixStatus)await updatePlan(el.dataset.remixStatus,{status:el.value});
    else if(el.matches("[data-editor-format]"))await updatePlan(state.activeRemix.slug,{format:el.value});
    else if(el.matches("[data-editor-stage]"))await updatePlan(state.activeRemix.slug,{production_stage:el.value});
    else if(el.matches("[data-editor-date]"))await updatePlan(state.activeRemix.slug,{scheduled_at:plannedISO(el.value)});
  }catch(e){showToast(e.message,"error");render();}
});
app.addEventListener("submit",async event=>{
  if(event.target.matches("[data-email-form]")){event.preventDefault();await submitEmailLogin(event.target);return;}
  if(event.target.matches("[data-profile-form]")){event.preventDefault();await saveProfile();return;}
  if(!event.target.matches("[data-competitor-form]"))return;event.preventDefault();
  state.importing=true;state.competitorError="";render();
  try{await apiRequest("/competitors",{method:"POST",body:JSON.stringify({account:state.competitorValue.trim(),platform:state.importPlatform,requested_count:state.importLimit})});await Promise.all([loadCompetitors(),loadImports()]);state.competitorValue="";showToast("Источник добавлен. Загрузка поставлена в очередь.");}
  catch(e){state.competitorError=e.message;}finally{state.importing=false;render();scheduleImportPolling();}
});
app.addEventListener("dragstart",event=>{const card=event.target.closest("[data-drag-slug]");if(card){event.dataTransfer.setData("text/plain",card.dataset.dragSlug);event.dataTransfer.effectAllowed="move";card.classList.add("dragging");}});
app.addEventListener("dragend",()=>app.querySelectorAll(".dragging,.drop-active").forEach(el=>el.classList.remove("dragging","drop-active")));
app.addEventListener("dragover",event=>{const zone=event.target.closest("[data-drop-status],[data-drop-date]");if(zone){event.preventDefault();event.dataTransfer.dropEffect="move";zone.classList.add("drop-active");}});
app.addEventListener("dragleave",event=>event.target.closest("[data-drop-status],[data-drop-date]")?.classList.remove("drop-active"));
app.addEventListener("drop",async event=>{
  const zone=event.target.closest("[data-drop-status],[data-drop-date]");if(!zone)return;event.preventDefault();
  const slug=event.dataTransfer.getData("text/plain"),r=state.remixes.find(r=>r.slug===slug);if(!r)return;
  try{await updatePlan(slug,zone.dataset.dropStatus?{status:zone.dataset.dropStatus}:{scheduled_at:zone.dataset.dropDate==="none"?null:plannedISO(`${zone.dataset.dropDate}T${r.scheduled_at?projectTime(r.scheduled_at):"12:00"}`)});}catch(e){showToast(e.message,"error");}
});
app.addEventListener("error",e=>{
  if(e.target.matches?.("[data-avatar-image]"))e.target.remove();
  else if(e.target.matches?.(".reel-thumb img")){e.target.parentElement.insertAdjacentHTML("afterbegin",icon("film-strip"));e.target.remove();}
},true);
document.addEventListener("keydown",event=>{
  if(event.key==="Escape"){state.dialog=null;state.openMenu=null;state.mobileNav=false;render();}
  if(state.dialog&&event.key==="Tab"){const nodes=[...app.querySelectorAll(".dialog-panel button,.dialog-panel a")];const first=nodes[0],last=nodes.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}
  const tab=event.target.closest?.("[data-tab]");if(tab&&["ArrowLeft","ArrowRight","Home","End"].includes(event.key)){event.preventDefault();app.querySelector(`[data-tab="${tab.dataset.tab==="reels"?"threads":"reels"}"]`)?.click();}
});
window.addEventListener("resize",()=>{const aside=app.querySelector(".sidebar");if(aside)aside.inert=matchMedia("(max-width:680px)").matches&&!state.mobileNav;autoSizeTextareas();});
document.addEventListener("visibilitychange",()=>{if(!document.hidden&&state.authChallenge&&!state.user)pollTelegramLogin();});
window.addEventListener("beforeunload",event=>{if(state.dirty){keepRecovery();event.preventDefault();event.returnValue="";}});
window.addEventListener("popstate",async()=>{
  // Native anchor navigation must not rebuild the landing and cancel its scroll.
  if(state.route==="/"&&location.pathname==="/")return;
  if(state.dirty&&!await saveActiveRemix({toast:false})){history.pushState({},"",state.route);return;}
  state.route=normalizeRoute(location.pathname);readRouteQuery();
  try{await loadRouteData();}catch(e){state.error=e.message;render();}
});
async function beginTelegramLogin(){
  if(state.authBusy)return;
  const attempt=++loginAttempt;
  clearTimeout(authPollTimer);state.authChallenge=null;state.authStatus="";state.authError="";state.authBusy=true;render();
  try{
    const challenge=await apiRequest("/auth/telegram/start",{method:"POST",body:JSON.stringify({return_to:loginReturnPath(new URLSearchParams(location.search).get("return_to"))})});
    if(attempt!==loginAttempt||state.route!=="/login"||state.user)return;
    state.authChallenge=challenge;
    state.authStatus="pending";render();pollTelegramLogin();
  }catch(e){if(attempt===loginAttempt){state.authError=e.message;render();}}
  finally{if(attempt===loginAttempt){state.authBusy=false;render();}}
}
async function beginYandexLogin(purpose="login"){
  if(state.authBusy)return;
  const attempt=++loginAttempt, userId=state.user?.id;
  state.authBusy=true;state.authError="";render();
  try{
    const result=await apiRequest("/auth/yandex/start",{method:"POST",body:JSON.stringify({purpose,return_to:loginReturnPath(new URLSearchParams(location.search).get("return_to"))})});
    if(attempt!==loginAttempt||state.user?.id!==userId||(purpose==="login"&&state.route!=="/login"))return;
    location.assign(result.authorize_url);
  }catch(error){state.authError=error.message;if(purpose==="link")showToast(error.message,"error");}
  finally{state.authBusy=false;render();}
}
async function submitEmailLogin(form,resend=false){
  if(state.authBusy||!state.emailLogin||state.user)return;
  const flow=state.emailLogin,attempt=++loginAttempt;
  const finish=Boolean(flow.challenge)&&!resend;
  const code=finish?new FormData(form).get('code'):null;
  if(!finish&&form)flow.email=String(new FormData(form).get('email')||'').trim();
  state.authBusy=true;state.authError="";render();
  try{
    const result=await apiRequest(`/auth/email/${finish?'finish':'start'}`,{method:'POST',body:JSON.stringify(finish?{challenge_id:flow.challenge.challenge_id,code}:{email:flow.email,return_to:loginReturnPath(new URLSearchParams(location.search).get('return_to'))})});
    if(attempt!==loginAttempt||state.route!=='/login'||state.emailLogin!==flow||state.user)return;
    if(finish){state.emailLogin=null;history.replaceState({},'',result.return_to);state.route=normalizeRoute(location.pathname);await bootstrap();}
    else{flow.challenge=result;flow.resendAt=Date.now()+result.resend_after*1000;updateEmailResend();}
  }catch(error){if(attempt===loginAttempt&&state.emailLogin===flow)state.authError=error.message;}
  finally{if(attempt===loginAttempt){state.authBusy=false;render();app.querySelector('#email-login-input')?.focus();}}
}
function updateEmailResend(){
  const flow=state.emailLogin;if(!flow?.challenge||state.route!=='/login')return;
  const remaining=Math.max(0,Math.ceil((flow.resendAt-Date.now())/1000));
  const button=app.querySelector('[data-action="resend-email"]');
  if(button){button.disabled=Boolean(remaining||state.authBusy);button.textContent=remaining?`Отправить повторно через ${remaining} с`:'Отправить код ещё раз';}
  if(remaining)setTimeout(()=>{if(state.emailLogin===flow)updateEmailResend();},1000);
}
function oauthError(){
  return ({yandex_invalid:"Запрос входа недействителен. Начните вход заново в этом браузере.",yandex_expired:"Время запроса истекло. Начните вход заново.",yandex_denied:"Вход через Яндекс отменён. Вы можете попробовать снова.",yandex_unavailable:"Не удалось получить ответ Яндекса. Попробуйте войти ещё раз.",yandex_conflict:"Этот Яндекс ID уже связан с другим аккаунтом, либо у вас уже подключён другой Яндекс ID.",yandex_disabled:"Аккаунт недоступен. Обратитесь в поддержку."})[new URLSearchParams(location.search).get("auth_error")]||"";
}
async function pollTelegramLogin(){
  clearTimeout(authPollTimer);
  const challenge=state.authChallenge;if(!challenge||state.user||state.route!=="/login")return;
  if(authPollInFlight===challenge)return;
  if(Date.now()>=new Date(challenge.expires_at).getTime()){state.authStatus="expired";render();return;}
  if(document.hidden){authPollTimer=setTimeout(pollTelegramLogin,2500);return;}
  authPollInFlight=challenge;
  try{
    const result=await apiRequest(`/auth/telegram/status?challenge_id=${encodeURIComponent(challenge.challenge_id)}`);
    if(state.authChallenge!==challenge)return;
    const changed=state.authStatus!==result.state||Boolean(state.authError);
    state.authStatus=result.state;state.authError="";if(changed)render();
    if(result.state==="approved"){
      const done=await apiRequest("/auth/telegram/finish",{method:"POST",body:JSON.stringify({challenge_id:challenge.challenge_id})});
      if(state.authChallenge!==challenge||state.route!=="/login")return;
      state.authChallenge=null;history.replaceState({},"",done.return_to);state.route=normalizeRoute(location.pathname);
      await bootstrap();return;
    }
    if(["expired","denied","consumed"].includes(result.state))return;
  }catch(e){if(state.authChallenge===challenge&&e.name!=="AbortError"){state.authError=`Ошибка соединения: ${e.message}`;render();}}
  finally{
    if(authPollInFlight===challenge)authPollInFlight=null;
    if(state.authChallenge===challenge&&state.route==="/login"&&!state.user&&!["expired","denied","consumed"].includes(state.authStatus))authPollTimer=setTimeout(pollTelegramLogin,2500);
  }
}
async function bootstrap(){
  try{
    const csrf=await apiRequest("/auth/csrf");state.csrf=csrf.csrf_token;state.authProviders=csrf.providers||{};
    let user;
    try{user=await apiRequest("/auth/me");}catch(e){if(e.status===401){clearAccountMemory();routeAccess();render();return;}throw e;}
    try{const previous=sessionStorage.getItem("auth-user-id");if(previous&&previous!==String(user.id))clearAccountMemory();sessionStorage.setItem("auth-user-id",String(user.id));}catch{}
    state.user=user;state.authError="";state.editorReturn=restoredReturnPath();
    routeAccess();
    state.competitors=await apiRequest("/competitors");
    readRouteQuery();await loadRouteData();
  }catch(e){
    if(state.user)state.error=e.message;else state.authError=e.message;
    state.loadingEditor=false;render();
  }
}
if(state.route==="/")render();
bootstrap();
