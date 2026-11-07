import type { RouteObject } from "react-router-dom";

import { guard } from "@/features/common/pages";
import BankPage from "./BankPage";
import SourcesPage from "./SourcesPage";
import TeachersPage from "./TeachersPage";

// F2 owns this file. All routes are admin-only (403 for teachers).
export const adminRoutes: RouteObject[] = [
  { path: "admin/sources", element: guard(["admin"], <SourcesPage />) },
  { path: "admin/bank", element: guard(["admin"], <BankPage />) },
  { path: "admin/teachers", element: guard(["admin"], <TeachersPage />) },
];
