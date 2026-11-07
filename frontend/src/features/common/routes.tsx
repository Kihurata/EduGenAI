import type { RouteObject } from "react-router-dom";

import SampleExamDetail from "@/pages/SampleExamDetail";
import SampleExams from "@/pages/SampleExams";

import { Home, NotFound, guard } from "./pages";

export const commonRoutes: RouteObject[] = [
  { index: true, element: <Home /> },
  // T-050 pages are still the legacy implementation (classes from the old styles.css, now removed): restyle later.
  { path: "sample-exams", element: guard(["teacher", "admin"], <SampleExams />) },
  { path: "sample-exams/:id", element: guard(["teacher", "admin"], <SampleExamDetail />) },
  { path: "*", element: <NotFound /> },
];
