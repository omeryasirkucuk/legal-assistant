"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { api, ApiError, type AdminUser } from "@/lib/api";
import { t } from "@/lib/i18n";

const usd = new Intl.NumberFormat("tr-TR", {
  style: "currency", currency: "USD", maximumFractionDigits: 6,
});

type Props = {
  ownId: string;
  onClose: () => void;
  onDemoted: () => void;
};

export function AdminPanel({ ownId, onClose, onDemoted }: Props) {
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

  return (
    <dialog ref={dialog} onCancel={onClose} aria-labelledby="admin-title"
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
      className="m-auto max-h-[90dvh] w-[min(94vw,60rem)] max-w-none overflow-auto rounded-xl border border-rule bg-paper p-0 text-ink shadow-xl backdrop:bg-black/35">
      <section>
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-rule bg-paper px-5 py-4 sm:px-6">
          <div>
            <h2 id="admin-title" className="font-serif text-2xl">{t("adminPanel")}</h2>
            <p className="mt-1 text-sm text-muted">{t("adminSpendDescription")}</p>
          </div>
          <button type="button" onClick={onClose} aria-label={t("close")}
            className="rounded-md p-2 text-muted hover:bg-sheet hover:text-ink">
            <X size={20} />
          </button>
        </header>
        <div className="px-5 pb-5 pt-4 sm:px-6">
          {error && <p role="alert" className="mb-4 text-sm text-danger">{error}</p>}
          {notice && <p role="status" className="mb-4 text-sm text-verified">{notice}</p>}
          {users === null && !error && <p role="status" className="text-sm text-muted">{t("loading")}</p>}
          {users?.length === 0 && <p className="text-sm text-muted">{t("adminNoUsers")}</p>}
          {users && users.length > 0 && (
            <>
              <div aria-hidden="true" className="hidden grid-cols-[minmax(0,1.5fr)_minmax(7rem,0.6fr)_minmax(7rem,0.6fr)_minmax(10rem,1fr)] gap-4 border-b border-rule px-3 pb-2 text-sm text-muted sm:grid">
                <span>{t("adminAccount")}</span>
                <span>{t("adminToday")}</span>
                <span>{t("adminTotal")}</span>
                <span>{t("adminRole")}</span>
              </div>
              <ul className="divide-y divide-rule">
                {users.map((account) => (
                  <li key={account.id}
                    className="grid grid-cols-2 items-center gap-3 py-3 sm:grid-cols-[minmax(0,1.5fr)_minmax(7rem,0.6fr)_minmax(7rem,0.6fr)_minmax(10rem,1fr)] sm:gap-4 sm:px-3">
                    <div className="col-span-2 min-w-0 sm:col-span-1">
                      <p className="break-words text-sm font-medium">{account.name}</p>
                      <p className="break-all text-sm text-muted">{account.email}</p>
                    </div>
                    <div className="text-sm tabular-nums" aria-label={t("adminToday")}>
                      <p className="text-muted sm:sr-only">{t("adminToday")}</p>
                      <p>{usd.format(account.today_cost_usd)}</p>
                    </div>
                    <div className="text-sm tabular-nums" aria-label={t("adminTotal")}>
                      <p className="text-muted sm:sr-only">{t("adminTotal")}</p>
                      <p>{usd.format(account.total_cost_usd)}</p>
                    </div>
                    <RoleForm key={String(account.is_admin)} account={account} saving={saving} onSave={saveRole} />
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

function RoleForm({ account, saving, onSave }: {
  account: AdminUser;
  saving: boolean;
  onSave: (account: AdminUser, isAdmin: boolean) => Promise<void>;
}) {
  const [isAdmin, setIsAdmin] = useState(account.is_admin);
  return (
    <form className="col-span-2 flex items-center gap-2 sm:col-span-1"
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
