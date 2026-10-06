import { ReticleDev } from './reticle-dev';
import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetBrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Kavach Console",
  description: "Autonomous AI Operations Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${inter.variable} ${jetBrainsMono.variable} antialiased min-h-screen bg-k-canvas text-k-body`}
      >{process.env.NODE_ENV === 'development' ? <ReticleDev /> : null}
        {children}
      </body>
    </html>
  );
}
