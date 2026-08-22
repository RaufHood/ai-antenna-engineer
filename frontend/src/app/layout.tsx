import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Antenna Placement Studio",
  description:
    "Agent-driven antenna placement and EM study for handset 3D models",
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
