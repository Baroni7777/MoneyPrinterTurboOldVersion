"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "../../../lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const project = await api<{ id: string }>("/v2/projects", { method: "POST", body: JSON.stringify({ name: form.get("name"), niche: form.get("niche"), target_audience: form.get("audience") }) });
      router.push(`/projects/${project.id}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Erro"); }
  }
  return <main><p><Link className="muted" href="/dashboard">← Painel</Link></p><div className="card"><h1>Novo projeto</h1><form onSubmit={submit}><p><input name="name" required placeholder="Nome do canal ou projeto" /></p><p><input name="niche" placeholder="Nicho" /></p><p><textarea name="audience" placeholder="Público-alvo" /></p>{error && <p className="error">{error}</p>}<button>Criar projeto</button></form></div></main>;
}
