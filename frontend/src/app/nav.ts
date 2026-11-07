import type { UserRole } from "@/types";

export interface NavItem {
  label: string;
  to: string;
  roles: UserRole[];
  prototype?: boolean;
}

const both: UserRole[] = ["teacher", "admin"];

export const NAV: NavItem[] = [
  { label: "Ma trận", to: "/matrices", roles: both },
  { label: "Đề thi", to: "/exams", roles: both },
  { label: "Ngân hàng đề", to: "/bank", roles: both },
  { label: "Đề mẫu", to: "/sample-exams", roles: both }, // GV thấy đề mình tải, admin thấy cả trường
  { label: "Chấm bài", to: "/classes", roles: both, prototype: true },
  { label: "Nguồn tài liệu", to: "/admin/sources", roles: ["admin"], prototype: true },
  { label: "Tài khoản", to: "/admin/teachers", roles: ["admin"] },
];

export const navFor = (role: UserRole) => NAV.filter((n) => n.roles.includes(role));
