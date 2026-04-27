import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "PH ETL — config generator",
  description: "Generate a YAML adapter config from sample data and a description.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
