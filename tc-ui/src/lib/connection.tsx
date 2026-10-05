"use client";

import * as React from "react";
import { useHealth, type ConnectionState } from "@/lib/hooks/use-api";

const ConnectionContext = React.createContext<ConnectionState>("connecting");

export function ConnectionProvider({ children }: { children: React.ReactNode }) {
  const { state } = useHealth();
  return <ConnectionContext.Provider value={state}>{children}</ConnectionContext.Provider>;
}

export function useConnection(): ConnectionState {
  return React.useContext(ConnectionContext);
}
