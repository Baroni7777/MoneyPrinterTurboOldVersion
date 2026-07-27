import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "MoneyPrinterTurbo Studio",
  description: "Gerencie projetos e gere vídeos.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt-BR"><body>{children}</body></html>;
}
