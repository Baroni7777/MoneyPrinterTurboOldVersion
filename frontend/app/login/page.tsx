"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const data = new FormData(event.currentTarget);
    try { await api("/v2/auth/login", { method: "POST", body: JSON.stringify({ email: data.get("email"), password: data.get("password") }) }); router.push("/dashboard"); router.refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Falha no login"); }
  }
  return <main style={{ maxWidth: 420, paddingTop: 100 }}><div className="card"><h1>MoneyPrinterTurbo Studio</h1><p className="muted">Entre para gerenciar seus projetos.</p><form onSubmit={submit}><p><input required name="email" type="email" placeholder="E-mail" /></p><p><input required name="password" type="password" placeholder="Senha" /></p>{error && <p className="error">{error}</p>}<button>Entrar</button></form></div></main>;
}
