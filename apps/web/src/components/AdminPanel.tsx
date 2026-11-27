"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import { ReportList } from "./ProblemReports";
import { X } from "lucide-react";
import { api, ApiError, type AccountBudget, type AdminInvite, type AdminUser } from "@/lib/api";
import { t } from "@/lib/i18n";

const usd = new Intl.NumberFormat("tr-TR", {
  style: "currency", currency: "USD", maximumFractionDigits: 6,
});

type Props = {
  ownId: string;
  onClose: () => void;
  onDemoted: () => void;
  onBudgetSaved: () => void;
};

export function AdminPanel({ ownId, onClose, onDemoted, onBudgetSaved }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    let active = true;
    api.adminUsers().then((accounts) => {
      if (active) setUsers(accounts);
    }).catch(() => {
      if (active) setError(t("adminLoadError"));
    });
    return () => {
      active = false;
      element?.close();
    };
  }, []);

  async function saveRole(account: AdminUser, isAdmin: boolean) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const role = await api.setUserRole(account.id, isAdmin);
      setUsers((list) => list?.map((item) =>
        item.id === account.id ? { ...item, ...role } : item) ?? null);
      if (account.id === ownId && !role.is_admin) onDemoted();
      else setNotice(t("adminRoleSaved", { name: account.name }));
    } catch (e) {
      setError(t(e instanceof ApiError && e.status === 409 ? "adminLastAdmin" : "adminSaveError"));
    } finally {
      setSaving(false);
    }
  }

  async function saveBudget(account: AdminUser, limits: AccountBudget) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const budget = await api.setUserBudget(account.id, limits);
      setUsers((list) => list?.map((item) =>
        item.id === account.id ? { ...item, ...budget } : item) ?? null);
      setNotice(t("adminBudgetSaved", { name: account.name }));
      if (account.id === ownId) onBudgetSaved();
    } catch {
      setError(t("adminSaveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <dialog ref={dialog} onCancel={onClose} aria-labelledby="admin-title"
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
      className="m-auto max-h-[90dvh] w-[min(94vw,60rem)] max-w-none overflow-y-auto overscroll-y-contain rounded-xl border border-rule bg-paper p-0 text-ink shadow-xl backdrop:bg-black/35">
      <section>
        <header className="top-0 z-10 md:sticky flex items-start justify-between gap-4 border-b border-rule bg-paper px-3 py-3 sm:px-6 sm:py-4">
          <div>
            <h2 id="admin-title" className="font-serif text-2xl">{t("adminPanel")}</h2>
            <p className="mt-1 text-sm text-muted">{t("adminSpendDescription")}</p>
          </div>
          <button type="button" onClick={onClose} aria-label={t("close")}
            className="rounded-md p-2 text-muted hover:bg-sheet hover:text-ink">
            <X size={20} />
          </button>
        </header>
        <div className="px-3 pb-4 pt-3 sm:px-6 sm:pb-5 sm:pt-4">
          <ReportList />
          <InviteForm />
          {error && <p role="alert" className="mb-4 text-sm text-danger">{error}</p>}
          {notice && <p role="status" className="mb-4 text-sm text-verified">{notice}</p>}
          {users === null && !error && <p role="status" className="text-sm text-muted">{t("loading")}</p>}
          {users?.length === 0 && <p className="text-sm text-muted">{t("adminNoUsers")}</p>}
          {users && users.length > 0 && (
            <>
              <p className="mb-3 text-sm text-muted">{t("adminBudgetHelp")}</p>
              <div aria-hidden="true" className="hidden grid-cols-[minmax(0,1.5fr)_minmax(4rem,0.6fr)_minmax(4rem,0.6fr)_minmax(4rem,0.6fr)_minmax(10rem,1fr)] gap-4 border-b border-rule px-3 pb-2 text-sm text-muted md:grid">
                <span>{t("adminAccount")}</span>
                <span>{t("adminToday")}</span>
                <span>{t("adminMonth")}</span>
                <span>{t("adminTotal")}</span>
                <span>{t("adminRole")}</span>
              </div>
              <ul className="divide-y divide-rule">
                {users.map((account) => (
                  <li key={account.id}
                    className="grid grid-cols-3 items-center gap-3 py-3 md:grid-cols-[minmax(0,1.5fr)_minmax(4rem,0.6fr)_minmax(4rem,0.6fr)_minmax(4rem,0.6fr)_minmax(10rem,1fr)] md:gap-4 md:px-3">
                    <div className="col-span-3 min-w-0 md:col-span-1">
                      <p className="break-words text-sm font-medium">{account.name}</p>
                      <p className="break-all text-sm text-muted">{account.email}</p>
                    </div>
                    <div className="text-sm tabular-nums" aria-label={t("adminToday")}>
                      <p className="text-muted md:sr-only">{t("adminToday")}</p>
                      <p>{usd.format(account.today_cost_usd)}</p>
                    </div>
                    <div className="text-sm tabular-nums" aria-label={t("adminMonth")}>
                      <p className="text-muted md:sr-only">{t("adminMonth")}</p>
                      <p>{usd.format(account.monthly_cost_usd)}</p>
                    </div>
                    <div className="text-sm tabular-nums" aria-label={t("adminTotal")}>
                      <p className="text-muted md:sr-only">{t("adminTotal")}</p>
                      <p>{usd.format(account.total_cost_usd)}</p>
                    </div>
                    <RoleForm key={String(account.is_admin)} account={account} saving={saving} onSave={saveRole} />
                    <BudgetForm account={account} saving={saving} onSave={saveBudget} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </section>
    </dialog>
  );
}

function InviteForm() {
  const [invites, setInvites] = useState<AdminInvite[] | null>(null);
  const revision = useRef(0);
  const [loadFailed, setLoadFailed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    let active = true;

    async function refresh() {
      const request = ++revision.current;
      try {
        const next = await api.adminInvites();
        if (active && request === revision.current) {
          setInvites(next);
          setLoadFailed(false);
        }
      } catch {
        if (active && request === revision.current) setLoadFailed(true);
      }
    }

    void refresh();
    const timer = window.setInterval(refresh, 15_000);
    window.addEventListener("focus", refresh);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const email = String(new FormData(form).get("email"));
    setCreating(true);
    setFeedback("");
    setError("");
    try {
      const invite = await api.createInvite(email);
      revision.current++;
      setInvites((list) => [invite, ...(list ?? []).filter((item) => item.id !== invite.id)]);
      form.reset();
    } catch (e) {
      const key = e instanceof ApiError && e.status === 409 ? "adminInviteRegistered" : "adminInviteError";
      setError(t(key));
    } finally {
      setCreating(false);
    }
  }

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      setFeedback(t("adminInviteCopied"));
    } catch {
      setFeedback(t("adminInviteCopyError"));
    }
  }

  return (
    <section className="mb-5 border-b border-rule pb-5" aria-labelledby="admin-invite-title">
      <h3 id="admin-invite-title" className="text-base font-medium">{t("adminInviteTitle")}</h3>
      <p className="mt-1 text-sm text-muted">{t("adminInviteDescription")}</p>
      <form onSubmit={create} className="mt-3 flex flex-wrap items-end gap-2">
        <label className="min-w-0 basis-full text-sm sm:min-w-40 sm:flex-1">
          {t("email")}
          <input name="email" required type="email" autoComplete="off" disabled={creating}
            className="mt-1 block w-full rounded-md border border-rule bg-sheet px-3 py-2" />
        </label>
        <button type="submit" disabled={creating}
          className="rounded-md border border-rule bg-sheet px-3 py-2 text-sm hover:bg-paper disabled:opacity-40">
          {t(creating ? "loading" : "adminInviteCreate")}
        </button>
      </form>
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      {loadFailed && <p role="alert" className="mt-2 text-sm text-danger">{t("adminInviteLoadError")}</p>}
      {invites === null && !loadFailed && <p className="mt-2 text-sm text-muted">{t("loading")}</p>}
      {invites && invites.length > 0 && (
        <ul className="mt-3 max-h-72 divide-y divide-rule overflow-y-auto rounded-md border border-rule bg-sheet">
          {invites.map((invite) => {
            const state = invite.status === "used" ? "adminInviteUsed"
              : invite.status === "expired" ? "adminInviteExpired" : "adminInviteActive";
            const date = invite.used_at ?? invite.expires_at;
            return (
              <li key={invite.id} className="p-3">
                <div className="flex flex-wrap justify-between gap-x-3 gap-y-1 text-sm">
                  <label className="break-all" htmlFor={invite.code ? `invite-${invite.id}` : undefined}>
                    {invite.email}
                  </label>
                  <p className={invite.status === "used" ? "text-verified" : "text-muted"}>
                    {t(state)}{date && ` · ${new Date(date).toLocaleString("tr-TR")}`}
                  </p>
                </div>
                {invite.code && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    <input id={`invite-${invite.id}`} readOnly value={invite.code}
                      onFocus={(event) => event.currentTarget.select()}
                      className="min-w-0 flex-1 basis-40 rounded-md border border-rule bg-paper px-2 py-2 font-mono text-sm" />
                    {invite.status === "active" && (
                      <button type="button" onClick={() => { if (invite.code) void copy(invite.code); }}
                        className="rounded-md border border-rule px-3 py-2 text-sm hover:bg-paper">
                        {t("adminInviteCopy")}
                      </button>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {feedback && <p role="status" className="mt-2 text-sm text-muted">{feedback}</p>}
    </section>
  );
}

function RoleForm({ account, saving, onSave }: {
  account: AdminUser;
  saving: boolean;
  onSave: (account: AdminUser, isAdmin: boolean) => Promise<void>;
}) {
  const [isAdmin, setIsAdmin] = useState(account.is_admin);
  return (
    <form className="col-span-3 flex items-center gap-2 md:col-span-1"
      onSubmit={(event) => { event.preventDefault(); void onSave(account, isAdmin); }}>
      <select aria-label={t("adminRoleFor", { name: account.name })} value={String(isAdmin)}
        onChange={(event) => setIsAdmin(event.target.value === "true")} disabled={saving}
        className="min-w-0 flex-1 rounded-md border border-rule bg-sheet px-2 py-2 text-sm">
        <option value="false">{t("adminRoleMember")}</option>
        <option value="true">{t("adminRoleAdmin")}</option>
      </select>
      <button type="submit" disabled={saving || isAdmin === account.is_admin}
        className="rounded-md border border-rule px-2 py-2 text-sm hover:bg-sheet disabled:opacity-40">
        {t("save")}
      </button>
    </form>
  );
}


function BudgetForm({ account, saving, onSave }: {
  account: AdminUser;
  saving: boolean;
  onSave: (account: AdminUser, limits: AccountBudget) => Promise<void>;
}) {
  const [daily, setDaily] = useState(account.daily_budget_usd?.toString() ?? "");
  const [monthly, setMonthly] = useState(account.monthly_budget_usd?.toString() ?? "");
  const limits = {
    daily_budget_usd: daily === "" ? null : Number(daily),
    monthly_budget_usd: monthly === "" ? null : Number(monthly),
  };
  const changed = limits.daily_budget_usd !== account.daily_budget_usd ||
    limits.monthly_budget_usd !== account.monthly_budget_usd;
  const field = "mt-1 w-full rounded-md border border-rule bg-sheet px-2 py-2 text-sm text-ink";

  return (
    <form aria-label={t("adminBudgetFor", { name: account.name })}
      className="col-span-full grid grid-cols-2 items-end gap-2 sm:flex sm:gap-3"
      onSubmit={(event) => { event.preventDefault(); void onSave(account, limits); }}>
      <label className="text-xs text-muted">
        {t("adminDailyLimit")}
        <input type="number" min="0" step="any" value={daily} disabled={saving}
          placeholder={String(account.default_daily_budget_usd)}
          onChange={(event) => setDaily(event.target.value)} className={field} />
      </label>
      <label className="text-xs text-muted">
        {t("adminMonthlyLimit")}
        <input type="number" min="0" step="any" value={monthly} disabled={saving}
          placeholder={t("adminUnlimited")}
          onChange={(event) => setMonthly(event.target.value)} className={field} />
      </label>
      <button type="submit" disabled={saving || !changed}
        className="col-span-2 justify-self-start rounded-md border border-rule px-2 py-2 text-sm hover:bg-sheet disabled:opacity-40">
        {t("save")}
      </button>
    </form>
  );
}
