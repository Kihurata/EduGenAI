import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// Tóm tắt: luồng hình khối (F-17) với BE dev (scripts/dev_server.py, RAG giả lập, không cần LLM hay Qdrant):
// tải ma trận → xác nhận → sinh đề → mở trang duyệt đề thấy hình SVG → sửa câu có hình vẫn còn hình → xuất DOCX có ảnh PNG.
const API = process.env.E2E_API ?? "http://localhost:8000";
const pwFile = path.resolve(process.cwd(), "../edugen-backend/dev_data/password.txt");
const PASSWORD = process.env.EDUGEN_DEV_PASSWORD ?? (fs.existsSync(pwFile) ? fs.readFileSync(pwFile, "utf8").trim() : "");
const MATRIX_PNG = path.resolve(process.cwd(), "../edugen-backend/tests/fixtures/matrices/ktgk_hk1_toan10.png");
const CELL_KEYS = ["topic", "content_unit", "type", "level", "count", "statement_levels", "competency_codes"];

async function until<T>(read: () => Promise<T>, done: (v: T) => boolean, what: string): Promise<T> {
  for (let i = 0; i < 60; i++) {
    const value = await read();
    if (done(value)) return value;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`timeout: ${what}`);
}

/** Dựng một đề đã sinh bằng API (giống người dùng: tải ma trận, xác nhận, sinh đề), trả id đề và header đăng nhập. */
async function generatedExam(request: APIRequestContext) {
  const login = await request.post(`${API}/api/v1/auth/login`, { data: { email: "gv@nd.vn", password: PASSWORD } });
  expect(login.ok(), "login").toBeTruthy();
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` };
  const get = async (url: string) => (await request.get(`${API}/api/v1${url}`, { headers })).json();

  const up = await request.post(`${API}/api/v1/matrices`, {
    headers,
    multipart: { file: { name: "mt.png", mimeType: "image/png", buffer: fs.readFileSync(MATRIX_PNG) } },
  });
  expect(up.status(), "upload matrix").toBe(202);
  const id = (await up.json()).id as string;
  const matrix = await until(() => get(`/matrices/${id}`), (m) => m.status === "parsed", "matrix parsed");
  const cells = matrix.cells.map((c: Record<string, unknown>) => Object.fromEntries(CELL_KEYS.map((k) => [k, c[k]])));
  expect((await request.put(`${API}/api/v1/matrices/${id}/cells`, { headers, data: { cells, grade: 12 } })).ok()).toBeTruthy();
  expect((await request.post(`${API}/api/v1/matrices/${id}/confirm`, { headers })).ok()).toBeTruthy();

  const created = await request.post(`${API}/api/v1/exams`, { headers, data: { matrix_id: id, duration_minutes: 45 } });
  expect(created.status(), "create exam").toBe(202);
  const examId = (await created.json()).id as string;
  await until(() => get(`/exams/${examId}`), (e) => e.status !== "generating", "exam generated");
  return { examId, headers };
}

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Email").fill("gv@nd.vn");
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.locator("header nav")).toBeVisible();
}

test.describe("hình khối trong đề", () => {
  test("review page shows the drawn figure, an edit keeps it, DOCX embeds a PNG", async ({ page, request }) => {
    const { examId, headers } = await generatedExam(request);
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await login(page);
    await page.goto(`/exams/${examId}`);
    const figures = page.getByTestId("question-figure");
    await expect(figures.first()).toBeVisible();
    expect(await figures.count(), "the mock geometry samples give several figures").toBeGreaterThanOrEqual(3);

    // The image is a real, decoded SVG (an <img>, so nothing in it can run as script) with the text description as alt.
    const first = figures.first();
    expect(await first.getAttribute("src")).toMatch(/^data:image\/svg\+xml/);
    expect(await first.getAttribute("alt")).toMatch(/^Hình /);
    expect(await first.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(100);
    expect(decodeURIComponent((await first.getAttribute("src"))!)).toContain("<line");

    // The figure stays inside the page on every viewport.
    const box = await first.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width);

    // Editing a question with a figure keeps the figure (BE redraws it from the spec).
    const before = await figures.count();
    const article = page.locator("article", { has: first });
    await article.getByRole("button", { name: "Sửa" }).click();
    await expect(article.getByTestId("question-figure")).toBeVisible(); // live preview in the editor
    await page.getByRole("button", { name: "Lưu câu" }).click();
    await expect(page.getByRole("button", { name: "Lưu câu" })).toHaveCount(0);
    await expect(figures).toHaveCount(before);

    // Approve, then the student copy has the figure as a PNG picture.
    expect((await request.post(`${API}/api/v1/exams/${examId}/approve`, { headers })).ok(), "approve").toBeTruthy();
    const docx = await request.get(`${API}/api/v1/exams/${examId}/export?variant=student`, { headers });
    expect(docx.ok(), "export").toBeTruthy();
    const body = await docx.body();
    expect(body.includes(".png"), "DOCX has a PNG picture (file names are stored uncompressed in the zip)").toBeTruthy();
    expect(errors).toEqual([]);
  });

  test("a question without a figure shows none", async ({ page, request }) => {
    const { examId } = await generatedExam(request);
    await login(page);
    await page.goto(`/exams/${examId}`);
    await expect(page.locator("article").first()).toBeVisible();
    const articles = await page.locator("article").count();
    const withFigure = await page.getByTestId("question-figure").count();
    expect(withFigure).toBeGreaterThan(0);
    expect(withFigure).toBeLessThan(articles);
  });
});
