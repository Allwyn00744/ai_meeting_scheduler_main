import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, ChevronRight } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { EmptyState } from "@/components/ui/EmptyState";
import { usersApi } from "@/api/users";
import { useAuth } from "@/hooks/useAuth";

function initialsOf(name: string) {
  const parts = name.trim().split(/\s+/);
  return parts.length === 1 ? parts[0].slice(0, 2).toUpperCase() : (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function Users() {
  const { user: me } = useAuth();
  const [query, setQuery] = React.useState("");

  const { data: users, isLoading } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });

  const filtered = (users ?? []).filter(
    (u) =>
      u.name.toLowerCase().includes(query.toLowerCase()) ||
      u.email.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[28px] font-bold text-slate-900">Your account</h1>
          <p className="mt-1 text-sm text-slate-500">
            A full team directory isn't available yet — this shows only your own account.
          </p>
        </div>
      </div>

      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Search by name or email..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <p className="shrink-0 text-sm text-slate-500">{users?.length ?? 0} account{users?.length === 1 ? "" : "s"}</p>
      </div>

      {isLoading ? (
        <div className="h-64 animate-pulse rounded-xl bg-slate-100" />
      ) : filtered.length === 0 ? (
        <EmptyState icon={<Search className="h-5 w-5" />} title="No matches" body="Try a different search term." />
      ) : (
        <Card>
          {filtered.map((u, i) => (
            <div
              key={u.id}
              className={`flex items-center gap-3 px-5 py-4 ${i !== filtered.length - 1 ? "border-b border-slate-100" : ""}`}
            >
              <Avatar initials={initialsOf(u.name)} colorClass="bg-brand-100 text-brand-700" size={40} />
              <div className="min-w-0 flex-1">
                <p className="font-medium text-slate-900">
                  {u.name} {u.id === me?.id && <span className="text-xs font-normal text-slate-400">(you)</span>}
                </p>
                <p className="text-sm text-slate-500">{u.email}</p>
              </div>
              <div className="hidden text-right sm:block">
                <Badge variant="neutral">{u.timezone}</Badge>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-slate-300" />
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
