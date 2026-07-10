import { test, expect } from "@playwright/test";

const uiUrl = process.env.COSCIENTIST_UI_URL ?? "http://127.0.0.1:8001";
const apiUrl = process.env.COSCIENTIST_API_URL ?? "http://127.0.0.1:8787";
const marker = "ui_ffmpeg_command_ok_20260701";

test("chat command workflow shows terminal stdout", async ({ browser, request }) => {
  const login = await request.post(`${apiUrl}/api/auth/login`, {
    data: {
      email: "haomingwang@stumail.ysu.edu.cn",
      password: "ResearchAdmin123!",
    },
  });
  expect(login.ok()).toBeTruthy();
  const session = await login.json();

  const context = await browser.newContext({
    viewport: { width: 1365, height: 840 },
    deviceScaleFactor: 1,
  });
  await context.addInitScript((token: string) => {
    window.localStorage.setItem("open_coscientist_auth_token", token);
  }, session.access_token);

  const page = await context.newPage();
  await page.goto(`${uiUrl}/workspace`, { waitUntil: "networkidle" });
  await expect(page.locator("#command-center-input")).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(1200);

  const prompt = `执行本地命令：echo ${marker}`;
  await page.locator("#command-center-input").click();
  await page.keyboard.type(prompt, { delay: 35 });
  await page.waitForTimeout(700);
  await page.getByRole("button", { name: /发送/ }).click();

  await expect(page.getByText("执行本地终端命令")).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(900);
  await page.getByRole("button", { name: /确认执行/ }).click();

  await expect(page.getByText("命令结果")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(marker)).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(4500);
  await context.close();
});
