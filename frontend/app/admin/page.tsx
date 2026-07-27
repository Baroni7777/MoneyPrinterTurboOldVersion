"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "../../lib/api";

type User = { id: string; email: string; display_name: string; system_role: string; status: string };
type Overview = { users: number; active_projects: number; queued_generations: number; processing_generations: number; failed_generations: number; completed_generations: number };

export default function AdminPage() {
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [overview, setOverview] = useState<Overview>();
  const [error, setError] = useState("");
  const load = () => Promise.all([api<User[]>("/v2/admin/users"), api<Overview>("/v2/admin/overview")]).then(([list, stats]) => { setUsers(list); setOverview(stats); }).catch((reason) => { setError(reason.message); router.replace("/dashboard"); });
  useEffect(() => { load(); }, []);
  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const form = new FormData(event.currentTarget);
    try {
      await api("/v2/admin/users", { method: "POST", body: JSON.stringify({ email: form.get("email"), display_name: form.get("display_name"), password: form.get("password"), system_role: form.get("system_role") }) });
      event.currentTarget.reset(); load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Erro"); }
  }
  return <main>
    <p><Link className="muted" href="/dashboard">&larr; Painel</Link></p><h1>Administracao</h1>
    {overview && <section className="grid"><article className="card"><small>Usuarios</small><h2>{overview.users}</h2></article><article className="card"><small>Projetos ativos</small><h2>{overview.active_projects}</h2></article><article className="card"><small>Fila / processando</small><h2>{overview.queued_generations} / {overview.processing_generations}</h2></article><article className="card"><small>Concluidas / falhas</small><h2>{overview.completed_generations} / {overview.failed_generations}</h2></article></section>}
    <div className="grid"><section className="card"><h2>Novo usuario</h2><form onSubmit={createUser}><p><input required name="display_name" placeholder="Nome" /></p><p><input required name="email" type="email" placeholder="E-mail" /></p><p><input required name="password" type="password" minLength={12} placeholder="Senha inicial" /></p><p><select name="system_role"><option value="user">Usuario</option><option value="admin">Administrador</option></select></p>{error && <p className="error">{error}</p>}<button>Criar usuario</button></form></section><section className="card"><h2>Usuarios</h2>{users.map((user) => <p key={user.id}><strong>{user.display_name}</strong><br /><span className="muted">{user.email} - {user.system_role} - {user.status}</span></p>)}</section></div>
  </main>;
}
