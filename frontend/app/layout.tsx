import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Engineering TC",
  description: "Engineering TC frontend — Step 1 scaffold",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
