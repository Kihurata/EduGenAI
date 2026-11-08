import type { UserRole } from "@/types";

export interface NavItem {
  label: string;
  to: string;
  roles: UserRole[];
  prototype?: boolean;
  /** Extra path prefixes that also highlight this tab (the whole flow under one tab). */
  also?: string[];
}

const teacher: UserRole[] = ["teacher"];
const admin: UserRole[] = ["admin"];

// Admin chỉ quản trị: tài khoản GV, chọn đề chính thức (ngân hàng đề), nguồn tài liệu RAG.
export const NAV: NavItem[] = [
  // Sinh đề = cả luồng ma trận → kiểm tra → sinh → duyệt → xuất (stepper trong trang dẫn qua từng bước).
  { label: "Sinh đề", to: "/matrices", roles: teacher, also: ["/exams"] },
  { label: "Đề của tôi", to: "/collection", roles: teacher }, // bộ sưu tập cá nhân + đề gửi trường
  { label: "Ngân hàng đề", to: "/bank", roles: teacher },
  { label: "Chấm bài", to: "/classes", roles: teacher, prototype: true },
  { label: "Tài khoản", to: "/admin/teachers", roles: admin },
  { label: "Ngân hàng đề", to: "/admin/bank", roles: admin },
  { label: "Nguồn tài liệu", to: "/admin/sources", roles: admin, prototype: true },
];

export const navFor = (role: UserRole) => NAV.filter((n) => n.roles.includes(role));
