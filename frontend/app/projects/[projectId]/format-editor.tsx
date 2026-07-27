"use client";

import { PointerEvent, useEffect, useRef, useState } from "react";

export type EditorialConfiguration = {
  ranking_size: number;
  aspect_ratio: string;
  order: string;
  title_template: string;
  font_family: string;
  title_color: string;
  accent_color: string;
  secondary_color: string;
  outline_color: string;
  title_size: number;
  item_size: number;
  outline_width: number;
  title_position: { x: number; y: number };
  ranking_position: { x: number; y: number };
  clip_duration: number;
  transition: string;
  show_full_ranking: boolean;
  show_watermark: boolean;
  watermark_text: string;
  source_audio: boolean;
};

export type EditorialFormat = {
  id: string;
  name: string;
  format_type: string;
  configuration: EditorialConfiguration;
  is_default: boolean;
};

const defaults: EditorialConfiguration = {
  ranking_size: 5,
  aspect_ratio: "9:16",
  order: "countdown",
  title_template: "RANKING BEST {{topic}}",
  font_family: "Anton",
  title_color: "#ffffff",
  accent_color: "#ff3344",
  secondary_color: "#ffd43b",
  outline_color: "#000000",
  title_size: 54,
  item_size: 42,
  outline_width: 3,
  title_position: { x: 50, y: 7 },
  ranking_position: { x: 8, y: 24 },
  clip_duration: 7,
  transition: "cut",
  show_full_ranking: true,
  show_watermark: false,
  watermark_text: "",
  source_audio: true,
};

type Props = {
  format?: EditorialFormat;
  saving: boolean;
  onSave: (name: string, configuration: EditorialConfiguration) => Promise<void>;
};

export default function FormatEditor({ format, saving, onSave }: Props) {
  const [name, setName] = useState("Ranking Top 5");
  const [config, setConfig] = useState<EditorialConfiguration>(defaults);
  const [activePosition, setActivePosition] = useState(3);
  const [dragging, setDragging] = useState<"title" | "ranking" | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!format) return;
    setName(format.name);
    setConfig({
      ...defaults,
      ...format.configuration,
      title_position: {
        ...defaults.title_position,
        ...format.configuration.title_position,
      },
      ranking_position: {
        ...defaults.ranking_position,
        ...format.configuration.ranking_position,
      },
    });
  }, [format]);

  function set<K extends keyof EditorialConfiguration>(
    key: K,
    value: EditorialConfiguration[K],
  ) {
    setConfig((current) => ({ ...current, [key]: value }));
  }

  function moveElement(event: PointerEvent<HTMLDivElement>) {
    if (!dragging || !previewRef.current) return;
    const bounds = previewRef.current.getBoundingClientRect();
    const point = {
      x: Math.max(0, Math.min(100, ((event.clientX - bounds.left) / bounds.width) * 100)),
      y: Math.max(0, Math.min(100, ((event.clientY - bounds.top) / bounds.height) * 100)),
    };
    setConfig((current) => ({
      ...current,
      [dragging === "title" ? "title_position" : "ranking_position"]: point,
    }));
  }

  function startDrag(
    event: PointerEvent<HTMLElement>,
    target: "title" | "ranking",
  ) {
    event.preventDefault();
    setDragging(target);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  const positions = Array.from(
    { length: config.ranking_size },
    (_, index) => config.order === "countdown" ? config.ranking_size - index : index + 1,
  );
  const previewTitle = config.title_template.replace("{{topic}}", "FUNNY MOMENTS");

  return (
    <div className="format-editor">
      <section className="card format-controls">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Formato editorial</span>
            <h2>Ranking vertical</h2>
          </div>
          <span className="saved-state">{format ? "Salvo no projeto" : "Novo formato"}</span>
        </div>

        <div className="control-grid">
          <label className="wide-control">
            Nome do formato
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label className="wide-control">
            Título
            <input
              value={config.title_template}
              onChange={(event) => set("title_template", event.target.value)}
            />
            <small>Use {"{{topic}}"} para inserir o tema da geração.</small>
          </label>
          <label>
            Posições
            <select
              value={config.ranking_size}
              onChange={(event) => set("ranking_size", Number(event.target.value))}
            >
              {[3, 4, 5, 6, 7, 8, 9, 10].map((size) => (
                <option key={size} value={size}>Top {size}</option>
              ))}
            </select>
          </label>
          <label>
            Ordem
            <select value={config.order} onChange={(event) => set("order", event.target.value)}>
              <option value="countdown">Contagem regressiva</option>
              <option value="ascending">Crescente</option>
            </select>
          </label>
          <label>
            Fonte
            <select
              value={config.font_family}
              onChange={(event) => set("font_family", event.target.value)}
            >
              <option value="Anton">Anton</option>
              <option value="Impact">Impact</option>
              <option value="Arial Black">Arial Black</option>
              <option value="Montserrat">Montserrat</option>
            </select>
          </label>
          <label>
            Transição
            <select
              value={config.transition}
              onChange={(event) => set("transition", event.target.value)}
            >
              <option value="cut">Corte direto</option>
              <option value="fade">Fade</option>
              <option value="zoom">Zoom</option>
            </select>
          </label>
          <label>
            Duração por clipe
            <div className="range-row">
              <input
                type="range"
                min="2"
                max="30"
                value={config.clip_duration}
                onChange={(event) => set("clip_duration", Number(event.target.value))}
              />
              <output>{config.clip_duration}s</output>
            </div>
          </label>
          <label>
            Tamanho do título
            <div className="range-row">
              <input
                type="range"
                min="20"
                max="100"
                value={config.title_size}
                onChange={(event) => set("title_size", Number(event.target.value))}
              />
              <output>{config.title_size}</output>
            </div>
          </label>
          <label>
            Tamanho dos itens
            <div className="range-row">
              <input
                type="range"
                min="16"
                max="80"
                value={config.item_size}
                onChange={(event) => set("item_size", Number(event.target.value))}
              />
              <output>{config.item_size}</output>
            </div>
          </label>
          <label>
            Contorno
            <div className="range-row">
              <input
                type="range"
                min="0"
                max="8"
                value={config.outline_width}
                onChange={(event) => set("outline_width", Number(event.target.value))}
              />
              <output>{config.outline_width}px</output>
            </div>
          </label>
        </div>

        <div className="color-controls">
          <label>Título<input type="color" value={config.title_color} onChange={(event) => set("title_color", event.target.value)} /></label>
          <label>Destaque<input type="color" value={config.accent_color} onChange={(event) => set("accent_color", event.target.value)} /></label>
          <label>Secundária<input type="color" value={config.secondary_color} onChange={(event) => set("secondary_color", event.target.value)} /></label>
          <label>Contorno<input type="color" value={config.outline_color} onChange={(event) => set("outline_color", event.target.value)} /></label>
        </div>

        <div className="toggle-list">
          <label><input type="checkbox" checked={config.show_full_ranking} onChange={(event) => set("show_full_ranking", event.target.checked)} /> Mostrar ranking completo</label>
          <label><input type="checkbox" checked={config.source_audio} onChange={(event) => set("source_audio", event.target.checked)} /> Manter áudio original dos clipes</label>
          <label><input type="checkbox" checked={config.show_watermark} onChange={(event) => set("show_watermark", event.target.checked)} /> Exibir marca d&apos;água</label>
        </div>
        {config.show_watermark && (
          <label>
            Texto da marca d&apos;água
            <input value={config.watermark_text} onChange={(event) => set("watermark_text", event.target.value)} />
          </label>
        )}
        <button disabled={saving || !name.trim()} onClick={() => onSave(name, config)}>
          {saving ? "Salvando..." : "Salvar como padrão do projeto"}
        </button>
      </section>

      <aside className="preview-panel">
        <div className="preview-toolbar">
          <div>
            <span className="eyebrow">Preview ao vivo</span>
            <strong>Arraste o título ou a lista</strong>
          </div>
          <select
            aria-label="Posição destacada"
            value={activePosition}
            onChange={(event) => setActivePosition(Number(event.target.value))}
          >
            {positions.map((position) => <option key={position} value={position}>Destacar #{position}</option>)}
          </select>
        </div>
        <div
          ref={previewRef}
          className="video-preview"
          onPointerMove={moveElement}
          onPointerUp={() => setDragging(null)}
          onPointerCancel={() => setDragging(null)}
        >
          <div className="preview-subject" />
          <div className="preview-vignette" />
          <strong
            className={`movable preview-title ${dragging === "title" ? "dragging" : ""}`}
            onPointerDown={(event) => startDrag(event, "title")}
            style={{
              left: `${config.title_position.x}%`,
              top: `${config.title_position.y}%`,
              color: config.title_color,
              fontSize: `${config.title_size / 3.2}px`,
              WebkitTextStroke: `${Math.max(1, config.outline_width / 2)}px ${config.outline_color}`,
            }}
          >
            {previewTitle}
          </strong>
          <ol
            className={`movable preview-ranking ${dragging === "ranking" ? "dragging" : ""}`}
            onPointerDown={(event) => startDrag(event, "ranking")}
            style={{
              left: `${config.ranking_position.x}%`,
              top: `${config.ranking_position.y}%`,
              fontSize: `${config.item_size / 2.7}px`,
              WebkitTextStroke: `${Math.max(1, config.outline_width / 2)}px ${config.outline_color}`,
            }}
          >
            {positions.map((position) => (
              <li
                key={position}
                style={{
                  color: position === activePosition
                    ? config.accent_color
                    : position % 2 === 0 ? config.title_color : config.secondary_color,
                }}
              >
                <b>{position}.</b>
                {position === activePosition && <span> Momento atual</span>}
              </li>
            ))}
          </ol>
          {config.show_watermark && (
            <span className="preview-watermark">{config.watermark_text || projectWatermark(name)}</span>
          )}
          <div className="safe-zone" />
        </div>
        <p className="preview-help">
          As linhas pontilhadas indicam a área segura para Shorts, Reels e TikTok.
        </p>
      </aside>
    </div>
  );
}

function projectWatermark(name: string) {
  return `@${name.toLowerCase().replace(/[^a-z0-9]+/g, "") || "canal"}`;
}
