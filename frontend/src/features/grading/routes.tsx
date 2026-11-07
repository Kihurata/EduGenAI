import type { RouteObject } from "react-router-dom";

import { ClassDetailPage, ClassesPage } from "./ClassesPage";
import { ResultsPage } from "./ResultsPage";
import { ReviewPage } from "./ReviewPage";
import { ScansPage } from "./ScansPage";
import { SheetsPage } from "./SheetsPage";

// F3 owns this file. All data is mock (features/grading/mock.ts) until the backend has grading endpoints.
export const gradingRoutes: RouteObject[] = [
  { path: "classes", element: <ClassesPage /> },
  { path: "classes/:id", element: <ClassDetailPage /> },
  { path: "sheets", element: <SheetsPage /> },
  { path: "scans", element: <ScansPage /> },
  { path: "scans/:id/review", element: <ReviewPage /> },
  { path: "results", element: <ResultsPage /> },
];
