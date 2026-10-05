import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { SessionProvider } from "@/lib/session";
import { ConnectionProvider } from "@/lib/connection";
import { ThemeProvider } from "@/lib/theme";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Engineering TC",
  description: "Engineering TC — Personal Engineering AI / Engineering Command Center",
  manifest: "/manifest.webmanifest",
  applicationName: "Engineering TC",
  appleWebApp: {
    capable: true,
    title: "Engineering TC",
    statusBarStyle: "default",
  },
  icons: {
    icon: [{ url: "/icons/icon-192.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icons/icon-192.svg" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#35E58C",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable}`}>
      <body className="bg-bg text-text antialiased">
        <ThemeProvider>
          <SessionProvider>
            <ConnectionProvider>{children}</ConnectionProvider>
          </SessionProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
