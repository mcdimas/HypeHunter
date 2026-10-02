import {test,expect} from '@playwright/test';
test('production read-only release smoke, no login or external providers',async({page,context})=>{
  await context.route('**/*',route=>{
    const request=route.request();
    if(request.method()!=='GET'||new URL(request.url()).hostname!=='hypehunter.ru') return route.abort();
    return route.continue();
  });
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await expect(page.locator('#pricing')).toContainText('1 999');
  await expect(page.locator('#pricing')).toContainText('3 900');
  await expect(page.locator('#pricing')).toContainText('Без сохранения карты и автосписаний');
  for(const path of ['/login','/legal/offer/','/legal/privacy/']) {
    const response=await page.goto(path);expect(response.status()).toBe(200);
  }
  const health=await page.request.get('/api/health');expect((await health.json()).database).toBe('connected');
  for(const path of ['/api/reels','/api/billing/status','/api/billing/receipts','/api/auth/me']) {
    const response=await page.request.get(path);
    expect([401,404]).toContain(response.status());
  }
  const fixture=await page.request.get('/_test/mailbox');
  expect(fixture.headers()['content-type']||'').not.toContain('application/json');
  expect(errors).toEqual([]);
});
