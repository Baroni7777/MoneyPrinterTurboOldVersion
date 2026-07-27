"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { api } from "../../../lib/api";
import { EditorialFormat } from "./format-editor";

type ProjectAsset = {
  id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  download_url: string;
};
type RankingItem = { position: number; title: string; asset_id: string };

export default function RankingGenerator({
  projectId,
  format,
  onCreated,
}: {
  projectId: string;
  format: EditorialFormat;
  onCreated: (message: string) => Promise<void>;
}) {
  const [mode, setMode] = useState<"auto" | "manual">("auto");
  const [source, setSource] = useState("pexels");
  const [topic, setTopic] = useState("");
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [items, setItems] = useState<RankingItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const size = format.configuration.ranking_size;

  useEffect(() => {
    setItems((current) =>
      Array.from({ length: size }, (_, index) => {
        const position = size - index;
        return (
          current.find((item) => item.position === position) || {
            position,
            title: "",
            asset_id: "",
          }
        );
      }),
    );
  }, [size]);

  async function loadAssets() {
    setAssets(await api<ProjectAsset[]>(`/v2/projects/${projectId}/assets`));
  }

  useEffect(() => {
    loadAssets().catch((caught) =>
      setError(caught instanceof Error ? caught.message : "Erro ao carregar vídeos"),
    );
  }, [projectId]);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const data = new FormData();
      data.append("file", file);
      await api(`/v2/projects/${projectId}/assets`, {
        method: "POST",
        body: data,
      });
      await loadAssets();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Falha no upload");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  function changeItem(
    position: number,
    field: "title" | "asset_id",
    value: string,
  ) {
    setItems((current) =>
      current.map((item) =>
        item.position === position ? { ...item, [field]: value } : item,
      ),
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const auto = mode === "auto";
    if (!auto && items.some((item) => !item.title.trim() || !item.asset_id)) {
      setError("Preencha o texto e selecione um vídeo em todas as posições.");
      return;
    }
    setSubmitting(true);
    try {
      const generation = await api<{ id: string }>(
        `/v2/projects/${projectId}/generations`,
        {
          method: "POST",
          body: JSON.stringify(
            auto
              ? {
                  video_subject: topic,
                  editorial_format_id: format.id,
                  auto_ranking: true,
                  ranking_size: size,
                  overrides: { video_source: source },
                }
              : {
                  video_subject: topic,
                  editorial_format_id: format.id,
                  ranking_items: items,
                },
          ),
        },
      );
      setTopic("");
      await onCreated(`Ranking enviado para renderização: ${generation.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Falha ao gerar ranking");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="card ranking-generator">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Produção por clipes</span>
          <h2>Novo {format.name}</h2>
        </div>
        {mode === "manual" && (
          <label className="upload-button">
            {uploading ? "Enviando..." : "Adicionar vídeo"}
            <input
              type="file"
              accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
              disabled={uploading}
              onChange={upload}
            />
          </label>
        )}
      </div>
      <div className="ranking-modes">
        <button
          type="button"
          className={mode === "auto" ? "active" : ""}
          onClick={() => setMode("auto")}
        >
          Automático por tema
        </button>
        <button
          type="button"
          className={mode === "manual" ? "active" : ""}
          onClick={() => setMode("manual")}
        >
          Meus vídeos
        </button>
      </div>
      <form onSubmit={submit}>
        <label>
          Tema do ranking
          <input
            required
            minLength={3}
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="Ex.: Funny cat moments"
          />
        </label>
        {mode === "auto" ? (
          <>
            <label>
              Fonte dos clipes
              <select
                value={source}
                onChange={(event) => setSource(event.target.value)}
              >
                <option value="pexels">Pexels (banco livre)</option>
                <option value="pixabay">Pixabay (banco livre)</option>
                <option value="coverr">Coverr (banco livre)</option>
                <option value="youtube">YouTube</option>
                <option value="tiktok">TikTok</option>
              </select>
            </label>
            <p className="muted ranking-auto-hint">
              A IA monta a lista do top {size}, busca os clipes na fonte
              escolhida, analisa cada candidato e baixa o que melhor representa
              cada posição. Nenhum upload é necessário.
            </p>
            {(source === "youtube" || source === "tiktok") && (
              <p className="error ranking-auto-hint">
                Baixar do YouTube e do TikTok viola os termos de uso das
                plataformas, e republicar clipes de terceiros numa compilação
                costuma ser violação de direito autoral — o risco prático é
                strike de Content ID e derrubada do canal. O YouTube ainda exige
                cookies de uma conta logada (<code>social_cookies_file</code>) para
                permitir o download.
              </p>
            )}
          </>
        ) : (
        <div className="ranking-slots">
          {items.map((item) => (
            <div className="ranking-slot" key={item.position}>
              <strong>#{item.position}</strong>
              <input
                required
                value={item.title}
                onChange={(event) =>
                  changeItem(item.position, "title", event.target.value)
                }
                placeholder="Texto desta posição"
              />
              <select
                required
                value={item.asset_id}
                onChange={(event) =>
                  changeItem(item.position, "asset_id", event.target.value)
                }
              >
                <option value="">Selecionar vídeo...</option>
                {assets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.original_filename}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
        )}
        {mode === "manual" && assets.length === 0 && (
          <p className="muted">
            Adicione seus vídeos licenciados ou próprios para preencher as posições.
          </p>
        )}
        {error && <p className="error">{error}</p>}
        <button disabled={submitting || uploading}>
          {submitting ? "Enviando..." : "Montar ranking"}
        </button>
      </form>
    </section>
  );
}
