import type { RouteObject } from "react-router-dom";

import { guard } from "@/features/common/pages";
import BankPage from "./BankPage";
import CollectionPage from "./CollectionPage";
import ExamExportPage from "./ExamExportPage";
import ExamReviewPage from "./ExamReviewPage";
import ExamsPage from "./ExamsPage";
import MatricesPage from "./MatricesPage";
import MatrixCheckPage from "./MatrixCheckPage";

// List pages are teacher-only; detail pages stay open to admin so they can inspect an exam before making it official.
export const teacherRoutes: RouteObject[] = [
  { path: "matrices", element: guard(["teacher"], <MatricesPage />) },
  { path: "matrices/:id", element: <MatrixCheckPage /> },
  { path: "exams", element: guard(["teacher"], <ExamsPage />) },
  { path: "exams/:id", element: <ExamReviewPage /> },
  { path: "exams/:id/export", element: <ExamExportPage /> },
  { path: "bank", element: guard(["teacher"], <BankPage />) },
  { path: "collection", element: guard(["teacher"], <CollectionPage />) },
];
