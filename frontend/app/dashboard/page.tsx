"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "../../lib/api";

type User = { display_name: string; system_role: string };
type Project = { id: string; name: string; niche: string; status: string };

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User>();
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    Promise.all([api<User>("/v2/auth/me"), api<Project[]>("/v2/projects")])
      .then(([me, list]) => { setUser(me); setProjects(list); })
      .catch(() => router.replace("/login"));
  }, [router]);

  return <main>
    <div className="row">
      <div><h1>Olá, {user?.display_name || ""}</h1><p className="muted">Projetos editoriais e gerações em um só lugar.</p></div>
      <div className="row"><Link className="button secondary" href="/admin">Administração</Link><Link className="button" href="/projects/new">Novo projeto</Link></div>
    </div>
    <section className="grid">{projects.map((project) => <Link className="card" key={project.id} href={`/projects/${project.id}`}><h2>{project.name}</h2><p className="muted">{project.niche || "Sem nicho definido"}</p><small>{project.status}</small></Link>)}</section>
  </main>;
}
