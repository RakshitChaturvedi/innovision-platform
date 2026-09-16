import { io, type Socket } from "socket.io-client";

const SOCKET_URL =
  import.meta.env.VITE_SOCKET_URL ?? "http://localhost:8000";

export function createSocket(token: string): Socket {
  return io(`${SOCKET_URL}/alerts`, {
    autoConnect: false,

    auth: {
      token,
    },

    transports: ["websocket"],
  });
}