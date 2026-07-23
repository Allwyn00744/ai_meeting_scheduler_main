import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, DoorOpen, MapPin, X, Archive, RefreshCcw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ResourceStatusBadge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { resourcesApi } from "@/api/resources";
import { getApiErrorMessage } from "@/api/client";
import type { Resource } from "@/types";

function CreateResourceDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { push } = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = React.useState("");
  const [type, setType] = React.useState("Meeting room");
  const [location, setLocation] = React.useState("");

  const create = useMutation({
    mutationFn: () => resourcesApi.create({ name, resource_type: type, location: location || undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resources"] });
      push("success", "Resource added");
      setName("");
      setLocation("");
      onClose();
    },
    onError: (err) => push("error", "Couldn't add resource", getApiErrorMessage(err)),
  });

  return (
    <Dialog open={open} onClose={onClose} title="Register new resource" description="Rooms and equipment your team can book.">
      <div className="space-y-3">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Name</label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Room 2B" />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Type</label>
          <Input value={type} onChange={(e) => setType(e.target.value)} placeholder="Meeting room" />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Location</label>
          <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Floor 2, East wing" />
        </div>
        <Button
          className="w-full"
          disabled={!name.trim() || !type.trim()}
          loading={create.isPending}
          onClick={() => create.mutate()}
        >
          Add resource
        </Button>
      </div>
    </Dialog>
  );
}

export default function Resources() {
  const { push } = useToast();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = React.useState(false);

  const { data: resources, isLoading } = useQuery({
    queryKey: ["resources"],
    queryFn: () => resourcesApi.list(),
  });

  const toggleActive = useMutation({
    mutationFn: (r: Resource) => resourcesApi.update(r.id, { is_active: !r.is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resources"] });
      push("success", "Resource updated");
    },
    onError: (err) => push("error", "Couldn't update resource", getApiErrorMessage(err)),
  });

  const total = resources?.length ?? 0;
  const activeCount = (resources ?? []).filter((r) => r.is_active).length;
  const inactiveCount = total - activeCount;
  const availabilityPct = total > 0 ? Math.round((activeCount / total) * 100) : 0;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[28px] font-bold text-ink-700">Resources Command Center</h1>
          <p className="mt-1 max-w-xl text-sm text-ink-700/60">
            Manage physical assets, meeting rooms, and specialized equipment across your scheduling ecosystem.
          </p>
        </div>
        <Button variant="dark" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" /> Add resource
        </Button>
      </div>

      {!isLoading && total > 0 && (
        <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-4">
          <div className="rounded-2xl bg-white p-5 shadow-card">
            <div className="flex items-center justify-between">
              <p className="text-sm text-ink-700/60">Total Assets</p>
              <Archive className="h-4 w-4 text-brand-600" />
            </div>
            <p className="mt-2 text-3xl font-bold text-ink-700">{total}</p>
          </div>
          <div className="rounded-2xl bg-white p-5 shadow-card">
            <div className="flex items-center justify-between">
              <p className="text-sm text-ink-700/60">Active</p>
              <RefreshCcw className="h-4 w-4 text-brand-600" />
            </div>
            <p className="mt-2 text-3xl font-bold text-ink-700">{availabilityPct}%</p>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-cream-200">
              <div className="h-full rounded-full bg-brand-500" style={{ width: `${availabilityPct}%` }} />
            </div>
          </div>
          <div className="rounded-2xl bg-white p-5 shadow-card">
            <div className="flex items-center justify-between">
              <p className="text-sm text-ink-700/60">Inactive</p>
              <TriangleAlert className="h-4 w-4 text-red-500" />
            </div>
            <p className="mt-2 text-3xl font-bold text-red-600">{inactiveCount}</p>
          </div>
          <div className="flex flex-col items-center justify-center rounded-2xl bg-white p-5 shadow-card">
            <p className="mb-2 text-sm font-semibold text-ink-700">Resource Health</p>
            <div
              className="relative flex h-20 w-20 items-center justify-center rounded-full"
              style={{ background: `conic-gradient(#FFB800 ${availabilityPct * 3.6}deg, #F0EADC 0deg)` }}
            >
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white text-sm font-bold text-ink-700">
                {availabilityPct}%
              </div>
            </div>
          </div>
        </div>
      )}

      <p className="mb-1 text-lg font-semibold text-ink-700">Registered Resources</p>
      <p className="mb-4 text-sm text-ink-700/60">Rooms, equipment, and other bookable assets.</p>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-2xl bg-white/60" />
          ))}
        </div>
      ) : !resources || resources.length === 0 ? (
        <EmptyState
          icon={<DoorOpen className="h-5 w-5" />}
          title="No resources yet"
          body="Add rooms or equipment so people can book them when scheduling meetings."
          actionLabel="Add resource"
          onAction={() => setCreateOpen(true)}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {resources.map((r) => (
            <div key={r.id} className="overflow-hidden rounded-2xl bg-white shadow-card">
              <div className="p-5">
                <div className="mb-3 flex items-start justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cream-100 text-brand-700">
                    <DoorOpen className="h-5 w-5" />
                  </div>
                  <ResourceStatusBadge isActive={r.is_active} />
                </div>
                <p className="font-semibold text-ink-700">{r.name}</p>
                <p className="mt-1 flex items-center gap-1 text-xs text-ink-700/50">
                  <MapPin className="h-3 w-3" /> {r.resource_type}
                  {r.location ? ` · ${r.location}` : ""}
                </p>
                <div className="mt-4 flex items-center justify-end border-t border-slate-100 pt-3">
                  <button
                    onClick={() => toggleActive.mutate(r)}
                    className="flex items-center gap-1 text-xs font-medium text-ink-700/60 hover:text-ink-700"
                  >
                    {r.is_active ? (
                      <>
                        <X className="h-3.5 w-3.5" /> Deactivate
                      </>
                    ) : (
                      "Reactivate"
                    )}
                  </button>
                </div>
              </div>
            </div>
          ))}

          <button
            onClick={() => setCreateOpen(true)}
            className="flex min-h-[176px] flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-300 bg-white/40 text-ink-700/50 hover:border-brand-400 hover:text-brand-700"
          >
            <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full border-2 border-current">
              <Plus className="h-4 w-4" />
            </div>
            <p className="text-sm font-medium">Register Resource</p>
            <p className="mt-1 max-w-[180px] text-center text-xs text-ink-700/40">
              Add new rooms, tech stacks, or equipment.
            </p>
          </button>
        </div>
      )}

      <CreateResourceDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
