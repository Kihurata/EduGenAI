import type { RouteObject } from "react-router-dom";

import { guard } from "@/features/common/pages";

import { ClassDetailPage, ClassesPage } from "./ClassesPage";
import { ResultsPage } from "./ResultsPage";
import { ReviewPage } from "./ReviewPage";
import { ScansPage } from "./ScansPage";
import { SheetsPage } from "./SheetsPage";

// F3 owns this file. Teacher-only. All data is mock (features/grading/mock.ts) until the backend has grading endpoints.
export const gradingRoutes: RouteObject[] = [
  { path: "classes", element: guard(["teacher"], <ClassesPage />) },
  { path: "classes/:id", element: guard(["teacher"], <ClassDetailPage />) },
  { path: "sheets", element: guard(["teacher"], <SheetsPage />) },
  { path: "scans", element: guard(["teacher"], <ScansPage />) },
  { path: "scans/:id/review", element: guard(["teacher"], <ReviewPage />) },
  { path: "results", element: guard(["teacher"], <ResultsPage />) },
];
