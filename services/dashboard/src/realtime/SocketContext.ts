import { createContext } from "react";
import type { Socket } from "socket.io-client";

export type SocketConnectionState =
  | "disconnected"
  | "connecting"
  | "connected"
  | "error";

export interface SocketContextValue {
  socket: Socket | null;
  connectionState: SocketConnectionState;
  connectionError: string | null;
}

export const SocketContext =
  createContext<SocketContextValue | null>(null);