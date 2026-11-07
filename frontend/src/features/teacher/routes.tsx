import type { RouteObject } from "react-router-dom";

import BankPage from "./BankPage";
import ExamExportPage from "./ExamExportPage";
import ExamReviewPage from "./ExamReviewPage";
import ExamsPage from "./ExamsPage";
import MatricesPage from "./MatricesPage";
import MatrixCheckPage from "./MatrixCheckPage";

export const teacherRoutes: RouteObject[] = [
  { path: "matrices", element: <MatricesPage /> },
  { path: "matrices/:id", element: <MatrixCheckPage /> },
  { path: "exams", element: <ExamsPage /> },
  { path: "exams/:id", element: <ExamReviewPage /> },
  { path: "exams/:id/export", element: <ExamExportPage /> },
  { path: "bank", element: <BankPage /> },
];
