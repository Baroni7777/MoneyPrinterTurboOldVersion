"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "../../../lib/api";
import FormatEditor, {
  EditorialConfiguration,
  EditorialFormat,
} from "./format-editor";
import RankingGenerator from "./ranking-generator";

type Project = { id: string; name: string; niche: string };
type Profile = { id: string; name: string; version: number };
type Generation = {
  id: string;
  status: string;
  video_subject: string;
  error_message: string | null;
  created_at: string;
};
type ApiKey = {
  id: string;
  project_id: string | null;
  name: string;
  key_prefix: string;
  revoked_at: string | null;
};
type Asset = { id: string; original_filename: string; download_url: string };
type Preset = {
  id: string;
  name: string;
  is_default: boolean;
  creative_profile_id: string;
  configuration: Record<string, unknown>;
};
type Tab = "overview" | "format" | "history" | "integration";

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project>();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [generations, setGenerations] = useState<Generation[]>([]);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [formats, setFormats] = useState<EditorialFormat[]>([]);
  const [assets, setAssets] = useState<Record<string, Asset[]>>({});
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [createdKey, setCreatedKey] = useState("");
  const [presetId, setPresetId] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [savingFormat, setSavingFormat] = useState(false);
  const [presetConfiguration, setPresetConfiguration] = useState(
    '{"video_source":"pexels","video_aspect":"9:16"}',
  );

  const load = useCallback(async () => {
    const [
      currentProject,
      currentProfiles,
      currentGenerations,
      allKeys,
      currentPresets,
      currentFormats,
    ] = await Promise.all([
      api<Project>(`/v2/projects/${projectId}`),
      api<Profile[]>(`/v2/projects/${projectId}/creative-profiles`),
      api<Generation[]>(`/v2/projects/${projectId}/generations`),
      api<ApiKey[]>("/v2/api-keys"),
      api<Preset[]>(`/v2/projects/${projectId}/presets`),
      api<EditorialFormat[]>(`/v2/projects/${projectId}/editorial-formats`),
    ]);
    setProject(currentProject);
    setProfiles(currentProfiles);
    setGenerations(currentGenerations);
    setPresets(currentPresets);
    setFormats(currentFormats);
    setKeys(allKeys.filter((key) => key.project_id === projectId));
    setPresetId(
      (previous) =>
        previous ||
        currentPresets.find((preset) => preset.is_default)?.id ||
        "",
    );
    const files = await Promise.all(
      currentGenerations.map(
        async (generation) =>
          [
            generation.id,
            await api<Asset[]>(
              `/v2/projects/${projectId}/generations/${generation.id}/assets`,
            ),
          ] as const,
      ),
    );
    setAssets(Object.fromEntries(files));
  }, [projectId]);

  useEffect(() => {
    load().catch((error) => setMessage(error.message));
  }, [load]);

  useEffect(() => {
    const timer = window.setInterval(
      () => load().catch(() => undefined),
      8000,
    );
    return () => window.clearInterval(timer);
  }, [load]);

  async function generate(event: FormEvent) {
    event.preventDefault();
    try {
      const defaultFormat = formats.find((format) => format.is_default);
      const result = await api<{ id: string }>(
        `/v2/projects/${projectId}/generations`,
        {
          method: "POST",
          body: JSON.stringify({
            video_subject: subject,
            preset_id: presetId || null,
            editorial_format_id: defaultFormat?.id || null,
          }),
        },
      );
      setSubject("");
      setMessage(`Geração criada: ${result.id}`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Erro");
    }
  }

  async function savePreset() {
    const name = window.prompt("Nome do preset");
    if (!name || !profiles[0]) return;
    try {
      const configuration = JSON.parse(presetConfiguration);
      const preset = await api<Preset>(`/v2/projects/${projectId}/presets`, {
        method: "POST",
        body: JSON.stringify({
          name,
          creative_profile_id: profiles[0].id,
          is_default: true,
          configuration,
        }),
      });
      setPresetId(preset.id);
      await load();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Configuração inválida",
      );
    }
  }

  async function saveEditorialFormat(
    name: string,
    configuration: EditorialConfiguration,
  ) {
    setSavingFormat(true);
    setMessage("");
    try {
      const current = formats.find((format) => format.is_default) || formats[0];
      if (current) {
        await api(
          `/v2/projects/${projectId}/editorial-formats/${current.id}`,
          {
            method: "PATCH",
            body: JSON.stringify({
              name,
              configuration,
              is_default: true,
            }),
          },
        );
      } else {
        await api(`/v2/projects/${projectId}/editorial-formats`, {
          method: "POST",
          body: JSON.stringify({
            name,
            format_type: "ranking",
            configuration,
            is_default: true,
          }),
        });
      }
      setMessage("Formato editorial salvo como padrão deste projeto.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Erro ao salvar");
    } finally {
      setSavingFormat(false);
    }
  }

  async function createKey() {
    try {
      const key = await api<ApiKey & { key: string }>("/v2/api-keys", {
        method: "POST",
        body: JSON.stringify({
          name: "n8n",
          project_id: projectId,
          scopes: ["generations:create", "generations:read"],
        }),
      });
      setCreatedKey(key.key);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Erro ao criar chave");
    }
  }

  async function revokeKey(keyId: string) {
    await api(`/v2/api-keys/${keyId}`, { method: "DELETE" });
    await load();
  }

  const currentFormat =
    formats.find((format) => format.is_default) || formats[0];

  return (
    <main className="project-page">
      <p>
        <Link className="muted" href="/dashboard">&larr; Projetos</Link>
      </p>
      <div className="row project-header">
        <div>
          <span className="eyebrow">Canal / projeto</span>
          <h1>{project?.name}</h1>
          <p className="muted">{project?.niche}</p>
        </div>
        <Link className="button secondary" href="/dashboard">Dashboard</Link>
      </div>

      <nav className="project-tabs" aria-label="Seções do projeto">
        <button className={activeTab === "overview" ? "active" : ""} onClick={() => setActiveTab("overview")}>Visão geral</button>
        <button className={activeTab === "format" ? "active" : ""} onClick={() => setActiveTab("format")}>Formato do vídeo</button>
        <button className={activeTab === "history" ? "active" : ""} onClick={() => setActiveTab("history")}>Gerações</button>
        <button className={activeTab === "integration" ? "active" : ""} onClick={() => setActiveTab("integration")}>Integrações</button>
      </nav>

      {message && <div className="notice">{message}</div>}

      {activeTab === "overview" && (
        <>
        <div className="grid overview-grid">
          <section className="card">
            <span className="eyebrow">Identidade criativa</span>
            <h2>Perfil e preset</h2>
            {profiles.map((profile) => (
              <p key={profile.id}>{profile.name} — versão {profile.version}</p>
            ))}
            <textarea
              value={presetConfiguration}
              onChange={(event) => setPresetConfiguration(event.target.value)}
              aria-label="Configuração JSON do preset"
            />
            <p><button className="secondary" onClick={savePreset}>Salvar preset</button></p>
          </section>
          <section className="card">
            <span className="eyebrow">Nova produção</span>
            <h2>Gerar vídeo</h2>
            <form onSubmit={generate}>
              <p>
                <select
                  value={presetId}
                  onChange={(event) => {
                    const selected = event.target.value;
                    setPresetId(selected);
                    const preset = presets.find((item) => item.id === selected);
                    if (preset) {
                      setPresetConfiguration(
                        JSON.stringify(preset.configuration, null, 2),
                      );
                    }
                  }}
                >
                  <option value="">Configuração padrão</option>
                  {presets.map((preset) => (
                    <option key={preset.id} value={preset.id}>
                      {preset.name}{preset.is_default ? " (padrão)" : ""}
                    </option>
                  ))}
                </select>
              </p>
              <p>
                <textarea
                  required
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                  placeholder="Tema do vídeo"
                />
              </p>
              <button>Gerar vídeo</button>
            </form>
            {currentFormat && (
              <p className="format-badge">
                Formato aplicado: <strong>{currentFormat.name}</strong>
              </p>
            )}
          </section>
        </div>
        {currentFormat && (
          <RankingGenerator
            projectId={projectId}
            format={currentFormat}
            onCreated={async (resultMessage) => {
              setMessage(resultMessage);
              await load();
              setActiveTab("history");
            }}
          />
        )}
        </>
      )}

      {activeTab === "format" && (
        <FormatEditor
          format={currentFormat}
          saving={savingFormat}
          onSave={saveEditorialFormat}
        />
      )}

      {activeTab === "integration" && (
        <section className="card integration-card">
          <span className="eyebrow">Automação</span>
          <h2>Integração com n8n</h2>
          <p className="muted">Crie uma chave limitada a este projeto.</p>
          <button onClick={createKey}>Nova chave</button>
          {createdKey && (
            <p className="secret">Copie agora: <code>{createdKey}</code></p>
          )}
          {keys.map((key) => (
            <p key={key.id}>
              <code>{key.key_prefix}...</code> {key.name}
              {!key.revoked_at && (
                <button className="link-button" onClick={() => revokeKey(key.id)}>
                  revogar
                </button>
              )}
            </p>
          ))}
        </section>
      )}

      {activeTab === "history" && (
        <GenerationHistory generations={generations} assets={assets} />
      )}
    </main>
  );
}

function GenerationHistory({
  generations,
  assets,
}: {
  generations: Generation[];
  assets: Record<string, Asset[]>;
}) {
  return (
    <section className="card history">
      <h2>Histórico de gerações</h2>
      {generations.length === 0 ? (
        <p className="muted">Nenhuma geração ainda.</p>
      ) : generations.map((generation) => (
        <article className="generation" key={generation.id}>
          <div>
            <strong>{generation.video_subject}</strong>
            <p className="muted">
              {new Date(generation.created_at).toLocaleString("pt-BR")}
            </p>
            {assets[generation.id]?.map((asset) => (
              <div key={asset.id}>
                <video controls src={`/api${asset.download_url}`} />
                <p>
                  <a className="muted" href={`/api${asset.download_url}`}>
                    Baixar {asset.original_filename}
                  </a>
                </p>
              </div>
            ))}
          </div>
          <div>
            <span className={`status ${generation.status}`}>
              {generation.status}
            </span>
            {generation.error_message && (
              <p className="error">{generation.error_message}</p>
            )}
          </div>
        </article>
      ))}
    </section>
  );
}
