import {test, expect, type Page} from '@playwright/test';
async function login(page: Page, username: string) {
  await page.goto('/');
  await page.getByLabel('账号').fill(username);
  await page.getByLabel('密码').fill('Test-only-password!');
  await page.getByRole('button', {name:'进入工作空间'}).click();
  await expect(page.getByLabel('输入问题')).toBeVisible();
}
async function send(page: Page, text: string) {
  await page.getByLabel('输入问题').fill(text);
  await page.getByLabel('发送问题').click();
  await expect(page.getByText('已完成', {exact:true}).last()).toBeVisible();
}
test('document upload, version switch, citation and disable', async ({page, browser}, info) => {
  await login(page, 'admin');
  await page.getByRole('link', {name:'知识文档'}).click();
  await page.getByLabel('选择知识文档').setInputFiles({name:'验收制度.txt', mimeType:'text/plain', buffer:Buffer.from('验收制度：远程办公每周最多三天。')});
  await page.getByRole('button', {name:'上传并处理'}).click();
  await expect(page.getByText('版本 1 · 处理完成')).toBeVisible();
  const context = await browser.newContext(); const employee = await context.newPage();
  await login(employee,'E1001'); await send(employee,'远程办公每周几天');
  await expect(employee.locator('.message.assistant')).toContainText('最多三天');
  await employee.getByRole('button', {name:/1. 验收制度/}).click();
  await expect(employee.getByRole('dialog')).toContainText('最多三天');
  await employee.getByLabel('关闭引用').click();
  await page.getByLabel('更新 验收制度.txt').setInputFiles({name:'验收制度.txt', mimeType:'text/plain', buffer:Buffer.from('验收制度：远程办公每周最多两天。')});
  await expect(page.getByText('版本 2 · 处理完成')).toBeVisible();
  await send(employee,'远程办公新规定');
  await expect(employee.locator('.message.assistant').last()).toContainText('最多两天');
  await page.getByRole('button', {name:'停用', exact:true}).click();
  await send(employee,'远程办公现在如何安排');
  await expect(employee.locator('.message.assistant').last()).toContainText('没有相关依据');
  await employee.screenshot({path:info.outputPath('chat.png'), fullPage:true});
  await page.screenshot({path:info.outputPath('documents.png'), fullPage:true});
  await context.close();
});
test('personal query, report edit, refresh and account isolation', async ({page, browser}, info) => {
  await login(page,'E1001'); await send(page,'根据我的项目记录生成周报');
  await expect(page.locator('.message.assistant').last()).toContainText('E1001');
  await page.getByRole('button', {name:'编辑并保存为周报'}).last().click();
  await page.getByLabel('周报标题').fill('验收周报');
  await page.getByLabel('周报正文').fill('已完成接口联调，下一步补充部署验证。');
  await page.getByRole('button', {name:'保存周报'}).click();
  await expect(page.getByText('周报已保存')).toBeVisible();
  await page.reload(); await page.getByRole('button', {name:/验收周报/}).click();
  await expect(page.getByLabel('周报正文')).toHaveValue('已完成接口联调，下一步补充部署验证。');
  await page.screenshot({path:info.outputPath('reports.png'), fullPage:true});
  const context = await browser.newContext(); const other = await context.newPage();
  await login(other,'E1002'); await other.getByRole('link', {name:'我的周报'}).click();
  await expect(other.getByRole('button', {name:/验收周报/})).toHaveCount(0);
  await expect(other.getByRole('link', {name:'知识文档'})).toHaveCount(0);
  await context.close();
});
test('stop preserves cancelled history', async ({page}) => {
  await login(page,'E1001');
  await page.getByLabel('输入问题').fill('慢速回答'); await page.getByLabel('发送问题').click();
  await expect(page.locator('.message.assistant').last()).toContainText('正在生成');
  await page.getByRole('button', {name:'停止生成'}).click();
  await expect(page.getByText('已停止', {exact:true}).last()).toBeVisible();
  await page.reload(); await page.locator('.conversation').first().click();
  await expect(page.getByText('已停止', {exact:true}).last()).toBeVisible();
});
