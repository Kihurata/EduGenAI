/**
 * Mock convention for areas without a backend yet (grading, sources).
 * - USE_MOCK is true unless VITE_USE_MOCK=false.
 * - Mock data lives in features/<area>/mock.ts, exposed as getX() functions so the UI
 *   never changes when a getX() is swapped for api().
 * - Every backend join point carries a comment (grep: grep -rn "TODO(BE)" src):
 *
 *   // TODO(BE): POST /api/v1/classes/{class_id}/students/import (multipart CSV)
 *   //   req : file=ma_hs,ho_ten,ngay_sinh
 *   //   res : { created: number, errors: [{row: number, message: string}] }
 *   //   owner: Backend (Huy/Phu) · feature: Khối 2 · now: mock in features/grading/mock.ts
 *
 * - Calls to existing real endpoints use `// API: GET /api/v1/...` instead of TODO(BE).
 */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

export const delay = <T>(value: T, ms = 300): Promise<T> => new Promise((r) => setTimeout(() => r(value), ms));
