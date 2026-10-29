"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n";

export default function LoginPage() {
  const router = useRouter();
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(form: FormData) {
    setBusy(true);
    setError(null);
    const email = String(form.get("email"));
    const password = String(form.get("password"));
    try {
      if (registering)
        await api.register(String(form.get("name")), email, password, String(form.get("invite")));
      else await api.login(email, password);
      router.replace("/");
    } catch {
      setError(registering ? t("registerFailed") : t("loginFailed"));
      setBusy(false);
    }
  }

  const field =
    "mt-1 w-full rounded-md border border-rule bg-sheet px-3 py-2.5 text-[15px] outline-none focus:border-cite";

  return (
    <main className="flex min-h-full items-center justify-center px-4 py-16">
      <div className="w-full max-w-sm">
        <p className="font-serif text-2xl leading-snug text-ink">{t("appTagline")}</p>
        <form action={submit} className="mt-10 space-y-4">
          <h1 className="text-sm font-semibold text-ink">
            {registering ? t("registerTitle") : t("loginTitle")}
          </h1>
          {registering && (
            <label className="block text-sm text-muted">
              {t("inviteCode")}
              <input name="invite" required autoComplete="off" className={field} />
            </label>
          )}
          {registering && (
            <label className="block text-sm text-muted">
              {t("name")}
              <input name="name" required autoComplete="name" className={field} />
            </label>
          )}
          <label className="block text-sm text-muted">
            {t("email")}
            <input name="email" type="email" required autoComplete="email" className={field} />
          </label>
          <label className="block text-sm text-muted">
            {t("password")}
            <input
              name="password"
              type="password"
              required
              minLength={8}
              autoComplete={registering ? "new-password" : "current-password"}
              className={field}
            />
          </label>
          {error && <p className="text-sm text-danger">{error}</p>}
          <button
            disabled={busy}
            className="w-full rounded-md bg-ink py-2.5 text-[15px] font-medium text-white disabled:opacity-60"
          >
            {registering ? t("registerAction") : t("loginAction")}
          </button>
        </form>
        <button
          type="button"
          onClick={() => {
            setRegistering(!registering);
            setError(null);
          }}
          className="mt-6 text-sm text-cite hover:underline"
        >
          {registering ? t("toLogin") : t("toRegister")}
        </button>
      </div>
    </main>
  );
}
