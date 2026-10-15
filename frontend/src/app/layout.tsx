import type { Metadata, Viewport } from "next";
import { Caveat, Geist } from "next/font/google";
import "./globals.css";
import { messages } from "@/i18n";

const geist = Geist({ variable: "--font-geist-sans", subsets: ["latin", "latin-ext"] });
const caveat = Caveat({ variable: "--font-caveat", subsets: ["latin", "latin-ext"] });

const t = messages();

export const metadata: Metadata = {
  title: t.app.name,
  description: t.app.tagline,
};

export const viewport: Viewport = {
  themeColor: "#07061a",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="tr" className={`${geist.variable} ${caveat.variable} h-full`}>
      <body className="min-h-full">
        <div className="phone">{children}</div>
      </body>
    </html>
  );
}
