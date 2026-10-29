"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, type LLMModel, type LLMSettings } from "@/lib/api";
import { t } from "@/lib/i18n";

type Props = { onClose: () => void };

export function SettingsPanel({ onClose }: Props) {
  const [settings, setSettings] = useState<LLMSettings | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [persisted, setPersisted] = useState(false);
  const [models, setModels] = useState<LLMModel[]>([]);
  const [modelSearch, setModelSearch] = useState("");
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelError, setModelError] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState("");

  useEffect(() => {
    api.llmSettings()
      .then((value) => {
        setSettings(value);
        setPersisted(value.is_saved);
      })
      .catch(() => setError(t("settingsLoadFailed")))
      .finally(() => setLoading(false));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!settings) return;
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const updated = await api.saveLLMSettings({
        base_url: settings.base_url,
        model_main: settings.model_main,
        model_draft: settings.model_draft,
        model_cheap: settings.model_cheap,
        model_judge: settings.model_judge,
        api_key: apiKey.trim() || undefined,
        clear_api_key: clearKey,
      });
      setSettings(updated);
      setPersisted(true);
      setApiKey("");
      setClearKey(false);
      setSaved(true);
      setTestResult("");
    } catch {
      setError(t("settingsSaveFailed"));
    } finally {
      setSaving(false);
    }
  }

  async function refreshModels() {
    setLoadingModels(true);
    setModelError("");
    try {
      setModels(await api.llmModels());
    } catch {
      setModels([]);
      setModelError(t("modelsLoadFailed"));
    } finally {
      setLoadingModels(false);
    }
  }

  async function testConnection() {
    setTesting(true);
    setTestResult("");
    setError("");
    try {
      const result = await api.testLLM();
      setTestResult(t("connectionWorks", { model: result.model }));
    } catch {
      setError(t("connectionFailed"));
    } finally {
      setTesting(false);
    }
  }

  const field =
    "mt-1 w-full rounded-md border border-rule bg-sheet px-3 py-2.5 text-sm text-ink outline-none focus:border-cite";
  const visibleModels = models.filter((model) =>
    `${model.name} ${model.id}`.toLocaleLowerCase().includes(modelSearch.trim().toLocaleLowerCase()),
  );

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/25"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        className="flex h-full w-full max-w-xl flex-col overflow-y-auto border-l border-rule bg-paper shadow-xl"
      >
        <header className="sticky top-0 flex items-start justify-between border-b border-rule bg-paper px-6 py-5">
          <div>
            <h2 id="settings-title" className="font-serif text-2xl text-ink">
              {t("settings")}
            </h2>
            <p className="mt-1 text-sm text-muted">{t("settingsSharedNotice")}</p>
          </div>
          <button onClick={onClose} aria-label={t("close")} className="rounded px-2 text-xl text-faint hover:text-ink">
            ×
          </button>
        </header>

        {loading ? (
          <p className="p-6 text-sm text-muted">{t("settingsLoading")}</p>
        ) : settings ? (
          <form onSubmit={submit} className="space-y-5 p-6">
            <label className="block text-sm text-muted">
              {t("openaiBaseUrl")}
              <input
                required
                type="url"
                value={settings.base_url}
                onChange={(event) => {
                  setSettings({ ...settings, base_url: event.target.value });
                  setPersisted(false);
                  setSaved(false);
                }}
                placeholder="http://localhost:8080/api"
                className={field}
              />
              <span className="mt-1 block text-xs text-faint">{t("openaiBaseUrlHelp")}</span>
            </label>

            <label className="block text-sm text-muted">
              {t("openaiApiKey")}
              <input
                type="password"
                autoComplete="new-password"
                value={apiKey}
                onChange={(event) => {
                  setApiKey(event.target.value);
                  setPersisted(false);
                  setSaved(false);
                  if (event.target.value) setClearKey(false);
                }}
                placeholder={settings.api_key_configured ? t("apiKeySaved") : t("apiKeyMissing")}
                className={field}
              />
              <span className="mt-1 block text-xs text-faint">{t("apiKeyEncryptedNotice")}</span>
            </label>

            {settings.api_key_configured && (
              <label className="flex items-center gap-2 text-sm text-muted">
                <input
                  type="checkbox"
                  checked={clearKey}
                  onChange={(event) => {
                    setClearKey(event.target.checked);
                    setPersisted(false);
                    setSaved(false);
                    if (event.target.checked) setApiKey("");
                  }}
                />
                {t("clearApiKey")}
              </label>
            )}

            <div className="border-t border-rule pt-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-ink">{t("modelIds")}</h3>
                  <p className="mt-1 text-xs text-faint">{t("modelsHelp")}</p>
                </div>
                <button
                  type="button"
                  onClick={refreshModels}
                  disabled={loadingModels}
                  className="shrink-0 rounded-md border border-rule px-3 py-2 text-xs text-muted hover:bg-sheet disabled:opacity-60"
                >
                  {loadingModels ? t("modelsLoading") : t("loadModels")}
                </button>
              </div>
              {modelError && <p role="alert" className="mt-3 text-xs text-danger">{modelError}</p>}
              {models.length > 0 && (
                <p className="mt-2 text-xs text-verified">{t("modelsLoaded", { count: models.length })}</p>
              )}
              {models.length > 0 && (
                <input
                  type="search"
                  value={modelSearch}
                  onChange={(event) => setModelSearch(event.target.value)}
                  placeholder={t("searchModels")}
                  aria-label={t("searchModels")}
                  className={`${field} mt-3`}
                />
              )}
              <div className="mt-3 grid gap-4 sm:grid-cols-2">
                {([
                  ["model_main", t("mainModel")],
                  ["model_draft", t("draftModel")],
                  ["model_cheap", t("cheapModel")],
                  ["model_judge", t("judgeModel")],
                ] as const).map(([key, label]) => (
                  <label key={key} className="block text-sm text-muted">
                    {label}
                    {models.length ? (
                      <select
                        required
                        value={settings[key]}
                        onChange={(event) => {
                          setSettings({ ...settings, [key]: event.target.value });
                          setPersisted(false);
                          setSaved(false);
                        }}
                        className={field}
                      >
                        {!visibleModels.some((model) => model.id === settings[key]) && (
                          <option value={settings[key]}>{t("modelNotInList", { model: settings[key] })}</option>
                        )}
                        {visibleModels.map((model) => (
                          <option key={model.id} value={model.id}>{model.name} · {model.id}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        required
                        value={settings[key]}
                        onChange={(event) => {
                          setSettings({ ...settings, [key]: event.target.value });
                          setPersisted(false);
                          setSaved(false);
                        }}
                        className={field}
                      />
                    )}
                  </label>
                ))}
              </div>
            </div>

            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
            {saved && <p role="status" className="text-sm text-verified">{t("settingsSaved")}</p>}
            {testResult && <p role="status" className="text-sm text-verified">{testResult}</p>}
            <div className="flex justify-end gap-3 border-t border-rule pt-4">
              <button type="button" onClick={onClose} className="rounded-md px-4 py-2 text-sm text-muted hover:bg-sheet">
                {t("close")}
              </button>
              <button
                type="button"
                onClick={testConnection}
                disabled={testing || !persisted}
                title={!persisted ? t("saveBeforeTest") : undefined}
                className="rounded-md border border-rule px-4 py-2 text-sm text-ink hover:bg-sheet disabled:opacity-50"
              >
                {testing ? t("connectionTesting") : t("testConnection")}
              </button>
              <button
                type="submit"
                disabled={saving}
                className="rounded-md bg-ink px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                {saving ? t("settingsSaving") : t("saveSettings")}
              </button>
            </div>
          </form>
        ) : (
          <p role="alert" className="p-6 text-sm text-danger">{error}</p>
        )}
      </section>
    </div>
  );
}
