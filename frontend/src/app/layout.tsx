import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kevin — AI antenna engineer",
  description:
    "An agent places antennas inside a real phone: it proposes, a solver scores, it iterates.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
