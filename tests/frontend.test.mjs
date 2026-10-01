import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";

// Exercise the shipped plain JS, with only the browser boundary stubbed.
function appContext() {
  const element = { innerHTML: "", addEventListener() {}, querySelector() { return null; },
    querySelectorAll() { return []; }, replaceChildren() {} };
  const location = new URL("https://hypehunter.ru/login");
  const storage = new Map();
  const windowListeners = new Map();
  const context = vm.createContext({
    URL, URLSearchParams, Intl, Date, DOMException, console, location,
    sessionStorage: { getItem: key => storage.get(key), setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k) },
    document: { hidden: false, querySelector: () => element, addEventListener() {} },
    window: { addEventListener: (type,fn)=>windowListeners.set(type,fn), scrollTo() {} },
    history: { replaceState(_a,_b,path) { location.href=new URL(path,location).href; },
      pushState(_a,_b,path) { location.href=new URL(path,location).href; } },
    matchMedia: () => ({ matches: false }), setTimeout: () => 1, clearTimeout() {},
    fetch: async () => { throw new Error("Unexpected request"); },
  });
  for (const file of ["ui/library.js", "ui/planner.js", "ui/editor.js", "ui/account.js", "ui/landing.js", "app.js"]) {
    vm.runInContext(readFileSync(new URL("../"+file, import.meta.url), "utf8").replace(/bootstrap\(\);\s*$/, ""), context);
  }
  context.run = code => vm.runInContext(code, context);
  context.windowListeners=windowListeners;
  return context;
}
const response = data => ({ ok: true, status: 200, json: async () => data });
const deferred = () => { let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve}; };

test("legal links are public documents and auth errors remain accessible and escaped", () => {
  const c=appContext();
  c.run('state.emailLogin={email:"test@gmail.com"};state.authError="Вход с этой почтой недоступен. <script>"');
  const html=c.run("loginPage()");
  assert.match(html,/role="alert"/);
  assert.match(html,/&lt;script&gt;/);
  assert.match(html,/href="\/legal\/offer\/"/);
  assert.match(html,/href="\/legal\/privacy\/"/);
  for(const name of ["offer","privacy"]){
    const page=readFileSync(new URL(`../legal/${name}/index.html`,import.meta.url),"utf8");
    assert.match(page,/hypehunter.ru/);
    assert.match(page,/772460063060/);
    assert.match(page,/<main id="main-content"/);
    assert.doesNotMatch(page,/<script/);
  }
});

test("shared illustration has no caption; Yandex uses a local SVG in both places", () => {
  const c=appContext();
  c.run('state.user={id:1,display_name:"Owner"}');
  for (const html of [c.run("landingPage()"), c.run("loginPage()")]) {
    assert.doesNotMatch(html, /figcaption|От находки к собственному сценарию|Пример адаптации/);
  }
  for (const html of [c.run("futureSignInButtons()"),c.run("accountSecurity()")]) {
    assert.match(html, /src="\/assets\/yandex-logo\.svg"/);
    assert.doesNotMatch(html, /yandex-letter|>Я</);
  }
});

test("email form uses one-time-code, escapes addresses and resets on account switch", () => {
  const c=appContext();
  c.run('state.authProviders={email:true};state.emailLogin={email:"test@mail.ru"}');
  assert.match(c.run('futureSignInButtons()'), /data-action="begin-email"/);
  assert.match(c.run('emailLoginForm()'), /autocomplete="email"/);
  c.run('state.emailLogin={email:"<script>",challenge:{expires_in_minutes:5},resendAt:Date.now()+60000}');
  const html=c.run('loginPage()');
  assert.match(html,/autocomplete="one-time-code"/);
  assert.match(html,/pattern="\[0-9\]\{6\}"/);
  assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(html,/<script>/);
  assert.match(html,/data-action="resend-email" disabled/);
  c.run('clearAccountMemory()');
  assert.equal(c.run('state.emailLogin'),null);
});

test("logout discards responses already in flight and resets account-only UI", async () => {
  const c=appContext(), pending=deferred();
  c.fetch=()=>pending.promise;
  c.run('state.user={id:1};state.competitorValue="@private";state.profileBusy=true;state.authBusy=true');
  const request=c.run('apiRequest("/reels")');
  c.run("clearAccountMemory()");
  pending.resolve(response({items:[{title:"Private old response"}]}));
  await assert.rejects(request,{name:"AbortError"});
  assert.equal(c.run("state.competitorValue"),"");
  assert.equal(c.run("state.profileBusy||state.authBusy"),false);
});

test("leaving the library invalidates a pending search response", async () => {
  const c=appContext(), pending=deferred();
  c.fetch=()=>pending.promise;
  c.run('state.user={id:1};state.route="/library"');
  const search=c.run("loadReels()");
  c.run('state.route="/"');await c.run("loadRouteData()");
  pending.resolve(response({items:[{title:"Stale"}],total:1,page_count:1,page:1}));
  await search;
  assert.equal(c.run("state.reels.length"),0);
});

test("a slow editor response cannot replace the newly opened draft", async () => {
  const c=appContext(), first=deferred(), second=deferred();
  c.fetch=path=>path.endsWith("/first")?first.promise:second.promise;
  c.run('state.user={id:1};state.route="/remixes/first"');
  const old=c.run("loadRouteData()");
  c.run('state.route="/remixes/second"');
  const current=c.run("loadRouteData()");
  const draft={slug:"second",title:"Second",hook:"",script:"",cta:"",thread_text:"",format:"reels",status:"idea"};
  second.resolve(response(draft));await current;
  first.resolve(response({...draft,slug:"first"}));await old;
  assert.equal(c.run("state.activeRemix.slug"),"second");
});

test("leaving login discards a pending challenge creation", async () => {
  const c=appContext(), pending=deferred();
  c.fetch=()=>pending.promise;
  const start=c.run("beginTelegramLogin()");
  c.run('state.route="/"');await c.run("loadRouteData()");
  pending.resolve(response({challenge_id:"old"}));await start;
  assert.equal(c.run("state.authChallenge"),null);
  assert.equal(c.run("state.authBusy"),false);
});

test("visibility changes do not start overlapping login polls", async () => {
  const c=appContext(), pending=deferred();
  let requests=0;c.fetch=()=>{requests++;return pending.promise;};
  c.run('state.authChallenge={challenge_id:"id",code:"123456",bot_url:"https://t.me/test_bot?start=id",expires_at:new Date(Date.now()+60000).toISOString()}');
  const first=c.run("pollTelegramLogin()");
  await c.run("pollTelegramLogin()");
  assert.equal(requests,1);
  c.run('state.route="/"');await c.run("loadRouteData()");
  pending.resolve(response({state:"approved"}));await first;
  assert.equal(requests,1);
  assert.equal(c.run("state.authChallenge"),null);
});

test("public landing has honest pricing, legal details and correct guest/member CTAs", () => {
  const c=appContext(), guest=c.run("landingPage()");
  assert.match(guest,/href="\/login" data-route>Подключиться/);
  assert.match(guest,/1 999/);assert.match(guest,/3 900/);
  assert.doesNotMatch(guest,/2 490|4 900|href="#"|pantela/i);
  assert.match(guest,/деньги не списываются/);
  assert.match(guest,/Объёмы указаны для будущих тарифов/);
  assert.match(guest,/Демичев Дмитрий Дмитриевич/);
  assert.match(guest,/772460063060/);
  c.run('state.user={id:1,display_name:"Private owner"};state.route="/";render()');
  const member=c.run("landingPage()");
  assert.match(member,/href="\/today" data-route>Открыть приложение/);
  assert.doesNotMatch(member,/Private owner/);
  assert.equal(c.run("state.route"),"/");
});

test("landing examples never expose or change account data and escape sample edits", () => {
  const c=appContext();
  c.run('state.reels=[{title:"PRIVATE_SOURCE"}];state.remixes=[{title:"PRIVATE_REMIX"}];state.activeRemix={title:"PRIVATE_DRAFT"};landingFormat="threads";landingStep=2;landingEdits.threads="</textarea><img src=x onerror=alert(1)>"');
  const html=c.run("landingPage()");
  assert.match(html,/example-tab-threads/);assert.match(html,/Пример Reels и Threads/);
  assert.doesNotMatch(html,/PRIVATE_SOURCE|PRIVATE_REMIX|PRIVATE_DRAFT|<img src=x/);
  assert.match(html,/&lt;\/textarea&gt;/);
  assert.equal(c.run("state.activeRemix.title"),"PRIVATE_DRAFT");
  assert.equal(c.run("state.dirty"),false);
});

test("landing animation pauses when hidden, honours reduced motion and cleans up", () => {
  const c=appContext(), pending=new Map(), listeners=new Map(), motionListeners=new Map();
  let seq=0;
  const word={textContent:"клиентов"};
  const root={querySelector:()=>word,querySelectorAll:()=>[],addEventListener(){},removeEventListener(){}};
  const motion={matches:false,addEventListener:(type,fn)=>motionListeners.set(type,fn),removeEventListener:type=>motionListeners.delete(type)};
  c.document.querySelector=()=>root;
  c.document.addEventListener=(type,fn)=>listeners.set(type,fn);
  c.document.removeEventListener=type=>listeners.delete(type);
  c.matchMedia=()=>motion;
  c.setTimeout=fn=>{pending.set(++seq,fn);return seq;};
  c.clearTimeout=id=>pending.delete(id);
  // app is captured during script loading; bind its query selector explicitly.
  c.root=root;c.run('app.querySelector=()=>root;mountLanding()');
  const advance=()=>{const [id,fn]=pending.entries().next().value;pending.delete(id);fn();};
  assert.equal(pending.size,1);advance();assert.equal(word.textContent,"клиенто");
  c.document.hidden=true;listeners.get("visibilitychange")();assert.equal(pending.size,0);
  c.document.hidden=false;listeners.get("visibilitychange")();assert.equal(pending.size,1);
  motion.matches=true;motionListeners.get("change")();assert.equal(pending.size,0);assert.equal(word.textContent,"клиентов");
  motion.matches=false;motionListeners.get("change")();advance();assert.equal(word.textContent,"клиенто");
  for(let i=0;i<13;i++)advance();assert.equal(word.textContent,"заявки");
  c.run("stopLandingEffects()");
  assert.equal(pending.size,0);assert.equal(listeners.size,0);assert.equal(motionListeners.size,0);
});

test("landing anchor history does not rebuild the DOM or request account data", async () => {
  const c=appContext();
  c.run('state.route="/";location.href="https://hypehunter.ru/#pricing";app.innerHTML="anchored page"');
  await c.windowListeners.get("popstate")();
  assert.equal(c.run("app.innerHTML"),"anchored page");
  assert.equal(c.location.hash,"#pricing");
});

test("landing has both source links and omits the three removed labels", () => {
  const c=appContext(), html=c.run("landingPage()");
  assert.equal((html.match(/href="https:\/\/github.com\/mcdimas\/HypeHunter"/g)||[]).length,2);
  assert.match(html,/ph-github-logo[^]*?GitHub<\/a>/);
  assert.match(html,/Исходный код на GitHub<\/a>/);
  assert.doesNotMatch(html,/Учебный пример|Плательщик налога|Ориентир для сравнения|Работа продюсера\*/);
  assert.doesNotMatch(html.split('<footer')[1],/href="\/login"/);
  assert.match(html,/landing-title-line/);
  const css=readFileSync(new URL('../ui/landing.css',import.meta.url),'utf8');
  assert.doesNotMatch(css,/landing-type-slot\{[^}]*min-width/);
});

test("Reels example autoplays the supplied inline video with the original poster", () => {
  const c=appContext(), html=c.run("landingExample()");
  const video=html.match(/<video\b[^>]*>/)?.[0];
  assert.ok(video);
  for(const attribute of ['autoplay','muted','loop','playsinline'])assert.match(video,new RegExp(`\\s${attribute}(?:\\s|>)`));
  assert.match(video,/src="\/assets\/landing-creator\.mp4"/);
  assert.match(video,/poster="\/assets\/landing-creator\.webp"/);
  assert.match(html,/<video[^]*<img[^]*<\/video>/);
  c.run('landingFormat="threads"');assert.doesNotMatch(c.run('landingExample()'),/<video/);
});
