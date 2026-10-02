import { test, expect } from '@playwright/test';

test.beforeEach(async ({context,page}) => {
  await context.route('**/*', async route => {
    const url=new URL(route.request().url());
    if(url.hostname==='127.0.0.1') return route.continue();
    // No actual payment page, OAuth provider, analytics or third-party assets.
    return route.abort();
  });
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.__errors=errors;
});
test.afterEach(async ({page})=>expect(page.__errors).toEqual([]));

async function login(page,request,email,returnTo='/library') {
  await page.goto('/login?return_to='+encodeURIComponent(returnTo));
  await page.getByRole('button',{name:'Войти по почте с кодом'}).click();
  await page.getByLabel('Email',{exact:true}).fill(email);
  await page.getByRole('button',{name:'Получить код',exact:true}).click();
  await expect(page.getByLabel('Код из письма')).toBeVisible();
  const response=await request.get('http://127.0.0.1:8001/_test/mailbox?email='+encodeURIComponent(email));
  const code=(await response.json()).code;
  await page.getByLabel('Код из письма').fill(code==='000000'?'111111':'000000');
  await page.getByRole('button',{name:'Войти',exact:true}).click();
  await expect(page.locator('[role=alert]')).toContainText('Неверный код');
  await page.getByLabel('Код из письма').fill(code);
  await page.getByRole('button',{name:'Войти',exact:true}).click();
  await expect(page).toHaveURL(new RegExp(returnTo.split('?')[0]+'(?:\\?|$)'));
}

test('landing, pricing, legal documents, theme and rejected email',async({page},testInfo)=>{
  await page.goto('/');
  await expect(page.getByRole('heading',{level:1})).toContainText('Reels и Threads');
  await expect(page.locator('#pricing')).toContainText('1 999');
  await expect(page.locator('#pricing')).toContainText('3 900');
  await expect(page.locator('#pricing')).toContainText('Без сохранения карты и автосписаний');
  await page.getByRole('button',{name:'Сменить тему'}).click();
  const theme=await page.locator('html').getAttribute('data-theme');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme',theme);
  await page.goto('/legal/offer/');
  await expect(page.locator('body')).toContainText('30');
  await page.goto('/legal/privacy/');
  await expect(page.locator('body')).toContainText('персональных данных');
  await page.goto('/login');
  await page.getByRole('button',{name:'Войти по почте с кодом'}).click();
  await page.getByLabel('Email',{exact:true}).fill(`blocked-${testInfo.project.name}@gmail.com`);
  await page.getByRole('button',{name:'Получить код',exact:true}).click();
  await expect(page.locator('[role=alert]')).toContainText('Вход с этой почтой недоступен');
});

test('new user → five best reels → translation → edit → plan → profile → logout',async({page,request},testInfo)=>{
  await login(page,request,`journey-${testInfo.project.name}-${testInfo.retry}@mail.ru`);
  await page.goto('/competitors');
  await page.getByLabel('Профиль конкурента').fill('e2e_creator');
  await page.getByRole('button',{name:'Загрузить',exact:true}).click();
  await expect.poll(async()=> (await (await page.request.get('/api/reels?page_size=100')).json()).total).toBe(5);
  const reels=await (await page.request.get('/api/reels?page_size=100')).json();
  expect(reels.items.map(r=>r.views).sort((a,b)=>a-b)).toEqual([7000,8000,9000,10000,11000]);
  expect(reels.items.every(r=>r.translation_status==='completed')).toBe(true);
  await page.goto('/library');
  await page.locator('[data-action=remix]').first().click();
  await expect(page.getByLabel('Название публикации')).toBeVisible();
  const draftPath=new URL(page.url()).pathname;
  await page.getByLabel('Название публикации').fill('Моя публикация');
  await page.getByLabel('Хук: ваша редакция').fill('Мой собственный хук');
  await page.getByRole('button',{name:'Сохранить',exact:true}).click();
  await expect(page.locator('[data-save-status]')).toHaveText('Сохранено');
  await page.getByLabel('Запланировано · Москва').fill('2026-11-05T12:00');
  await page.getByLabel('Статус: Моя публикация').selectOption('ready');
  await page.getByRole('link',{name:'В контент-план'}).click();
  await expect(page.getByRole('link',{name:'Моя публикация',exact:true})).toBeVisible();
  await page.goto(draftPath);
  await expect(page.getByLabel('Хук: ваша редакция')).toHaveValue('Мой собственный хук');
  await expect(page.getByLabel('Запланировано · Москва')).toHaveValue('2026-11-05T12:00');
  const trial=await (await page.request.get('/api/trial')).json();
  expect(trial).toEqual({limit:5,used:5,remaining:0});
  await page.goto('/account');
  await page.getByLabel('Имя',{exact:true}).fill('Тестовый автор');
  await page.getByRole('button',{name:'Сохранить изменения'}).click();
  await expect(page.locator('[data-profile-message]')).toHaveText('Изменения сохранены');
  await page.getByRole('button',{name:'Светлая',exact:true}).click();
  await page.reload();
  await expect(page.getByLabel('Имя',{exact:true})).toHaveValue('Тестовый автор');
  await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  await page.goto('/account?tab=scenarios');
  await page.getByLabel('Бренд или имя').fill('Тестовая студия');
  await page.locator('[name=scenario_tone][value=bold]').check();
  await page.locator('[data-preferences-form] button[type=submit]').click();
  await expect(page.locator('[data-preferences-status]')).toHaveText('Настройки сохранены');
  await page.reload();
  await expect(page.getByLabel('Бренд или имя')).toHaveValue('Тестовая студия');
  await expect(page.locator('[name=scenario_tone][value=bold]')).toBeChecked();
  await page.getByRole('button',{name:'Выйти',exact:true}).click();
  await expect(page).toHaveURL(/\/login/);
  await expect.poll(async()=>(await page.request.get('/api/reels')).status()).toBe(401);
});

test('plan preserved through login → explicit consent → payment → access once; isolation',async({page,request,browser},testInfo)=>{
  const email=`billing-${testInfo.project.name}-${testInfo.retry}@mail.ru`;
  await login(page,request,email,'/account?tab=subscription&plan=start');
  await expect(page.getByRole('heading',{name:'Старт на 30 дней'})).toBeVisible();
  await expect(page.getByLabel('Принимаю')).not.toBeChecked();
  await page.getByLabel('Email для чека').fill('receipt-only@mail.ru');
  await page.getByLabel('Принимаю').check();
  // The provider navigation is intercepted, no financial transaction occurs.
  await page.route('https://yoomoney.ru/**',route=>route.fulfill({contentType:'text/html',body:'<h1>Fake checkout</h1>'}));
  let resolveOrder;
  const made=new Promise(resolve=>{resolveOrder=resolve;});
  await page.route('**/api/billing/checkout',async route=>{
    const response=await route.fetch();
    resolveOrder(await response.json());
    await route.fulfill({response});
  });
  await page.getByRole('button',{name:'Перейти к оплате'}).click();
  const order=await made;
  await expect(page).toHaveURL('https://yoomoney.ru/checkout/e2e');
  expect(order.amount).toBe('1999.00');
  const csrf=(await (await page.request.get('https://127.0.0.1:4174/api/auth/csrf')).json()).csrf_token;
  const settlement=await request.post('http://127.0.0.1:8001/_test/settle/e2e-'+order.id,{headers:{
    Origin:'https://127.0.0.1:4174','X-CSRF-Token':csrf,Cookie:'__Host-hype_csrf='+csrf}});
  expect(settlement.ok(),await settlement.text()).toBe(true);
  const refreshed=page.waitForResponse(response=>response.url().includes('/payments/'+order.id+'/refresh'));
  await page.goto('/account?tab=subscription&payment='+order.id);
  const confirmation=await refreshed;
  expect(confirmation.status(),JSON.stringify(await confirmation.json())).toBe(200);
  await expect.poll(async()=> (await (await page.request.get('/api/trial')).json()).limit).toBe(40);
  const before=await (await page.request.get('/api/billing/status')).json();
  expect(before.auto_renew).toBe(false);
  await page.reload();
  const after=await (await page.request.get('/api/billing/status')).json();
  expect(after.subscription.access_until).toBe(before.subscription.access_until);
  await expect(page.locator('[data-action=choose-plan]')).toHaveCount(0);
  expect((await (await page.request.get('/api/auth/me')).json()).email).toBe(email);
  // Another real browser session cannot see the first user's package/data.
  const other=await browser.newContext({baseURL:'https://127.0.0.1:4174',ignoreHTTPSErrors:true});
  const second=await other.newPage();
  await login(second,request,`other-${testInfo.project.name}-${testInfo.retry}@mail.ru`);
  expect((await (await second.request.get('/api/billing/status')).json()).payments).toEqual([]);
  expect((await (await second.request.get('/api/trial')).json()).limit).toBe(5);
  expect((await second.request.get('/api/billing/receipts')).status()).toBe(404);
  await other.close();
});
