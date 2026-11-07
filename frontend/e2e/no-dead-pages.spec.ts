import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// Tóm tắt: no-dead-pages check. Logs in as teacher/admin, visits every route, asserts h1/non-blank/no console
// errors/no ComingSoon, follows every internal link once, and walks the Khối 2 mock flow.
const pwFile = path.resolve(process.cwd(), "../edugen-backend/dev_data/password.txt");
const PASSWORD = process.env.EDUGEN_DEV_PASSWORD ?? (fs.existsSync(pwFile) ? fs.readFileSync(pwFile, "utf8").trim() : "");
const NOT_FOUND = "Không tìm thấy trang";
const SHOTS = path.resolve(process.cwd(), "e2e/screens");
const COMING = /Sắp có|đang được xây dựng/;

const TEACHER_ROUTES = ["/", "/matrices", "/exams", "/bank", "/sample-exams", "/classes", "/sheets", "/scans", "/results"];
const ADMIN_ROUTES = ["/admin/sources", "/admin/bank", "/admin/teachers"];

async function login(page: Page, email: string) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.locator("header nav")).toBeVisible();
}

function watchConsole(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  return errors;
}

/** Assertions on the page currently shown. `errors` is drained so each page only owns its own console errors. */
async function checkPage(page: Page, label: string, errors: string[]) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
  const vp = page.viewportSize()!;
  if (vp.width === 1440) {
    fs.mkdirSync(SHOTS, { recursive: true });
    await page.screenshot({ path: path.join(SHOTS, `${label.replace(/[^\w-]+/g, "_")}.png`), fullPage: true });
  }
  expect.soft(await page.locator("h1").count(), `${label}: exactly one h1`).toBe(1);
  const text = (await page.locator("main").innerText()).trim();
  expect.soft(text.length, `${label}: main not blank`).toBeGreaterThan(10);
  expect.soft(text, `${label}: no ComingSoon`).not.toMatch(COMING);
  expect.soft(errors.splice(0), `${label}: console errors`).toEqual([]);
  if (vp.width <= 390) {
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect.soft(over, `${label}: horizontal overflow px`).toBeLessThanOrEqual(0);
  }
}

async function hrefs(page: Page): Promise<string[]> {
  return page.locator('main a[href^="/"], header a[href^="/"]').evaluateAll((as) => as.map((a) => a.getAttribute("href")!));
}

async function visit(page: Page, route: string, errors: string[], crawled: Set<string>) {
  await page.goto(route);
  await checkPage(page, route, errors);
  const links = [...new Set(await hrefs(page))];
  for (const href of links) {
    if (crawled.has(href)) continue;
    crawled.add(href);
    await page.goto(href);
    await page.waitForLoadState("networkidle");
    const h1 = await page.locator("h1").first().innerText();
    expect.soft(h1, `link ${href} (from ${route}) lands on 404`).not.toContain(NOT_FOUND);
    expect.soft(await page.locator("main").innerText(), `link ${href} (from ${route}) is ComingSoon`).not.toMatch(COMING);
    errors.length = 0;
  }
  return links;
}

test.describe("teacher", () => {
  test("every route and link renders", async ({ page }) => {
    const errors = watchConsole(page);
    await login(page, "gv@nd.vn");
    const crawled = new Set<string>();
    const all: string[] = [];
    for (const r of TEACHER_ROUTES) all.push(...(await visit(page, r, errors, crawled)));
    // Detail routes discovered from the lists (hrefs are what a click would follow).
    const detail = [...new Set(all)].filter((h) => /^\/(matrices|exams)\/[^/]+(\/export)?$/.test(h));
    for (const d of detail.slice(0, 6)) await visit(page, d, errors, crawled);
    const exam = detail.find((h) => /^\/exams\/[^/]+$/.test(h));
    if (exam) await visit(page, `${exam}/export`, errors, crawled);
    else test.info().annotations.push({ type: "note", description: "no exam in the dev DB: /exams/:id and /export not exercised" });
    if (!detail.some((h) => h.startsWith("/matrices/"))) test.info().annotations.push({ type: "note", description: "no matrix in dev DB: /matrices/:id not exercised" });
    // class detail: reached via the class list "Mở lớp" link
    await page.goto("/classes");
    await page.waitForLoadState("networkidle");
    await page.getByRole("link", { name: "Mở lớp" }).click();
    await expect(page).toHaveURL(/\/classes\/[^/]+$/);
    await checkPage(page, "classes-detail", errors);
  });

  test("admin routes show 403", async ({ page }) => {
    await login(page, "gv@nd.vn");
    for (const r of ADMIN_ROUTES) {
      await page.goto(r);
      await expect(page.locator("h1"), r).toHaveText("Không có quyền truy cập");
    }
    await expect(page.locator("header nav a[href^='/admin']")).toHaveCount(0);
  });

  test("Khối 2 mock flow", async ({ page }) => {
    const errors = watchConsole(page);
    await login(page, "gv@nd.vn");
    await page.locator("header nav").getByRole("link", { name: "Chấm bài" }).click();
    await expect(page).toHaveURL(/\/classes$/);
    await checkPage(page, "flow-classes", errors);
    await page.getByRole("link", { name: "Mở lớp" }).click();
    await expect(page).toHaveURL(/\/classes\/[^/]+$/);
    await checkPage(page, "flow-class-detail", errors);
    await page.locator('main a[href^="/sheets?class="]').first().click();
    await expect(page).toHaveURL(/\/sheets\?class=/);
    await checkPage(page, "flow-sheets", errors);
    const exam = page.locator("main select").first();
    const opts = await exam.locator("option").evaluateAll((os) => os.map((o) => (o as HTMLOptionElement).value).filter(Boolean));
    expect(opts.length, "sheets: at least one approved exam to pick (seed an approved exam in the dev DB)").toBeGreaterThan(0);
    await exam.selectOption(opts[0]);
    await page.getByRole("button", { name: "Tạo phiếu" }).click();
    await page.getByRole("link", { name: "Tiếp tục" }).click();
    await expect(page).toHaveURL(/\/scans$/);
    await checkPage(page, "flow-scans", errors);
    const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
    await page.getByLabel("Chọn tệp quét").setInputFiles([
      { name: "a.png", mimeType: "image/png", buffer: png },
      { name: "b.png", mimeType: "image/png", buffer: png },
    ]);
    await expect(page.getByText("Đã nhận").first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: "Chấm các phiếu đã nhận" }).click();
    for (let i = 0; i < 4 && /\/review$/.test(page.url()); i++) {
      await expect(page).toHaveURL(/\/scans\/[^/]+\/review$/);
      await checkPage(page, `flow-review-${i}`, errors);
      const before = page.url();
      await page.getByRole("button", { name: "Xác nhận phiếu" }).click();
      await page.waitForURL((u) => u.toString() !== before);
    }
    await expect(page).toHaveURL(/\/results$/);
    await checkPage(page, "flow-results", errors);
  });
});

test.describe("admin", () => {
  test("every route and link renders", async ({ page }) => {
    const errors = watchConsole(page);
    await login(page, "admin@nd.vn");
    const crawled = new Set<string>();
    for (const r of [...TEACHER_ROUTES, ...ADMIN_ROUTES]) await visit(page, r, errors, crawled);
    for (const item of ["Nguồn tài liệu", "Tài khoản"]) {
      await page.locator("header nav").getByRole("link", { name: item }).click();
      await expect(page.locator("h1")).not.toHaveText("Không có quyền truy cập");
    }
  });
});

test("unknown path shows 404 with working home button", async ({ page }) => {
  await login(page, "gv@nd.vn");
  await page.goto("/zzz");
  await expect(page.locator("h1")).toHaveText(NOT_FOUND);
  await page.getByRole("button", { name: "Về trang chủ" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator("h1")).toContainText("Xin chào");
});
