import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PrototypeBanner } from "@/components/PrototypeBanner";
import { EmptyState, ErrorState } from "@/components/states";
import { GRADING_STEPS, Stepper } from "@/components/Stepper";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { addClass, getClass, getClasses } from "./mock";
import { StudentPanel } from "./StudentPanel";
import { Gate, useLoad } from "./useLoad";

export function ClassesPage() {
  const { data, error, loading, reload } = useLoad(getClasses, []);
  const [selected, setSelected] = useState<string>();
  const [name, setName] = useState("");

  const add = async () => {
    const c = await addClass(name.trim());
    setName("");
    setSelected(c.id);
    reload();
  };
  const current = data?.find((c) => c.id === selected) ?? data?.[0];

  return (
    <section>
      <PrototypeBanner />
      <Stepper steps={GRADING_STEPS} current={0} />
      <h1 className="mb-4 text-xl font-semibold">Lớp và học sinh</h1>
      <Gate loading={loading} error={error} reload={reload} hasData={!!data} />
      {data && (
        <div className="grid gap-8 md:grid-cols-[16rem_1fr]">
          <div>
            <form
              className="mb-3 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (name.trim()) void add();
              }}
            >
              <Input aria-label="Tên lớp mới" placeholder="Tên lớp, ví dụ 12A3" value={name} onChange={(e) => setName(e.target.value)} />
              <Button type="submit" disabled={!name.trim()}>Thêm lớp</Button>
            </form>
            {data.length === 0 ? (
              <EmptyState title="Chưa có lớp" hint="Nhập tên lớp ở trên để bắt đầu." />
            ) : (
              <ul className="border-t border-line">
                {data.map((c) => (
                  <li key={c.id} className="border-b border-line">
                    <button
                      type="button"
                      onClick={() => setSelected(c.id)}
                      className={cn("flex w-full cursor-pointer items-center justify-between px-2 py-2 text-left text-sm hover:bg-soft", c === current && "font-semibold text-accent")}
                    >
                      <span>{c.name}</span>
                      <span className="text-muted">{c.students.length} HS</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {current && <StudentPanel cls={current} onChange={reload} withLinks />}
        </div>
      )}
    </section>
  );
}

export function ClassDetailPage() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useLoad(() => getClass(id), [id]);

  return (
    <section>
      <PrototypeBanner />
      <Stepper steps={GRADING_STEPS} current={0} />
      <h1 className="mb-4 text-xl font-semibold">{data ? `Lớp ${data.name}` : "Chi tiết lớp"}</h1>
      <Gate loading={loading} error={error} reload={reload} hasData={!!data} />
      {!loading && !error && !data && (
        <ErrorState message="Không tìm thấy lớp này." />
      )}
      {!loading && !error && !data && (
        <p className="mt-3 text-center"><Link to="/classes" className="text-accent underline">Về danh sách lớp</Link></p>
      )}
      {data && (
        <>
          <StudentPanel cls={data} onChange={reload} />
          <div className="mt-6 flex items-center gap-4">
            <Link to={`/sheets?class=${data.id}`} className="inline-flex h-9 items-center rounded-sm border border-accent bg-accent px-3 text-sm font-medium text-surface">
              Tạo phiếu trả lời
            </Link>
            <Link to="/classes" className="text-sm text-accent underline">Quay lại danh sách lớp</Link>
          </div>
        </>
      )}
    </section>
  );
}
